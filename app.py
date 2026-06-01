"""
app.py
BSよしもと 視聴率レポートシステム
Streamlit Web アプリ
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── パス設定 ──
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'core'))

# ── ページ設定 ──
st.set_page_config(
    page_title='BSよしもと レポートシステム',
    page_icon='📺',
    layout='wide',
    initial_sidebar_state='collapsed',
)

# ── スタイル ──
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #141418; }
  [data-testid="stHeader"] { background: #141418; }
  h1, h2, h3 { color: #f0ede8 !important; }
  .stButton > button {
    background: #f5a623; color: #141418; font-weight: 700;
    border: none; padding: 12px 32px; font-size: 16px;
    border-radius: 4px; width: 100%;
  }
  .stButton > button:hover { background: #e8782a; }
  .stRadio > label { color: #d0ccc8 !important; }
  [data-testid="stFileUploader"] {
    background: #1c1c22; border: 2px dashed #2a2a35; border-radius: 6px;
  }
  .status-box {
    background: #1c1c22; border-left: 4px solid #f5a623;
    padding: 12px 16px; border-radius: 4px; margin: 8px 0;
    color: #d0ccc8; font-size: 13px;
  }
  .error-box {
    background: #2a1c1c; border-left: 4px solid #f87171;
    padding: 12px 16px; border-radius: 4px; margin: 8px 0;
    color: #f0ede8; font-size: 13px;
  }
</style>
""", unsafe_allow_html=True)

# ── ヘッダー ──
st.markdown("""
<div style="background:linear-gradient(135deg,#1c1c22,#141418);border-left:5px solid #f5a623;
     padding:20px 28px;margin-bottom:28px;border-radius:4px;">
  <div style="font-size:10px;letter-spacing:4px;color:#f5a623;margin-bottom:6px;">
    WEEKLY AUDIENCE REPORT SYSTEM
  </div>
  <div style="font-size:28px;font-weight:700;color:#f0ede8;">
    BSよしもと レポートシステム
  </div>
</div>
""", unsafe_allow_html=True)

# ── Drive設定 ──
DRIVE_FOLDER_ID     = '1JIKlOBc42pUTHhHaShInWo_YT_9-GmrJ'
SUMMARIES_FOLDER_ID = st.secrets.get('summaries_folder_id', DRIVE_FOLDER_ID) if hasattr(st, 'secrets') else DRIVE_FOLDER_ID


# ── Drive接続確認 ──
@st.cache_resource
def get_drive():
    try:
        from core.drive_helper import get_drive_service
        return get_drive_service()
    except Exception as e:
        return None

# ── レポートタイプ選択 ──
st.markdown("### 作成するレポートを選択してください")

report_type = st.radio(
    '',
    options=['① 最新週次レポート', '② 番宣効果検証', '③ クール総括マクロ', '④ 過去レポート取り込み（肥後用）'],
    horizontal=True,
    label_visibility='collapsed',
)

st.divider()


def _build_promo_section(promo_result: dict) -> str:
    """番宣効果検証セクションのHTML生成（PDF埋め込み用）"""
    if not promo_result:
        return ''
    matched   = promo_result.get('matched', [])
    unmatched = promo_result.get('unmatched', [])
    sm        = promo_result.get('summary', {})
    if not matched and not unmatched:
        return ''

    JCOLOR = {
        '◎ 効果あり':    '#4ade80',
        '○ やや効果あり': '#86efac',
        '△ 横ばい':      '#fbbf24',
        '× 効果見えず':   '#f87171',
        '判定保留':       '#7a7a8c',
        '今週実績のみ':   '#7a7a8c',
    }

    total   = sm.get('total_promo', len(matched) + len(unmatched))
    effect  = sm.get('effect_found', 0)
    summary_text = (
        f'今週は番宣対象{total}番組のうち{len(matched)}番組で視聴データを確認。'
        f'うち{effect}番組は過去平均を上回った。'
    )

    def _ppl(i):
        return f"{i['viewing_ppl']:,}人" if i.get('viewing_ppl', 0) > 0 else '—'

    def _dev(i):
        return f"{i['viewing_dev']:,}台" if i.get('viewing_dev', 0) > 0 else '—'

    def _past4(i):
        p = i.get('past_4w_avg_ppl') or i.get('past_avg_ppl')
        w = i.get('past_4w_weeks') or i.get('past_weeks', 0)
        if not p:
            return '—'
        return f'{p:,}人<br><small style="color:#7a7a8c;">{w}週平均</small>'

    def _diff4(i):
        cr = i.get('diff_4w_pct') if i.get('diff_4w_pct') is not None else i.get('change_rate')
        if cr is None:
            return '—'
        c = '#4ade80' if cr > 0 else '#f87171'
        return f'<span style="color:{c};font-weight:700;">{cr:+.1f}%</span>'

    matched_rows = ''.join(f'''<tr style="border-bottom:1px solid #2a2a35;">
      <td style="padding:6px 8px;font-size:11px;color:#f0ede8;">{i["program"]}</td>
      <td style="padding:6px 8px;font-size:10px;color:#f5a623;">{i["period"]}</td>
      <td style="padding:6px 8px;font-size:10px;color:#d0ccc8;">{i["spots"]}</td>
      <td style="padding:6px 8px;font-size:10px;color:#d0ccc8;">{i["material"]}</td>
      <td style="text-align:right;padding:6px 8px;font-size:11px;font-weight:700;color:{"#4ade80" if i.get("viewing_ppl",0)>0 else "#7a7a8c"};">{_ppl(i)}</td>
      <td style="text-align:right;padding:6px 8px;font-size:10px;color:#d0ccc8;">{_dev(i)}</td>
      <td style="text-align:right;padding:6px 8px;font-size:10px;color:#d0ccc8;">{_past4(i)}</td>
      <td style="text-align:right;padding:6px 8px;font-size:11px;">{_diff4(i)}</td>
      <td style="padding:6px 8px;font-size:10px;font-weight:700;color:{JCOLOR.get(i.get("judgment",""), "#d0ccc8")};">{i.get("judgment","—")}</td>
    </tr>''' for i in matched[:30])

    unmatched_block = ''
    if unmatched:
        urows = ''.join(f'''<tr style="border-bottom:1px solid #2a2a35;">
          <td style="padding:5px 8px;font-size:11px;color:#f0ede8;">{i["program"]}</td>
          <td style="padding:5px 8px;font-size:10px;color:#f5a623;">{i["period"]}</td>
          <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;">{i["spots"]}</td>
          <td style="padding:5px 8px;font-size:10px;color:#f87171;">CSVに番組が見つかりません</td>
        </tr>''' for i in unmatched[:20])
        unmatched_block = f'''
        <div style="margin-top:18px;">
          <div style="font-size:10px;letter-spacing:3px;color:#f87171;border-bottom:1px solid #2a2a35;padding-bottom:6px;margin-bottom:10px;">要確認リスト（CSV未照合）</div>
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="border-bottom:1px solid #f87171;">
              <th style="text-align:left;padding:5px 8px;color:#d0ccc8;font-size:10px;">番組名</th>
              <th style="text-align:left;padding:5px 8px;color:#d0ccc8;font-size:10px;">番宣期間</th>
              <th style="text-align:left;padding:5px 8px;color:#d0ccc8;font-size:10px;">SPOT</th>
              <th style="text-align:left;padding:5px 8px;color:#d0ccc8;font-size:10px;">備考</th>
            </tr></thead>
            <tbody>{urows}</tbody>
          </table>
        </div>'''

    return f'''
    <div style="background:#1c1c22;border-radius:6px;padding:20px 24px;margin-bottom:24px;border:1px solid #2a2a35;">
      <div style="font-size:10px;letter-spacing:4px;color:#f5a623;border-bottom:1px solid #2a2a35;padding-bottom:8px;margin-bottom:12px;">番宣効果検証</div>
      <div style="font-size:12px;color:#d0ccc8;margin-bottom:14px;padding:8px 12px;background:#141418;border-radius:4px;border-left:3px solid #f5a623;">{summary_text}</div>
      <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="border-bottom:1px solid #f5a623;">
          <th style="text-align:left;padding:6px 8px;color:#d0ccc8;font-size:10px;">番組名</th>
          <th style="text-align:left;padding:6px 8px;color:#d0ccc8;font-size:10px;">番宣期間</th>
          <th style="text-align:left;padding:6px 8px;color:#d0ccc8;font-size:10px;">SPOT</th>
          <th style="text-align:left;padding:6px 8px;color:#d0ccc8;font-size:10px;">素材</th>
          <th style="text-align:right;padding:6px 8px;color:#d0ccc8;font-size:10px;">今週視聴人数</th>
          <th style="text-align:right;padding:6px 8px;color:#d0ccc8;font-size:10px;">視聴機器数</th>
          <th style="text-align:right;padding:6px 8px;color:#d0ccc8;font-size:10px;">比較基準</th>
          <th style="text-align:right;padding:6px 8px;color:#d0ccc8;font-size:10px;">増減</th>
          <th style="text-align:left;padding:6px 8px;color:#d0ccc8;font-size:10px;">判定</th>
        </tr></thead>
        <tbody>{matched_rows}</tbody>
      </table>
      </div>
      {unmatched_block}
    </div>'''


# ════════════════════════════════════════
# ① 週次レポート
# ════════════════════════════════════════
if report_type == '① 最新週次レポート':
    st.markdown("#### 📊 週次レポート生成")
    st.markdown('<div class="status-box">Google Driveから最新CSVを自動取得してPDFレポートを生成します。</div>', unsafe_allow_html=True)

    use_drive = st.checkbox('Google Driveから自動取得する（推奨）', value=True)

    uploaded_e1a  = []
    uploaded_e2a  = None
    uploaded_rank = None

    if not use_drive:
        st.markdown("**CSVファイルをアップロード**（E1A×7本、E2A×1本、ランキング×1本）")
        uploaded_files = st.file_uploader('', type=['csv'], accept_multiple_files=True, key='weekly_csv')
        if uploaded_files:
            uploaded_e1a  = [f for f in uploaded_files if 'E1A' in f.name]
            uploaded_e2a  = next((f for f in uploaded_files if 'E2A' in f.name), None)
            uploaded_rank = next((f for f in uploaded_files if 'ランキング' in f.name or 'ranking' in f.name.lower()), None)
            st.markdown(f'<div class="status-box">E1A: {len(uploaded_e1a)}本 / E2A: {"✅" if uploaded_e2a else "❌"} / ランキング: {"✅" if uploaded_rank else "❌"}</div>', unsafe_allow_html=True)

    if st.button('📄 レポートを生成する', key='gen_weekly'):
        with st.spinner('レポート生成中... 2〜3分かかります'):
            try:
                import tempfile, os
                from core.generate_report import (
                    load_e2a, load_e1a, load_ranking, analyze_e1a, analyze_ranking,
                    analyze_jimoto, detect_week_info, calculate_total_ppl,
                    find_specific_programs, find_ytube_programs, generate_html,
                    save_trend_data,
                )
                from core.charts import generate_all_charts
                from core.embed_charts import embed_charts_into_html
                from core.make_pdf import generate_pdf_from_html_string

                tmpdir = tempfile.mkdtemp()
                e1a_paths, e2a_path, rank_path = [], None, None

                if use_drive:
                    st.info('Google Driveからファイルを取得中...')
                    from core.drive_helper import get_latest_csv_files
                    csv_files = get_latest_csv_files(DRIVE_FOLDER_ID)
                    if not csv_files['e1a'] or not csv_files['e2a'] or not csv_files['rank']:
                        st.error('DriveにCSVが見つかりません。スタッフにアップロードを依頼してください。')
                        st.stop()
                    e1a_paths = [f['path'] for f in csv_files['e1a']]
                    e2a_path  = csv_files['e2a'][0]['path']
                    rank_path = csv_files['rank'][0]['path']
                    file_names = [f['name'] for f in csv_files['e1a']] + [csv_files['e2a'][0]['name'], csv_files['rank'][0]['name']]
                    st.markdown(f'<div class="status-box">取得完了: {", ".join(file_names)}</div>', unsafe_allow_html=True)
                    for w in csv_files.get('warnings', []):
                        st.warning(w)
                else:
                    if not uploaded_e1a or not uploaded_e2a or not uploaded_rank:
                        st.error('全ファイルを選択してください（E1A×7本、E2A×1本、ランキング×1本）')
                        st.stop()
                    for uf in uploaded_e1a:
                        p = os.path.join(tmpdir, uf.name)
                        with open(p, 'wb') as f: f.write(uf.getvalue())
                        e1a_paths.append(p)
                    e2a_path  = os.path.join(tmpdir, uploaded_e2a.name)
                    rank_path = os.path.join(tmpdir, uploaded_rank.name)
                    with open(e2a_path,  'wb') as f: f.write(uploaded_e2a.getvalue())
                    with open(rank_path, 'wb') as f: f.write(uploaded_rank.getvalue())

                st.info('データ分析中...')
                df_e2a    = load_e2a(e2a_path)
                df_e1a    = load_e1a(e1a_paths)
                rank      = load_ranking(rank_path)
                e1a_data  = analyze_e1a(df_e1a)
                rank_data = analyze_ranking(rank)
                jimoto    = analyze_jimoto(df_e2a)
                week_num, week_range = detect_week_info(df_e2a)
                total_ppl, total_count = calculate_total_ppl(df_e2a)
                specific  = find_specific_programs(df_e2a)
                ytube     = find_ytube_programs(df_e2a)

                data = dict(
                    week_num=week_num, week_range=week_range,
                    kpi_avg=rank_data['kpi_avg'], kpi_max=rank_data['kpi_max'],
                    kpi_max_program=rank_data['kpi_max_program'], kpi_max_time=rank_data['kpi_max_time'],
                    yoshi_rank=e1a_data['yoshi_rank'],
                    rival_labels=e1a_data['rival_labels'], rival_data=e1a_data['rival_data'],
                    zone_avgs=e1a_data['zone_avgs'], day_avgs=e1a_data['day_avgs'], heat=e1a_data['heat'],
                    best_day=max(e1a_data['day_avgs'], key=e1a_data['day_avgs'].get) if e1a_data['day_avgs'] else '日',
                    yoshi_avg=e1a_data['yoshi_avg'], jcom_avg=e1a_data['jcom_avg'], jcom_zones=e1a_data['jcom_zones'],
                    top10_yoshi=rank_data['top10_yoshi'], top10_all=rank_data['top10_all'],
                    demos=rank_data['demos'], yoshi_demos=rank_data.get('yoshi_demos', {}), jcom_demos=rank_data.get('jcom_demos', {}),
                    jimoto=jimoto,
                    total_all_ppl=total_ppl, total_program_count=total_count,
                    specific_programs=specific,
                    ytube_data=ytube,
                )

                st.info('グラフ生成中...')
                # trend_data をロード
                trend_json_path = os.path.join(tmpdir, 'trend_data.json')
                try:
                    from core.history_store import load_summaries_from_archive
                    from core.drive_helper import load_all_summaries
                    summaries = load_summaries_from_archive(DRIVE_FOLDER_ID) or load_all_summaries(SUMMARIES_FOLDER_ID)
                    trend_data = [{'week_num':s['week_num'],'week_range':s['week_range'],
                                   'kpi_avg':s['kpi_avg'],'kpi_max':s['kpi_max']} for s in summaries]
                    trend_data.append({'week_num':week_num,'week_range':week_range,
                                       'kpi_avg':rank_data['kpi_avg'],'kpi_max':rank_data['kpi_max']})
                    with open(trend_json_path, 'w', encoding='utf-8') as f:
                        json.dump(trend_data, f, ensure_ascii=False)
                except Exception:
                    trend_data = []

                from core.charts import generate_all_charts as _gen_charts
                chart_imgs = _gen_charts(data, trend_data)

                st.info('HTML生成中...')
                template_path = str(ROOT / 'template.html')
                prev = None
                if trend_data and len(trend_data) >= 2:
                    prev = {'kpi_avg': trend_data[-2]['kpi_avg']}
                html = generate_html(data, template_path, prev)
                html = embed_charts_into_html(html, chart_imgs)

                st.info('PDF変換中...')
                pdf_bytes = generate_pdf_from_html_string(html)

                # ── ダウンロード用パッケージ生成 ──
                from core.drive_helper import _extract_date
                from datetime import timedelta as _td
                from core.program_history import build_program_weekly
                from core.export_package import build_weekly_zip

                _we = _extract_date(csv_files['e2a'][0]['name']) if use_drive else None
                if isinstance(_we, datetime): _we = _we.date()
                _ws   = (_we - _td(days=6)) if _we else None
                _year = _we.year if _we else datetime.now().year

                summary = {
                    'year':                _year,
                    'week_num':            week_num,
                    'week_start':          _ws.strftime('%Y/%m/%d') if _ws else '',
                    'week_end':            _we.strftime('%Y/%m/%d') if _we else '',
                    'week_range':          week_range,
                    'kpi_avg':             rank_data['kpi_avg'],
                    'kpi_max':             rank_data['kpi_max'],
                    'kpi_max_program':     rank_data['kpi_max_program'],
                    'kpi_max_time':        rank_data['kpi_max_time'],
                    'total_all_ppl':       total_ppl,
                    'total_program_count': total_count,
                    'top10_yoshi':         rank_data['top10_yoshi'],
                    'day_avgs':            e1a_data['day_avgs'],
                    'zone_avgs':           e1a_data['zone_avgs'],
                    'generated_at':        datetime.now().isoformat(),
                }

                prog_records = []
                try:
                    prog_records = build_program_weekly(df_e2a, _year, week_num, _ws, _we)
                except Exception:
                    pass

                zip_bytes = build_weekly_zip(pdf_bytes, _year, week_num, summary, prog_records)

                st.success(f'✅ WEEK {week_num} レポート生成完了！Drive自動保存は行いません。')
                st.info('📁 生成後、Google DriveのBSよしもと_視聴率レポート保管庫へ手動アップロードしてください。')
                _col1, _col2 = st.columns(2)
                with _col1:
                    st.download_button(
                        label='📥 PDFをダウンロード',
                        data=pdf_bytes,
                        file_name=f'bs_report_{_year}_W{week_num:02d}.pdf',
                        mime='application/pdf',
                        key='dl_weekly_pdf',
                    )
                with _col2:
                    st.download_button(
                        label='📦 Drive登録用ZIPをダウンロード',
                        data=zip_bytes,
                        file_name=f'drive_upload_{_year}_W{week_num:02d}.zip',
                        mime='application/zip',
                        key='dl_weekly_zip',
                    )

            except Exception as e:
                st.markdown(f'<div class="error-box">❌ エラーが発生しました: {e}</div>', unsafe_allow_html=True)
                import traceback
                st.code(traceback.format_exc())


# ════════════════════════════════════════
# ② 番宣効果検証（専用レポート）
# ════════════════════════════════════════
elif report_type == '② 番宣効果検証':
    st.markdown("#### 📋 番宣効果判定レポート")
    st.markdown(
        '<div class="status-box">'
        '番宣対象番組の今週視聴データと過去履歴を照合して効果を判定します。'
        '週次レポートとは独立した「番宣効果判定レポート」を生成します。'
        '</div>',
        unsafe_allow_html=True,
    )

    use_drive_excel = st.checkbox('番宣ExcelもDriveから自動取得する（推奨）', value=True, key='promo_excel_drive')
    excel_upload = None
    if not use_drive_excel:
        excel_upload = st.file_uploader('月間_宣伝強化番組_管理リスト.xlsx', type=['xlsx'], key='promo_excel')

    # ── 番組履歴ステータス（事前確認） ──────────────────────────
    st.markdown("---")
    st.markdown("**📦 番組履歴データ確認**（過去4週・13週平均の比較に使用）")
    try:
        from core.promo_effect_report import load_program_history as _lph
        _pre_df, _pre_dbg = _lph(DRIVE_FOLDER_ID)
        if _pre_df.empty:
            st.error(
                f'⛔ 番組別履歴データが読み込めません。\n\n'
                f'原因: {_pre_dbg.get("error", "不明")}\n\n'
                '**PDF生成前に「④ 過去レポート取り込み（肥後用）」で履歴データを再構築してください。**\n'
                '再構築後のZIPをDriveの `05_番組別履歴/` へアップロードすることで照合が可能になります。'
            )
            _pre_hist_ok = False
        else:
            st.success(
                f'✅ 履歴データ読込成功: {_pre_dbg["row_count"]}行 / '
                f'{_pre_dbg["week_count"]}週分 / {_pre_dbg["program_count"]}番組'
            )
            if _pre_dbg['weeks']:
                st.caption(f'含まれる週: {", ".join(_pre_dbg["weeks"])}')
            _pre_hist_ok = True
    except Exception as _pre_ex:
        st.warning(f'⚠️ 履歴データ確認中にエラー: {_pre_ex}')
        _pre_hist_ok = False
    st.markdown("---")

    if st.button('📋 番宣効果判定レポートを生成', key='gen_promo'):
        with st.spinner('番宣効果判定レポート生成中...'):
            try:
                import tempfile
                import pandas as pd
                from datetime import timedelta
                from core.generate_report import load_e2a, detect_week_info
                from core.drive_helper import (
                    list_files_in_folder, _extract_date,
                    download_to_tempfile, get_excel_file,
                )
                from core.make_pdf import generate_pdf_from_html_string
                from core.promo_effect_report import (
                    load_program_history,
                    build_promo_effect_items,
                    build_promo_effect_html,
                )
                from core.export_package import build_promo_zip

                tmpdir = tempfile.mkdtemp()

                # ── E2A CSV 取得（E1A・ランキングは不要）──────────
                st.info('Google Drive から最新 E2A CSV を取得中...')
                _all_csv = list_files_in_folder(DRIVE_FOLDER_ID, name_contains='.csv')
                _e2a_candidates = [
                    (f, _extract_date(f['name']))
                    for f in _all_csv if 'E2A_HM' in f['name']
                ]
                _e2a_candidates = [(f, d) for f, d in _e2a_candidates if d is not None]
                if not _e2a_candidates:
                    st.error('⛔ DriveフォルダにE2A_HM CSVが見つかりません。スタッフにアップロードを依頼してください。')
                    st.stop()
                _e2a_candidates.sort(key=lambda x: x[1], reverse=True)
                _e2a_file, we = _e2a_candidates[0]
                e2a_path = download_to_tempfile(_e2a_file['id'], suffix='.csv')
                ws = we - timedelta(days=6)
                st.markdown(
                    f'<div class="status-box">E2A取得: {_e2a_file["name"]} '
                    f'（対象週: {ws.month}/{ws.day}〜{we.month}/{we.day}）</div>',
                    unsafe_allow_html=True,
                )

                # ── 番宣 Excel 取得 ────────────────────────────────
                excel_path = None
                if use_drive_excel:
                    st.info('Drive から番宣 Excel を取得中...')
                    try:
                        excel_info = get_excel_file(DRIVE_FOLDER_ID)
                    except Exception as _ex_err:
                        excel_info = None
                        st.warning(f'⚠️ Drive Excel 取得エラー: {_ex_err}')
                    if excel_info:
                        excel_path = excel_info['path']
                        st.success(f'使用 Excel: {excel_info["name"]}')
                    else:
                        st.warning('⚠️ Drive に番宣 Excel が見つかりません。手動アップロードしてください。')
                        _fallback = st.file_uploader(
                            '月間_宣伝強化番組_管理リスト.xlsx（手動）',
                            type=['xlsx'], key='promo_excel_fallback',
                        )
                        if _fallback:
                            import os
                            _p = os.path.join(tmpdir, 'promo_manual.xlsx')
                            with open(_p, 'wb') as _fh:
                                _fh.write(_fallback.getvalue())
                            excel_path = _p
                        else:
                            st.stop()
                elif excel_upload:
                    import os
                    _p = os.path.join(tmpdir, 'promo.xlsx')
                    with open(_p, 'wb') as _fh:
                        _fh.write(excel_upload.getvalue())
                    excel_path = _p
                else:
                    st.error('番宣 Excel をアップロードしてください。')
                    st.stop()

                # ── E2A 読み込み ──────────────────────────────────
                st.info('E2A CSV を読み込み中...')
                df_e2a = load_e2a(e2a_path)
                week_num, week_range = detect_week_info(df_e2a)
                year_val = we.year

                # ── 番組履歴読み込み（詳細ステータス表示）────────
                st.info('番組別履歴データを読み込み中...')
                prog_hist_df, hist_dbg = load_program_history(DRIVE_FOLDER_ID)

                st.markdown("**履歴読込ステータス:**")
                _hcol1, _hcol2, _hcol3, _hcol4 = st.columns(4)
                _hcol1.metric('フォルダ確認', '✅' if hist_dbg['folder_found'] else '❌')
                _hcol2.metric('データ行数',   hist_dbg['row_count'])
                _hcol3.metric('週数',         hist_dbg['week_count'])
                _hcol4.metric('番組数',       hist_dbg['program_count'])
                if hist_dbg['weeks']:
                    st.caption(f'履歴週: {", ".join(hist_dbg["weeks"])}')
                if hist_dbg['error']:
                    st.markdown(
                        f'<div class="error-box">⛔ 履歴読込エラー: {hist_dbg["error"]}</div>',
                        unsafe_allow_html=True,
                    )

                # ── 履歴なし → PDF生成を停止 ──────────────────────
                if prog_hist_df.empty:
                    st.markdown(
                        '<div class="error-box" style="font-size:15px;padding:20px;">'
                        '⛔ <strong>履歴データ未読込のため、番宣効果判定レポートは生成できません。</strong><br><br>'
                        '「④ 過去レポート取り込み（肥後用）」で過去 CSV から履歴を再構築し、'
                        'ZIPを Drive の <code>05_番組別履歴/</code> へアップロードしてください。'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    st.stop()

                # ── 番宣効果照合・判定 ────────────────────────────
                st.info('番宣 Excel と視聴データを照合・判定中...')
                try:
                    promo_result = build_promo_effect_items(
                        df_e2a, excel_path, prog_hist_df,
                        week_start=ws, week_end=we,
                        cur_year=year_val, cur_week_num=week_num,
                    )
                except ValueError as _ve:
                    st.error(str(_ve))
                    st.stop()

                sm          = promo_result['summary']
                all_items   = promo_result['all_items']
                effect      = promo_result['effect']
                no_effect   = promo_result['no_effect']
                pending     = promo_result['pending']
                needs_check = promo_result['needs_check']
                hist_debug  = promo_result['hist_debug']

                # ── Streamlit 結果表示 ────────────────────────────
                st.markdown("---")
                st.markdown("**📊 効果判定サマリー**")
                _mc1, _mc2, _mc3, _mc4, _mc5, _mc6, _mc7 = st.columns(7)
                _mc1.metric('番宣対象',     f"{sm['total_promo']}件")
                _mc2.metric('CSV照合成功',  f"{sm['csv_matched']}件")
                _mc3.metric('履歴比較成功', f"{sm['hist_compared']}件")
                _mc4.metric('効果あり',     f"{sm['effect_found']}件")
                _mc5.metric('効果見えず',   f"{sm['no_effect']}件")
                _mc6.metric('判定保留',     f"{sm['pending']}件")
                _mc7.metric('要確認',       f"{sm['needs_check']}件")

                # 全件テーブル
                if all_items:
                    st.markdown("**全件 効果判定テーブル**")
                    _rows_disp = []
                    for _i in all_items:
                        _d4  = _i.get('diff_4w_pct')
                        _d13 = _i.get('diff_13w_pct')
                        _rows_disp.append({
                            '番組名':        _i['program'],
                            '番宣期間':      _i['period'],
                            'SPOT':          _i['spots'],
                            '今週視聴人数':  f"{_i['viewing_ppl']:,}人"       if _i.get('viewing_ppl')       else '—',
                            '過去4週平均':   f"{_i['past_4w_avg_ppl']:,}人"   if _i.get('past_4w_avg_ppl')   else '—',
                            '4週比':         f'{_d4:+.1f}%'                   if _d4  is not None            else '—',
                            '過去13週平均':  f"{_i['past_13w_avg_ppl']:,}人"  if _i.get('past_13w_avg_ppl')  else '—',
                            '13週比':        f'{_d13:+.1f}%'                  if _d13 is not None            else '—',
                            '判定':          _i['judgment'],
                            'コメント':      (_i.get('comment') or '')[:60],
                            '照合':          _i['match_type'],
                        })
                    st.dataframe(pd.DataFrame(_rows_disp), use_container_width=True)

                # 候補一致の警告
                _cands = [_i for _i in all_items if _i.get('match_type') == '候補一致']
                if _cands:
                    st.warning(f'⚠️ 候補一致が {len(_cands)} 件あります。番組名の表記ゆれを確認してください。')

                # 要確認：類似候補表示
                if needs_check:
                    with st.expander(f'⚠️ 要確認リスト（{len(needs_check)}件）— 番組名不一致・期間未設定など'):
                        _ck_rows = []
                        for _i in needs_check:
                            _sim = ', '.join(_i.get('similar_titles', [])[:3]) or '（候補なし）'
                            _ck_rows.append({
                                '番組名':    _i['program'],
                                '番宣期間':  _i['period'],
                                'SPOT':      _i['spots'],
                                '理由':      _i['comment'][:60],
                                '類似候補':  _sim,
                            })
                        st.dataframe(pd.DataFrame(_ck_rows), use_container_width=True)

                # 番組別 履歴照合デバッグ
                with st.expander('🔍 番組別 履歴照合デバッグ情報（過去平均が空の原因確認）'):
                    _dbg_rows = []
                    for _prog, _di in hist_debug.items():
                        _dbg_rows.append({
                            '番組名（Excel）': _prog,
                            '正規化後':        _di.get('正規化後', ''),
                            '4週平均':         _di.get('4w', ''),
                            '13週平均':        _di.get('13w', ''),
                        })
                    if _dbg_rows:
                        st.dataframe(pd.DataFrame(_dbg_rows), use_container_width=True)
                    else:
                        st.info('照合対象番組がありませんでした。')

                # ── 専用PDF生成 ───────────────────────────────────
                st.info('番宣効果判定レポート PDF 生成中...')
                promo_html = build_promo_effect_html(
                    promo_result, week_range, week_num, year_val,
                )
                pdf_bytes = generate_pdf_from_html_string(promo_html)

                # ── Drive 登録用 ZIP ──────────────────────────────
                _ws_str = ws.strftime('%Y/%m/%d') if ws else ''
                _we_str = we.strftime('%Y/%m/%d') if we else ''
                _promo_records = [{
                    'year':                    year_val,
                    'week_num':                week_num,
                    'week_start':              _ws_str,
                    'week_end':                _we_str,
                    'program':                 _it['program'],
                    'normalized_title':        _it.get('normalized_title', ''),
                    'promo_period':            _it['period'],
                    'spots':                   _it['spots'],
                    'material':                _it.get('material', '—'),
                    'current_viewing_ppl':     _it.get('viewing_ppl', 0),
                    'current_viewing_devices': _it.get('viewing_dev', 0),
                    'past_4w_avg_ppl':         _it.get('past_4w_avg_ppl'),
                    'past_13w_avg_ppl':        _it.get('past_13w_avg_ppl'),
                    'diff_4w_pct':             _it.get('diff_4w_pct'),
                    'diff_13w_pct':            _it.get('diff_13w_pct'),
                    'judgment':                _it.get('judgment'),
                    'comment':                 _it.get('comment'),
                    'match_type':              _it.get('match_type'),
                } for _it in all_items]
                zip_bytes_p = build_promo_zip(pdf_bytes, year_val, week_num, _promo_records)

                st.success(f'✅ {year_val}年 W{week_num:02d} 番宣効果判定レポート生成完了！')
                st.info('📁 生成後、Google Drive の BSよしもと_視聴率レポート保管庫へ手動アップロードしてください。')
                _pcol1, _pcol2 = st.columns(2)
                with _pcol1:
                    st.download_button(
                        label='📥 番宣効果判定レポート PDF をダウンロード',
                        data=pdf_bytes,
                        file_name=f'promo_effect_report_{year_val}_W{week_num:02d}.pdf',
                        mime='application/pdf',
                        key='dl_promo_pdf',
                    )
                with _pcol2:
                    st.download_button(
                        label='📦 Drive 登録用 ZIP をダウンロード',
                        data=zip_bytes_p,
                        file_name=f'drive_upload_promo_{year_val}_W{week_num:02d}.zip',
                        mime='application/zip',
                        key='dl_promo_zip',
                    )

            except Exception as _e:
                st.markdown(f'<div class="error-box">❌ エラー: {_e}</div>', unsafe_allow_html=True)
                import traceback
                st.code(traceback.format_exc())


# ════════════════════════════════════════
# ③ クール総括マクロ
# ════════════════════════════════════════
elif report_type == '③ クール総括マクロ':
    st.markdown("#### 📈 クール総括マクロレポート")
    st.markdown('<div class="status-box">蓄積された週次データからクール（四半期）の総括レポートを生成します。</div>', unsafe_allow_html=True)

    _q_labels = {1:'第1クール（W01〜W13）',2:'第2クール（W14〜W26）',
                 3:'第3クール（W27〜W39）',4:'第4クール（W40〜W53）'}
    col_y, col_q = st.columns(2)
    with col_y:
        macro_year = st.number_input('対象年', min_value=2024, max_value=2030, value=datetime.now().year)
    with col_q:
        quarter = st.selectbox('対象クール', [1, 2, 3, 4], format_func=lambda q: _q_labels[q])

    if st.button('📈 クール総括レポートを生成', key='gen_macro'):
        with st.spinner('マクロレポート生成中...'):
            try:
                from core.drive_helper import load_all_summaries
                from core.macro_report import generate_macro_html, get_quarter
                from core.make_pdf import generate_pdf_from_html_string
                from core.history_store import load_summaries_from_archive, load_promo_history_df

                # 保管庫の04_週次サマリーJSON/から読み込み。なければ旧フォルダへフォールバック
                all_summaries = load_summaries_from_archive(DRIVE_FOLDER_ID) or load_all_summaries(SUMMARIES_FOLDER_ID)

                # manual_weekly_summary_from_pdf.csv をマージ（JSONに無い週を補完）
                try:
                    from core.history_store import load_manual_summary_df
                    _manual_df = load_manual_summary_df(DRIVE_FOLDER_ID)
                    if not _manual_df.empty:
                        _existing_keys = {(s.get('year', 0), s.get('week_num', 0)) for s in all_summaries}
                        _added = 0
                        for _, _row in _manual_df.iterrows():
                            _k = (int(_row.get('year', 0)), int(_row.get('week_num', 0)))
                            if _k not in _existing_keys:
                                all_summaries.append(_row.dropna().to_dict())
                                _added += 1
                        if _added:
                            all_summaries.sort(key=lambda s: (s.get('year', 0), s.get('week_num', 0)))
                            st.info(f'📄 manual_weekly_summary_from_pdf.csv から {_added}週分を補完しました。')
                            st.caption('※ 延べ推計視聴人数はREGZAシステムによる推計値です。')
                except Exception:
                    pass

                # 対象年 + 対象クールで絞り込み
                year_val = int(macro_year)
                quarter_summaries = [
                    s for s in all_summaries
                    if s.get('year', 2026) == year_val
                    and get_quarter(s.get('week_num', 0)) == quarter
                ]

                if not quarter_summaries:
                    st.warning(
                        f'{year_val}年 {_q_labels[quarter]} のデータがまだありません。\n'
                        '週次レポートのZIPをDriveにアップロードしてから再実行してください。'
                    )
                    st.stop()

                # 週数表示
                total_weeks = 13
                found_weeks = len(quarter_summaries)
                if found_weeks < total_weeks:
                    st.markdown(
                        f'<div class="status-box">現在 {found_weeks}週分で作成します'
                        f'（{total_weeks}週そろうと完全版になります）</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.info(f'{found_weeks}週分のデータで作成します。')

                # 番宣データ：06_番宣履歴/から読み込み
                promo_data = []
                try:
                    promo_hist_df = load_promo_history_df(DRIVE_FOLDER_ID)
                    if not promo_hist_df.empty and 'year' in promo_hist_df.columns and 'week_num' in promo_hist_df.columns:
                        _qwks = [float(s['week_num']) for s in quarter_summaries]
                        _mask = (promo_hist_df['year'].astype(float) == float(year_val)) & \
                                (promo_hist_df['week_num'].astype(float).isin(_qwks))
                        promo_data = promo_hist_df[_mask].to_dict('records')
                except Exception:
                    pass
                if not promo_data:
                    for s in quarter_summaries:
                        promo_data.extend(s.get('promo_items', []))

                html = generate_macro_html(quarter_summaries, quarter, year_val, promo_data)
                pdf_bytes = generate_pdf_from_html_string(html)

                st.success(f'✅ {year_val}年 第{quarter}クール マクロレポート生成完了！Drive自動保存は行いません。')
                st.info('📁 生成後、Google DriveのBSよしもと_視聴率レポート保管庫の「03_クール総括PDF」へ手動アップロードしてください。')
                st.download_button(
                    label=f'📥 macro_report_{year_val}_q{quarter}.pdf をダウンロード',
                    data=pdf_bytes,
                    file_name=f'macro_report_{year_val}_q{quarter}.pdf',
                    mime='application/pdf',
                )

            except Exception as e:
                st.markdown(f'<div class="error-box">❌ エラー: {e}</div>', unsafe_allow_html=True)
                import traceback; st.code(traceback.format_exc())


# ════════════════════════════════════════
# ④ 過去レポート取り込み（バックフィル）
# ════════════════════════════════════════
elif report_type == '④ 過去レポート取り込み（肥後用）':
    st.markdown("#### 📁 過去レポート取り込み")
    st.markdown(
        '<div class="status-box">Drive の archive / Ratings-archive フォルダ内の過去E2A CSVから番組別週次履歴を再構築します。</div>',
        unsafe_allow_html=True,
    )

    # ── A. 過去CSVから履歴データを再構築 ──────────────────────────
    st.markdown("##### 1️⃣ 過去CSVから履歴データを再構築")
    st.markdown(
        "Ratings フォルダおよびサブフォルダ内の E2A_HM CSV を全件読み込み、"
        "番組別履歴JSONとサマリーJSONを生成します。"
    )

    if st.button('🔄 過去CSVから履歴データを再構築', key='btn_backfill'):
        with st.spinner('過去CSVを読み込み中... しばらくお待ちください'):
            try:
                from core.backfill_history import build_history_from_archive
                from core.export_package import build_backfill_zip
                from datetime import date as _today_cls

                result = build_history_from_archive(DRIVE_FOLDER_ID)
                weekly   = result['weekly']
                e2a_cnt  = result['e2a_count']
                ok_cnt   = result['success_count']
                skipped  = result['skipped']

                if ok_cnt == 0:
                    st.warning('⚠️ 処理できたE2Aファイルが0件でした。DriveのarchiveフォルダにE2A_HM CSVが存在するか確認してください。')
                else:
                    st.success(f'✅ {e2a_cnt}件中 {ok_cnt}週分の番組履歴を再構築しました。')

                    if skipped:
                        with st.expander(f'⚠️ スキップされたファイル（{len(skipped)}件）'):
                            import pandas as pd
                            st.dataframe(pd.DataFrame(skipped, columns=['ファイル名', '理由']),
                                         use_container_width=True)

                    zip_bytes_bf = build_backfill_zip(weekly)
                    today_str = _today_cls.today().strftime('%Y%m%d')
                    st.download_button(
                        label='📦 Drive登録用ZIPをダウンロード',
                        data=zip_bytes_bf,
                        file_name=f'drive_upload_history_backfill_{today_str}.zip',
                        mime='application/zip',
                        key='dl_backfill_zip',
                    )
                    st.info(
                        '解凍後、ZIPの 04_週次サマリーJSON/ と 05_番組別履歴/ の中身を\n'
                        'Google DriveのBSよしもと_視聴率レポート保管庫へ手動アップロードしてください。'
                    )

            except Exception as _e:
                st.markdown(f'<div class="error-box">❌ バックフィルエラー: {_e}</div>', unsafe_allow_html=True)
                import traceback; st.code(traceback.format_exc())

    st.divider()

    # ── B. 過去PDF由来 手動サマリーCSVテンプレート ──────────────────
    st.markdown("##### 2️⃣ 過去PDF由来 手動サマリーCSVテンプレート")
    st.markdown(
        "過去のPDFレポートからKPIを手入力するためのCSVテンプレートです。\n"
        "記入後は `manual_weekly_summary_from_pdf.csv` という名前でDriveのratingsフォルダへアップロードしてください。\n"
        "③クール総括マクロで自動的に読み込み、週次サマリーJSONに無い週を補完します。"
    )
    st.caption('※ 延べ推計視聴人数（total_all_ppl）はREGZAシステムによる推計値です。')

    try:
        from core.export_package import build_manual_summary_template_csv
        _tmpl_csv = build_manual_summary_template_csv()
        st.download_button(
            label='📥 テンプレートCSVをダウンロード',
            data=_tmpl_csv,
            file_name='manual_weekly_summary_from_pdf.csv',
            mime='text/csv',
            key='dl_manual_template',
        )
    except Exception as _e:
        st.error(f'テンプレート生成エラー: {_e}')

    st.divider()

    # ── C. Drive保管庫 フォルダ構成ガイド ───────────────────────────
    st.markdown("##### 3️⃣ Drive保管庫 フォルダ構成")
    st.markdown("""
```
BSよしもと_視聴率レポート保管庫/
├── 01_週次レポートPDF/       ← ①で生成したPDF
├── 02_番宣効果検証PDF/       ← ②で生成したPDF
├── 03_クール総括PDF/         ← ③で生成したPDF
├── 04_週次サマリーJSON/      ← ①ZIPに同梱 / バックフィルZIPに同梱
├── 05_番組別履歴/            ← ①ZIPに同梱 / バックフィルZIPに同梱
├── 06_番宣履歴/              ← ②ZIPに同梱
└── 99_過去レポート取り込み/  ← 過去レポートPDF（参照のみ・分析対象外）
```
""")
    st.info('PDFの保管は参照用途のみです。クール総括マクロはJSON（04〜06）のデータを分析に使用します。')


# ── フッター ──
st.divider()
st.markdown('<p style="color:#4a4a5a;font-size:11px;text-align:center;">BSよしもと 編成制作局 ／ 視聴データ：REGZA</p>', unsafe_allow_html=True)
