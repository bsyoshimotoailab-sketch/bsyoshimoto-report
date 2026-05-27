#!/usr/bin/env python3
"""
charts.py
matplotlibでグラフを生成してbase64 PNG文字列を返すモジュール
（Chart.js CDNが使えない環境向け）
"""
import base64
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm

# 日本語フォント設定（OS問わず自動検出）
def _setup_jp_font():
    import platform, glob
    candidates = []
    if platform.system() == 'Windows':
        candidates = ['C:/Windows/Fonts/meiryo.ttc', 'C:/Windows/Fonts/YuGothM.ttc']
    else:
        # Linux (Streamlit Cloud) / Mac
        candidates = glob.glob('/usr/share/fonts/**/Noto*CJK*.otf', recursive=True) +                      glob.glob('/usr/share/fonts/**/Noto*CJK*.ttc', recursive=True) +                      glob.glob('/System/Library/Fonts/ヒラギノ*.ttc') +                      glob.glob('/usr/share/fonts/**/*.ttf', recursive=True)
    for f in candidates:
        try:
            import os
            if os.path.exists(f):
                fm.fontManager.addfont(f)
                prop = fm.FontProperties(fname=f)
                matplotlib.rcParams["font.family"] = prop.get_name()
                return
        except: continue
    # フォールバック: DejaVu
    matplotlib.rcParams["font.family"] = "DejaVu Sans"

_setup_jp_font()

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# カラーパレット（レポートのデザインに合わせた濃いめのオレンジ系）
ACCENT    = '#f5a623'
ACCENT2   = '#e85d26'
BG        = '#141418'
SURFACE   = '#1c1c22'
BORDER    = '#2a2a35'
TEXT_MUTED = '#7a7a8c'
TEXT_DIM   = '#4a4a5a'
JCOM_COLOR = '#a0a0e0'
UP_COLOR   = '#4ade80'
DOWN_COLOR = '#f87171'

def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return f"data:image/png;base64,{b64}"

def _setup_ax(ax, title='', desc=''):
    ax.set_facecolor(BG)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(BORDER)
    ax.spines['bottom'].set_color(BORDER)
    ax.tick_params(colors=TEXT_MUTED, labelsize=8)
    ax.yaxis.label.set_color(TEXT_MUTED)
    ax.xaxis.label.set_color(TEXT_MUTED)
    if title:
        ax.set_title(title, color='#f0ede8', fontsize=10, fontweight='bold', pad=8)

def chart_zone(zone_avgs: dict) -> str:
    """時間帯別平均視聴量（横棒グラフ）"""
    zones  = ['深夜\n22-29時', '夜\n18-22時', '夕方\n14-18時', '朝\n8-12時', '昼\n12-14時', '早朝\n5-8時']
    keys   = ['深夜', '夜', '夕方', '朝', '昼', '早朝']
    values = [zone_avgs.get(k, 0) for k in keys]
    colors = [ACCENT, '#e8782a', 'rgba(245,166,35,0.5)'.replace('rgba(','#').replace(',0.5)',''),
              '#b8832a', '#8a6020', '#5a4010']
    # グラデーション代わりに透明度で表現
    alphas = [1.0, 0.85, 0.55, 0.35, 0.25, 0.15]

    fig, ax = plt.subplots(figsize=(5, 2.8), facecolor=BG)
    bars = ax.barh(zones, values, color=[ACCENT]*6, alpha=1.0, height=0.6)
    for bar, alpha in zip(bars, alphas):
        bar.set_alpha(alpha)
    _setup_ax(ax)
    ax.set_xlabel('%', color=TEXT_MUTED, fontsize=8)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.4f}%'))
    ax.set_xlim(0, max(values) * 1.3 if max(values) > 0 else 0.001)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_day(day_avgs: dict) -> str:
    """曜日別平均視聴量（縦棒グラフ）"""
    days   = ['月', '火', '水', '木', '金', '土', '日']
    values = [day_avgs.get(d, 0) for d in days]
    max_v  = max(values) if values else 0
    colors = [ACCENT if v == max_v else f'{ACCENT}55' for v in values]

    fig, ax = plt.subplots(figsize=(5, 2.8), facecolor=BG)
    ax.bar(days, values, color=colors, width=0.6)
    _setup_ax(ax)
    ax.set_ylabel('%', color=TEXT_MUTED, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.4f}%'))
    ax.set_ylim(0, max_v * 1.3 if max_v > 0 else 0.001)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_heatmap(heat: dict) -> str:
    """曜日×時間帯ヒートマップ（大きく表示）"""
    zones = ['深夜', '夜', '夕方', '昼', '朝', '早朝']
    days  = ['月', '火', '水', '木', '金', '土', '日']
    data  = np.array([[heat.get(z, {}).get(d, 0) for d in days] for z in zones])

    fig, ax = plt.subplots(figsize=(13, 5.5), facecolor=BG)
    max_v = data.max() if data.max() > 0 else 0.001
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        'yoshi', ['#1c1c22', '#5a2808', '#c84d1a', '#f5a623']
    )
    im = ax.imshow(data, aspect='auto', cmap=cmap, vmin=0, vmax=max_v)
    ax.set_xticks(range(7)); ax.set_xticklabels(days, color='#f0ede8', fontsize=13, fontweight='bold')
    ax.set_yticks(range(6)); ax.set_yticklabels(zones, color=TEXT_MUTED, fontsize=11)
    ax.set_facecolor(BG)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(colors=TEXT_MUTED, length=0, pad=8)
    # 値と勝敗マークを表示
    for i in range(len(zones)):
        for j in range(len(days)):
            v = data[i, j]
            text_color = 'white' if v > max_v * 0.35 else TEXT_MUTED
            if v > 0:
                ax.text(j, i - 0.15, f'{v:.3f}%', ha='center', va='center',
                        fontsize=9, color=text_color, fontweight='bold')
                if v == max_v:
                    ax.text(j, i + 0.28, '★ MAX', ha='center', va='center',
                            fontsize=7, color=ACCENT)
            else:
                ax.text(j, i, '—', ha='center', va='center',
                        fontsize=9, color=TEXT_DIM)
    # カラーバー
    cbar = fig.colorbar(im, ax=ax, fraction=0.018, pad=0.02)
    cbar.ax.tick_params(colors=TEXT_MUTED, labelsize=8)
    cbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.3f}%'))
    cbar.ax.set_facecolor(BG)
    fig.patch.set_facecolor(BG)
    fig.tight_layout(pad=0.8)
    return _fig_to_b64(fig)


def chart_rival(rival_labels: list, rival_data: list) -> str:
    """全局比較棒グラフ"""
    colors = [ACCENT if l == 'BSよしもと' else f'#ffffff22' for l in rival_labels]
    # 暗い背景に白っぽいバー
    bar_colors = [ACCENT if l == 'BSよしもと' else '#3a3a4a' for l in rival_labels]

    fig, ax = plt.subplots(figsize=(7, 2.5), facecolor=BG)
    bars = ax.bar(rival_labels, rival_data, color=bar_colors, width=0.7)
    _setup_ax(ax)
    ax.set_ylabel('%', color=TEXT_MUTED, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.2f}%'))
    ax.set_ylim(0, max(rival_data) * 1.15 if rival_data else 0.3)
    plt.xticks(rotation=35, ha='right', fontsize=7, color=TEXT_MUTED)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_jcom_time(jcom_zones: dict) -> str:
    """BSよしもと vs J:COM 時間帯別比較"""
    labels = ['昼\n12-16時', '夕方\n16-20時', '夜\n20-24時']
    keys   = ['昼\n12-16時', '夕方\n16-20時', '夜\n20-24時']
    bs_vals   = [jcom_zones.get(k, {}).get('bs',   0) for k in keys]
    jcom_vals = [jcom_zones.get(k, {}).get('jcom', 0) for k in keys]

    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(4, 2.5), facecolor=BG)
    ax.bar(x - w/2, bs_vals,   w, label='BSよしもと', color=ACCENT)
    ax.bar(x + w/2, jcom_vals, w, label='J:COM BS',   color=JCOM_COLOR)
    _setup_ax(ax)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8, color=TEXT_MUTED)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.4f}%'))
    max_v = max(bs_vals + jcom_vals) if (bs_vals + jcom_vals) else 0.01
    ax.set_ylim(0, max_v * 1.3)
    ax.legend(fontsize=7, facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT_MUTED)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_jimoto_live(live_data: list) -> str:
    """ジモトノチカラ 生放送 推計人数"""
    if not live_data: return ''
    labels = [f"{r['day']} {r['date']}" for r in live_data]
    values = [r['total_ppl'] / 1000 for r in live_data]
    max_v  = max(values) if values else 2
    colors = [ACCENT if v == max_v else f'{ACCENT}88' for v in values]

    fig, ax = plt.subplots(figsize=(4.5, 2.2), facecolor=BG)
    ax.bar(labels, values, color=colors, width=0.6)
    _setup_ax(ax)
    ax.set_ylabel('千人', color=TEXT_MUTED, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y*1000:.0f}人'))
    ax.set_ylim(0, max_v * 1.3)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_jimoto_device(live_data: list) -> str:
    """ジモトノチカラ 生放送 機器数（ライブ vs 再生）"""
    if not live_data: return ''
    labels      = [f"{r['day']} {r['date']}" for r in live_data]
    live_devs   = [r['live_dev']   for r in live_data]
    replay_devs = [r['replay_dev'] for r in live_data]

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(4.5, 2.2), facecolor=BG)
    ax.bar(x, live_devs,   label='ライブ', color=ACCENT, width=0.6)
    ax.bar(x, replay_devs, label='再生',   color=f'{ACCENT}44', width=0.6, bottom=live_devs)
    _setup_ax(ax)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8, color=TEXT_MUTED)
    ax.set_ylabel('台', color=TEXT_MUTED, fontsize=8)
    ax.legend(fontsize=7, facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT_MUTED)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_jimoto_replay(replay_data: list) -> str:
    """ジモトノチカラ 深夜再放送 推計人数"""
    if not replay_data: return ''
    labels = [f"{r['day']} {r['date']}" for r in replay_data]
    values = [r['total_ppl'] / 1000 for r in replay_data]
    max_v  = max(values) if values else 2
    colors = ['#a0a0e0' if v == max_v else '#a0a0e066' for v in values]

    fig, ax = plt.subplots(figsize=(4.5, 2.2), facecolor=BG)
    ax.bar(labels, values, color=colors, width=0.6)
    _setup_ax(ax)
    ax.set_ylabel('千人', color=TEXT_MUTED, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y*1000:.0f}人'))
    ax.set_ylim(0, max_v * 1.3)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def chart_jimoto_compare(live_data: list, replay_data: list) -> str:
    """ジモトノチカラ 生放送 vs 深夜再放送 機器数比較"""
    n = min(len(live_data), len(replay_data))
    if n == 0: return ''
    labels = [f"{live_data[i]['day'][-1]}/{replay_data[i]['day'][-1]}" for i in range(n)]
    live_devs   = [live_data[i]['total_dev']   for i in range(n)]
    replay_devs = [replay_data[i]['total_dev'] for i in range(n)]

    x = np.arange(n)
    w = 0.35
    fig, ax = plt.subplots(figsize=(4.5, 2.2), facecolor=BG)
    ax.bar(x - w/2, live_devs,   w, label='生放送',     color=ACCENT)
    ax.bar(x + w/2, replay_devs, w, label='深夜再放送', color=JCOM_COLOR)
    _setup_ax(ax)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8, color=TEXT_MUTED)
    ax.set_ylabel('台', color=TEXT_MUTED, fontsize=8)
    ax.legend(fontsize=7, facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT_MUTED)
    fig.tight_layout(pad=0.5)
    return _fig_to_b64(fig)


def generate_all_charts(data: dict) -> dict:
    """全グラフを生成してbase64辞書を返す"""
    ji = data['jimoto']
    print("  📊 時間帯グラフ...")
    charts = {
        'zone':           chart_zone(data['zone_avgs']),
        'day':            chart_day(data['day_avgs']),
        'heatmap':        chart_heatmap(data['heat']),
        'rival':          chart_rival(data['rival_labels'], data['rival_data']),
        'jcom_time':      chart_jcom_time(data['jcom_zones']),
        'jimoto_live':    chart_jimoto_live(ji['live']),
        'jimoto_device':  chart_jimoto_device(ji['live']),
        'jimoto_replay':  chart_jimoto_replay(ji['replay']),
        'jimoto_compare': chart_jimoto_compare(ji['live'], ji['replay']),
    }
    return charts
