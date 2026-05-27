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
    options=['① 週次レポート', '② 番宣効果検証', '③ クール総括マクロ'],
    horizontal=True,
    label_visibility='collapsed',
)

st.divider()

def _build_promo_section(items: list) -> str:
    if not items: return ''
    rows = ''.join(f'''<tr style="border-bottom:1px solid #2a2a35;">
      <td style="padding:7px 8px;font-size:12px;color:#f0ede8;">{p["program"]}</td>
      <td style="padding:7px 8px;font-size:11px;color:#f5a623;">{p["period"]}</td>
      <td style="padding:7px 8px;font-size:11px;color:#d0ccc8;">{p["spots"]}</td>
      <td style="padding:7px 8px;font-size:11px;color:#d0ccc8;">{p["material"]}</td>
      <td style="text-align:right;padding:7px 8px;font-size:12px;font-weight:700;color:{"#4ade80" if p["viewing"]>0 else "#7a7a8c"};">{f"{p['viewing']:,}人" if p["viewing"]>0 else "計測中"}</td>
    </tr>''' for p in items[:20])
    return f'''
    <div style="background:#1c1c22;border-radius:6px;padding:20px 24px;margin-bottom:24px;border:1px solid #2a2a35;">
      <div style="font-size:10px;letter-spacing:4px;color:#f5a623;border-bottom:1px solid #2a2a35;padding-bottom:8px;margin-bottom:16px;">番宣効果モニタリング</div>
      <div style="font-size:12px;color:#d0ccc8;margin-bottom:14px;">月間_宣伝強化番組_管理リストと今週の視聴データの照合</div>
      <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="border-bottom:1px solid #f5a623;">
          <th style="text-align:left;padding:7px 8px;color:#d0ccc8;font-size:11px;">番組名</th>
          <th style="text-align:left;padding:7px 8px;color:#d0ccc8;font-size:11px;">番宣期間</th>
          <th style="text-align:left;padding:7px 8px;color:#d0ccc8;font-size:11px;">SPOT回数</th>
          <th style="text-align:left;padding:7px 8px;color:#d0ccc8;font-size:11px;">素材</th>
          <th style="text-align:right;padding:7px 8px;color:#d0ccc8;font-size:11px;">今週視聴人数</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      </div>
    </div>'''


# ════════════════════════════════════════
# ① 週次レポート
# ════════════════════════════════════════
if report_type == '① 週次レポート':
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
                    from core.drive_helper import load_all_summaries
                    summaries = load_all_summaries(SUMMARIES_FOLDER_ID)
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

                # 週次サマリーをDriveに保存
                try:
                    from core.drive_helper import save_weekly_summary
                    summary = {
                        'week_num': week_num, 'week_range': week_range,
                        'kpi_avg': rank_data['kpi_avg'], 'kpi_max': rank_data['kpi_max'],
                        'kpi_max_program': rank_data['kpi_max_program'], 'kpi_max_time': rank_data['kpi_max_time'],
                        'top10_yoshi': rank_data['top10_yoshi'],
                        'total_all_ppl': total_ppl,
                        'generated_at': datetime.now().isoformat(),
                    }
                    save_weekly_summary(SUMMARIES_FOLDER_ID, week_num, summary)
                except Exception:
                    pass  # 保存失敗しても続行

                st.success(f'✅ WEEK {week_num} レポート生成完了！')
                st.download_button(
                    label=f'📥 bs_report_w{week_num}.pdf をダウンロード',
                    data=pdf_bytes,
                    file_name=f'bs_report_w{week_num}.pdf',
                    mime='application/pdf',
                )

            except Exception as e:
                st.markdown(f'<div class="error-box">❌ エラーが発生しました: {e}</div>', unsafe_allow_html=True)
                import traceback
                st.code(traceback.format_exc())


# ════════════════════════════════════════
# ② 番宣効果検証
# ════════════════════════════════════════
elif report_type == '② 番宣効果検証':
    st.markdown("#### 📋 番宣効果検証レポート")
    st.markdown('<div class="status-box">今週のCSV + 月間_宣伝強化番組_管理リスト.xlsx から番宣効果を検証したPDFを生成します。</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**今週のCSV（9ファイル）**")
        promo_csv_files = st.file_uploader('', type=['csv'], accept_multiple_files=True, key='promo_csv')
    with col2:
        st.markdown("**番宣Excelファイル**")
        excel_file = st.file_uploader('月間_宣伝強化番組_管理リスト.xlsx', type=['xlsx'], key='promo_excel')

    if st.button('📋 番宣効果検証レポートを生成', key='gen_promo'):
        with st.spinner('検証レポート生成中...'):
            try:
                import pandas as pd
                import tempfile, os

                if not promo_csv_files or not excel_file:
                    st.error('CSVファイルと番宣Excelの両方をアップロードしてください')
                    st.stop()

                tmpdir = tempfile.mkdtemp()
                from core.generate_report import load_e2a, load_e1a, load_ranking, analyze_e1a, analyze_ranking, analyze_jimoto, detect_week_info, calculate_total_ppl, find_specific_programs, find_ytube_programs, generate_html
                from core.charts import generate_all_charts as _gen_charts
                from core.embed_charts import embed_charts_into_html
                from core.make_pdf import generate_pdf_from_html_string

                e1a_paths = []
                e2a_path = rank_path = None
                for uf in promo_csv_files:
                    p = os.path.join(tmpdir, uf.name)
                    with open(p, 'wb') as f: f.write(uf.getvalue())
                    if 'E1A' in uf.name: e1a_paths.append(p)
                    elif 'E2A' in uf.name: e2a_path = p
                    elif 'ランキング' in uf.name or 'ranking' in uf.name.lower(): rank_path = p

                excel_path = os.path.join(tmpdir, 'promo.xlsx')
                with open(excel_path, 'wb') as f: f.write(excel_file.getvalue())

                df_e2a   = load_e2a(e2a_path)
                df_e1a   = load_e1a(e1a_paths)
                rank     = load_ranking(rank_path)
                e1a_data = analyze_e1a(df_e1a)
                rank_data= analyze_ranking(rank)
                jimoto   = analyze_jimoto(df_e2a)
                week_num, week_range = detect_week_info(df_e2a)
                total_ppl, total_count = calculate_total_ppl(df_e2a)
                specific = find_specific_programs(df_e2a)
                ytube    = find_ytube_programs(df_e2a)

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
                    demos=rank_data['demos'], yoshi_demos=rank_data.get('yoshi_demos',{}), jcom_demos=rank_data.get('jcom_demos',{}),
                    jimoto=jimoto,
                    total_all_ppl=total_ppl, total_program_count=total_count,
                    specific_programs=specific,
                    ytube_data=ytube,
                )

                # 番宣効果データ読み込み
                xl = pd.read_excel(excel_path, sheet_name='サマリー', dtype=str).dropna(subset=['番組名'])
                promo_items = []
                from core.generate_report import get_date_cols, get_metric_e2a
                name_col = df_e2a.attrs.get('name_col', 'title')
                mc = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
                for _, row in xl.iterrows():
                    program = str(row.get('番組名','')).strip()
                    period  = str(row.get('重点強化期間','')).strip()
                    spots   = str(row.get('放送回数','')).strip()
                    material= str(row.get('制作素材','')).strip()
                    if not program or program == 'nan': continue
                    # 視聴データ照合
                    viewing = 0
                    try:
                        rows = df_e2a[(df_e2a[mc].str.strip() == 'value_1_31') &
                                      df_e2a[name_col].str.contains(program[:8], na=False)].copy()
                        for col in get_date_cols(df_e2a):
                            rows[col] = pd.to_numeric(rows[col], errors='coerce')
                            vals = rows[col].dropna(); vals = vals[vals > 0]
                            viewing += int(float(vals.sum()) * 1000)
                    except: pass
                    promo_items.append({'program':program,'period':period,'spots':spots,'material':material,'viewing':viewing})

                # 番宣セクションをHTMLに追加
                promo_html = _build_promo_section(promo_items)
                chart_imgs = _gen_charts(data, [])
                template_path = str(ROOT / 'template.html')
                html = generate_html(data, template_path, None)
                html = embed_charts_into_html(html, chart_imgs)
                # フッター直前に番宣セクションを挿入
                html = html.replace('<div class="footer">', promo_html + '<div class="footer">')

                pdf_bytes = generate_pdf_from_html_string(html)
                st.success(f'✅ WEEK {week_num} 番宣効果検証レポート生成完了！')
                st.download_button(
                    label=f'📥 bs_report_w{week_num}_promo.pdf をダウンロード',
                    data=pdf_bytes,
                    file_name=f'bs_report_w{week_num}_promo.pdf',
                    mime='application/pdf',
                )

            except Exception as e:
                st.markdown(f'<div class="error-box">❌ エラー: {e}</div>', unsafe_allow_html=True)
                import traceback; st.code(traceback.format_exc())


# ════════════════════════════════════════
# ③ クール総括マクロ
# ════════════════════════════════════════
elif report_type == '③ クール総括マクロ':
    st.markdown("#### 📈 クール総括マクロレポート")
    st.markdown('<div class="status-box">蓄積された週次データからクール（四半期）の総括レポートを生成します。</div>', unsafe_allow_html=True)

    year    = st.number_input('対象年', min_value=2024, max_value=2030, value=datetime.now().year)
    quarter = st.selectbox('対象クール', [1, 2, 3, 4],
                           format_func=lambda q: {1:'第1クール（1〜3月）',2:'第2クール（4〜6月）',3:'第3クール（7〜9月）',4:'第4クール（10〜12月）'}[q])

    st.markdown("**番宣Excelファイル（任意）**")
    macro_excel = st.file_uploader('月間_宣伝強化番組_管理リスト.xlsx', type=['xlsx'], key='macro_excel')

    if st.button('📈 クール総括レポートを生成', key='gen_macro'):
        with st.spinner('マクロレポート生成中...'):
            try:
                from core.drive_helper import load_all_summaries
                from core.macro_report import generate_macro_html, get_quarter
                from core.make_pdf import generate_pdf_from_html_string

                all_summaries = load_all_summaries(SUMMARIES_FOLDER_ID)

                # 対象クールの週を絞り込み
                quarter_summaries = [s for s in all_summaries if get_quarter(s.get('week_num', 0)) == quarter]

                if not quarter_summaries:
                    st.warning(f'第{quarter}クールのデータがまだありません。週次レポートを先に生成してください。')
                    st.stop()

                st.info(f'{len(quarter_summaries)}週分のデータを集計中...')

                # 番宣データ読み込み
                promo_data = []
                if macro_excel:
                    import pandas as pd, tempfile, os
                    tmpdir = tempfile.mkdtemp()
                    excel_path = os.path.join(tmpdir, 'promo.xlsx')
                    with open(excel_path, 'wb') as f: f.write(macro_excel.getvalue())
                    xl = pd.read_excel(excel_path, sheet_name='サマリー', dtype=str).dropna(subset=['番組名'])
                    for _, row in xl.iterrows():
                        program = str(row.get('番組名','')).strip()
                        if not program or program == 'nan': continue
                        promo_data.append({
                            'program': program,
                            'period':  str(row.get('重点強化期間','')).strip(),
                            'spots':   str(row.get('放送回数','')).strip(),
                        })

                html = generate_macro_html(quarter_summaries, quarter, int(year), promo_data)
                pdf_bytes = generate_pdf_from_html_string(html)

                st.success(f'✅ {year}年 第{quarter}クール マクロレポート生成完了！')
                st.download_button(
                    label=f'📥 macro_report_{year}_q{quarter}.pdf をダウンロード',
                    data=pdf_bytes,
                    file_name=f'macro_report_{year}_q{quarter}.pdf',
                    mime='application/pdf',
                )

            except Exception as e:
                st.markdown(f'<div class="error-box">❌ エラー: {e}</div>', unsafe_allow_html=True)
                import traceback; st.code(traceback.format_exc())

# ── フッター ──
st.divider()
st.markdown('<p style="color:#4a4a5a;font-size:11px;text-align:center;">BSよしもと 編成制作局 ／ 視聴データ：VideoResearch</p>', unsafe_allow_html=True)
