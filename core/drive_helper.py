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
    """フォルダ内のファイル一覧を取得"""
    service = get_drive_service()
    query = f"'{folder_id}' in parents and trashed=false"
    if name_contains:
        query += f" and name contains '{name_contains}'"
    results = service.files().list(
        q=query,
        orderBy='createdTime desc',
        fields='files(id, name, mimeType, createdTime, modifiedTime)',
        pageSize=200,
    ).execute()
    return results.get('files', [])


def download_file(file_id: str) -> bytes:
    """ファイルをバイト列でダウンロード"""
    from googleapiclient.http import MediaIoBaseDownload
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
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


def upload_file(folder_id: str, filename: str, data: bytes, mime_type: str = 'application/octet-stream') -> str:
    """ファイルをフォルダにアップロードしてfile_idを返す"""
    from googleapiclient.http import MediaIoBaseUpload
    service = get_drive_service()

    # 既存ファイルを検索
    existing = list_files_in_folder(folder_id, name_contains=filename)
    existing = [f for f in existing if f['name'] == filename]

    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type)

    if existing:
        # 上書き更新
        result = service.files().update(
            fileId=existing[0]['id'],
            media_body=media,
        ).execute()
    else:
        # 新規作成
        result = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
        ).execute()

    return result.get('id')


def _extract_date(filename: str):
    """ファイル名から YYYYMMDD を抽出して datetime を返す。見つからなければ None"""
    m = re.search(r'(\d{8})', filename)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y%m%d')
        except ValueError:
            return None
    return None


def get_latest_csv_files(folder_id: str) -> dict:
    """
    ratingsフォルダからファイル名のYYYYMMDDを元に最新週のCSVを取得。
    基準：E2A_HM の最新日付を week_end、week_end-6日を week_start とし、
    その範囲のE1A 7本・E2A 1本・ランキング 1本を返す。
    Returns: {'e1a': [{'path':..., 'name':...}, ...], 'e2a': [...], 'rank': [...]}
    """
    files = list_files_in_folder(folder_id, name_contains='.csv')

    e1a_all   = [f for f in files if 'E1A_HM' in f['name']]
    e2a_all   = [f for f in files if 'E2A_HM' in f['name']]
    rank_all  = [f for f in files if 'ランキング' in f['name'] or 'ranking' in f['name'].lower()]

    # ── 最新E2A日付を week_end とする ──
    e2a_dated = [(f, _extract_date(f['name'])) for f in e2a_all]
    e2a_dated = [(f, d) for f, d in e2a_dated if d is not None]
    if not e2a_dated:
        raise ValueError("E2A_HM CSVがDriveフォルダに見つかりません。")
    e2a_dated.sort(key=lambda x: x[1], reverse=True)
    week_end   = e2a_dated[0][1]
    week_start = week_end - timedelta(days=6)

    # ── E1A: week_start〜week_end の7日分 ──
    e1a_in_range = [
        f for f in e1a_all
        if _extract_date(f['name']) is not None
        and week_start <= _extract_date(f['name']) <= week_end
    ]
    if len(e1a_in_range) != 7:
        needed     = [(week_start + timedelta(days=i)).strftime('%Y%m%d') for i in range(7)]
        found_names = [f['name'] for f in e1a_in_range]
        raise ValueError(
            f"E1Aファイルが7本揃っていません（{len(e1a_in_range)}本）。\n"
            f"必要な日付: {', '.join(needed)}\n"
            f"見つかったファイル: {', '.join(found_names) if found_names else 'なし'}"
        )
    e1a_in_range.sort(key=lambda f: _extract_date(f['name']))

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

    result = {'e1a': [], 'e2a': [], 'rank': []}

    for f in e1a_in_range:
        tmp_path = download_to_tempfile(f['id'], suffix='.csv')
        result['e1a'].append({'path': tmp_path, 'name': f['name']})

    tmp_path = download_to_tempfile(e2a_match[0]['id'], suffix='.csv')
    result['e2a'].append({'path': tmp_path, 'name': e2a_match[0]['name']})

    tmp_path = download_to_tempfile(rank_match[0]['id'], suffix='.csv')
    result['rank'].append({'path': tmp_path, 'name': rank_match[0]['name']})

    return result


def get_excel_file(folder_id: str, filename: str = '月間_宣伝強化番組_管理リスト.xlsx') -> str:
    """番宣Excelファイルをダウンロードして一時パスを返す"""
    service = get_drive_service()
    # フォルダ全体を再帰検索
    query = f"name='{filename}' and trashed=false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    if not files:
        return None
    tmp_path = download_to_tempfile(files[0]['id'], suffix='.xlsx')
    return tmp_path


def save_weekly_summary(folder_id: str, week_num: int, summary: dict):
    """週次サマリーをDriveのsummariesフォルダに保存"""
    data = json.dumps(summary, ensure_ascii=False, indent=2).encode('utf-8')
    upload_file(folder_id, f'week_{week_num:02d}_summary.json', data, 'application/json')


def load_all_summaries(folder_id: str) -> list:
    """全週次サマリーを読み込む"""
    files = list_files_in_folder(folder_id, name_contains='_summary.json')
    summaries = []
    for f in sorted(files, key=lambda x: x['name']):
        try:
            data = download_file(f['id'])
            summaries.append(json.loads(data.decode('utf-8')))
        except Exception:
            continue
    return summaries
