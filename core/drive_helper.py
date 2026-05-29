#!/usr/bin/env python3
"""
drive_helper.py
Google Drive サービスアカウント接続ヘルパー
トークン切れなし・永続接続
"""
import io
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    import streamlit as st
    IN_STREAMLIT = True
except ImportError:
    IN_STREAMLIT = False


def get_drive_service():
    """サービスアカウントでDriveサービスを取得"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/drive.file',
    ]

    # Streamlit Secretsから認証情報を取得
    if IN_STREAMLIT and hasattr(st, 'secrets') and 'google_service_account' in st.secrets:
        sa_info = {str(k): str(v) for k, v in st.secrets['google_service_account'].items()}
        # TOMLでエスケープされた "\n" を実際の改行コードに変換
        if 'private_key' in sa_info:
            sa_info['private_key'] = sa_info['private_key'].replace('\\n', '\n')
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    else:
        # ローカル開発用: service_account.jsonファイルを使用
        sa_path = Path(__file__).parent.parent / 'service_account.json'
        if sa_path.exists():
            creds = service_account.Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)
        else:
            raise FileNotFoundError(
                "認証情報が見つかりません。Streamlit SecretsにGoogleサービスアカウント情報を設定してください。"
            )

    return build('drive', 'v3', credentials=creds)


def list_files_in_folder(folder_id: str, name_contains: str = None) -> list:
    """フォルダ内のファイル一覧を取得（共有ドライブ対応）"""
    service = get_drive_service()
    query = f"'{folder_id}' in parents and trashed=false"
    if name_contains:
        query += f" and name contains '{name_contains}'"
    results = service.files().list(
        q=query,
        orderBy='createdTime desc',
        fields='files(id, name, mimeType, createdTime, modifiedTime)',
        pageSize=200,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return results.get('files', [])


def download_file(file_id: str) -> bytes:
    """ファイルをバイト列でダウンロード（共有ドライブ対応）"""
    from googleapiclient.http import MediaIoBaseDownload
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()


def download_to_tempfile(file_id: str, suffix: str = '.csv') -> str:
    """ファイルを一時ファイルにダウンロードしてパスを返す"""
    data = download_file(file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return tmp.name



def find_archive_folders(folder_id: str) -> list:
    """ratingsフォルダ直下のarchive系サブフォルダを返す（共有ドライブ対応）"""
    ARCHIVE_NAMES = {'archive', 'Archive', 'ARCHIVE', 'Ratings-archive', 'ratings-archive'}
    items = list_files_in_folder(folder_id)
    return [f for f in items
            if f['mimeType'] == 'application/vnd.google-apps.folder'
            and f['name'] in ARCHIVE_NAMES]


def list_files_recursive(folder_id: str, max_depth: int = 2) -> list:
    """フォルダ内の非フォルダファイルを再帰的に取得"""
    items = list_files_in_folder(folder_id)
    result = [f for f in items if f['mimeType'] != 'application/vnd.google-apps.folder']
    if max_depth > 0:
        for sf in [f for f in items if f['mimeType'] == 'application/vnd.google-apps.folder']:
            result.extend(list_files_recursive(sf['id'], max_depth - 1))
    return result


def get_all_archive_csvs(folder_id: str) -> dict:
    """
    ratingsフォルダおよびarchive/Ratings-archiveサブフォルダから全CSVを収集して分類する。

    Returns: {
        'e2a':  [{'id', 'name', 'date'}, ...],
        'e1a':  [{'id', 'name', 'date'}, ...],
        'rank': [{'id', 'name', 'date'}, ...],
    }
    """
    all_files = []

    direct = list_files_in_folder(folder_id)
    all_files.extend(direct)

    for af in find_archive_folders(folder_id):
        all_files.extend(list_files_recursive(af['id']))

    e2a, e1a, rank = [], [], []
    seen = set()
    for f in all_files:
        if f['id'] in seen:
            continue
        seen.add(f['id'])
        if not f['name'].endswith('.csv'):
            continue
        d = _extract_date(f['name'])
        entry = {'id': f['id'], 'name': f['name'], 'date': d}
        if 'E2A_HM' in f['name']:
            e2a.append(entry)
        elif 'E1A_HM' in f['name']:
            e1a.append(entry)
        elif 'ランキング' in f['name'] or 'ranking' in f['name'].lower():
            rank.append(entry)

    return {'e2a': e2a, 'e1a': e1a, 'rank': rank}


def _extract_date(filename: str):
    """ファイル名から YYYYMMDD を抽出して datetime.date を返す。見つからなければ None"""
    m = re.search(r'(\d{8})', filename)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y%m%d').date()
        except ValueError:
            return None
    return None


def get_latest_csv_files(folder_id: str) -> dict:
    """
    ratingsフォルダからファイル名のYYYYMMDDを元に最新週のCSVを取得。
    基準：E2A_HM の最新日付を week_end、week_end-6日を week_start とし、
    その範囲のE1A（5本以上）・E2A 1本・ランキング 1本を返す。

    Returns: {
        'e1a':       [{'path':..., 'name':...}, ...],
        'e2a':       [{'path':..., 'name':...}],
        'rank':      [{'path':..., 'name':...}],
        'warnings':  ['E1Aは7本中6本で生成します。不足: 20260525'],
        'week_start': 'YYYYMMDD',
        'week_end':   'YYYYMMDD',
    }
    """
    files = list_files_in_folder(folder_id, name_contains='.csv')

    e1a_all  = [f for f in files if 'E1A_HM' in f['name']]
    e2a_all  = [f for f in files if 'E2A_HM' in f['name']]
    rank_all = [f for f in files if 'ランキング' in f['name'] or 'ranking' in f['name'].lower()]

    # ── 最新E2A日付を week_end とする ──
    e2a_dated = [(f, _extract_date(f['name'])) for f in e2a_all]
    e2a_dated = [(f, d) for f, d in e2a_dated if d is not None]
    if not e2a_dated:
        raise ValueError("E2A_HM CSVがDriveフォルダに見つかりません。")
    e2a_dated.sort(key=lambda x: x[1], reverse=True)
    week_end   = e2a_dated[0][1]
    week_start = week_end - timedelta(days=6)

    # ── E1A: week_start〜week_end の範囲で取得（5本未満なら停止、5〜6本はwarning） ──
    e1a_in_range = [
        f for f in e1a_all
        if _extract_date(f['name']) is not None
        and week_start <= _extract_date(f['name']) <= week_end
    ]
    e1a_in_range.sort(key=lambda f: _extract_date(f['name']))

    warnings = []
    if len(e1a_in_range) < 5:
        needed      = [(week_start + timedelta(days=i)).strftime('%Y%m%d') for i in range(7)]
        found_names = [f['name'] for f in e1a_in_range]
        raise ValueError(
            f"E1Aファイルが不足しています（{len(e1a_in_range)}本）。5本以上必要です。\n"
            f"必要な日付: {', '.join(needed)}\n"
            f"見つかったファイル: {', '.join(found_names) if found_names else 'なし'}"
        )
    if len(e1a_in_range) < 7:
        all_dates   = {(week_start + timedelta(days=i)).strftime('%Y%m%d') for i in range(7)}
        found_dates = {_extract_date(f['name']).strftime('%Y%m%d') for f in e1a_in_range}
        missing     = sorted(all_dates - found_dates)
        warnings.append(
            f"E1Aは7本中{len(e1a_in_range)}本で生成します。不足: {', '.join(missing)}"
        )

    # ── E2A: week_end と同日付の1本 ──
    e2a_match = [f for f, d in e2a_dated if d == week_end]
    if not e2a_match:
        raise ValueError(f"E2A_HM の {week_end.strftime('%Y%m%d')} が見つかりません。")

    # ── ランキング: week_end と同日付の1本 ──
    rank_match = [
        f for f in rank_all
        if _extract_date(f['name']) == week_end
    ]
    if not rank_match:
        raise ValueError(f"ランキングCSVの {week_end.strftime('%Y%m%d')} が見つかりません。")

    result = {
        'e1a':        [],
        'e2a':        [],
        'rank':       [],
        'warnings':   warnings,
        'week_start': week_start.strftime('%Y%m%d'),
        'week_end':   week_end.strftime('%Y%m%d'),
    }

    for f in e1a_in_range:
        tmp_path = download_to_tempfile(f['id'], suffix='.csv')
        result['e1a'].append({'path': tmp_path, 'name': f['name']})

    tmp_path = download_to_tempfile(e2a_match[0]['id'], suffix='.csv')
    result['e2a'].append({'path': tmp_path, 'name': e2a_match[0]['name']})

    tmp_path = download_to_tempfile(rank_match[0]['id'], suffix='.csv')
    result['rank'].append({'path': tmp_path, 'name': rank_match[0]['name']})

    return result


def get_excel_file(folder_id: str) -> dict:
    """
    番宣Excelファイルをキーワード検索でDriveから取得。
    ファイル名に '宣伝'/'番宣'/'強化番組' を含む最新更新ファイルを使用。
    Google スプレッドシート形式にも対応。

    Returns: {'path': tmp_path, 'name': filename} or None
    """
    from googleapiclient.http import MediaIoBaseDownload
    service = get_drive_service()

    SHEETS_MIME = 'application/vnd.google-apps.spreadsheet'
    KEYWORDS = ['宣伝', '番宣', '強化番組']

    # フォルダ内 + キーワード検索（OR 条件）
    kw_clauses = ' or '.join(f"name contains '{kw}'" for kw in KEYWORDS)
    query = f"'{folder_id}' in parents and trashed=false and ({kw_clauses})"
    results = service.files().list(
        q=query,
        orderBy='modifiedTime desc',
        fields='files(id, name, mimeType, modifiedTime)',
        pageSize=20,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get('files', [])

    # xlsx / Google スプレッドシートを優先。どちらでもなければ最初のヒットを使う
    xlsx_mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    preferred = [f for f in files if f['mimeType'] in (xlsx_mime, SHEETS_MIME)]
    target = (preferred or files or [None])[0]
    if target is None:
        return None

    # Google スプレッドシートは export API で xlsx に変換
    if target['mimeType'] == SHEETS_MIME:
        request = service.files().export_media(
            fileId=target['id'],
            mimeType=xlsx_mime,
        )
    else:
        request = service.files().get_media(fileId=target['id'])

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.write(fh.getvalue())
    tmp.close()
    return {'path': tmp.name, 'name': target['name']}



def load_all_summaries(folder_id: str) -> list:
    """
    全週次サマリーを読み込む。
    新形式 summary_YYYY_WXX.json と旧形式 week_XX_summary.json の両方に対応。
    year・week_num 順にソートして返す。
    """
    all_files = list_files_in_folder(folder_id, name_contains='.json')

    new_files = [f for f in all_files if re.match(r'summary_\d{4}_W\d+\.json', f['name'])]
    old_files = [f for f in all_files if re.match(r'week_\d+_summary\.json', f['name'])]

    summaries = []

    for f in sorted(new_files, key=lambda x: x['name']):
        try:
            data = download_file(f['id'])
            summaries.append(json.loads(data.decode('utf-8')))
        except Exception:
            continue

    # 旧形式：新形式に存在しない週だけ取り込む（後方互換）
    existing = {(s.get('year', 0), s.get('week_num', 0)) for s in summaries}
    for f in sorted(old_files, key=lambda x: x['name']):
        try:
            data = download_file(f['id'])
            s = json.loads(data.decode('utf-8'))
            if 'year' not in s:
                s['year'] = 2026  # 旧形式は year 未保存のため 2026 と推定
            if (s.get('year', 0), s.get('week_num', 0)) not in existing:
                summaries.append(s)
        except Exception:
            continue

    summaries.sort(key=lambda s: (s.get('year', 0), s.get('week_num', 0)))
    return summaries
