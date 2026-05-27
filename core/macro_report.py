#!/usr/bin/env python3
"""
macro_report.py
クール（四半期）総括マクロレポート生成
"""
import base64
import io
import re
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# ── フォント設定（charts.pyと同じ方式）──
def _setup_font():
    import glob, platform
    if platform.system() == 'Windows':
        candidates = ['C:/Windows/Fonts/meiryo.ttc']
    else:
        candidates = glob.glob('/usr/share/fonts/**/Noto*CJK*.otf', recursive=True) + \
                     glob.glob('/usr/share/fonts/**/Noto*CJK*.ttc', recursive=True)
    for f in candidates:
        try:
            import os
            if os.path.exists(f):
                fm.fontManager.addfont(f)
                matplotlib.rcParams['font.family'] = fm.FontProperties(fname=f).get_name()
                return
        except: continue
_setup_font()

ACCENT = '#f5a623'; BG = '#141418'; BORDER = '#2a2a35'; TEXT_MUTED = '#d0ccc8'


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=BG, edgecolor='none')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return f'data:image/png;base64,{b64}'


def _quarter_name(q: int) -> str:
    return {1: '第1クール（1〜3月）', 2: '第2クール（4〜6月）',
            3: '第3クール（7〜9月）', 4: '第4クール（10〜12月）'}.get(q, f'第{q}クール')


def get_quarter(week_num: int) -> int:
    """週番号から四半期を判定"""
    if week_num <= 13: return 1
    if week_num <= 26: return 2
    if week_num <= 39: return 3
    return 4


def chart_weekly_trend(summaries: list) -> str:
    """週次KPI推移折れ線グラフ"""
    if not summaries: return ''
    weeks  = [f"W{s['week_num']}" for s in summaries]
    values = [s.get('kpi_avg', 0) for s in summaries]
    max_vals = [s.get('kpi_max', 0) for s in summaries]

    fig, ax = plt.subplots(figsize=(13, 4), facecolor=BG)
    x = list(range(len(weeks)))

    # 最高視聴量（薄いライン）
    ax.plot(x, max_vals, color=ACCENT, linewidth=1, alpha=0.3, linestyle='--')
    # 平均視聴量（メインライン）
    ax.plot(x, values, color=ACCENT, linewidth=2.5, marker='o',
            markersize=7, markerfacecolor=ACCENT, markeredgecolor=BG, markeredgewidth=2, zorder=3)
    ax.fill_between(x, values, alpha=0.1, color=ACCENT)

    ax.set_facecolor(BG)
    for s in ['top','right']: ax.spines[s].set_visible(False)
    ax.spines['left'].set_color(BORDER); ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=10)
    ax.set_xticks(x); ax.set_xticklabels(weeks, color='#f0ede8', fontsize=10, rotation=45, ha='right')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f'{y:.4f}%'))
    ax.set_ylim(0, max(max_vals)*1.3 if max_vals else 0.05)

    for i, v in enumerate(values):
        ax.annotate(f'{v:.4f}%', (i, v), textcoords='offset points',
                    xytext=(0, 10), ha='center', fontsize=8, color=ACCENT)

    fig.patch.set_facecolor(BG)
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def chart_top_programs(summaries: list) -> str:
    """クール内TOP番組ランキング（累積視聴量）"""
    program_totals = {}
    for s in summaries:
        for p in s.get('top10_yoshi', []):
            title = p.get('title', '')[:25]
            program_totals[title] = program_totals.get(title, 0) + p.get('val', 0)

    if not program_totals: return ''

    sorted_progs = sorted(program_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    labels = [p[0] for p in sorted_progs]
    values = [p[1] for p in sorted_progs]

    fig, ax = plt.subplots(figsize=(13, 5), facecolor=BG)
    colors = [ACCENT if i == 0 else f'{ACCENT}66' for i in range(len(labels))]
    bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.6)
    ax.set_facecolor(BG)
    for s in ['top','right']: ax.spines[s].set_visible(False)
    ax.spines['left'].set_color(BORDER); ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f'{x:.3f}%'))
    fig.patch.set_facecolor(BG)
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def chart_promo_effect(summaries: list, promo_data: list) -> str:
    """番宣効果累積グラフ（番宣あり週 vs なし週の平均比較）"""
    if not promo_data: return ''

    promo_weeks = set()
    for p in promo_data:
        week_range = p.get('week_range', '')
        for s in summaries:
            if s.get('week_range', '') == week_range:
                promo_weeks.add(s['week_num'])

    with_promo    = [s['kpi_avg'] for s in summaries if s['week_num'] in promo_weeks]
    without_promo = [s['kpi_avg'] for s in summaries if s['week_num'] not in promo_weeks]

    avg_with    = sum(with_promo)    / len(with_promo)    if with_promo    else 0
    avg_without = sum(without_promo) / len(without_promo) if without_promo else 0

    fig, ax = plt.subplots(figsize=(6, 3.5), facecolor=BG)
    bars = ax.bar(['番宣強化週', '通常週'], [avg_with, avg_without],
                  color=[ACCENT, '#3a3a4a'], width=0.5)
    ax.set_facecolor(BG)
    for s in ['top','right']: ax.spines[s].set_visible(False)
    ax.spines['left'].set_color(BORDER); ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=11)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f'{y:.4f}%'))

    for bar, val in zip(bars, [avg_with, avg_without]):
        ax.text(bar.get_x() + bar.get_width()/2, val + max(avg_with, avg_without)*0.02,
                f'{val:.4f}%', ha='center', fontsize=11, color='#f0ede8', fontweight='bold')

    if avg_without > 0:
        diff = (avg_with - avg_without) / avg_without * 100
        sign = '+' if diff >= 0 else ''
        ax.set_title(f'番宣強化週は通常週比 {sign}{diff:.1f}%', color='#f0ede8', fontsize=12, pad=10)

    fig.patch.set_facecolor(BG)
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def build_macro_notes(summaries: list) -> str:
    """マクロコメント自動生成"""
    if not summaries: return '<p>データなし</p>'

    notes = []
    avgs = [s.get('kpi_avg', 0) for s in summaries]
    best_week = summaries[avgs.index(max(avgs))] if avgs else None
    worst_week = summaries[avgs.index(min(avgs))] if avgs else None

    if best_week:
        notes.append(f'<strong>最高週はWEEK {best_week["week_num"]}（{best_week["week_range"]}）</strong>。週平均 {best_week["kpi_avg"]:.4f}%。要因：{best_week.get("kpi_max_program", "不明")}')

    if worst_week and worst_week != best_week:
        notes.append(f'最低週はWEEK {worst_week["week_num"]}（{worst_week["week_range"]}）。週平均 {worst_week["kpi_avg"]:.4f}%。')

    # トレンド判定
    if len(avgs) >= 4:
        first_half = sum(avgs[:len(avgs)//2]) / (len(avgs)//2)
        second_half = sum(avgs[len(avgs)//2:]) / (len(avgs) - len(avgs)//2)
        if second_half > first_half * 1.05:
            notes.append(f'クール後半にかけて<strong>上昇トレンド</strong>。前半平均{first_half:.4f}% → 後半平均{second_half:.4f}%。')
        elif second_half < first_half * 0.95:
            notes.append(f'クール後半にかけて<strong>下降トレンド</strong>。前半平均{first_half:.4f}% → 後半平均{second_half:.4f}%。')
        else:
            notes.append(f'クール全体を通じて<strong>安定した視聴量</strong>を維持。前半{first_half:.4f}% / 後半{second_half:.4f}%。')

    # 新喜劇占有率
    all_top10 = []
    for s in summaries:
        all_top10.extend(s.get('top10_yoshi', []))
    shinki = sum(1 for p in all_top10 if '新喜劇' in p.get('title', ''))
    if all_top10:
        ratio = shinki / len(all_top10) * 100
        notes.append(f'クール内TOP10のうち<strong>{ratio:.0f}%が新喜劇コンテンツ</strong>（{shinki}/{len(all_top10)}枠）。')

    html = '<ul style="padding:0;list-style:none;">'
    for n in notes:
        html += f'<li style="padding:6px 0 6px 18px;position:relative;font-size:13px;color:#f0ede8;line-height:1.6;"><span style="position:absolute;left:0;color:#f5a623;">▸</span>{n}</li>'
    html += '</ul>'
    return html


def generate_macro_html(summaries: list, quarter: int, year: int = None, promo_data: list = None) -> str:
    """マクロレポートHTMLを生成"""
    if year is None:
        year = datetime.now().year
    q_name = _quarter_name(quarter)
    promo_data = promo_data or []

    trend_chart   = chart_weekly_trend(summaries)
    top_chart     = chart_top_programs(summaries)
    promo_chart   = chart_promo_effect(summaries, promo_data) if promo_data else ''
    macro_notes   = build_macro_notes(summaries)

    # 統計サマリー
    avgs    = [s.get('kpi_avg', 0) for s in summaries]
    maxes   = [s.get('kpi_max', 0) for s in summaries]
    q_avg   = sum(avgs) / len(avgs) if avgs else 0
    q_max   = max(maxes) if maxes else 0
    q_weeks = len(summaries)
    total_ppl = sum(s.get('total_all_ppl', 0) for s in summaries)

    week_range_str = ''
    if summaries:
        first = summaries[0].get('week_range', '')
        last  = summaries[-1].get('week_range', '')
        # "X/Y（曜）〜 X/Y（曜）" から開始日と終了日だけ取る
        m1 = re.match(r'(\S+)', first)
        m2 = re.search(r'〜\s*(\S+)', last)
        if m1 and m2:
            week_range_str = f'{m1.group(1)}〜{m2.group(1)}'

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>BSよしもと {year} {q_name} マクロレポート</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=Oswald:wght@400;700&display=swap');
  :root {{
    --accent: #f5a623; --bg: #141418; --surface: #1c1c22;
    --border: #2a2a35; --text: #f0ede8; --muted: #d0ccc8; --dim: #7a7a8c;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Noto Sans JP', sans-serif; padding: 24px; }}
  .header {{ background: linear-gradient(135deg, #1c1c22, #141418); border-left: 5px solid var(--accent); padding: 20px 28px; margin-bottom: 28px; }}
  .header-sub {{ font-size: 10px; letter-spacing: 4px; color: var(--accent); text-transform: uppercase; margin-bottom: 8px; }}
  .header-title {{ font-size: 32px; font-weight: 700; color: var(--text); }}
  .header-date {{ font-size: 20px; color: var(--accent); float: right; font-family: 'Oswald', sans-serif; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }}
  .kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px; }}
  .kpi-label {{ font-size: 11px; letter-spacing: 2px; color: var(--muted); margin-bottom: 8px; }}
  .kpi-value {{ font-family: 'Oswald', sans-serif; font-size: 36px; color: var(--accent); line-height: 1; }}
  .kpi-unit {{ font-size: 14px; }}
  .section-label {{ font-size: 10px; letter-spacing: 4px; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 20px; margin-top: 32px; }}
  .chart-block {{ background: var(--surface); border-radius: 6px; padding: 20px 24px; margin-bottom: 20px; border: 1px solid var(--border); }}
  .chart-title {{ font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 14px; }}
  .notes-box {{ background: linear-gradient(135deg, rgba(245,166,35,0.08), rgba(232,93,38,0.04)); border: 1px solid rgba(245,166,35,0.3); border-radius: 6px; padding: 20px 24px; margin-bottom: 24px; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .footer {{ font-size: 10px; color: var(--dim); border-top: 1px solid var(--border); padding-top: 12px; margin-top: 32px; }}
  img {{ max-width: 100%; height: auto; display: block; }}
  @page {{ margin: 12mm 10mm; }}
  @media print {{
    * {{ animation: none !important; }}
    .section-label {{ page-break-before: always; break-before: page; }}
    .kpi-grid, .chart-block, .notes-box, .two-col {{ page-break-inside: avoid; break-inside: avoid; }}
    .footer {{ page-break-before: avoid; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-sub">QUARTERLY MACRO REPORT — BSよしもと クール総括</div>
  <div class="header-date">{year} {q_name}</div>
  <div class="header-title">BSよしもと<br>クール総括レポート</div>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">集計週数</div>
    <div class="kpi-value">{q_weeks}<span class="kpi-unit">週</span></div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px;">{week_range_str}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">クール平均視聴量</div>
    <div class="kpi-value">{q_avg:.4f}<span class="kpi-unit">%</span></div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">クール最高視聴量</div>
    <div class="kpi-value">{q_max:.3f}<span class="kpi-unit">%</span></div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">延べ視聴人数（合計）</div>
    <div class="kpi-value" style="font-size:24px;">{total_ppl:,}<span class="kpi-unit">人</span></div>
  </div>
</div>

<div class="section-label">週次KPIトレンド</div>
<div class="chart-block">
  <div class="chart-title">週間平均視聴量の推移</div>
  {'<img src="' + trend_chart + '">' if trend_chart else '<p style="color:var(--muted)">データなし</p>'}
</div>

<div class="section-label">クール総括コメント</div>
<div class="notes-box">
  {macro_notes}
</div>

<div class="section-label">クール内TOP番組（累積）</div>
<div class="chart-block">
  <div class="chart-title">クール内 高視聴番組ランキング</div>
  {'<img src="' + top_chart + '">' if top_chart else '<p style="color:var(--muted)">データなし</p>'}
</div>

{'<div class="section-label">番宣効果分析</div><div class="two-col"><div class="chart-block"><div class="chart-title">番宣強化週 vs 通常週 平均視聴量比較</div>' + ('<img src="' + promo_chart + '">' if promo_chart else '<p style="color:var(--muted)">番宣データなし</p>') + '</div>' + _promo_table_html(promo_data, summaries) + '</div>' if promo_data else ''}

<div class="section-label">週次データ一覧</div>
<div class="chart-block">
  <table style="width:100%;border-collapse:collapse;font-size:12px;">
    <thead>
      <tr style="border-bottom:1px solid var(--accent);">
        <th style="text-align:left;padding:8px;color:var(--muted);">週</th>
        <th style="text-align:left;padding:8px;color:var(--muted);">期間</th>
        <th style="text-align:right;padding:8px;color:var(--muted);">平均視聴量</th>
        <th style="text-align:right;padding:8px;color:var(--muted);">最高視聴量</th>
        <th style="text-align:left;padding:8px;color:var(--muted);">最高番組</th>
      </tr>
    </thead>
    <tbody>
      {''.join(f"""<tr style="border-bottom:1px solid var(--border);">
        <td style="padding:7px 8px;font-family:'Oswald',sans-serif;color:var(--accent);">W{s['week_num']}</td>
        <td style="padding:7px 8px;color:var(--muted);font-size:11px;">{s.get('week_range','')}</td>
        <td style="text-align:right;padding:7px 8px;color:var(--text);">{s.get('kpi_avg',0):.4f}%</td>
        <td style="text-align:right;padding:7px 8px;color:var(--accent);font-weight:700;">{s.get('kpi_max',0):.3f}%</td>
        <td style="padding:7px 8px;color:var(--muted);font-size:11px;">{s.get('kpi_max_program','')[:30]}</td>
      </tr>""" for s in summaries)}
    </tbody>
  </table>
</div>

<div class="footer">
  BSよしもと 編成制作局 ／ 視聴データ：VideoResearch ／ 生成日時：{datetime.now().strftime('%Y.%m.%d')} ／ 対象：{year} {q_name}
</div>

</body>
</html>'''

    return html


def _promo_table_html(promo_data: list, summaries: list) -> str:
    """番宣効果テーブルHTML"""
    if not promo_data:
        return '<div class="chart-block"><p style="color:var(--muted)">番宣データなし</p></div>'

    rows = ''
    for p in promo_data[:10]:
        rows += f'''<tr style="border-bottom:1px solid var(--border);">
          <td style="padding:6px 8px;font-size:12px;color:#f0ede8;">{p.get("program","")}</td>
          <td style="padding:6px 8px;font-size:11px;color:var(--muted);">{p.get("period","")}</td>
          <td style="padding:6px 8px;font-size:11px;color:var(--accent);">{p.get("spots","")}</td>
        </tr>'''

    return f'''<div class="chart-block">
      <div class="chart-title">番宣強化番組リスト</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead><tr style="border-bottom:1px solid var(--accent);">
          <th style="text-align:left;padding:6px 8px;color:var(--muted);">番組名</th>
          <th style="text-align:left;padding:6px 8px;color:var(--muted);">番宣期間</th>
          <th style="text-align:left;padding:6px 8px;color:var(--muted);">SPOT回数</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>'''
