#!/usr/bin/env python3
"""
export_package.py
週次・番宣レポート生成物を Drive登録用 ZIP にまとめる
"""
import io
import json
import zipfile


def build_weekly_zip(pdf_bytes: bytes, year: int, week_num: int,
                     summary: dict, program_records: list) -> bytes:
    """
    週次レポート Drive登録用 ZIP。保管庫フォルダ構成に準拠。

    含まれるファイル:
      01_週次レポートPDF/bs_report_YYYY_WXX.pdf
      04_週次サマリーJSON/summary_YYYY_WXX.json
      05_番組別履歴/program_weekly_YYYY_WXX.json
      05_番組別履歴/program_weekly_YYYY_WXX.csv  (人間確認用)
      README.txt
    """
    w = f'W{week_num:02d}'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'01_週次レポートPDF/bs_report_{year}_{w}.pdf', pdf_bytes)
        zf.writestr(
            f'04_週次サマリーJSON/summary_{year}_{w}.json',
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        prog_payload = {'year': year, 'week_num': week_num, 'programs': program_records}
        zf.writestr(
            f'05_番組別履歴/program_weekly_{year}_{w}.json',
            json.dumps(prog_payload, ensure_ascii=False, indent=2),
        )
        if program_records:
            import pandas as pd
            zf.writestr(
                f'05_番組別履歴/program_weekly_{year}_{w}.csv',
                pd.DataFrame(program_records).to_csv(index=False),
            )
        zf.writestr('README.txt', _readme_weekly(year, week_num))
    return buf.getvalue()


def build_promo_zip(pdf_bytes: bytes, year: int, week_num: int,
                    promo_records: list) -> bytes:
    """
    番宣効果検証 Drive登録用 ZIP。

    含まれるファイル:
      02_番宣効果検証PDF/promo_report_YYYY_WXX.pdf
      06_番宣履歴/promo_YYYY_WXX.json
      06_番宣履歴/promo_weekly_YYYY_WXX.csv  (人間確認用)
      README.txt
    """
    w = f'W{week_num:02d}'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'02_番宣効果検証PDF/promo_report_{year}_{w}.pdf', pdf_bytes)
        promo_payload = {'year': year, 'week_num': week_num, 'items': promo_records}
        zf.writestr(
            f'06_番宣履歴/promo_{year}_{w}.json',
            json.dumps(promo_payload, ensure_ascii=False, indent=2),
        )
        if promo_records:
            import pandas as pd
            zf.writestr(
                f'06_番宣履歴/promo_weekly_{year}_{w}.csv',
                pd.DataFrame(promo_records).to_csv(index=False),
            )
        zf.writestr('README.txt', _readme_promo(year, week_num))
    return buf.getvalue()


def _readme_weekly(year: int, week_num: int) -> str:
    w = f'W{week_num:02d}'
    return (
        f'BSよしもと 視聴率レポートシステム - Drive登録用パッケージ\n'
        f'{year}年 第{week_num}週 週次レポート\n'
        f'※ Drive自動保存は行いません。下記フォルダへ手動でアップロードしてください。\n\n'
        f'保存先: BSよしもと_視聴率レポート保管庫/\n'
        f'  01_週次レポートPDF/     ← bs_report_{year}_{w}.pdf\n'
        f'  04_週次サマリーJSON/    ← summary_{year}_{w}.json\n'
        f'  05_番組別履歴/          ← program_weekly_{year}_{w}.json / .csv\n'
    )


def _readme_promo(year: int, week_num: int) -> str:
    w = f'W{week_num:02d}'
    return (
        f'BSよしもと 視聴率レポートシステム - Drive登録用パッケージ\n'
        f'{year}年 第{week_num}週 番宣効果検証\n'
        f'※ Drive自動保存は行いません。下記フォルダへ手動でアップロードしてください。\n\n'
        f'保存先: BSよしもと_視聴率レポート保管庫/\n'
        f'  02_番宣効果検証PDF/  ← promo_report_{year}_{w}.pdf\n'
        f'  06_番宣履歴/          ← promo_{year}_{w}.json / promo_weekly_{year}_{w}.csv\n'
    )
