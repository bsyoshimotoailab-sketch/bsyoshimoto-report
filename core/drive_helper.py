#!/usr/bin/env python3
"""
drive_helper.py
Google Drive サービスアカウント接続ヘルパー
トークン切れなし・永続接続
"""
import io
import json
import os
import tempfile
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
        sa_info = dict(st.secrets['google_service_account'])
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    else:
        # ローカル開発用: service_account.jsonファイルを使用
        sa_path = Path(__file__).parent.parent / 'service_account.json'
        if sa_path.exists():
            creds = service_account.Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)
        else:
            raise FileNotFoundError("service_account.json が見つかりません")

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


def get_latest_csv_files(folder_id: str) -> dict:
    """
    ratingsフォルダから最新のCSVファイルを取得
    Returns: {'e1a': [path1, ...], 'e2a': [path], 'rank': [path]}
    """
    files = list_files_in_folder(folder_id, name_contains='.csv')

    # archiveフォルダのファイルは除外（直下のみ）
    e1a_files  = sorted([f for f in files if 'E1A_HM' in f['name']], key=lambda x: x['name'])
    e2a_files  = sorted([f for f in files if 'E2A_HM' in f['name']], key=lambda x: x['name'])
    rank_files = sorted([f for f in files if 'ランキング' in f['name'] or 'ranking' in f['name'].lower()], key=lambda x: x['name'])

    result = {'e1a': [], 'e2a': [], 'rank': []}

    for f in e1a_files:
        tmp_path = download_to_tempfile(f['id'], suffix='.csv')
        result['e1a'].append({'path': tmp_path, 'name': f['name']})

    for f in e2a_files[:1]:  # E2Aは1本
        tmp_path = download_to_tempfile(f['id'], suffix='.csv')
        result['e2a'].append({'path': tmp_path, 'name': f['name']})

    for f in rank_files[:1]:  # ランキングは1本
        tmp_path = download_to_tempfile(f['id'], suffix='.csv')
        result['rank'].append({'path': tmp_path, 'name': f['name']})

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
