#!/usr/bin/env python3
"""
history_store.py
Drive上の番組履歴・番宣履歴・PDFの保存と読み込み

フォルダ構成（DRIVE_FOLDER_ID 直下に自動作成）:
BSよしもと_視聴率レポート保管庫/
  01_週次レポートPDF/
  02_番宣効果検証PDF/
  03_クール総括PDF/
  04_週次サマリーJSON/
  05_番組別履歴/
  06_番宣履歴/
  99_過去レポート取り込み/
"""
import io
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


# ── フォルダ取得・作成 ────────────────────────────────

def get_or_create_subfolder(parent_id: str, name: str) -> str:
    """parent_id 直下に name フォルダを取得または作成してIDを返す"""
    cache_key = f'{parent_id}/{name}'
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    from core.drive_helper import get_drive_service
    service = get_drive_service()
    q = (f"'{parent_id}' in parents and name='{name}' "
         f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = service.files().list(q=q, fields='files(id)').execute()
    files = res.get('files', [])
    if files:
        fid = files[0]['id']
    else:
        meta = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }
        fid = service.files().create(body=meta, fields='id').execute()['id']

    _folder_cache[cache_key] = fid
    return fid


def get_archive_root(root_id: str) -> str:
    """BSよしもと_視聴率レポート保管庫 フォルダのIDを返す（なければ作成）"""
    return get_or_create_subfolder(root_id, ARCHIVE_ROOT)


def get_archive_folder(root_id: str, key: str) -> str:
    """ARCHIVE_FOLDERS[key] に対応するフォルダのIDを返す"""
    archive_id = get_archive_root(root_id)
    name = ARCHIVE_FOLDERS[key]
    return get_or_create_subfolder(archive_id, name)


def _action_label(action: str) -> str:
    return '上書き保存' if action == 'updated' else '新規保存'


# ── JSON 保存・読み込み ──────────────────────────────

def save_json(folder_id: str, filename: str, data) -> dict:
    """JSONをDriveフォルダに保存。Returns: {'id', 'action'}"""
    from core.drive_helper import upload_file
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    return upload_file(folder_id, filename, payload, 'application/json')


def load_json(folder_id: str, filename: str):
    from core.drive_helper import list_files_in_folder, download_file
    exact = [f for f in list_files_in_folder(folder_id) if f['name'] == filename]
    if not exact:
        return None
    return json.loads(download_file(exact[0]['id']).decode('utf-8'))


# ── CSV 追記・更新 ────────────────────────────────────

def update_csv(folder_id: str, filename: str, new_rows: list,
               key_cols: list = None) -> dict:
    """
    既存CSVにnew_rowsを追記し同キーの行は上書きして保存。
    Returns: {'id', 'action'} または None（new_rows が空の場合）
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
        cols = [c for c in key_cols if c in existing_df.columns and c in new_df.columns]
        if cols:
            def _key(df_):
                return df_[cols].astype(str).apply('|'.join, axis=1)
            existing_df = existing_df[~_key(existing_df).isin(set(_key(new_df)))]
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
        return pd.read_csv(io.BytesIO(download_file(exact[0]['id'])), dtype=str)
    except Exception:
        return None


# ── 番組別週次実績 ────────────────────────────────────

def save_program_weekly(root_id: str, year: int, week_num: int,
                        records: list) -> dict:
    """
    05_番組別履歴/ にJSONとCSVを保存する。
    Returns: {'json_file', 'json_action', 'csv_action', 'records'}
    """
    folder_id = get_archive_folder(root_id, 'program')
    json_name = f'program_weekly_{year}_W{week_num:02d}.json'

    jr = save_json(folder_id, json_name, {
        'year': year, 'week_num': week_num, 'programs': records,
    })
    cr = update_csv(folder_id, 'program_history_all.csv', records,
                    key_cols=['year', 'week_num', 'normalized_title'])

    return {
        'json_file':   json_name,
        'json_action': _action_label(jr.get('action', 'created')),
        'csv_action':  _action_label(cr.get('action', 'updated')) if cr else '—',
        'records':     len(records),
    }


def load_program_history_df(root_id: str):
    """05_番組別履歴/program_history_all.csv を DataFrame で返す（なければ空DF）"""
    import pandas as pd
    try:
        folder_id = get_archive_folder(root_id, 'program')
    except Exception:
        return pd.DataFrame()
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
    06_番宣履歴/ にJSONとCSVを保存する。
    Returns: {'json_file', 'json_action', 'csv_action', 'records'}
    """
    folder_id = get_archive_folder(root_id, 'promo')
    json_name = f'promo_{year}_W{week_num:02d}.json'

    jr = save_json(folder_id, json_name, {
        'year': year, 'week_num': week_num, 'items': records,
    })
    cr = update_csv(folder_id, 'promo_history_all.csv', records,
                    key_cols=['year', 'week_num', 'normalized_title'])

    return {
        'json_file':   json_name,
        'json_action': _action_label(jr.get('action', 'created')),
        'csv_action':  _action_label(cr.get('action', 'updated')) if cr else '—',
        'records':     len(records),
    }


def load_promo_history_df(root_id: str):
    """06_番宣履歴/promo_history_all.csv を DataFrame で返す（なければ空DF）"""
    import pandas as pd
    try:
        folder_id = get_archive_folder(root_id, 'promo')
    except Exception:
        return pd.DataFrame()
    df = load_csv(folder_id, 'promo_history_all.csv')
    if df is None or df.empty:
        return pd.DataFrame()
    for col in ('year', 'week_num', 'current_viewing_ppl', 'current_viewing_devices',
                'past_4w_avg_ppl', 'past_13w_avg_ppl', 'diff_4w_pct', 'diff_13w_pct'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


# ── PDF 保存 ──────────────────────────────────────────

_PDF_FOLDER_MAP = {
    'weekly': 'weekly_pdf',
    'promo':  'promo_pdf',
    'macro':  'macro_pdf',
}


def save_report_pdf(root_id: str, report_type: str,
                    filename: str, pdf_bytes: bytes) -> dict:
    """
    reports/{type}/ に PDF を保存。
    report_type: 'weekly' | 'promo' | 'macro'
    Returns: {'id', 'action', 'action_label', 'filename'}
    """
    from core.drive_helper import upload_file
    key = _PDF_FOLDER_MAP.get(report_type, 'weekly_pdf')
    folder_id = get_archive_folder(root_id, key)
    result = upload_file(folder_id, filename, pdf_bytes, 'application/pdf')
    result['action_label'] = _action_label(result.get('action', 'created'))
    result['filename'] = filename
    return result


# ── 過去レポートPDF一括取り込み ────────────────────────

def save_archive_pdfs(root_id: str, files: list) -> list:
    """
    99_過去レポート取り込み/ に PDF を保存する。
    files: [{'name': str, 'data': bytes}, ...]
    Returns: [{'filename', 'action_label'}, ...]
    """
    from core.drive_helper import upload_file
    folder_id = get_archive_folder(root_id, 'archive')
    results = []
    for f in files:
        try:
            r = upload_file(folder_id, f['name'], f['data'], 'application/pdf')
            results.append({
                'filename':     f['name'],
                'action_label': _action_label(r.get('action', 'created')),
            })
        except Exception as e:
            results.append({'filename': f['name'], 'action_label': f'エラー: {e}'})
    return results
