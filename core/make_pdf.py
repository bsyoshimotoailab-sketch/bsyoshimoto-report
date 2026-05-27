#!/usr/bin/env python3
"""
make_pdf.py
HTMLをPDFに変換（Playwright使用・クラウド対応）
"""
import os
import sys
import tempfile
from pathlib import Path


def _launch_chromium(p):
    """Chromiumを起動。実行ファイル未検出時のみ自動インストールしてリトライ"""
    import subprocess
    _ARGS = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    try:
        return p.chromium.launch(args=_ARGS)
    except Exception as e:
        msg = str(e)
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
            subprocess.run(
                [sys.executable, '-m', 'playwright', 'install', 'chromium'],
                check=True
            )
            return p.chromium.launch(args=_ARGS)
        raise


def html_to_pdf(html_path: str, out_path: str) -> str:
    """HTMLファイルをPDFに変換"""
    from playwright.sync_api import sync_playwright

    url = Path(html_path).resolve().as_uri()

    with sync_playwright() as p:
        browser = _launch_chromium(p)
        context = browser.new_context(viewport={'width': 1240, 'height': 900})
        page = context.new_page()
        page.emulate_media(media='screen')
        page.goto(url, wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(3000)
        page.pdf(
            path=out_path,
            format='A4',
            print_background=True,
            margin={'top': '8mm', 'bottom': '8mm', 'left': '6mm', 'right': '6mm'}
        )
        browser.close()

    return out_path


def generate_pdf_from_html_string(html_content: str) -> bytes:
    """HTML文字列をPDFバイト列に変換"""
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, 'report.html')
        pdf_path  = os.path.join(tmpdir, 'report.pdf')

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        html_to_pdf(html_path, pdf_path)

        with open(pdf_path, 'rb') as f:
            return f.read()
