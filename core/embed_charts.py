#!/usr/bin/env python3
"""
embed_charts.py
matplotlibで生成したグラフ画像をHTMLに埋め込む
（Chart.js canvasをimg要素で置換）
"""
import re
import sys


def embed_charts_into_html(html: str, chart_imgs: dict) -> str:
    """
    HTMLのcanvas要素をmatplotlib生成のbase64 img要素で置換する
    """

    # canvas id → chart_imgs キーのマッピング
    canvas_map = {
        'zoneChart':         'zone',
        'dayChart':          'day',
        'heatmap':           'heatmap',       # heatmapはdivなので別処理
        'allRankTable':      None,            # テーブルはそのまま
        'rankTable':         None,
        'demoList':          None,
        'rivalChart':        'rival',
        'jcomTimeChart':     'jcom_time',
        'jimotoLiveChart':   'jimoto_live',
        'jimotoDeviceChart': 'jimoto_device',
        'jimotoReplayChart': 'jimoto_replay',
        'jimotoCompareChart':'jimoto_compare',
        'trendChart':        'trend',
    }

    # 1. canvas要素をimg要素で置換
    def replace_canvas(m):
        canvas_id = m.group(1)
        chart_key = canvas_map.get(canvas_id)
        if chart_key and chart_key in chart_imgs:
            img_src = chart_imgs[chart_key]
            return f'<img id="{canvas_id}" src="{img_src}" style="width:100%;height:auto;display:block;">'
        return m.group(0)  # 変換しない

    html = re.sub(
        r'<canvas id="([^"]+)"[^>]*></canvas>',
        replace_canvas,
        html
    )

    # 2. ヒートマップ（divベース）をimgで置換
    if 'heatmap' in chart_imgs:
        img_src = chart_imgs['heatmap']
        # heatmap divはCSSでdisplay:gridになっているため、
        # imgをgrid-column:1/-1で全列にまたがるdivで包んでフル幅表示にする
        html = re.sub(
            r'(<div id="heatmap"[^>]*>)(.*?)(</div>)',
            lambda m: m.group(1) + f'<div style="grid-column:1/-1;"><img src="{img_src}" style="width:100%;height:auto;display:block;"></div>' + m.group(3),
            html,
            flags=re.DOTALL
        )

    # 3. Chart.jsのscriptタグを削除（不要になるため）
    html = re.sub(
        r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/Chart\.js/[^"]+"></script>',
        '',
        html
    )

    # 4. グラフ描画のJSコード（new Chart(...)）をコメントアウト
    # → scriptブロック全体をシンプルなテーブル・デモグラ生成のみに絞る
    # JSはテーブル生成（ランキング・デモグラ）に必要なので残す

    return html
