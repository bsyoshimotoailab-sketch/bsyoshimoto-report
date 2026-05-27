#!/usr/bin/env python3
"""
make_pdf.py
HTMLをPDFに変換（Playwright使用・クラウド対応）
"""
import http.server
import os
import sys
import tempfile
import threading
import time
from pathlib import Path


def _install_playwright_if_needed():
    """Playwright Chromiumが未インストールなら自動インストール"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch()
        return True
    except Exception:
        try:
            import subprocess
            subprocess.run(
                [sys.executable, '-m', 'playwright', 'install', 'chromium', '--with-deps'],
                check=True, capture_output=True
            )
            return True
        except Exception as e:
            print(f"Playwright インストール失敗: {e}")
            return False


def html_to_pdf(html_path: str, out_path: str) -> str:
    """HTMLファイルをPDFに変換"""
    from playwright.sync_api import sync_playwright

    work_dir = str(Path(html_path).parent)
    original_dir = os.getcwd()

    try:
        os.chdir(work_dir)

        # ローカルHTTPサーバーを起動（Chart.js CDN回避のため）
        port = 18765
        httpd = http.server.HTTPServer(
            ('localhost', port),
            http.server.SimpleHTTPRequestHandler
        )
        t = threading.Thread(target=httpd.serve_forever)
        t.daemon = True
        t.start()
        time.sleep(0.5)

        url = f'http://localhost:{port}/{Path(html_path).name}'

        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
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

        httpd.shutdown()
        return out_path

    finally:
        os.chdir(original_dir)


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
