#!/usr/bin/env python3
"""
history_store.py
Drive上の番組履歴・番宣履歴・サマリーの読み込み（読み取り専用）

Drive側の手動保存フォルダ構成（DRIVE_FOLDER_ID 直下）:
BSよしもと_視聴率レポート保管庫/
  01_週次レポートPDF/
  02_番宣効果検証PDF/
  03_クール総括PDF/
  04_週次サマリーJSON/
  05_番組別履歴/
  06_番宣履歴/
  99_過去レポート取り込み/
"""
import json

ARCHIVE_ROOT = 'BSよしもと_視聴率レポート保管庫'

ARCHIVE_FOLDERS = {
    'weekly_pdf':  '01_週次レポートPDF',
    'promo_pdf':   '02_番宣効果検証PDF',
    'macro_pdf':   '03_クール総括PDF',
    'summary':     '04_週次サマリーJSON',
    'program':     '05_番組別履歴',
    'promo':       '06_番宣履歴',
    'archive':     '99_過去レポート取り込み',
}

_folder_cache: dict = {}


# ── フォルダ検索（読み取り専用・作成しない） ─────────────────────

def _find_subfolder(parent_id: str, name: str, service) -> str:
    """parent_id 直下の name フォルダIDを返す。存在しなければNone（作成しない）"""
    cache_key = f'{parent_id}/{name}'
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]
    q = (f"'{parent_id}' in parents and name='{name}' "
         f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = service.files().list(
        q=q, fields='files(id)',
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get('files', [])
    if not files:
        return None
    fid = files[0]['id']
    _folder_cache[cache_key] = fid
    return fid


def get_archive_folder(root_id: str, key: str):
    """
    ARCHIVE_FOLDERS[key] のフォルダIDを返す。存在しなければNone（作成しない）。
    """
    from core.drive_helper import get_drive_service
    try:
        service = get_drive_service()
        archive_id = _find_subfolder(root_id, ARCHIVE_ROOT, service)
        if archive_id is None:
            return None
        return _find_subfolder(archive_id, ARCHIVE_FOLDERS[key], service)
    except Exception:
        return None


# ── 週次サマリー読み込み ──────────────────────────────────────────

def load_summaries_from_archive(root_id: str) -> list:
    """
    04_週次サマリーJSON/ の summary_*.json を全件読み込む。
    フォルダが存在しない場合は空リストを返す。
    """
    from core.drive_helper import load_all_summaries
    try:
        folder_id = get_archive_folder(root_id, 'summary')
    except Exception:
        return []
    if folder_id is None:
        return []
    return load_all_summaries(folder_id)


# ── 番組別履歴読み込み ────────────────────────────────────────────

def load_program_history_df(root_id: str):
    """
    05_番組別履歴/ の program_weekly_*.json を全件読み込んでDataFrameを返す。
    ファイルが存在しない場合は空DataFrameを返す。
    """
    import pandas as pd
    from core.drive_helper import list_files_in_folder, download_file
    try:
        folder_id = get_archive_folder(root_id, 'program')
    except Exception:
        return pd.DataFrame()
    if folder_id is None:
        return pd.DataFrame()

    files = list_files_in_folder(folder_id, name_contains='program_weekly_')
    json_files = sorted(
        [f for f in files if f['name'].endswith('.json')],
        key=lambda x: x['name'],
    )
    all_records = []
    for f in json_files:
        try:
            data = json.loads(download_file(f['id']).decode('utf-8'))
            all_records.extend(data.get('programs', []))
        except Exception:
            continue

    if not all_records:
        return pd.DataFrame()
    df = pd.DataFrame(all_records)
    for col in ('year', 'week_num', 'total_viewing_ppl', 'total_viewing_devices',
                'avg_viewing_ppl', 'max_viewing_ppl', 'broadcast_count'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ── 番宣履歴読み込み ──────────────────────────────────────────────

def load_promo_history_df(root_id: str):
    """
    06_番宣履歴/ の promo_*.json を全件読み込んでDataFrameを返す。
    ファイルが存在しない場合は空DataFrameを返す。
    """
    import pandas as pd
    from core.drive_helper import list_files_in_folder, download_file
    try:
        folder_id = get_archive_folder(root_id, 'promo')
    except Exception:
        return pd.DataFrame()
    if folder_id is None:
        return pd.DataFrame()

    files = list_files_in_folder(folder_id, name_contains='promo_')
    json_files = sorted(
        [f for f in files if f['name'].endswith('.json')],
        key=lambda x: x['name'],
    )
    all_records = []
    for f in json_files:
        try:
            data = json.loads(download_file(f['id']).decode('utf-8'))
            all_records.extend(data.get('items', []))
        except Exception:
            continue

    if not all_records:
        return pd.DataFrame()
    df = pd.DataFrame(all_records)
    for col in ('year', 'week_num', 'current_viewing_ppl', 'current_viewing_devices',
                'past_4w_avg_ppl', 'past_13w_avg_ppl', 'diff_4w_pct', 'diff_13w_pct'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df
