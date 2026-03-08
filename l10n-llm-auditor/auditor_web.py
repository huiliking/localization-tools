#!/usr/bin/env python3
"""
auditor_web.py  —  l10n-llm-auditor (Web)
==========================================
Flask web app. Paste a public GitHub repo URL,
get an HTML localization audit report instantly.
No cloning. No download. Uses GitHub API.

Usage:
  pip install flask requests
  python auditor_web.py
  # Open http://localhost:5000

Optional GitHub token (avoids 60 req/hr rate limit):
  set GITHUB_TOKEN=ghp_xxx   (Windows)
  export GITHUB_TOKEN=ghp_xxx (Mac/Linux)
"""

import os
import re
import requests
from flask import Flask, request, render_template_string, jsonify
from datetime import datetime
from scanner_core import CoreScanner, AuditReport, generate_html_report

app = Flask(__name__)

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

SUPPORTED_EXTENSIONS = {'.js', '.ts', '.jsx', '.tsx', '.py'}
SKIP_PATHS = {'node_modules', '.venv', '__pycache__', 'dist', 'build', '.next', 'vendor'}
MAX_FILES = 200      # cap to avoid rate limits
MAX_FILE_SIZE = 200  # KB


# ─── GitHub API helpers ───────────────────────────────────────────────────────

def github_headers():
    h = {'Accept': 'application/vnd.github.v3+json'}
    if GITHUB_TOKEN:
        h['Authorization'] = f'token {GITHUB_TOKEN}'
    return h


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract owner/repo from various GitHub URL formats."""
    url = url.strip().rstrip('/')
    patterns = [
        r'github\.com/([^/]+)/([^/\?#]+)',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            owner, repo = m.group(1), m.group(2)
            repo = repo.replace('.git', '')
            return owner, repo
    return None


def get_repo_tree(owner: str, repo: str) -> list[dict] | None:
    """Fetch full file tree via GitHub API."""
    # Get default branch
    repo_resp = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}',
        headers=github_headers(), timeout=10
    )
    if repo_resp.status_code != 200:
        return None
    default_branch = repo_resp.json().get('default_branch', 'main')

    # Get recursive tree
    tree_resp = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1',
        headers=github_headers(), timeout=15
    )
    if tree_resp.status_code != 200:
        return None

    return tree_resp.json().get('tree', [])


def should_scan_file(path: str) -> bool:
    """Filter out non-source files and skip directories."""
    parts = path.split('/')
    # Skip if any path component is in the skip list
    if any(p in SKIP_PATHS for p in parts):
        return False
    # Check extension
    ext = '.' + path.rsplit('.', 1)[-1] if '.' in path else ''
    return ext in SUPPORTED_EXTENSIONS


def fetch_file_content(owner: str, repo: str, path: str) -> str | None:
    """Fetch a single file's content via GitHub raw URL."""
    try:
        url = f'https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}'
        resp = requests.get(url, headers=github_headers(), timeout=10)
        if resp.status_code == 200:
            # Skip very large files
            if len(resp.content) > MAX_FILE_SIZE * 1024:
                return None
            return resp.text
    except Exception:
        pass
    return None


def scan_github_repo(owner: str, repo: str) -> tuple[AuditReport, str | None]:
    """
    Main entry point for web scanning.
    Returns (AuditReport, error_message_or_None)
    """
    # Get file tree
    tree = get_repo_tree(owner, repo)
    if tree is None:
        return None, f"Could not access repo {owner}/{repo}. Check the URL or rate limits."

    # Filter to scannable files
    scannable = [
        item['path'] for item in tree
        if item['type'] == 'blob' and should_scan_file(item['path'])
    ]

    if not scannable:
        return None, "No JS/TS/Python files found in this repository."

    # Cap file count
    if len(scannable) > MAX_FILES:
        scannable = scannable[:MAX_FILES]
        truncated = True
    else:
        truncated = False

    # Fetch file contents
    file_tuples = []
    errors = []
    for path in scannable:
        content = fetch_file_content(owner, repo, path)
        if content:
            file_tuples.append((path, content))
        else:
            errors.append(path)

    if not file_tuples:
        return None, "Could not fetch any file contents. Possible rate limit — try adding a GITHUB_TOKEN."

    # Run scanner
    scanner = CoreScanner()
    llm_calls, findings = scanner.scan_files(file_tuples)

    report = AuditReport(
        scan_path=f'github.com/{owner}/{repo}',
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        files_scanned=len(file_tuples),
        llm_calls=llm_calls,
        findings=findings
    )

    note = None
    if truncated:
        note = f"Large repo: scanned first {MAX_FILES} source files only."
    if errors:
        note = (note or '') + f" {len(errors)} files could not be fetched."

    return report, note


# ─── Web UI ───────────────────────────────────────────────────────────────────

INDEX_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>l10n-llm-auditor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');
  :root {
    --bg:#0d0f14; --surface:#161921; --surface2:#1e222d; --border:#2a2f3d;
    --text:#c9d1e0; --dim:#5a6478; --accent:#4f9cf9; --good:#22c55e;
    --mono:'IBM Plex Mono',monospace; --sans:'IBM Plex Sans',sans-serif;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:var(--sans);
         min-height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; padding:40px 20px; }

  .card {
    background:var(--surface); border:1px solid var(--border); border-radius:12px;
    padding:48px; width:100%; max-width:560px;
  }

  .logo {
    font-family:var(--mono); font-size:22px; font-weight:600;
    color:var(--accent); letter-spacing:.08em; text-transform:uppercase;
    margin-bottom:6px;
  }

  .tagline {
    color:var(--dim); font-size:13px; font-family:var(--mono); margin-bottom:36px;
  }

  label {
    display:block; font-size:11px; text-transform:uppercase;
    letter-spacing:.1em; color:var(--dim); font-family:var(--mono);
    margin-bottom:10px;
  }

  input[type=text] {
    width:100%; padding:12px 16px; background:var(--surface2);
    border:1px solid var(--border); border-radius:6px; color:var(--text);
    font-family:var(--mono); font-size:13px; outline:none;
    transition:border-color .2s;
  }
  input[type=text]:focus { border-color:var(--accent); }
  input[type=text]::placeholder { color:var(--dim); }

  button {
    margin-top:16px; width:100%; padding:13px;
    background:var(--accent); color:#fff; border:none; border-radius:6px;
    font-family:var(--mono); font-size:13px; font-weight:600;
    letter-spacing:.05em; cursor:pointer; transition:opacity .2s;
  }
  button:hover { opacity:.88; }
  button:disabled { opacity:.4; cursor:not-allowed; }

  .examples {
    margin-top:24px; padding-top:20px; border-top:1px solid var(--border);
  }

  .examples-label {
    font-size:10px; text-transform:uppercase; letter-spacing:.1em;
    color:var(--dim); font-family:var(--mono); margin-bottom:10px;
  }

  .example-btn {
    display:inline-block; margin:4px 4px 4px 0;
    padding:4px 10px; background:var(--surface2); border:1px solid var(--border);
    border-radius:4px; font-family:var(--mono); font-size:11px; color:var(--accent);
    cursor:pointer; transition:border-color .15s;
  }
  .example-btn:hover { border-color:var(--accent); }

  .status {
    margin-top:18px; padding:12px 16px; background:var(--surface2);
    border:1px solid var(--border); border-radius:6px;
    font-family:var(--mono); font-size:12px; color:var(--dim);
    display:none;
  }
  .status.visible { display:block; }
  .status.error { color:#ef4444; border-color:#ef4444; }

  .note {
    margin-top:28px; font-size:11px; color:var(--dim);
    font-family:var(--mono); line-height:1.7; text-align:center;
  }
  .note a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>

<div class="card">
  <div class="logo">l10n-llm-auditor</div>
  <div class="tagline">// LLM localization coverage for public GitHub repos</div>

  <label for="repo-url">GitHub Repository URL</label>
  <input type="text" id="repo-url"
    placeholder="https://github.com/vercel/ai"
    autocomplete="off" spellcheck="false">
  <button id="scan-btn" onclick="startScan()">Scan Repository</button>

  <div class="status" id="status-msg"></div>

  <div class="examples">
    <div class="examples-label">Try these →</div>
    <span class="example-btn" onclick="setUrl('https://github.com/vercel/ai')">vercel/ai</span>
    <span class="example-btn" onclick="setUrl('https://github.com/openai/openai-node')">openai/openai-node</span>
    <span class="example-btn" onclick="setUrl('https://github.com/anthropics/anthropic-sdk-python')">anthropic-sdk-python</span>
  </div>
</div>

<div class="note">
  Scans JS · TS · JSX · TSX · Python &nbsp;·&nbsp;
  Skips node_modules, .venv, dist &nbsp;·&nbsp;
  Max {{ max_files }} files per scan<br>
  Add a <a href="https://github.com/settings/tokens" target="_blank">GitHub token</a>
  as <code>GITHUB_TOKEN</code> env var to avoid rate limits
</div>

<script>
function setUrl(url) {
  document.getElementById('repo-url').value = url;
}

async function startScan() {
  const url = document.getElementById('repo-url').value.trim();
  if (!url) return;

  const btn = document.getElementById('scan-btn');
  const status = document.getElementById('status-msg');

  btn.disabled = true;
  btn.textContent = 'Scanning...';
  status.className = 'status visible';
  status.textContent = 'Fetching repository file tree...';

  try {
    const resp = await fetch('/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });

    const data = await resp.json();

    if (data.error) {
      status.className = 'status visible error';
      status.textContent = 'Error: ' + data.error;
    } else {
      status.textContent = 'Scan complete — opening report...';
      // Open report in new tab
      // Write report into current page (avoids popup blocker)
      // Store suggested filename for download
      window._reportFilename = data.filename || 'l10n_audit_report.html';
      document.open();
      document.write(data.html);
      document.close();
    }
  } catch (e) {
    status.className = 'status visible error';
    status.textContent = 'Request failed: ' + e.message;
  }

  btn.disabled = false;
  btn.textContent = 'Scan Repository';
}

document.getElementById('repo-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') startScan();
});
</script>
</body>
</html>'''


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(INDEX_HTML, max_files=MAX_FILES)


@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing url parameter'}), 400

    parsed = parse_github_url(data['url'])
    if not parsed:
        return jsonify({'error': 'Invalid GitHub URL. Expected: https://github.com/owner/repo'})

    owner, repo = parsed
    print(f"\n[Web] Scanning {owner}/{repo}...")

    report, note = scan_github_repo(owner, repo)

    if report is None:
        return jsonify({'error': note or 'Scan failed'})

    source_label = f'github.com/{owner}/{repo}'
    if note:
        source_label += f' ({note})'

    html = generate_html_report(report, source_label=source_label)
    from datetime import datetime as dt
    ts = dt.now().strftime('%Y%m%d_%H%M%S')
    filename = f'l10n_audit_{owner}_{repo}_{ts}.html'
    return jsonify({'html': html, 'note': note, 'filename': filename})


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'token': bool(GITHUB_TOKEN)})


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("""
+==========================================+
|       l10n-llm-auditor  (web)           |
|   LLM Localization Coverage Analysis    |
+==========================================+

  Open: http://localhost:5000

  Tip: set GITHUB_TOKEN env var to avoid
       GitHub API rate limits (60 req/hr)
""")
    if GITHUB_TOKEN:
        print("  [+] GitHub token detected - rate limit: 5000 req/hr")
    else:
        print("  [!] No GitHub token - rate limit: 60 req/hr")
    print()
    app.run(debug=True, port=5000)
