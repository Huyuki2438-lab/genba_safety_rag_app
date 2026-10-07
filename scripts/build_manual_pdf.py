"""利用マニュアルのHTMLからPDFを生成する。

HTML（利用マニュアル/現場KYアシスト_利用マニュアル.html）が正本。内容を直す場合は
HTMLを編集し、このスクリプトでPDFを作り直す。PDFは直接編集しない。

PDF出力はアプリ本体（backend/app/api/v1/pdf.py）と同じく、Playwright + Microsoft Edge を使う。
用紙・余白はHTML内の @page（A4 / 12mm）に従う。

使い方: python scripts/build_manual_pdf.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

MANUAL_DIR = Path(__file__).resolve().parents[1] / "利用マニュアル"
HTML = MANUAL_DIR / "現場KYアシスト_利用マニュアル.html"
PDF = HTML.with_suffix(".pdf")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, timeout=30000)
        try:
            page = browser.new_page()
            page.goto(HTML.as_uri(), wait_until="load", timeout=60000)
            page.pdf(path=str(PDF), prefer_css_page_size=True, print_background=True)
        finally:
            browser.close()
    print(f"generated: {PDF}")


if __name__ == "__main__":
    main()
