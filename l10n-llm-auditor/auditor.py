#!/usr/bin/env python3
"""
auditor.py  —  l10n-llm-auditor (Local)
========================================
Scans a downloaded JS/TS/Python codebase for LLM localization issues.

Usage:
  python auditor.py <path_to_codebase>
  python auditor.py <path_to_codebase> --live --api-key <anthropic_key>
  python auditor.py <path_to_codebase> --output my_report.html

Requires:
  pip install requests
"""

import os
import argparse
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from scanner_core import (
    LocalScanner, AuditReport, generate_html_report
)


# ─── Live Tester ─────────────────────────────────────────────────────────────

@dataclass
class LiveTestResult:
    locale: str
    status: str
    request_language: str
    response_language: str
    response_snippet: str
    endpoint: str


class LiveTester:
    TEST_LOCALES = {'en': 'English', 'es': 'Spanish', 'fr': 'French'}
    TEST_PROMPT = "Tell me today's date and greet me warmly."

    def __init__(self, api_key: str):
        self.api_key = api_key

    def run(self, llm_calls: list) -> list:
        has_anthropic = any('anthropic' in c.endpoint.lower() for c in llm_calls)
        if not has_anthropic:
            print("\n[Live Tester] No Anthropic API calls found — skipping.")
            return []
        print(f"\n[Live Tester] Testing {len(self.TEST_LOCALES)} locales...")
        results = []
        for locale, lang_name in self.TEST_LOCALES.items():
            print(f"  -> {locale} ({lang_name})...")
            r = self._test_locale(locale, lang_name)
            results.append(r)
            print(f"     {r.status} | detected: {r.response_language}")
        return results

    def _test_locale(self, locale: str, lang_name: str) -> LiveTestResult:
        try:
            resp = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': 'claude-haiku-4-5-20251001',
                    'max_tokens': 150,
                    'system': f'You are a helpful assistant. Always respond in the language for locale: {locale}',
                    'messages': [{'role': 'user', 'content': self.TEST_PROMPT}]
                },
                timeout=20
            )
            if resp.status_code != 200:
                return LiveTestResult(locale, 'ERROR', lang_name, 'unknown',
                                      f'HTTP {resp.status_code}', 'api.anthropic.com')
            text = resp.json()['content'][0]['text']
            detected = self._detect_language(text)
            status = 'PASS' if detected.lower() in [locale, lang_name.lower()] else 'FAIL'
            return LiveTestResult(locale, status, lang_name, detected, text[:120], 'api.anthropic.com')
        except Exception as e:
            return LiveTestResult(locale, 'ERROR', lang_name, 'unknown', str(e), 'api.anthropic.com')

    def _detect_language(self, text: str) -> str:
        try:
            resp = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': 'claude-haiku-4-5-20251001',
                    'max_tokens': 10,
                    'system': 'Detect the language. Reply with ONLY the language name in English.',
                    'messages': [{'role': 'user', 'content': text[:300]}]
                },
                timeout=10
            )
            return resp.json()['content'][0]['text'].strip()
        except:
            return 'unknown'


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='l10n-llm-auditor: Scan a local codebase for LLM localization issues'
    )
    parser.add_argument('path', help='Path to codebase folder')
    parser.add_argument('--live', action='store_true', help='Run live locale tests')
    parser.add_argument('--api-key', help='Anthropic API key')
    parser.add_argument('--output', default=None, help='Output HTML file (default: l10n_audit_YYYYMMDD_HHMMSS.html)')
    args = parser.parse_args()

    print("""
+==========================================+
|       l10n-llm-auditor  (local)         |
|   LLM Localization Coverage Analysis    |
+==========================================+
""")

    scan_path = Path(args.path)
    if not scan_path.exists():
        print(f"[ERROR] Path not found: {scan_path}")
        return

    js = [f for f in list(scan_path.rglob('*.js')) + list(scan_path.rglob('*.ts')) +
          list(scan_path.rglob('*.jsx')) + list(scan_path.rglob('*.tsx'))
          if 'node_modules' not in str(f) and '.min.' not in f.name]
    py = [f for f in scan_path.rglob('*.py')
          if '.venv' not in str(f) and '__pycache__' not in str(f)]
    total_files = len(js) + len(py)

    report = AuditReport(
        scan_path=str(scan_path.resolve()),
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        files_scanned=total_files
    )

    print("[Phase 1] Static Analysis...")
    scanner = LocalScanner(args.path)
    report.llm_calls, report.findings = scanner.scan()

    critical = [f for f in report.findings if f.severity == 'CRITICAL']
    warnings  = [f for f in report.findings if f.severity == 'WARNING']
    print(f"\n  -> {len(report.llm_calls)} LLM calls | {len(critical)} critical | {len(warnings)} warnings")

    if args.live:
        api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            print("\n[Live Test] No API key. Use --api-key or set ANTHROPIC_API_KEY")
        else:
            tester = LiveTester(api_key)
            report.live_results = tester.run(report.llm_calls)

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = args.output or f'l10n_audit_{timestamp_str}.html'
    print(f"\n[Report] Writing {output_file}...")
    html = generate_html_report(report)
    Path(output_file).write_text(html, encoding='utf-8')
    print(f"  -> Saved: {Path(output_file).resolve()}")
    print(f"\nDone. Files: {total_files}  LLM calls: {len(report.llm_calls)}  Issues: {len(report.findings)}")


if __name__ == '__main__':
    main()
