#!/usr/bin/env python3
"""
sheets_helper.py
Google Sheets API ユーティリティ（読み取り専用）

使用する認証情報は drive_helper と同じサービスアカウント。
promo_sheet_id は secrets.toml で上書き可。未設定なら DEFAULT_PROMO_SHEET_ID を使用。
"""
from pathlib import Path

try:
    import streamlit as st
    IN_STREAMLIT = True
except ImportError:
    IN_STREAMLIT = False

# 番宣管理スプレッドシートID（secrets.toml で上書き可）
DEFAULT_PROMO_SHEET_ID = '1e_z3kDX6vl0XktW7jiLg303D0WKPqUEberVP4qX9RG4'
PROMO_TAB_NAME = 'AI判定用_AUTO'

SHEETS_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

# 今週視聴人数・メモ欄として扱うべき列名（番宣リストから除外）
_PPL_LIKE_COLS = frozenset([
    '今週視聴人数', '視聴人数', '視聴者数', '推計視聴人数', '延べ視聴人数',
    '今週実績', '現在の視聴人数', 'viewers', '備考メモ', 'メモ',
])


def get_sheets_service():
    """サービスアカウントで Sheets API サービスを取得"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if IN_STREAMLIT and hasattr(st, 'secrets') and 'google_service_account' in st.secrets:
        sa_info = {str(k): str(v) for k, v in st.secrets['google_service_account'].items()}
        if 'private_key' in sa_info:
            sa_info['private_key'] = sa_info['private_key'].replace('\\n', '\n')
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SHEETS_SCOPES,
        )
    else:
        sa_path = Path(__file__).parent.parent / 'service_account.json'
        if sa_path.exists():
            creds = service_account.Credentials.from_service_account_file(
                str(sa_path), scopes=SHEETS_SCOPES,
            )
        else:
            raise FileNotFoundError(
                'Sheets API: 認証情報が見つかりません。'
                'Streamlit Secrets に google_service_account を設定してください。'
            )

    return build('sheets', 'v4', credentials=creds)


def get_promo_sheet_id() -> str:
    """
    secrets.toml の promo_sheet_id を優先。未設定なら DEFAULT_PROMO_SHEET_ID を返す。
    """
    if IN_STREAMLIT and hasattr(st, 'secrets'):
        sid = st.secrets.get('promo_sheet_id')
        if sid:
            return str(sid).strip()
    return DEFAULT_PROMO_SHEET_ID


def read_sheet_as_df(spreadsheet_id: str, tab_name: str):
    """
    Google Sheets の指定タブを pandas DataFrame で返す。
    1行目をヘッダーとして使用する。
    """
    import pandas as pd

    service = get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=tab_name,
            valueRenderOption='UNFORMATTED_VALUE',
        )
        .execute()
    )

    values = result.get('values', [])
    if not values:
        return pd.DataFrame()

    header = [str(h).strip() for h in values[0]]
    rows = []
    for row in values[1:]:
        padded = row + [''] * (len(header) - len(row))
        rows.append([str(v) if v != '' else '' for v in padded[:len(header)]])

    return pd.DataFrame(rows, columns=header)


def load_ai_promo_tab(spreadsheet_id: str) -> tuple:
    """
    AI判定用_AUTO タブを読み込み (items, meta) を返す。

    items: list of dict — 各行: {番組名, 重点強化期間, SPOT回数, 制作素材}
           ※ 今週視聴人数・備考欄など PPL 系の列は意図的に除外する
    meta:  dict — 読み込みメタデータ
        {spreadsheet_id, tab_name, row_count,
         name_col, period_col, spot_col, all_columns, excluded_cols}

    空行・説明行はそのまま含める（build_promo_effect_items 側でフィルタ）
    """
    df = read_sheet_as_df(spreadsheet_id, PROMO_TAB_NAME)

    meta = {
        'spreadsheet_id': spreadsheet_id,
        'tab_name':        PROMO_TAB_NAME,
        'row_count':       0,
        'name_col':        '（未検出）',
        'period_col':      '（未検出）',
        'spot_col':        '（未検出）',
        'all_columns':     [],
        'excluded_cols':   [],
    }

    if df.empty:
        return [], meta

    meta['all_columns'] = list(df.columns)

    # PPL系列を記録（除外対象）
    excluded = [c for c in df.columns if c.strip() in _PPL_LIKE_COLS]
    meta['excluded_cols'] = excluded

    # 列名マッピング
    col_map: dict = {}
    for c in df.columns:
        s = c.strip()
        if s == '番組名' and '番組名' not in col_map:
            col_map['番組名'] = c
        elif s == '重点強化期間' and '重点強化期間' not in col_map:
            col_map['重点強化期間'] = c
        elif s in ('SPOT回数', '放送回数', 'SPOT', 'SPOT数') and 'SPOT回数' not in col_map:
            col_map['SPOT回数'] = c
        elif s == '制作素材' and '制作素材' not in col_map:
            col_map['制作素材'] = c

    if '番組名' not in col_map:
        raise ValueError(
            f'AI判定用_AUTO タブに「番組名」列が見つかりません。'
            f'実際の列: {list(df.columns)}'
        )

    meta['name_col']   = col_map.get('番組名', '（未検出）')
    meta['period_col'] = col_map.get('重点強化期間', '（未検出）')
    meta['spot_col']   = col_map.get('SPOT回数', '（未検出）')

    items = []
    for _, row in df.iterrows():
        name     = str(row.get(col_map.get('番組名', ''), '')).strip()
        period   = str(row.get(col_map.get('重点強化期間', ''), '')).strip()
        spots    = str(row.get(col_map.get('SPOT回数', ''), '')).strip()
        material = str(row.get(col_map.get('制作素材', ''), '')).strip()

        items.append({
            '番組名':       name,
            '重点強化期間': period,
            'SPOT回数':     spots,
            '制作素材':     material,
        })

    meta['row_count'] = len(items)
    return items, meta
