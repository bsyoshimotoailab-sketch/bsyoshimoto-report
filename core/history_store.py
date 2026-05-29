#!/usr/bin/env python3
"""
history_store.py
Drive上の番組履歴・番宣履歴・PDFの保存と読み込み
"""
import io
import json

SUBFOLDER_PROGRAM_HISTORY = 'program_history'
SUBFOLDER_PROMO_HISTORY   = 'promo_history'


# ── フォルダ取得・作成 ────────────────────────────────

def get_or_create_subfolder(parent_id: str, name: str) -> str:
    """parent_id 直下に name フォルダを取得または作成し、そのIDを返す"""
    from core.drive_helper import get_drive_service
    service = get_drive_service()
    q = (f"'{parent_id}' in parents and name='{name}' "
         f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = service.files().list(q=q, fields='files(id)').execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    meta = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    f = service.files().create(body=meta, fields='id').execute()
    return f['id']


def _get_or_create_nested(root_id: str, *parts: str) -> str:
    """root_id 配下にネストしたサブフォルダを取得または作成"""
    cur = root_id
    for part in parts:
        cur = get_or_create_subfolder(cur, part)
    return cur


# ── JSON 保存・読み込み ──────────────────────────────

def save_json(folder_id: str, filename: str, data) -> str:
    from core.drive_helper import upload_file
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    return upload_file(folder_id, filename, payload, 'application/json')


def load_json(folder_id: str, filename: str):
    from core.drive_helper import list_files_in_folder, download_file
    files = [f for f in list_files_in_folder(folder_id) if f['name'] == filename]
    if not files:
        return None
    return json.loads(download_file(files[0]['id']).decode('utf-8'))


# ── CSV 追記・更新 ────────────────────────────────────

def update_csv(folder_id: str, filename: str, new_rows: list,
               key_cols: list = None) -> str:
    """
    DriveフォルダのCSVにnew_rowsを追記・重複排除して保存する。
    key_cols が指定された場合、同じキー値の既存行を置き換える。
    """
    import pandas as pd
    from core.drive_helper import list_files_in_folder, download_file, upload_file

    new_df = pd.DataFrame(new_rows)
    if new_df.empty:
        return None

    existing_df = None
    exact = [f for f in list_files_in_folder(folder_id) if f['name'] == filename]
    if exact:
        try:
            raw = download_file(exact[0]['id'])
            existing_df = pd.read_csv(io.BytesIO(raw), dtype=str)
        except Exception:
            existing_df = None

    if existing_df is not None and not existing_df.empty and key_cols:
        cols_present = [c for c in key_cols if c in existing_df.columns and c in new_df.columns]
        if cols_present:
            def _key(df_):
                return df_[cols_present].astype(str).apply('|'.join, axis=1)
            new_keys = set(_key(new_df))
            existing_df = existing_df[~_key(existing_df).isin(new_keys)]
        combined = pd.concat([existing_df, new_df.astype(str)], ignore_index=True)
    elif existing_df is not None and not existing_df.empty:
        combined = pd.concat([existing_df, new_df.astype(str)], ignore_index=True)
    else:
        combined = new_df.astype(str)

    csv_bytes = combined.to_csv(index=False).encode('utf-8')
    return upload_file(folder_id, filename, csv_bytes, 'text/csv')


def load_csv(folder_id: str, filename: str):
    import pandas as pd
    from core.drive_helper import list_files_in_folder, download_file
    exact = [f for f in list_files_in_folder(folder_id) if f['name'] == filename]
    if not exact:
        return None
    try:
        raw = download_file(exact[0]['id'])
        return pd.read_csv(io.BytesIO(raw), dtype=str)
    except Exception:
        return None


# ── 番組別週次実績 ────────────────────────────────────

def save_program_weekly(root_id: str, year: int, week_num: int,
                        records: list) -> dict:
    """
    番組別週次実績をJSONとprogram_history_all.csvで保存する。
    Returns: {'folder_id': str, 'json_file': str, 'records': int}
    """
    folder_id = get_or_create_subfolder(root_id, SUBFOLDER_PROGRAM_HISTORY)
    json_name = f'program_weekly_{year}_W{week_num:02d}.json'
    save_json(folder_id, json_name, {
        'year': year, 'week_num': week_num, 'programs': records,
    })
    update_csv(
        folder_id, 'program_history_all.csv', records,
        key_cols=['year', 'week_num', 'normalized_title'],
    )
    return {'folder_id': folder_id, 'json_file': json_name, 'records': len(records)}


def load_program_history_df(root_id: str):
    """program_history_all.csv を読み込んで DataFrame を返す（なければ空DF）"""
    import pandas as pd
    folder_id = get_or_create_subfolder(root_id, SUBFOLDER_PROGRAM_HISTORY)
    df = load_csv(folder_id, 'program_history_all.csv')
    if df is None or df.empty:
        return pd.DataFrame()
    for col in ('year', 'week_num', 'total_viewing_ppl', 'total_viewing_devices',
                'avg_viewing_ppl', 'max_viewing_ppl', 'broadcast_count'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ── 番宣履歴 ─────────────────────────────────────────

def save_promo_weekly(root_id: str, year: int, week_num: int,
                      records: list) -> dict:
    """
    番宣週次照合結果をJSONとpromo_history_all.csvで保存する。
    Returns: {'json_file': str, 'records': int}
    """
    folder_id = get_or_create_subfolder(root_id, SUBFOLDER_PROMO_HISTORY)
    json_name = f'promo_{year}_W{week_num:02d}.json'
    save_json(folder_id, json_name, {
        'year': year, 'week_num': week_num, 'items': records,
    })
    update_csv(
        folder_id, 'promo_history_all.csv', records,
        key_cols=['year', 'week_num', 'normalized_title'],
    )
    return {'json_file': json_name, 'records': len(records)}


def load_promo_history_df(root_id: str):
    """promo_history_all.csv を読み込んで DataFrame を返す（なければ空DF）"""
    import pandas as pd
    folder_id = get_or_create_subfolder(root_id, SUBFOLDER_PROMO_HISTORY)
    df = load_csv(folder_id, 'promo_history_all.csv')
    if df is None or df.empty:
        return pd.DataFrame()
    for col in ('year', 'week_num', 'current_viewing_ppl', 'current_viewing_devices',
                'past_4w_avg_ppl', 'past_13w_avg_ppl', 'diff_4w_pct', 'diff_13w_pct'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ── PDF 保存 ──────────────────────────────────────────

def save_report_pdf(root_id: str, report_type: str,
                    filename: str, pdf_bytes: bytes) -> str:
    """
    PDFを reports/{report_type}/ に保存する。
    report_type: 'weekly' | 'promo' | 'macro'
    """
    from core.drive_helper import upload_file
    reports_id = get_or_create_subfolder(root_id, 'reports')
    folder_id  = get_or_create_subfolder(reports_id, report_type)
    return upload_file(folder_id, filename, pdf_bytes, 'application/pdf')
