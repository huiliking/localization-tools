"""
scanner_core.py
===============
Shared detection logic for l10n-llm-auditor.
Used by both auditor.py (local) and auditor_web.py (web).

Scans JS/TS and Python source files for LLM API calls
and audits them for localization (l10n) issues.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str       # CRITICAL | WARNING | INFO
    rule_id: str
    message: str
    file: str
    line: int
    snippet: str
    suggestion: str


@dataclass
class LLMCall:
    file: str
    line: int
    endpoint: str
    snippet: str
    language: str = 'unknown'           # 'js' | 'python'
    has_locale_in_prompt: bool = False
    has_locale_param: bool = False
    has_hardcoded_lang: bool = False
    locale_received_not_forwarded: bool = False


@dataclass
class AuditReport:
    scan_path: str
    timestamp: str
    files_scanned: int
    llm_calls: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    live_results: list = field(default_factory=list)   # populated by LiveTester


# ─── Detection Patterns ───────────────────────────────────────────────────────

LLM_ENDPOINTS = [
    r'api\.openai\.com',
    r'api\.anthropic\.com',
    r'[\w\-]+\.openai\.azure\.com',
    r'generativelanguage\.googleapis\.com',
    r'api\.cohere\.ai',
    r'api\.mistral\.ai',
    r'[\w\-]+\.api\.cognitive\.microsoft\.com',
]

# JS/TS patterns
# Require fetch/axios call on same line as URL — prevents flagging bare string
# comparisons like: this.baseURL !== 'https://api.openai.com/v1'
LLM_ENDPOINT_PATTERN = re.compile(
    r'(fetch|axios\.post|axios\.request|axios\.get)\s*\(\s*["\']https?://(' +
    '|'.join(LLM_ENDPOINTS) + r')',
    re.IGNORECASE
)

FETCH_BLOCK_PATTERN = LLM_ENDPOINT_PATTERN  # alias — same rule

JS_LOCALE_IN_PROMPT = re.compile(
    r'\$\{[^}]*(?:locale|lang|language)[^}]*\}|'
    r'["\'](?:locale|language|lang)["\']:\s*["\$]|'
    r'respond in (?:the language|locale)|'
    r'accept.language',
    re.IGNORECASE
)

JS_LOCALE_PARAM = re.compile(
    r'function.*\(.*(?:locale|lang|language|userLocale|targetLang).*\)|'
    r'(?:locale|lang|language)\s*[=:,\)]',
    re.IGNORECASE
)

JS_FUNCTION_START = re.compile(
    r'\bfunction\b|=>\s*\{|async\s+function',
    re.IGNORECASE
)

# Python patterns
PYTHON_HTTP_PATTERN = re.compile(
    r'(?:requests|httpx)\s*\.\s*(?:post|get|request)\s*\(\s*[f]?["\']https?://(' +
    '|'.join(LLM_ENDPOINTS) + r')',
    re.IGNORECASE
)

LOCAL_LLM_PATTERN = re.compile(
    r'(?:requests|httpx)\s*\.\s*(?:post|get)\s*\(\s*[f]?["\']'
    r'https?://(?:localhost|127\.0\.0\.1):\d+/(?:api/generate|api/chat|v1/)',
    re.IGNORECASE
)

PYTHON_REQUESTS_CALL = re.compile(
    r'(?:requests|httpx)\s*\.\s*(?:post|get)\s*\(',
    re.IGNORECASE
)

LLM_URL_IN_WINDOW = re.compile(
    r'(?:api\.openai\.com|api\.anthropic\.com|localhost:\d+|127\.0\.0\.1:\d+)'
    r'|/(?:api/generate|api/chat|v1/chat/completions|v1/messages)',
    re.IGNORECASE
)

PYTHON_FSTRING_LOCALE = re.compile(
    r'\{[^}]*(?:locale|lang|language|target_locale)[^}]*\}',
    re.IGNORECASE
)

PYTHON_LOCALE_IN_PROMPT = re.compile(
    r'["\'](?:locale|language|lang)["\']\s*:\s*|'
    r'respond in (?:the language|locale)|'
    r'Accept-Language',
    re.IGNORECASE
)

PYTHON_DEF_LOCALE = re.compile(
    r'def\s+\w+\s*\([^)]*(?:locale|lang|language|target_locale)[^)]*\)',
    re.IGNORECASE
)

PYTHON_DEF_START = re.compile(
    r'^\s*(?:async\s+)?def\s+'
)

# Shared
HARDCODED_LANG_PATTERNS = [
    r'respond\s+in\s+english',
    r'always\s+(?:respond|reply|answer)\s+in\s+english',
    r'response\s+in\s+english',
    r'en-US',
    r'language:\s*["\']en["\']',
    r'lang:\s*["\']en["\']',
]


# ─── Core Scanner ─────────────────────────────────────────────────────────────

class CoreScanner:
    """
    Language-aware scanner. Accepts either:
      - A list of (filename, content) tuples  [web mode]
      - A filesystem path                      [local mode — see LocalScanner]
    """

    def __init__(self):
        self.llm_calls: list[LLMCall] = []
        self.findings: list[Finding] = []

    def scan_files(self, files: list[tuple[str, str]]) -> tuple[list[LLMCall], list[Finding]]:
        """
        files: list of (relative_filename, file_content) tuples
        """
        self.llm_calls = []
        self.findings = []

        for filename, content in files:
            try:
                if filename.endswith('.py'):
                    self._scan_python(filename, content)
                elif filename.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    self._scan_js(filename, content)
            except Exception as e:
                print(f"  [!] Error scanning {filename}: {e}")

        self._generate_findings()
        return self.llm_calls, self.findings

    # ── JS/TS ──────────────────────────────────────────────────────────────────

    def _scan_js(self, filename: str, content: str):
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if not FETCH_BLOCK_PATTERN.search(line) and not LLM_ENDPOINT_PATTERN.search(line):
                continue

            func_start = self._find_js_func_start(lines, i - 1)
            ctx_start = max(0, func_start)
            ctx_end = min(len(lines), i + 25)
            context = '\n'.join(lines[ctx_start:ctx_end])

            call = LLMCall(
                file=filename,
                line=i,
                endpoint=self._extract_endpoint(line),
                snippet=line.strip(),
                language='js'
            )

            call.has_hardcoded_lang = any(
                re.search(p, context, re.IGNORECASE) for p in HARDCODED_LANG_PATTERNS
            )
            call.has_locale_in_prompt = bool(JS_LOCALE_IN_PROMPT.search(context))

            func_sig = '\n'.join(lines[ctx_start:ctx_start + 5])
            call.has_locale_param = bool(JS_LOCALE_PARAM.search(func_sig))
            call.locale_received_not_forwarded = (
                call.has_locale_param and
                not call.has_locale_in_prompt and
                not call.has_hardcoded_lang
            )

            self.llm_calls.append(call)

    def _find_js_func_start(self, lines: list, idx: int) -> int:
        for i in range(idx, max(0, idx - 30), -1):
            if JS_FUNCTION_START.search(lines[i]):
                return i
        return max(0, idx - 15)

    # ── Python ─────────────────────────────────────────────────────────────────

    def _scan_python(self, filename: str, content: str):
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            is_llm_call = (
                PYTHON_HTTP_PATTERN.search(line) or
                LOCAL_LLM_PATTERN.search(line)
            )
            if not is_llm_call and PYTHON_REQUESTS_CALL.search(line):
                lookahead = ' '.join(lines[i:min(len(lines), i + 3)])
                if LLM_URL_IN_WINDOW.search(lookahead):
                    is_llm_call = True

            if not is_llm_call:
                continue

            func_start = self._find_python_def_start(lines, i - 1)
            ctx_start = max(0, func_start)
            ctx_end = min(len(lines), i + 30)
            context = '\n'.join(lines[ctx_start:ctx_end])

            # Endpoint label
            endpoint = self._extract_endpoint(line)
            lookahead_check = line + ' '.join(lines[i:min(len(lines), i + 3)])
            if any(x in lookahead_check for x in ['localhost', '127.0.0.1']) or \
               'ollama' in lookahead_check.lower():
                endpoint = 'localhost (Ollama / local LLM)'
            elif endpoint == 'unknown':
                endpoint = 'LLM API (dynamic URL)'

            call = LLMCall(
                file=filename,
                line=i,
                endpoint=endpoint,
                snippet=line.strip(),
                language='python'
            )

            call.has_hardcoded_lang = any(
                re.search(p, context, re.IGNORECASE) for p in HARDCODED_LANG_PATTERNS
            )
            call.has_locale_in_prompt = bool(
                PYTHON_FSTRING_LOCALE.search(context) or
                PYTHON_LOCALE_IN_PROMPT.search(context)
            )

            func_sig = '\n'.join(lines[ctx_start:ctx_start + 3])
            call.has_locale_param = bool(PYTHON_DEF_LOCALE.search(func_sig))
            call.locale_received_not_forwarded = (
                call.has_locale_param and
                not call.has_locale_in_prompt and
                not call.has_hardcoded_lang
            )

            self.llm_calls.append(call)

    def _find_python_def_start(self, lines: list, idx: int) -> int:
        for i in range(idx, max(0, idx - 40), -1):
            if PYTHON_DEF_START.match(lines[i]):
                return i
        return max(0, idx - 15)

    # ── Shared ─────────────────────────────────────────────────────────────────

    def _extract_endpoint(self, line: str) -> str:
        for pattern in LLM_ENDPOINTS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                return m.group(0)
        return 'unknown'

    def _generate_findings(self):
        for call in self.llm_calls:
            if not call.has_locale_in_prompt and not call.has_hardcoded_lang:
                self.findings.append(Finding(
                    severity='CRITICAL',
                    rule_id='L001',
                    message='LLM API call has no locale or language context',
                    file=call.file,
                    line=call.line,
                    snippet=call.snippet,
                    suggestion='Add locale to system prompt: "Respond in the language for locale: {userLocale}"'
                ))

            if call.locale_received_not_forwarded:
                self.findings.append(Finding(
                    severity='CRITICAL',
                    rule_id='L002',
                    message='Locale parameter received but not forwarded to LLM prompt',
                    file=call.file,
                    line=call.line,
                    snippet=call.snippet,
                    suggestion='Inject locale into prompt: f"Respond in locale: {locale}"'
                ))

            if call.has_hardcoded_lang:
                self.findings.append(Finding(
                    severity='WARNING',
                    rule_id='L003',
                    message='Hardcoded language instruction detected',
                    file=call.file,
                    line=call.line,
                    snippet=call.snippet,
                    suggestion='Replace hardcoded language with a dynamic locale variable'
                ))


# ─── Local Scanner (filesystem wrapper) ──────────────────────────────────────

class LocalScanner(CoreScanner):
    """Wraps CoreScanner for local filesystem scanning."""

    def __init__(self, scan_path: str):
        super().__init__()
        self.scan_path = Path(scan_path)

    def scan(self) -> tuple[list[LLMCall], list[Finding]]:
        js_files = list(self.scan_path.rglob('*.js')) + \
                   list(self.scan_path.rglob('*.ts')) + \
                   list(self.scan_path.rglob('*.jsx')) + \
                   list(self.scan_path.rglob('*.tsx'))
        js_files = [f for f in js_files
                    if 'node_modules' not in str(f) and '.min.' not in f.name]

        py_files = list(self.scan_path.rglob('*.py'))
        py_files = [f for f in py_files
                    if '.venv' not in str(f) and '__pycache__' not in str(f)]

        all_files = js_files + py_files
        print(f"\n[Scanner] {len(js_files)} JS/TS + {len(py_files)} Python files")

        file_tuples = []
        for fp in all_files:
            try:
                relative = str(fp.relative_to(self.scan_path))
                content = fp.read_text(encoding='utf-8', errors='ignore')
                file_tuples.append((relative, content))
                print(f"  [read] {relative}")
            except Exception as e:
                print(f"  [!] Could not read {fp.name}: {e}")

        return self.scan_files(file_tuples)


# ─── HTML Report Generator ────────────────────────────────────────────────────

def generate_html_report(report: AuditReport, source_label: str = '') -> str:
    """Generate a self-contained HTML audit report."""

    critical = [f for f in report.findings if f.severity == 'CRITICAL']
    warnings  = [f for f in report.findings if f.severity == 'WARNING']

    score = max(0, 100 - len(critical) * 20 - len(warnings) * 8)

    if score >= 80:
        grade, grade_color = 'Good', '#22c55e'
    elif score >= 50:
        grade, grade_color = 'Needs Work', '#f59e0b'
    else:
        grade, grade_color = 'Poor', '#ef4444'

    def severity_badge(sev):
        colors = {'CRITICAL': '#ef4444', 'WARNING': '#f59e0b', 'INFO': '#6366f1'}
        return f'<span class="badge" style="background:{colors.get(sev,"#888")}">{sev}</span>'

    def finding_card(f):
        return f'''
        <div class="finding finding-{f.severity.lower()}">
          <div class="finding-header">
            {severity_badge(f.severity)}
            <span class="rule-id">{f.rule_id}</span>
            <span class="finding-file">{f.file}
              <span class="line-num">line {f.line}</span>
            </span>
          </div>
          <p class="finding-msg">{f.message}</p>
          <pre class="snippet">{f.snippet}</pre>
          <div class="suggestion">
            <span class="fix-label">💡 Fix:</span> {f.suggestion}
          </div>
        </div>'''

    findings_html = ''.join(finding_card(f) for f in report.findings) \
        if report.findings else '<div class="empty-state">✓ No issues found</div>'

    # LLM calls table rows
    call_rows = ''
    for c in report.llm_calls:
        if c.has_locale_in_prompt:
            status, cls = '✓ Locale-aware', 'good'
        elif c.has_hardcoded_lang:
            status, cls = '⚠ Hardcoded lang', 'warn'
        else:
            status, cls = '✗ No locale', 'bad'
        lang_tag = f'<span class="lang-tag lang-{c.language}">{c.language}</span>'
        call_rows += f'''<tr>
          <td class="fname">{c.file}</td>
          <td class="linenum">:{c.line}</td>
          <td>{lang_tag}</td>
          <td class="endpoint">{c.endpoint}</td>
          <td><span class="status-icon {cls}">{status}</span></td>
        </tr>'''

    # Live test section
    live_section = ''
    if report.live_results:
        rows = ''
        for r in report.live_results:
            icon = {'PASS': '✓', 'FAIL': '✗', 'ERROR': '⚠'}.get(r.status, '?')
            rows += f'''<tr class="live-{r.status.lower()}">
              <td><span class="locale-tag">{r.locale}</span></td>
              <td>{r.request_language}</td>
              <td>{r.response_language}</td>
              <td><span class="status-icon {r.status.lower()}">{icon} {r.status}</span></td>
              <td class="preview">{r.response_snippet[:80]}…</td>
            </tr>'''
        live_section = f'''
        <section class="section">
          <h2 class="section-title">Live Locale Tests</h2>
          <table>
            <thead><tr>
              <th>Locale</th><th>Requested</th><th>Detected</th>
              <th>Status</th><th>Preview</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>'''

    scan_label = source_label or report.scan_path

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>l10n-llm-auditor Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');
  :root {{
    --bg:#0d0f14; --surface:#161921; --surface2:#1e222d; --border:#2a2f3d;
    --text:#c9d1e0; --dim:#5a6478; --accent:#4f9cf9;
    --critical:#ef4444; --warning:#f59e0b; --good:#22c55e;
    --mono:'IBM Plex Mono',monospace; --sans:'IBM Plex Sans',sans-serif;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.6}}
  .header{{background:var(--surface);border-bottom:1px solid var(--border);padding:24px 40px;display:flex;justify-content:space-between;align-items:center}}
  .header h1{{font-family:var(--mono);font-size:17px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}}
  .header .sub{{color:var(--dim);font-size:12px;margin-top:3px;font-family:var(--mono)}}
  .header-meta{{text-align:right;font-family:var(--mono);font-size:11px;color:var(--dim);line-height:1.9}}
  .scorecard{{display:grid;grid-template-columns:180px 1fr;margin:28px 40px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}}
  .score-main{{background:var(--surface2);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:28px;border-right:1px solid var(--border)}}
  .score-num{{font-size:60px;font-weight:700;font-family:var(--mono);color:{grade_color};line-height:1}}
  .score-lbl{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;margin-top:5px}}
  .score-grade{{margin-top:8px;font-size:13px;font-weight:600;color:{grade_color}}}
  .score-stats{{display:grid;grid-template-columns:repeat(4,1fr)}}
  .stat{{padding:20px;border-right:1px solid var(--border);text-align:center}}
  .stat:last-child{{border-right:none}}
  .stat-num{{font-size:32px;font-weight:700;font-family:var(--mono)}}
  .stat-lbl{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin-top:3px}}
  .stat.critical .stat-num{{color:var(--critical)}}
  .stat.warning .stat-num{{color:var(--warning)}}
  .stat.good .stat-num{{color:var(--good)}}
  .stat.info .stat-num{{color:var(--accent)}}
  .section{{margin:0 40px 28px}}
  .section-title{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);font-family:var(--mono);font-weight:600;margin-bottom:14px;padding-bottom:7px;border-bottom:1px solid var(--border)}}
  .finding{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;margin-bottom:9px;border-left:3px solid transparent}}
  .finding-critical{{border-left-color:var(--critical)}}
  .finding-warning{{border-left-color:var(--warning)}}
  .finding-header{{display:flex;align-items:center;gap:9px;margin-bottom:7px;flex-wrap:wrap}}
  .badge{{font-size:9px;font-weight:700;padding:2px 7px;border-radius:3px;color:#fff;font-family:var(--mono);letter-spacing:.05em}}
  .rule-id{{font-family:var(--mono);font-size:11px;color:var(--dim);background:var(--surface2);padding:2px 6px;border-radius:3px}}
  .finding-file{{font-family:var(--mono);font-size:12px;color:var(--accent)}}
  .line-num{{color:var(--dim)}}
  .finding-msg{{color:var(--text);margin-bottom:7px;font-size:13px}}
  .snippet{{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:9px 13px;font-family:var(--mono);font-size:11px;color:#a8b5cc;overflow-x:auto;margin-bottom:7px;white-space:pre-wrap;word-break:break-all}}
  .suggestion{{font-size:12px;color:var(--dim);padding:7px 11px;background:var(--surface2);border-radius:4px}}
  .fix-label{{font-weight:600;color:var(--good)}}
  table{{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}}
  th{{background:var(--surface2);padding:9px 13px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);font-family:var(--mono);border-bottom:1px solid var(--border)}}
  td{{padding:9px 13px;border-bottom:1px solid var(--border);font-size:12px}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:var(--surface2)}}
  .fname{{font-family:var(--mono);color:var(--accent);font-size:11px}}
  .linenum{{font-family:var(--mono);color:var(--dim);font-size:11px}}
  .endpoint{{font-family:var(--mono);font-size:11px;color:var(--dim)}}
  .lang-tag{{font-family:var(--mono);font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}}
  .lang-js{{background:#1a2a1a;color:#4ade80}}
  .lang-python{{background:#1a1a2a;color:#818cf8}}
  .status-icon.good,.status-icon.pass{{color:var(--good)}}
  .status-icon.bad,.status-icon.fail{{color:var(--critical)}}
  .status-icon.warn,.status-icon.error{{color:var(--warning)}}
  .locale-tag{{font-family:var(--mono);background:var(--surface2);border:1px solid var(--border);padding:2px 7px;border-radius:3px;font-size:11px}}
  .preview{{font-family:var(--mono);font-size:11px;color:var(--dim);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .empty-state{{text-align:center;padding:36px;color:var(--good);font-family:var(--mono);background:var(--surface);border:1px solid var(--border);border-radius:6px}}
  .footer{{margin:32px 40px;padding-top:20px;border-top:1px solid var(--border);font-family:var(--mono);font-size:11px;color:var(--dim);text-align:center}}
</style>
</head>
<body>

<header class="header">
  <div>
    <h1>l10n-llm-auditor</h1>
    <div class="sub">LLM Localization Coverage Report</div>
  </div>
  <div class="header-meta">
    <div>{scan_label}</div>
    <div>{report.timestamp}</div>
    <div>{report.files_scanned} files scanned</div>
  </div>
</header>

<div class="scorecard">
  <div class="score-main">
    <div class="score-num">{score}</div>
    <div class="score-lbl">L10N Score</div>
    <div class="score-grade">{grade}</div>
  </div>
  <div class="score-stats">
    <div class="stat critical"><div class="stat-num">{len(critical)}</div><div class="stat-lbl">Critical</div></div>
    <div class="stat warning"><div class="stat-num">{len(warnings)}</div><div class="stat-lbl">Warnings</div></div>
    <div class="stat info"><div class="stat-num">{len(report.llm_calls)}</div><div class="stat-lbl">LLM Calls</div></div>
    <div class="stat good"><div class="stat-num">{report.files_scanned}</div><div class="stat-lbl">Files</div></div>
  </div>
</div>

<section class="section">
  <h2 class="section-title">LLM API Calls Detected ({len(report.llm_calls)})</h2>
  <table>
    <thead><tr><th>File</th><th>Line</th><th>Lang</th><th>Endpoint</th><th>L10N Status</th></tr></thead>
    <tbody>{call_rows}</tbody>
  </table>
</section>

<section class="section">
  <h2 class="section-title">Findings ({len(report.findings)} issues)</h2>
  {findings_html}
</section>

{live_section}

<footer class="footer">
  l10n-llm-auditor · {report.timestamp}
</footer>
</body>
</html>'''
