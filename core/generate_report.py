#!/usr/bin/env python3
"""
generate_report.py
BSよしもと 週次視聴量レポート 自動生成スクリプト

使い方:
  python generate_report.py
    --e2a  E2A_HM_番組単位.csv
    --e1a  E1A_HM_番組単位.csv
    --rank 7_ランキング.csv
    [--jimoto jimoto_daily.csv]
    [--prev  prev_week.json]
    [--out   output.html]
    [--template template.html]
"""
import os, re, json, argparse
from datetime import datetime
from pathlib import Path
import pandas as pd

EXCLUDE = ['テレビショッピング','お買い物情報','ショップチャンネル','ウェザーニュース']
YOSHIMOTO = 'BSよしもと'
JCOM = 'J:COM BS'
CHANNELS_4K = ['NHKBSP4K','BS日テレ4K','BS朝日4K','BS-TBS4K','BSテレ東4K','BSフジ4K']

# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────
def parse_hour(s):
    if not isinstance(s, str): return None
    parts = s.strip().split()
    for p in parts:
        m = re.match(r'^(\d{1,2}):\d{2}', p)
        if m: return int(m.group(1))
    return None

def get_zone(h):
    if h is None: return None
    if  5 <= h <  8: return '早朝'
    if  8 <= h < 12: return '朝'
    if 12 <= h < 14: return '昼'
    if 14 <= h < 18: return '夕方'
    if 18 <= h < 22: return '夜'
    return '深夜'  # 22-29 and 0-5

def get_dayname_from_str(s):
    if not isinstance(s, str): return '?'
    m = re.search(r'[（(]([月火水木金土日])[）)]', s)
    return m.group(1) if m else '?'

def get_date_cols(df):
    # "3/16 (月)" 形式 または "20260316" 形式の列を両方認識する
    return [c for c in df.columns if
            re.search(r'\d{1,2}/\d{1,2}', str(c)) or
            re.fullmatch(r'\d{8}', str(c).strip())]

def fv(v, d=4):
    """format value as % string"""
    if v is None or (isinstance(v, float) and pd.isna(v)): return '0.0000'
    return f"{float(v):.{d}f}"

def jnum(v, d=4):
    """value → JS number string"""
    if v is None or (isinstance(v, float) and pd.isna(v)): return '0'
    return f"{float(v):.{d}f}"

def js_arr(lst, d=4):
    return '[' + ','.join(jnum(v, d) for v in lst) + ']'

# ─────────────────────────────────────────
# CSV読み込み
# ─────────────────────────────────────────
def load_e2a(path):
    df = pd.read_csv(path, encoding='utf-16', sep='\t', dtype=str, low_memory=False)
    ch_col = next((c for c in df.columns if 'CH' in str(c) and '枝番' in str(c)), None)
    if ch_col: df = df[df[ch_col].str.strip() == YOSHIMOTO].copy()
    name_col = next((c for c in df.columns if c == 'title'), None)
    if name_col:
        for ex in EXCLUDE:
            df = df[~df[name_col].str.contains(ex, na=False)]
    df.attrs['name_col'] = name_col or 'title'
    return df

def load_e1a(path):
    if isinstance(path, list):
        dfs = [pd.read_csv(p, encoding='utf-16', sep='\t', dtype=str, low_memory=False) for p in path]
        return pd.concat(dfs, ignore_index=True)
    return pd.read_csv(path, encoding='utf-16', sep='\t', dtype=str, low_memory=False)

def load_ranking(path):
    df = pd.read_csv(path, encoding='utf-16', sep='\t', header=0, skiprows=[1], dtype=str, low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns[10:]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def get_metric_e2a(df, metric):
    col = 'Unnamed: 12' if 'Unnamed: 12' in df.columns else 'Unnamed: 13'
    return df[df[col].str.strip() == metric].copy()

def get_metric_e1a(df, metric):
    return df[df['Unnamed: 13'].str.strip() == metric].copy()

def calculate_total_ppl(df_e2a):
    """BSよしもと全番組の週間推計人数合計（value_1_31の合計×1000）"""
    date_cols = get_date_cols(df_e2a)
    try:
        metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
        ppl_rows = df_e2a[df_e2a[metric_col].str.strip() == 'value_1_31'].copy()
        total = 0
        count = 0
        for col in date_cols:
            ppl_rows[col] = pd.to_numeric(ppl_rows[col], errors='coerce')
            vals = ppl_rows[col].dropna()
            vals = vals[vals > 0]
            total += float(vals.sum()) * 1000
            count += len(vals)
        return int(total), count
    except Exception:
        return 0, 0


def find_specific_programs(df_e2a):
    """特定番組（東野山里・水田信二・日曜22:00）の視聴データを検索"""
    name_col = df_e2a.attrs.get('name_col', 'title')
    date_cols = get_date_cols(df_e2a)
    metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
    targets = [
        {'key': 'higashino_yamazato', 'keywords': ['東野', 'インプット'], 'label': '東野山里のインプット'},
        {'key': 'mizuta', 'keywords': ['水田', '注文の多い料理'], 'label': '水田信二の注文の多い料理教室'},
        {'key': 'sunday_22', 'keywords': [], 'label': '日曜22:00枠', 'is_sunday_22': True},
    ]
    results = {}
    dev_rows_all = df_e2a[df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12'].copy()
    for target in targets:
        programs = []
        if target.get('is_sunday_22'):
            if 'program_begin' in dev_rows_all.columns:
                filtered = dev_rows_all[
                    dev_rows_all['program_begin'].str.contains(r'[（(]日[）)]', na=False, regex=True) &
                    dev_rows_all['program_begin'].str.contains(' 22:', na=False)
                ]
            else:
                filtered = pd.DataFrame()
        else:
            mask = pd.Series([False] * len(dev_rows_all), index=dev_rows_all.index)
            for kw in target['keywords']:
                mask = mask | dev_rows_all[name_col].str.contains(kw, na=False)
            filtered = dev_rows_all[mask]
        for _, row in filtered.iterrows():
            for col in date_cols:
                val = pd.to_numeric(str(row.get(col, '')).strip(), errors='coerce')
                if pd.notna(val) and val > 0:
                    day = get_dayname_from_str(col)
                    date_m = re.search(r'(\d+/\d+)', str(col))
                    date_short = date_m.group(1) if date_m else ''
                    ppl_r = df_e2a[
                        (df_e2a[metric_col].str.strip() == 'value_1_31') &
                        (df_e2a[name_col] == row[name_col])
                    ].copy()
                    ppl_val = 0
                    if not ppl_r.empty and col in ppl_r.columns:
                        ppl_r[col] = pd.to_numeric(ppl_r[col], errors='coerce')
                        pv = ppl_r[col].dropna()
                        if not pv.empty:
                            ppl_val = int(float(pv.iloc[0]) * 1000)
                    programs.append({
                        'title': str(row[name_col]),
                        'day': day,
                        'date': date_short,
                        'devices': int(val),
                        'ppl': ppl_val,
                    })
                    break
        results[target['key']] = {'label': target['label'], 'programs': programs}
    return results


# ─────────────────────────────────────────
# E1A分析 (全局比較・時間帯)
# ─────────────────────────────────────────

def find_ytube_programs(df_e2a):
    """Y-Tube大賞の視聴データを検索（日付フィルタなし・全エピソード対象）"""
    name_col = df_e2a.attrs.get('name_col', 'title')
    date_cols = get_date_cols(df_e2a)
    metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'

    dev_rows = df_e2a[
        (df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12') &
        df_e2a[name_col].str.contains('Y-Tube', na=False)
    ].copy()
    # フォールバック: 列名表記ゆれ対応
    if dev_rows.empty:
        dev_rows = df_e2a[
            df_e2a[metric_col].str.contains('視聴機器数', na=False) &
            df_e2a[name_col].str.contains('Y-Tube', na=False)
        ].copy()

    programs = []
    for _, row in dev_rows.iterrows():
        title = str(row[name_col])

        # 番組名の括弧内日付を優先（例: "Y-Tube大賞(3/23)" → "3/23"）
        title_date_m = re.search(r'[（(](\d{1,2}/\d{1,2})[）)]', title)
        date_short = title_date_m.group(1) if title_date_m else ''
        day = '?'

        # 全日付列を合算してデバイス数を取得（フィルタなし）
        total_devices = 0
        for col in date_cols:
            val = pd.to_numeric(str(row.get(col, '')).strip(), errors='coerce')
            if pd.notna(val) and val > 0:
                total_devices += int(val)
                if day == '?':
                    day = get_dayname_from_str(col)
                    if not date_short:
                        dm = re.search(r'(\d+/\d+)', str(col))
                        date_short = dm.group(1) if dm else ''

        # 推計人数
        ppl_val = 0
        ppl_rows = df_e2a[
            df_e2a[metric_col].str.contains('value_1_31', na=False) &
            (df_e2a[name_col] == row[name_col])
        ].copy()
        if not ppl_rows.empty:
            for col in date_cols:
                if col in ppl_rows.columns:
                    ppl_rows[col] = pd.to_numeric(ppl_rows[col], errors='coerce')
                    pv = ppl_rows[col].dropna()
                    if not pv.empty and float(pv.iloc[0]) > 0:
                        ppl_val += int(float(pv.iloc[0]) * 1000)

        programs.append({
            'title': title,
            'day': day, 'date': date_short,
            'devices': total_devices, 'ppl': ppl_val,
        })

    return {'label': 'Y-Tube大賞', 'programs': programs}


def load_trend_data():
    """trend_data.jsonを読み込む"""
    import os
    if not os.path.exists('trend_data.json'):
        return []
    try:
        with open('trend_data.json', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []


def save_trend_data(data):
    """今週のKPIをtrend_data.jsonに追記して返す"""
    trend = load_trend_data()
    entry = {
        'week_num':   data['week_num'],
        'week_range': data['week_range'],
        'kpi_avg':    data['kpi_avg'],
        'kpi_max':    data['kpi_max'],
    }
    trend = [t for t in trend if t['week_num'] != data['week_num']]
    trend.append(entry)
    trend.sort(key=lambda x: x['week_num'])
    with open('trend_data.json', 'w', encoding='utf-8') as f:
        json.dump(trend, f, ensure_ascii=False, indent=2)
    return trend


def build_editors_notes(data):
    """データから今週の編成インサイトHTMLを自動生成"""
    notes = []
    top10     = data.get('top10_yoshi', [])
    kpi_avg   = data.get('kpi_avg', 0)
    day_avgs  = data.get('day_avgs', {})
    zone_avgs = data.get('zone_avgs', {})
    ji        = data.get('jimoto', {})

    # MVP分析
    if top10 and kpi_avg > 0:
        mvp = top10[0]
        ratio = mvp['val'] / kpi_avg
        if ratio >= 5:
            notes.append(f'<strong>今週のMVP「{mvp["title"]}」（{mvp["time"]}）が週平均の{ratio:.0f}倍を記録</strong>。この番組が今週の視聴を単独で牽引した。')
        elif ratio >= 2:
            notes.append(f'<strong>「{mvp["title"]}」（{mvp["time"]}）が週平均の{ratio:.1f}倍</strong>でトップ。')

    # 曜日格差
    if day_avgs:
        best_day  = max(day_avgs, key=day_avgs.get)
        nonzero   = {k:v for k,v in day_avgs.items() if v > 0}
        if nonzero:
            worst_day = min(nonzero, key=nonzero.get)
            best_val  = day_avgs[best_day]
            worst_val = nonzero[worst_day]
            if best_val > 0 and worst_val > 0:
                ratio = best_val / worst_val
                notes.append(f'曜日別では<strong>{best_day}曜が最強</strong>（{best_val:.4f}%）。最弱の{worst_day}曜と{ratio:.1f}倍差。')

    # 時間帯分析
    if zone_avgs:
        max_zone = max(zone_avgs, key=zone_avgs.get)
        nonzero_z = {k:v for k,v in zone_avgs.items() if v > 0}
        if len(nonzero_z) >= 2:
            min_zone  = min(nonzero_z, key=nonzero_z.get)
            max_val   = zone_avgs[max_zone]
            min_val   = nonzero_z[min_zone]
            if max_val > 0 and min_val > 0:
                ratio = max_val / min_val
                notes.append(f'時間帯は「<strong>{max_zone}</strong>」が最強で最弱帯の{ratio:.0f}倍。夜帯の充実が引き続き優先課題。')

    # 新喜劇支配率
    shinki_count = sum(1 for p in top10 if '新喜劇' in p.get('title', ''))
    if shinki_count >= 4:
        notes.append(f'TOP10のうち<strong>{shinki_count}本が新喜劇</strong>。シリーズ安定視聴が局の屋台骨。')

    # ジモト深夜
    if ji:
        replay_ratio = ji.get('replay_ratio', 0)
        if replay_ratio > 20:
            notes.append(f'ジモトノチカラの深夜再放送が生放送比<strong>+{replay_ratio}%</strong>を記録。固定の深夜視聴層が引き続き確認されている。')

    if not notes:
        notes.append('今週のデータを集計しました。次週以降のトレンドと合わせてご確認ください。')

    html = '<ul class="insight-list" style="padding:0;list-style:none;">'
    for n in notes:
        html += f'<li style="padding:5px 0 5px 14px;position:relative;font-size:13px;color:var(--text-primary);"><span style=\"position:absolute;left:0;color:var(--accent);font-size:10px;top:7px;\">▸</span>{n}</li>'
    html += '</ul>'
    return html


def analyze_e1a(df):
    disp = get_metric_e1a(df, '表示数値').copy()
    ch_all = [c for c in disp.columns if c in
              ['NHKBS','BS日テレ','BS朝日','BS-TBS','BSテレ東','BSフジ','BS10','BS11','BS12','J:COM BS','BSよしもと']]
    for c in ch_all:
        disp[c] = pd.to_numeric(disp[c], errors='coerce')

    # 各局の週平均
    channel_avgs = {}
    for ch in ch_all:
        vals = disp[ch].dropna()
        vals = vals[vals > 0]
        channel_avgs[ch] = float(vals.mean()) if len(vals) > 0 else 0.0

    # 全局順位（4K除く）
    sorted_chs = sorted(channel_avgs.items(), key=lambda x: x[1], reverse=True)
    yoshi_rank = next((i+1 for i,(c,_) in enumerate(sorted_chs) if c == YOSHIMOTO), 11)

    # ライバル棒グラフ用
    rival_labels = [c for c,_ in sorted_chs]
    rival_data   = [v for _,v in sorted_chs]

    # BSよしもと vs J:COM 時間帯別
    disp['_hour'] = disp['program_begin'].apply(parse_hour)
    jcom_zones = {}
    for h1,h2,label in [(12,16,'昼\n12-16時'),(16,20,'夕方\n16-20時'),(20,24,'夜\n20-24時')]:
        sub = disp[(disp['_hour'] >= h1) & (disp['_hour'] < h2)]
        bs = sub[YOSHIMOTO].dropna()
        jc = sub[JCOM].dropna() if JCOM in sub.columns else pd.Series([])
        jcom_zones[label] = {
            'bs':   float(bs.mean())  if len(bs) > 0 else 0.0,
            'jcom': float(jc.mean())  if len(jc) > 0 else 0.0,
        }

    # 時間帯別（BSよしもと全体）
    yoshi_col = YOSHIMOTO
    zone_avgs = {}
    for z in ['深夜','夜','夕方','昼','朝','早朝']:
        if z == '深夜':
            sub = disp[(disp['_hour'] >= 22) | (disp['_hour'] < 5)]
        else:
            ranges = {'夜':(18,22),'夕方':(14,18),'昼':(12,14),'朝':(8,12),'早朝':(5,8)}
            h1,h2 = ranges[z]
            sub = disp[(disp['_hour'] >= h1) & (disp['_hour'] < h2)]
        vals = sub[yoshi_col].dropna() if yoshi_col in sub.columns else pd.Series([])
        vals = vals[vals > 0]
        zone_avgs[z] = float(vals.mean()) if len(vals) > 0 else 0.0

    # 曜日別（BSよしもと）
    disp['_day'] = disp['program_begin'].apply(get_dayname_from_str)
    day_avgs = {}
    for d in ['月','火','水','木','金','土','日']:
        sub = disp[disp['_day'] == d]
        vals = sub[yoshi_col].dropna() if yoshi_col in sub.columns else pd.Series([])
        vals = vals[vals > 0]
        day_avgs[d] = float(vals.mean()) if len(vals) > 0 else 0.0

    # ヒートマップ
    heat = {}
    for z in ['深夜','夜','夕方','昼','朝','早朝']:
        heat[z] = {}
        if z == '深夜':
            sub = disp[(disp['_hour'] >= 22) | (disp['_hour'] < 5)]
        else:
            ranges = {'夜':(18,22),'夕方':(14,18),'昼':(12,14),'朝':(8,12),'早朝':(5,8)}
            h1,h2 = ranges[z]
            sub = disp[(disp['_hour'] >= h1) & (disp['_hour'] < h2)]
        for d in ['月','火','水','木','金','土','日']:
            dsub = sub[sub['_day'] == d]
            vals = dsub[yoshi_col].dropna() if yoshi_col in dsub.columns else pd.Series([])
            vals = vals[vals > 0]
            heat[z][d] = float(vals.mean()) if len(vals) > 0 else 0.0

    # J:COM 総合指標
    yoshi_avg = channel_avgs.get(YOSHIMOTO, 0)
    jcom_avg  = channel_avgs.get(JCOM, 0)

    return {
        'channel_avgs': channel_avgs,
        'rival_labels': rival_labels,
        'rival_data':   rival_data,
        'yoshi_rank':   yoshi_rank,
        'zone_avgs':    zone_avgs,
        'day_avgs':     day_avgs,
        'heat':         heat,
        'jcom_zones':   jcom_zones,
        'yoshi_avg':    yoshi_avg,
        'jcom_avg':     jcom_avg,
    }

# ─────────────────────────────────────────
# 7_ランキング分析
# ─────────────────────────────────────────
def analyze_ranking(rank):
    ch_col = 'Unnamed: 4'
    name_col = 'Unnamed: 1'
    time_col = 'Unnamed: 2'

    # 4K除く全局TOP10
    no4k = rank[~rank[ch_col].str.contains('4K', na=False)]
    top10_all = no4k.nlargest(10, '家+個.1')[[name_col, time_col, ch_col, '家+個.1']].copy()
    top10_all_list = []
    for i, (_, r) in enumerate(top10_all.iterrows()):
        t = str(r[time_col])
        day_m = re.search(r'[（(]([月火水木金土日])[）)]', t)
        time_m = re.search(r'(\d+:\d+)$', t)
        time_str = f"{day_m.group(1)} {time_m.group(1)}" if day_m and time_m else t
        top10_all_list.append({
            'rank':  i+1,
            'ch':    str(r[ch_col]),
            'title': str(r[name_col]),
            'time':  time_str,
            'val':   float(r['家+個.1']) if pd.notna(r['家+個.1']) else 0,
        })

    # BSよしもとTOP10
    yoshi = rank[rank[ch_col].str.strip() == YOSHIMOTO].copy()
    for ex in EXCLUDE:
        yoshi = yoshi[~yoshi[name_col].str.contains(ex, na=False)]
    top10_yoshi = yoshi.nlargest(10, '家+個.1')[[name_col, time_col, '家+個.1']].copy()
    top10_yoshi_list = []
    for _, r in top10_yoshi.iterrows():
        t = str(r[time_col])
        day_m = re.search(r'[（(]([月火水木金土日])[）)]', t)
        time_m = re.search(r'(\d+:\d+)$', t)
        time_str = f"{day_m.group(1)} {time_m.group(1)}" if day_m and time_m else t
        top10_yoshi_list.append({
            'title': str(r[name_col]),
            'time':  time_str,
            'val':   float(r['家+個.1']) if pd.notna(r['家+個.1']) else 0,
        })

    # デモグラ平均
    demo_map = {
        'M4（男65以上）': 'M4.1', 'F4（女65以上）': 'F4.1',
        'M3（男50-64）':  'M3.1', 'M2（男35-49）': 'M2.1',
        'F3（女50-64）':  'F3.1', 'U49（49歳以下）': 'U49.1',
    }
    demos = []
    max_demo = 0
    for label, col in demo_map.items():
        if col in yoshi.columns:
            val = float(yoshi[col].mean()) if yoshi[col].notna().any() else 0
            max_demo = max(max_demo, val)
    if max_demo == 0: max_demo = 0.007

    for label, col in demo_map.items():
        val = float(yoshi[col].mean()) if col in yoshi.columns and yoshi[col].notna().any() else 0
        demos.append({'label': label, 'val': val, 'max': max_demo})

    # KPI
    kpi_avg = float(yoshi['家+個.1'].mean()) if yoshi['家+個.1'].notna().any() else 0
    kpi_max = float(yoshi['家+個.1'].max()) if yoshi['家+個.1'].notna().any() else 0
    max_row = yoshi.loc[yoshi['家+個.1'].idxmax()] if yoshi['家+個.1'].notna().any() else None
    if max_row is not None:
        t = str(max_row[time_col])
        day_m = re.search(r'[（(]([月火水木金土日])[）)]', t)
        time_m = re.search(r'(\d+:\d+)$', t)
        kpi_max_program = str(max_row[name_col])[:30]
        kpi_max_time = f"{day_m.group(1)} {time_m.group(1)}" if day_m and time_m else t
    else:
        kpi_max_program = '不明'
        kpi_max_time = ''

    # J:COM demo比較
    jcom = rank[rank[ch_col].str.strip() == JCOM]
    jcom_demos = {
        'M4': float(jcom['M4.1'].mean()) if 'M4.1' in jcom.columns and jcom['M4.1'].notna().any() else 0,
        'U49': float(jcom['U49.1'].mean()) if 'U49.1' in jcom.columns and jcom['U49.1'].notna().any() else 0,
        'F4': float(jcom['F4.1'].mean()) if 'F4.1' in jcom.columns and jcom['F4.1'].notna().any() else 0,
    }
    yoshi_demos = {
        'M4': demos[0]['val'] if demos else 0,
        'U49': demos[5]['val'] if len(demos) > 5 else 0,
        'F4': demos[1]['val'] if len(demos) > 1 else 0,
    }

    return {
        'kpi_avg':       kpi_avg,
        'kpi_max':       kpi_max,
        'kpi_max_program': kpi_max_program,
        'kpi_max_time':  kpi_max_time,
        'top10_all':     top10_all_list,
        'top10_yoshi':   top10_yoshi_list,
        'demos':         demos,
        'jcom_demos':    jcom_demos,
        'yoshi_demos':   yoshi_demos,
    }

# ─────────────────────────────────────────
# E2A ジモトノチカラ分析
# ─────────────────────────────────────────
def analyze_jimoto(df):
    name_col = df.attrs.get('name_col', 'title')
    date_cols = get_date_cols(df)

    def get_val(metric, title_pat, col):
        rows = get_metric_e2a(df, metric)
        rows = rows[rows[name_col].str.contains(title_pat, na=False, regex=True)]
        if rows.empty: return None
        rows[col] = pd.to_numeric(rows[col], errors='coerce')
        v = rows[col].dropna()
        return float(v.iloc[0]) if not v.empty else None

    # 生放送: "[生]発信Live ジモトノチカラ！"
    live_pat = r'\[生\].*ジモトノチカラ'
    # 深夜再放送: "発信Live ジモトノチカラ！" (no [生])
    replay_pat = r'^(?!\[生\]).*ジモトノチカラ'

    live_data = []
    for col in date_cols:
        day = get_dayname_from_str(col)
        # この日の生放送行を探す
        live_rows = get_metric_e2a(df, 'E1A_HM_ツールヒント用列値_視聴機器数_12')
        live_rows = live_rows[live_rows[name_col].str.contains(live_pat, na=False, regex=True)]
        live_rows[col] = pd.to_numeric(live_rows[col], errors='coerce')
        day_live = live_rows[live_rows[col].notna() & (live_rows[col] > 0)]
        if day_live.empty: continue

        row = day_live.iloc[0]
        prog_begin = row['program_begin'] if 'program_begin' in row else ''
        date_m = re.search(r'(\d+/\d+)', str(prog_begin))
        date_short = date_m.group(1) if date_m else col

        title = row[name_col]

        def gv(metric):
            rows = get_metric_e2a(df, metric)
            rows = rows[rows[name_col] == title]
            if rows.empty: return None
            rows[col] = pd.to_numeric(rows[col], errors='coerce')
            v = rows[col].dropna()
            return float(v.iloc[0]) if not v.empty else None

        live_dev1  = gv('E1A_HM_ツールヒント用列値_視聴機器数_1')
        live_dev2  = gv('E1A_HM_ツールヒント用列値_視聴機器数_2')
        live_dev12 = gv('E1A_HM_ツールヒント用列値_視聴機器数_12')
        live_ppl1  = gv('value_1_31')
        live_ppl2  = gv('value_2_31')
        live_ppl12 = gv('value_12_31')

        live_data.append({
            'day':        day,
            'date':       date_short,
            'live_dev':   int(live_dev1)  if live_dev1  else 0,
            'replay_dev': int(live_dev2)  if live_dev2  else 0,
            'total_dev':  int(live_dev12) if live_dev12 else 0,
            'live_ppl':   int(round(float(live_ppl1 or 0)  * 1000)),
            'replay_ppl': int(round(float(live_ppl2 or 0)  * 1000)),
            'total_ppl':  int(round(float(live_ppl12 or 0) * 1000)),
        })

    # 深夜再放送
    replay_data = []
    replay_rows_dev = get_metric_e2a(df, 'E1A_HM_ツールヒント用列値_視聴機器数_12')
    replay_rows_dev = replay_rows_dev[
        replay_rows_dev[name_col].str.contains('ジモトノチカラ', na=False) &
        ~replay_rows_dev[name_col].str.contains(r'\[生\]', na=False, regex=True)
    ]

    for _, rrow in replay_rows_dev.iterrows():
        title = rrow[name_col]
        prog_begin = rrow['program_begin'] if 'program_begin' in rrow else ''
        # 実際の放送日 (program_begin から)
        date_m = re.search(r'(\d+/\d+)', str(prog_begin))
        actual_date = date_m.group(1) if date_m else ''
        actual_day = get_dayname_from_str(str(prog_begin))

        # どのdatecolにデータがあるか
        for col in date_cols:
            col_val = pd.to_numeric(str(rrow[col]).strip(), errors="coerce")
            if pd.notna(col_val) and col_val > 0:
                total_dev = int(col_val)
                # 人数
                ppl_rows = get_metric_e2a(df, 'value_12_31')
                ppl_rows = ppl_rows[ppl_rows[name_col] == title]
                ppl_rows[col] = pd.to_numeric(ppl_rows[col], errors='coerce')
                ppl_v = ppl_rows[col].dropna()
                total_ppl = int(round(float(ppl_v.iloc[0]) * 1000)) if not ppl_v.empty else 0
                # コンテンツ名
                cm = re.search(r'[！!][\(（](\d+/\d+)[\)）]', title)
                content = f"{cm.group(1)}放送分" if cm else title

                # 生放送平均との比較
                avg_live = sum(r['total_dev'] for r in live_data) / len(live_data) if live_data else 1
                ratio = int(round((total_dev / avg_live - 1) * 100)) if avg_live > 0 else 0

                replay_data.append({
                    'day':       actual_day,
                    'date':      actual_date,
                    'content':   content,
                    'total_dev': total_dev,
                    'total_ppl': total_ppl,
                    'ratio':     ratio,
                })
                break  # 1行につき1日分のデータ

    # KPI集計
    total_live_ppl   = sum(r['total_ppl'] for r in live_data)
    total_replay_ppl = sum(r['total_ppl'] for r in replay_data)
    total_ppl_all    = total_live_ppl + total_replay_ppl

    total_live_dev   = sum(r['total_dev'] for r in live_data)
    total_replay_dev = sum(r['total_dev'] for r in replay_data)
    total_dev_all    = total_live_dev + total_replay_dev

    avg_live_dev   = total_live_dev   / len(live_data)   if live_data   else 0
    avg_replay_dev = total_replay_dev / len(replay_data) if replay_data else 0
    replay_ratio   = int(round((avg_replay_dev / avg_live_dev - 1) * 100)) if avg_live_dev > 0 else 0

    avg_live_ppl = total_live_ppl / len(live_data) if live_data else 0

    return {
        'live':          live_data,
        'replay':        replay_data,
        'total_ppl':     total_ppl_all,
        'total_dev':     total_dev_all,
        'replay_ratio':  replay_ratio,
        'avg_live_dev':  round(avg_live_dev, 1),
        'avg_live_ppl':  round(avg_live_ppl),
    }

# ─────────────────────────────────────────
# 週情報の抽出
# ─────────────────────────────────────────
def detect_week_info(df_e2a):
    date_cols = get_date_cols(df_e2a)
    if not date_cols:
        now = datetime.now()
        return now.isocalendar()[1], f"{now.month}/{now.day}（？）〜"

    # 最初と最後の日付列から週情報を作る
    first_col = date_cols[0]
    last_col  = date_cols[-1]

    def col_to_label(c):
        m = re.match(r'(\d+/\d+)\s*[（(]([月火水木金土日])[）)]', str(c))
        if m: return f"{m.group(1)}（{m.group(2)}）"
        m2 = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', str(c).strip())
        if m2:
            from datetime import date as _d
            try:
                dt = _d(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                return f"{dt.month}/{dt.day}（{'月火水木金土日'[dt.weekday()]}）"
            except: pass
        return str(c)

    week_range = f"{col_to_label(first_col)}〜 {col_to_label(last_col)}"

    # 週番号を frame_date から推定
    if 'frame_date' in df_e2a.columns:
        dates = df_e2a['frame_date'].dropna().unique()
        for d in dates:
            if isinstance(d, str):
                m = re.search(r'(\d{4})/(\d+)/(\d+)', d)
                if m:
                    from datetime import date
                    try:
                        dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                        week_num = dt.isocalendar()[1]
                        return week_num, week_range
                    except: pass

    # frame_date が使えない場合は date_cols の最初の列から直接計算
    m2 = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', str(first_col).strip())
    if m2:
        from datetime import date as _d2
        try:
            dt = _d2(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
            return dt.isocalendar()[1], week_range
        except: pass
    m = re.match(r'(\d+)/(\d+)', str(first_col))
    if m:
        from datetime import date as _d2
        try:
            dt = _d2(datetime.now().year, int(m.group(1)), int(m.group(2)))
            return dt.isocalendar()[1], week_range
        except: pass

    # 最終フォールバック：現在日時から
    return datetime.now().isocalendar()[1], week_range

# ─────────────────────────────────────────
# HTML生成
# ─────────────────────────────────────────
def generate_html(data, template_path, prev=None):
    import os as _os
    if not _os.path.isabs(template_path):
        template_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), template_path)
    with open(template_path, encoding='utf-8') as f:
        html = f.read()

    r = data  # shorthand

    # ── ヘッダー ──
    html = re.sub(r'2026 WEEK \d+', f"2026 WEEK {r['week_num']}", html)
    html = re.sub(r'3/9（月）〜 3/15（日）', r['week_range'], html)

    # ── KPIカード ──
    # 週間平均
    avg_disp = f"{r['kpi_avg']:.4f}"
    html = re.sub(r'>0\.15<span style="font-size:18px;letter-spacing:0">%',
                  f'>{avg_disp}<span style="font-size:18px;letter-spacing:0">%', html)
    # 前週比
    if prev and 'kpi_avg' in prev:
        diff = r['kpi_avg'] - prev['kpi_avg']
        sign = '▲' if diff >= 0 else '▼'
        badge_cls = 'badge-up' if diff >= 0 else 'badge-down'
        badge = f'<span class="kpi-badge {badge_cls}">{sign} 前週比 {diff:+.4f}%</span>'
    else:
        badge = '<span class="kpi-badge badge-up">初回（前週比なし）</span>'
    html = re.sub(r'<span class="kpi-badge badge-up">▲ 前週比 \+0\.02%</span>', badge, html)

    # 週間最高
    max_disp = f"{r['kpi_max']:.3f}"
    html = re.sub(r'>0\.02<span style="font-size:18px;letter-spacing:0">%',
                  f'>{max_disp}<span style="font-size:18px;letter-spacing:0">%', html)
    html = re.sub(r'新喜劇（日22:00）',
                  f"{r['kpi_max_program']}（{r['kpi_max_time']}）", html)

    # 全局順位
    html = re.sub(r'>11<span style="font-size:18px;letter-spacing:0">位',
                  f'>{r["yoshi_rank"]}<span style="font-size:18px;letter-spacing:0">位', html)

    # 最強曜日
    html = re.sub(r'<div class="kpi-value">日</div>',
                  f'<div class="kpi-value">{r["best_day"]}</div>', html)
    best_day_avg = r.get('best_day_avg',
                         r.get('day_avgs', {}).get(r.get('best_day', ''), 0.0) or 0.0)
    html = re.sub(r'週平均 0\.003% ／ 最上位',
                  f'週平均 {best_day_avg:.4f}% ／ 最上位', html)

    # ── J:COM 総合指標 ──
    def jcom_rep(old_bs, old_jcom, new_bs, new_jcom, html):
        html = html.replace(f'>{old_bs}%</span>', f'>{new_bs}%</span>', 1)
        html = html.replace(f'>{old_jcom}%</span>', f'>{new_jcom}%</span>', 1)
        return html

    html = html.replace('>0.0016%</span>', f'>{fv(r.get("yoshi_avg", 0))}</span>', 1)
    html = html.replace('>0.0035%</span>', f'>{fv(r.get("jcom_avg", 0))}</span>', 1)
    html = html.replace('>0.0067%</span>', f'>{fv(r.get("yoshi_demos", {}).get("M4", 0))}</span>', 1)
    html = html.replace('>0.0087%</span>', f'>{fv(r.get("jcom_demos", {}).get("M4", 0))}</span>', 1)
    html = html.replace('>0.0003%</span>', f'>{fv(r.get("yoshi_demos", {}).get("U49", 0))}</span>', 1)
    html = html.replace('>0.0000%</span>', f'>{fv(r.get("jcom_demos", {}).get("U49", 0))}</span>', 1)
    html = html.replace('>0.0026%</span>', f'>{fv(r.get("yoshi_demos", {}).get("F4", 0))}</span>', 1)
    html = html.replace('>0.0113%</span>', f'>{fv(r.get("jcom_demos", {}).get("F4", 0))}</span>', 1)

    # J:COM vs BS 順位表示（仮: 全局順位）
    jcom_rank = r.get('jcom_rank', r['yoshi_rank'])  # placeholder
    html = html.replace(
        '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:52px;color:var(--accent);letter-spacing:2px;line-height:1;">10位</div>',
        f'<div style="font-family:\'Bebas Neue\',sans-serif;font-size:52px;color:var(--accent);letter-spacing:2px;line-height:1;">{r["yoshi_rank"]}位</div>'
    )

    # ── Jimoto KPI ──
    ji = r['jimoto']
    html = html.replace('>10,570<span style="font-size:14px;letter-spacing:0;">人',
                        f'>{ji["total_ppl"]:,}<span style="font-size:14px;letter-spacing:0;">人')
    html = html.replace('>676<span style="font-size:14px;letter-spacing:0;">台',
                        f'>{ji["total_dev"]:,}<span style="font-size:14px;letter-spacing:0;">台')
    html = html.replace('>+46<span style="font-size:14px;letter-spacing:0;">%',
                        f'>{ji["replay_ratio"]:+d}<span style="font-size:14px;letter-spacing:0;">%')
    html = html.replace('平均視聴機器数 68.8台 ／ 平均推計人数 1,370人',
                        f'平均視聴機器数 {ji["avg_live_dev"]}台 ／ 平均推計人数 {ji["avg_live_ppl"]:,.0f}人')

    # ── 深夜再放送⚠️テキスト ──
    html = html.replace(
        '⚠️ 注目：深夜再放送の視聴機器数が生放送を平均 +46% 上回っている',
        f'⚠️ 注目：深夜再放送の視聴機器数が生放送を平均 {ji["replay_ratio"]:+d}% 上回っている'
    )

    # ── MVP注入 ──
    if r.get('top10_yoshi'):
        mvp = r['top10_yoshi'][0]
        mvp_ratio = mvp['val'] / r['kpi_avg'] if r['kpi_avg'] > 0 else 0
        html = html.replace('id="mvp-title" style="font-size:17px;font-weight:700;color:var(--text-primary);">—',
                            f'id="mvp-title" style="font-size:17px;font-weight:700;color:var(--text-primary);">{mvp["title"]}')
        html = html.replace('id="mvp-time" style="font-size:13px;color:var(--text-primary);margin-top:3px;">—',
                            f'id="mvp-time" style="font-size:13px;color:var(--text-primary);margin-top:3px;">{mvp["time"]}')
        html = html.replace('id="mvp-val" style="font-size:52px;color:var(--accent);line-height:1;">—',
                            f'id="mvp-val" style="font-size:52px;color:var(--accent);line-height:1;">{mvp["val"]:.3f}%')
        html = html.replace('id="mvp-ratio" style="font-size:13px;color:var(--text-primary);margin-top:2px;">—',
                            f'id="mvp-ratio" style="font-size:13px;color:var(--text-primary);margin-top:2px;">週平均の{mvp_ratio:.1f}倍')

    # ── Y-Tube大賞注入 ──
    ytube = r.get('ytube_data', {})
    ytube_programs = ytube.get('programs', [])
    if ytube_programs:
        rows_html = ''
        for p in ytube_programs:
            rows_html += f'<tr><td>{p["day"]} {p["date"]}</td><td style="max-width:250px;">{p["title"]}</td><td style="text-align:right;">{p["devices"]}台</td><td style="text-align:right;">{p["ppl"]:,}人</td></tr>'
        html = re.sub(
            r'(<tbody id="ytube-tbody">)(.*?)(</tbody>)',
            lambda m: m.group(1) + rows_html + m.group(3),
            html, flags=re.DOTALL
        )

    # ── EDITOR'S NOTES自動生成 ──
    notes_html = build_editors_notes(r)
    html = re.sub(
        r'(<div id="editors-notes"[^>]*>)(.*?)(</div>)',
        lambda m: m.group(1) + notes_html + m.group(3),
        html, flags=re.DOTALL
    )

    # ── フッター ──
    today_str = datetime.now().strftime('%Y.%m.%d')
    html = re.sub(r'生成日時：[\d\.]+', f'生成日時：{today_str}', html)
    html = re.sub(r'データ期間：[^<"]+', f'データ期間：{r["week_range"]}', html)

    # ── EDITOR'S NOTES の週番号 ──
    html = re.sub(r'第\d+週', f'第{r["week_num"]}週', html)

    # ── 週間全国推計人数 ──
    total_ppl = r.get('total_all_ppl', 0)
    prog_count = r.get('total_program_count', 0)
    html = re.sub(r'>[\d,]+ *<span id="total-ppl-unit"', f'>{total_ppl:,}<span id="total-ppl-unit"', html)
    html = re.sub(r'id="total-prog-count">[^<]*', f'id="total-prog-count">{prog_count:,}', html)
    html = html.replace('>999,999<span id="total-ppl-unit"', f'>{total_ppl:,}<span id="total-ppl-unit"')

    # ── 注目番組データ ──
    sp = r.get('specific_programs', {})
    for key in ['higashino_yamazato', 'mizuta', 'sunday_22']:
        pg = sp.get(key, {}).get('programs', [])
        if pg:
            rows_html = ''
            for p in pg:
                rows_html += f'<tr><td>{p["day"]} {p["date"]}</td><td style="max-width:300px;">{p["title"]}</td><td style="text-align:right;">{p["devices"]}台</td><td style="text-align:right;">{p["ppl"]:,}人</td></tr>'
            html = html.replace(f'id="specific-{key}"', f'id="specific-{key}"', 1)
            html = re.sub(f'(<tbody id="specific-{key}">)(.*?)(</tbody>)',
                          lambda m: m.group(1) + rows_html + m.group(3),
                          html, flags=re.DOTALL)

    # ── JavaScript データ部分を置換 ──
    new_js = build_js(r)
    # scriptタグ内を新しいデータで置換
    html = re.sub(r'(<script>)(.*?)(</script>)', r'\1' + new_js + r'\3', html, flags=re.DOTALL)

    return html


def build_js(r):
    """Chartデータ入りのJSブロックを生成"""
    ji = r['jimoto']

    # ─ 時間帯データ ─
    zones = ['深夜','夜','夕方','昼','朝','早朝']
    zone_vals = [r['zone_avgs'].get(z, 0) for z in zones]

    # ─ 曜日データ ─
    days = ['月','火','水','木','金','土','日']
    day_vals = [r['day_avgs'].get(d, 0) for d in days]
    max_day_val = max(day_vals) if day_vals else 0.003

    # ─ ヒートマップ ─
    heat_rows = []
    for z in zones:
        row = [r['heat'].get(z, {}).get(d, 0) for d in days]
        heat_rows.append('[' + ','.join(f'{v:.4f}' for v in row) + ']')
    heat_js = '[\n  ' + ',\n  '.join(heat_rows) + '\n]'
    max_heat = max(max(r['heat'].get(z, {}).values(), default=0) for z in zones)
    if max_heat == 0: max_heat = 0.020

    # ─ BSよしもとTOP10 ─
    top10_js_items = []
    for p in r['top10_yoshi']:
        title = p['title'].replace("'", "\\'")
        top10_js_items.append(
            f"  {{title:'{title}', time:'{p['time']}', val:'{p['val']:.3f}'}}"
        )
    top10_js = '[\n' + ',\n'.join(top10_js_items) + '\n]'

    # ─ デモグラ ─
    demo_colors = ['#f5a623','#e8782a','#c4a43e','rgba(245,166,35,0.55)','rgba(245,166,35,0.45)','rgba(245,166,35,0.25)']
    demo_js_items = []
    for i, d in enumerate(r['demos']):
        color = demo_colors[i] if i < len(demo_colors) else '#f5a623'
        demo_js_items.append(
            f"  {{label:'{d['label']}', val:{d['val']:.4f}, max:{d['max']:.4f}, color:'{color}'}}"
        )
    demo_js = '[\n' + ',\n'.join(demo_js_items) + '\n]'

    # ─ 全局TOP10 ─
    ch_color_map = "{'NHKBS':'rgba(255,255,255,0.12)', 'BSよしもと': '#f5a623', 'J:COM BS':'#a0a0e0'}"
    all_top10_items = []
    for p in r['top10_all']:
        title = p['title'].replace("'", "\\'")
        all_top10_items.append(
            f"  {{rank:{p['rank']}, ch:'{p['ch']}', title:'{title}', time:'{p['time']}', val:'{p['val']:.2f}', note:''}}"
        )
    all_top10_js = '[\n' + ',\n'.join(all_top10_items) + '\n]'

    # ─ ライバル棒グラフ ─
    rival_labels_js = json.dumps(r['rival_labels'], ensure_ascii=False)
    rival_data_js   = '[' + ','.join(f'{v:.4f}' for v in r['rival_data']) + ']'

    # ─ J:COM 時間帯比較 ─
    jcom_zone_keys = ['昼\n12-16時','夕方\n16-20時','夜\n20-24時']
    jcom_bs_vals   = [r['jcom_zones'].get(k, {}).get('bs',   0) for k in jcom_zone_keys]
    jcom_jcom_vals = [r['jcom_zones'].get(k, {}).get('jcom', 0) for k in jcom_zone_keys]

    # ─ ジモトノチカラ 生放送テーブル ─
    live_rows_html = ''
    live_star_ppl = max((r['total_ppl'] for r in ji['live']), default=0) if ji['live'] else 0
    total_live_dev1 = total_live_dev2 = total_live_dev12 = 0
    total_live_ppl1 = total_live_ppl2 = total_live_ppl12 = 0
    for row in ji['live']:
        is_star = row['total_ppl'] == live_star_ppl
        day_style = 'color:var(--accent)' if is_star else 'color:var(--text-primary)'
        ppl_style = 'color:var(--accent)' if is_star else 'color:var(--text-primary)'
        star = ' ★' if is_star else ''
        replay_dev_str = f"{row['replay_dev']}台" if row['replay_dev'] else '—'
        replay_ppl_str = f"{row['replay_ppl']:,}人" if row['replay_ppl'] else '—'
        total_live_dev1  += row['live_dev']
        total_live_dev2  += row['replay_dev']
        total_live_dev12 += row['total_dev']
        total_live_ppl1  += row['live_ppl']
        total_live_ppl2  += row['replay_ppl']
        total_live_ppl12 += row['total_ppl']
        live_rows_html += f'''
        <tr>
          <td><span style="font-weight:700;{day_style};">{row["day"]} {row["date"]}{star}</span></td>
          <td style="color:var(--text-dim);">13:00-16:00</td>
          <td style="text-align:right;">{row["live_dev"]}台</td>
          <td style="text-align:right;color:var(--accent);">{replay_dev_str}</td>
          <td style="text-align:right;font-weight:700;">{row["total_dev"]}台</td>
          <td style="text-align:right;">{row["live_ppl"]:,}人</td>
          <td style="text-align:right;color:var(--accent);">{replay_ppl_str}</td>
          <td style="text-align:right;font-weight:700;{ppl_style};">{row["total_ppl"]:,}人</td>
        </tr>'''

    live_rows_html += f'''
        <tr style="border-top:1px solid var(--accent);font-weight:700;">
          <td colspan="2" style="color:var(--text-muted);font-size:10px;letter-spacing:1px;">週計 / 平均</td>
          <td style="text-align:right;">{total_live_dev1}台</td>
          <td style="text-align:right;">{total_live_dev2}台</td>
          <td style="text-align:right;color:var(--accent);">{total_live_dev12}台</td>
          <td style="text-align:right;">{total_live_ppl1:,}人</td>
          <td style="text-align:right;">{total_live_ppl2:,}人</td>
          <td style="text-align:right;color:var(--accent);">{total_live_ppl12:,}人</td>
        </tr>'''

    # ─ ジモトノチカラ 深夜再放送テーブル ─
    replay_rows_html = ''
    replay_star_dev = max((r['total_dev'] for r in ji['replay']), default=0) if ji['replay'] else 0
    total_replay_dev = total_replay_ppl = 0
    for row in ji['replay']:
        is_star = row['total_dev'] == replay_star_dev
        dev_style = 'color:var(--accent)' if is_star else 'color:var(--up)'
        star = ' ★' if is_star else ''
        ratio_style = 'color:var(--up)' if row['ratio'] >= 0 else 'color:var(--down)'
        total_replay_dev += row['total_dev']
        total_replay_ppl += row['total_ppl']
        replay_rows_html += f'''
        <tr>
          <td><span style="font-weight:700;{dev_style};">{row["day"]} {row["date"]}{star}</span></td>
          <td style="color:var(--text-dim);">02:30-04:30</td>
          <td style="color:var(--text-muted);">{row["content"]}</td>
          <td style="text-align:right;font-weight:700;{dev_style};">{row["total_dev"]}台</td>
          <td style="text-align:right;font-weight:700;">{row["total_ppl"]:,}人</td>
          <td style="text-align:right;{ratio_style};">{row["ratio"]:+d}%</td>
        </tr>'''

    avg_ratio = int(sum(r['ratio'] for r in ji['replay']) / len(ji['replay'])) if ji['replay'] else 0
    replay_rows_html += f'''
        <tr style="border-top:1px solid var(--border);font-weight:700;">
          <td colspan="3" style="color:var(--text-muted);font-size:10px;letter-spacing:1px;">週計 / 平均</td>
          <td style="text-align:right;color:var(--up);">{total_replay_dev}台</td>
          <td style="text-align:right;color:var(--up);">{total_replay_ppl:,}人</td>
          <td style="text-align:right;color:var(--up);">avg {avg_ratio:+d}%</td>
        </tr>'''

    # ─ ジモトノチカラ チャートデータ ─
    live_ppl_data = js_arr([r['total_ppl'] / 1000 for r in ji['live']], 2)
    live_ppl_labels = json.dumps([f"{r['day']} {r['date']}" for r in ji['live']], ensure_ascii=False)
    live_dev_live   = json.dumps([r['live_dev']   for r in ji['live']])
    live_dev_replay = json.dumps([r['replay_dev'] for r in ji['live']])
    replay_ppl_data   = js_arr([r['total_ppl'] / 1000 for r in ji['replay']], 2)
    replay_ppl_labels = json.dumps([f"{r['day']} {r['date']}" for r in ji['replay']], ensure_ascii=False)
    compare_live_dev   = json.dumps([r['total_dev'] for r in ji['live']])
    compare_replay_dev = json.dumps([r['total_dev'] for r in ji['replay']])
    compare_labels     = json.dumps([f"{ji['live'][i]['day'][-1] if i < len(ji['live']) else '?'}/{ji['replay'][i]['day'][-1] if i < len(ji['replay']) else '?'}" for i in range(min(len(ji['live']), len(ji['replay'])))], ensure_ascii=False) if ji['live'] and ji['replay'] else '[]'

    max_live_ppl = max((r['total_ppl'] / 1000 for r in ji['live']), default=2.0) * 1.2
    max_replay_ppl = max((r['total_ppl'] / 1000 for r in ji['replay']), default=2.0) * 1.2

    # ジモトノチカラ 生放送のbgColor（最高値を強調）
    live_ppl_max_val = max((r['total_ppl'] / 1000 for r in ji['live']), default=0)
    live_bg_colors = json.dumps([
        '#f5a623' if r['total_ppl'] / 1000 == live_ppl_max_val else 'rgba(245,166,35,0.5)'
        for r in ji['live']
    ])
    replay_ppl_max_val = max((r['total_ppl'] / 1000 for r in ji['replay']), default=0)
    replay_bg_colors = json.dumps([
        '#a0a0e0' if r['total_ppl'] / 1000 == replay_ppl_max_val else 'rgba(160,160,224,0.5)'
        for r in ji['replay']
    ])

    js = f"""
Chart.defaults.color = '#7a7a8c';
Chart.defaults.font.family = "'Noto Sans JP', sans-serif";
Chart.defaults.font.size = 11;

const accent = '#f5a623';
const accent2 = '#e85d26';
const surface2 = '#1c1c22';
const border = '#2a2a35';

// 1. 時間帯別
new Chart(document.getElementById('zoneChart'), {{
  type: 'bar',
  data: {{
    labels: ['深夜\\n22-29時','夜\\n18-22時','夕方\\n14-18時','朝\\n8-12時','昼\\n12-14時','早朝\\n5-8時'],
    datasets: [{{
      data: {js_arr(zone_vals)},
      backgroundColor: ['#f5a623','#e8782a','rgba(245,166,35,0.5)','rgba(245,166,35,0.3)','rgba(245,166,35,0.2)','rgba(245,166,35,0.1)'],
      borderRadius: 2,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false, indexAxis: 'y',
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.x.toFixed(4)+'%' }} }} }},
    scales: {{
      x: {{ grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v.toFixed(4)+'%' }} }},
      y: {{ grid: {{ display: false }}, border: {{ display: false }} }}
    }}
  }}
}});

// 2. 曜日別
const dayData = {js_arr(day_vals)};
const maxDayVal = {max_day_val:.4f};
new Chart(document.getElementById('dayChart'), {{
  type: 'bar',
  data: {{
    labels: ['月','火','水','木','金','土','日'],
    datasets: [{{
      data: dayData,
      backgroundColor: dayData.map(v => v === maxDayVal ? accent : 'rgba(245,166,35,0.35)'),
      borderRadius: 2, borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.y.toFixed(4)+'%' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v.toFixed(4)+'%' }} }}
    }}
  }}
}});

// 3. ヒートマップ
const zones = ['深夜(22-29時)','夜(18-22時)','夕方(14-18時)','昼(12-14時)','朝(8-12時)','早朝(5-8時)'];
const days  = ['月','火','水','木','金','土','日'];
const heatData = {heat_js};
const hm = document.getElementById('heatmap');
hm.innerHTML += '<div class="heatmap-header"></div>';
days.forEach(d => hm.innerHTML += '<div class="heatmap-header">' + d + '</div>');
const maxVal = {max_heat:.4f};
heatData.forEach((row, zi) => {{
  hm.innerHTML += '<div class="heatmap-row-label">' + zones[zi].split('(')[0] + '</div>';
  row.forEach(val => {{
    const intensity = Math.pow(val / maxVal, 0.5);
    const r2 = Math.round(232 + (245-232)*intensity);
    const g2 = Math.round(87 + (166-87)*intensity);
    const b2 = Math.round(38 + (35-38)*intensity);
    const alpha = 0.1 + intensity * 0.9;
    hm.innerHTML += '<div class="heatmap-cell" style="background:rgba(' + r2 + ',' + g2 + ',' + b2 + ',' + alpha + ')" title="' + val.toFixed(4) + '%">' + (val > 0 ? val.toFixed(4) : '') + '</div>';
  }});
}});

// 4. BSよしもとランキング
const top10 = {top10_js};
const table = document.getElementById('rankTable');
table.innerHTML = '<tr><th>順位</th><th>番組</th><th style="text-align:right">視聴量</th></tr>';
top10.forEach((item, i) => {{
  table.innerHTML += '<tr><td><span class="rank-num' + (i<3?' top3':'') + '">' + (i+1) + '</span></td><td><div class="rank-title">' + item.title + '</div><div class="rank-time">' + item.time + '</div></td><td class="rank-val">' + item.val + '<span>%</span></td></tr>';
}});

// 5. デモグラ
const demos = {demo_js};
const demoList = document.getElementById('demoList');
demos.forEach(d => {{
  const pct = Math.round(d.val / d.max * 100);
  demoList.innerHTML += '<div class="demo-item"><div class="demo-header"><span>' + d.label + '</span><span class="demo-val">' + d.val.toFixed(4) + '%</span></div><div class="demo-bar-bg"><div class="demo-bar-fill" style="width:' + pct + '%;background:' + d.color + '"></div></div></div>';
}});

// 6. ライバルチャート
const rivalLabels = {rival_labels_js};
const rivalData   = {rival_data_js};
new Chart(document.getElementById('rivalChart'), {{
  type: 'bar',
  data: {{
    labels: rivalLabels,
    datasets: [{{ data: rivalData, backgroundColor: rivalLabels.map(l => l === 'BSよしもと' ? accent : 'rgba(255,255,255,0.12)'), borderRadius: 2 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.y.toFixed(4)+'%' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 8 }}, maxRotation: 35 }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v.toFixed(2)+'%', font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 全局TOP10
const allTop10 = {all_top10_js};
const chColor = {ch_color_map};
const allTable = document.getElementById('allRankTable');
allTable.innerHTML = '<tr><th>順位</th><th>局</th><th>番組</th><th style="text-align:right">放送日時</th><th style="text-align:right">視聴量</th></tr>';
allTop10.forEach(item => {{
  const isYoshi = item.ch === 'BSよしもと';
  const color = chColor[item.ch] || 'rgba(255,255,255,0.1)';
  allTable.innerHTML += '<tr' + (isYoshi ? ' style="background:rgba(245,166,35,0.06);"' : '') + '><td><span class="rank-num' + (item.rank<=3?' top3':'') + '">' + item.rank + '</span></td><td><span style="font-size:10px;padding:2px 6px;border-radius:2px;background:' + color + ';color:' + (item.ch==='BSよしもと'?'#f5a623':item.ch==='J:COM BS'?'#a0a0e0':'var(--text-muted)') + ';">' + item.ch + '</span></td><td><div class="rank-title">' + item.title + '</div></td><td class="rank-val" style="font-size:12px;">' + item.time + '</td><td class="rank-val">' + item.val + '<span>%</span></td></tr>';
}});

// J:COM 時間帯別比較
new Chart(document.getElementById('jcomTimeChart'), {{
  type: 'bar',
  data: {{
    labels: ['昼\\n12-16時', '夕方\\n16-20時', '夜\\n20-24時'],
    datasets: [
      {{ label: 'BSよしもと', data: {js_arr(jcom_bs_vals)}, backgroundColor: accent, borderRadius: 2, borderSkipped: false }},
      {{ label: 'J:COM BS',   data: {js_arr(jcom_jcom_vals)}, backgroundColor: '#a0a0e0', borderRadius: 2, borderSkipped: false }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: true, labels: {{ color: '#7a7a8c', font: {{ size: 9 }}, boxWidth: 10 }} }},
               tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(4)+'%' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v.toFixed(4)+'%', font: {{ size: 8 }} }} }}
    }}
  }}
}});

// 7a. ジモトノチカラ 生放送 推計人数
new Chart(document.getElementById('jimotoLiveChart'), {{
  type: 'bar',
  data: {{
    labels: {live_ppl_labels},
    datasets: [{{ label: '推計視聴人数', data: {live_ppl_data}, backgroundColor: {live_bg_colors}, borderRadius: 2, borderSkipped: false }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' ' + (ctx.parsed.y*1000).toFixed(0) + '人' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, min: 0, max: {max_live_ppl:.2f},
           ticks: {{ callback: v => (v*1000).toFixed(0)+'人', font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 7b. ジモトノチカラ 生放送 機器数
new Chart(document.getElementById('jimotoDeviceChart'), {{
  type: 'bar',
  data: {{
    labels: {live_ppl_labels},
    datasets: [
      {{ label: 'ライブ', data: {live_dev_live}, backgroundColor: '#f5a623', borderRadius: 2, borderSkipped: false }},
      {{ label: '再生',   data: {live_dev_replay},  backgroundColor: 'rgba(245,166,35,0.25)', borderRadius: 2, borderSkipped: false }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: true, labels: {{ color: '#7a7a8c', font: {{ size: 9 }}, boxWidth: 10 }} }},
               tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.dataset.label + ': ' + ctx.parsed.y + '台' }} }} }},
    scales: {{
      x: {{ stacked: true, grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
      y: {{ stacked: true, grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v+'台', font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 7c. 深夜再放送 推計人数
new Chart(document.getElementById('jimotoReplayChart'), {{
  type: 'bar',
  data: {{
    labels: {replay_ppl_labels},
    datasets: [{{ label: '推計視聴人数', data: {replay_ppl_data}, backgroundColor: {replay_bg_colors}, borderRadius: 2, borderSkipped: false }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' ' + (ctx.parsed.y*1000).toFixed(0) + '人' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, min: 0, max: {max_replay_ppl:.2f},
           ticks: {{ callback: v => (v*1000).toFixed(0)+'人', font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 7d. 生放送 vs 深夜再放送 機器数比較
new Chart(document.getElementById('jimotoCompareChart'), {{
  type: 'bar',
  data: {{
    labels: {compare_labels},
    datasets: [
      {{ label: '生放送',     data: {compare_live_dev},   backgroundColor: '#f5a623', borderRadius: 2, borderSkipped: false }},
      {{ label: '深夜再放送', data: {compare_replay_dev}, backgroundColor: '#a0a0e0', borderRadius: 2, borderSkipped: false }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: true, labels: {{ color: '#7a7a8c', font: {{ size: 9 }}, boxWidth: 10 }} }},
               tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.dataset.label + ': ' + ctx.parsed.y + '台' }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
      y: {{ grid: {{ color: border }}, border: {{ color: border }}, ticks: {{ callback: v => v+'台', font: {{ size: 9 }} }} }}
    }}
  }}
}});
"""
    # テーブル行置換のためのマーカーをHTMLに埋め込む
    # (これはHTMLのJSブロックに含めない - 別途HTML置換で対応)
    return js


def replace_jimoto_tables(html, jimoto_data):
    """ジモトノチカラのHTMLテーブル行を置換"""
    ji = jimoto_data
    # ... (この処理はgenerate_htmlで実行)
    return html

# ─────────────────────────────────────────
# メイン
# ─────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--e2a',      default='E2A_HM_番組単位.csv')
    ap.add_argument('--e1a',      default='E1A_HM_番組単位.csv')
    ap.add_argument('--rank',     default='7_ランキング.csv')
    ap.add_argument('--jimoto',   default=None)
    ap.add_argument('--prev',     default='prev_week.json')
    ap.add_argument('--template', default='template.html')
    ap.add_argument('--out',      default='bs_report.html')
    args = ap.parse_args()

    print("📊 CSVを読み込み中...")
    df_e2a = load_e2a(args.e2a)
    df_e1a = load_e1a(args.e1a)
    rank   = load_ranking(args.rank)

    print("🔢 E1A (全局比較) 分析中...")
    e1a_data = analyze_e1a(df_e1a)

    print("🔢 ランキング分析中...")
    rank_data = analyze_ranking(rank)

    print("📺 ジモトノチカラ分析中...")
    jimoto_data = analyze_jimoto(df_e2a)

    print("📅 週情報を検出中...")
    week_num, week_range = detect_week_info(df_e2a)

    print("🔢 全番組推計人数を集計中...")
    total_all_ppl, total_program_count = calculate_total_ppl(df_e2a)

    print("🔍 注目番組を検索中...")
    specific_programs = find_specific_programs(df_e2a)

    # 前週データ読み込み
    prev = None
    if os.path.exists(args.prev):
        with open(args.prev, encoding='utf-8') as f:
            prev = json.load(f)
        print(f"📁 前週データを読み込みました: {args.prev}")

    # 全データをマージ
    data = {
        'week_num':    week_num,
        'week_range':  week_range,
        # KPI (rankingから)
        'kpi_avg':     rank_data['kpi_avg'],
        'kpi_max':     rank_data['kpi_max'],
        'kpi_max_program': rank_data['kpi_max_program'],
        'kpi_max_time':    rank_data['kpi_max_time'],
        # 全局順位・ライバル (e1aから)
        'yoshi_rank':  e1a_data['yoshi_rank'],
        'rival_labels': e1a_data['rival_labels'],
        'rival_data':   e1a_data['rival_data'],
        # 時間帯・曜日・ヒートマップ (e1aから)
        'zone_avgs':   e1a_data['zone_avgs'],
        'day_avgs':    e1a_data['day_avgs'],
        'heat':        e1a_data['heat'],
        'best_day':    max(e1a_data['day_avgs'], key=e1a_data['day_avgs'].get) if e1a_data['day_avgs'] else '日',
        'best_day_avg': max(e1a_data['day_avgs'].values()) if e1a_data['day_avgs'] else 0,
        # J:COM比較
        'yoshi_avg':   e1a_data['yoshi_avg'],
        'jcom_avg':    e1a_data['jcom_avg'],
        'jcom_zones':  e1a_data['jcom_zones'],
        'yoshi_demos': rank_data['yoshi_demos'],
        'jcom_demos':  rank_data['jcom_demos'],
        # 番組ランキング・デモグラ
        'top10_all':   rank_data['top10_all'],
        'top10_yoshi': rank_data['top10_yoshi'],
        'demos':       rank_data['demos'],
        # ジモトノチカラ
        'jimoto':      jimoto_data,
        # 週間全体
        'total_all_ppl':       total_all_ppl,
        'total_program_count': total_program_count,
        # 注目番組
        'specific_programs': specific_programs,
    }

    print("🖊️  HTMLを生成中...")
    html = generate_html(data, args.template, prev)

    # ジモトノチカラ テーブル行の置換
    ji = jimoto_data
    # 生放送テーブル（既存のtrタグをすべて置換）
    live_table_pattern = re.compile(
        r'(<tr>\s*<td><span style="font-weight:700;color:var\(--text-primary\);">月 3/9</span>.*?</tr>\s*<tr style="border-top:1px solid var\(--accent\).*?</tr>)',
        re.DOTALL
    )
    # 簡単な置換: weekの生放送テーブル全体を新しいデータで生成
    if ji['live']:
        live_rows = ''
        total_d1 = total_d2 = total_d12 = total_p1 = total_p2 = total_p12 = 0
        max_ppl = max(r['total_ppl'] for r in ji['live'])
        for row in ji['live']:
            star = ' ★' if row['total_ppl'] == max_ppl else ''
            is_star = row['total_ppl'] == max_ppl
            rd = f"{row['replay_dev']}台" if row['replay_dev'] else '—'
            rp = f"{row['replay_ppl']:,}人" if row['replay_ppl'] else '—'
            total_d1 += row['live_dev']; total_d2 += row['replay_dev']
            total_d12 += row['total_dev']; total_p1 += row['live_ppl']
            total_p2 += row['replay_ppl']; total_p12 += row['total_ppl']
            sc = 'color:var(--accent)' if is_star else 'color:var(--text-primary)'
            live_rows += f'<tr><td><span style="font-weight:700;{sc};">{row["day"]} {row["date"]}{star}</span></td><td style="color:var(--text-dim);">13:00-16:00</td><td style="text-align:right;">{row["live_dev"]}台</td><td style="text-align:right;color:var(--accent);">{rd}</td><td style="text-align:right;font-weight:700;">{row["total_dev"]}台</td><td style="text-align:right;">{row["live_ppl"]:,}人</td><td style="text-align:right;color:var(--accent);">{rp}</td><td style="text-align:right;font-weight:700;{sc};">{row["total_ppl"]:,}人</td></tr>'
        live_rows += f'<tr style="border-top:1px solid var(--accent);font-weight:700;"><td colspan="2" style="color:var(--text-muted);font-size:10px;letter-spacing:1px;">週計 / 平均</td><td style="text-align:right;">{total_d1}台</td><td style="text-align:right;">{total_d2}台</td><td style="text-align:right;color:var(--accent);">{total_d12}台</td><td style="text-align:right;">{total_p1:,}人</td><td style="text-align:right;">{total_p2:,}人</td><td style="text-align:right;color:var(--accent);">{total_p12:,}人</td></tr>'
        # 既存の生放送テーブル行を置換
        old_live = re.search(r'(<tr>\s*\n?\s*<td><span style="font-weight:700;color:var\(--text-primary\);">月 3/9</span>.*?</tr>\s*\n?\s*<tr style="border-top:1px solid var\(--accent\).*?</tr>)', html, re.DOTALL)
        if old_live:
            html = html[:old_live.start()] + live_rows + html[old_live.end():]

    if ji['replay']:
        replay_rows = ''
        total_rd = total_rp = 0
        max_dev = max(r['total_dev'] for r in ji['replay'])
        for row in ji['replay']:
            star = ' ★' if row['total_dev'] == max_dev else ''
            is_star = row['total_dev'] == max_dev
            dc = 'color:var(--accent)' if is_star else 'color:var(--up)'
            rc = 'color:var(--up)' if row['ratio'] >= 0 else 'color:var(--down)'
            total_rd += row['total_dev']; total_rp += row['total_ppl']
            replay_rows += f'<tr><td><span style="font-weight:700;{dc};">{row["day"]} {row["date"]}{star}</span></td><td style="color:var(--text-dim);">02:30-04:30</td><td style="color:var(--text-muted);">{row["content"]}</td><td style="text-align:right;font-weight:700;{dc};">{row["total_dev"]}台</td><td style="text-align:right;font-weight:700;">{row["total_ppl"]:,}人</td><td style="text-align:right;{rc};">{row["ratio"]:+d}%</td></tr>'
        avg_r = int(sum(r['ratio'] for r in ji['replay']) / len(ji['replay']))
        replay_rows += f'<tr style="border-top:1px solid var(--border);font-weight:700;"><td colspan="3" style="color:var(--text-muted);font-size:10px;letter-spacing:1px;">週計 / 平均</td><td style="text-align:right;color:var(--up);">{total_rd}台</td><td style="text-align:right;color:var(--up);">{total_rp:,}人</td><td style="text-align:right;color:var(--up);">avg {avg_r:+d}%</td></tr>'
        old_replay = re.search(r'(<tr>\s*\n?\s*<td><span style="font-weight:700;color:var\(--text-primary\);">火 3/10</span>.*?</tr>\s*\n?\s*<tr style="border-top:1px solid var\(--border\).*?</tr>)', html, re.DOTALL)
        if old_replay:
            html = html[:old_replay.start()] + replay_rows + html[old_replay.end():]

    # 今週データを前週用JSONとして保存
    save_data = {
        'kpi_avg': data['kpi_avg'],
        'kpi_max': data['kpi_max'],
        'week_num': week_num,
        'week_range': week_range,
        'zone_avgs': data['zone_avgs'],
        'day_avgs':  data['day_avgs'],
    }
    with open('prev_week.json', 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print("💾 prev_week.json を保存しました（次週の前週比に使用）")

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ レポートHTML生成完了: {args.out}")
    return args.out


if __name__ == '__main__':
    main()


# ─────────────────────────────────────────
# テーブル・デモグラ・ランキングをPythonで直接HTML生成
# （JavaScriptに依存しない方式）
# ─────────────────────────────────────────
def build_static_sections(data: dict) -> dict:
    """JS生成だったセクションをPythonで静的HTML化"""

    # ── BSよしもとTOP10テーブル ──
    top10_rows = '<tr><th>順位</th><th>番組</th><th style="text-align:right">視聴量</th></tr>'
    for i, p in enumerate(data['top10_yoshi']):
        top3_cls = ' top3' if i < 3 else ''
        top10_rows += f'''
        <tr>
          <td><span class="rank-num{top3_cls}">{i+1}</span></td>
          <td>
            <div class="rank-title">{p["title"]}</div>
            <div class="rank-time">{p["time"]}</div>
          </td>
          <td class="rank-val">{p["val"]:.3f}<span>%</span></td>
        </tr>'''

    # ── 全局TOP10テーブル ──
    ch_badge = {
        'NHKBS':    ('rgba(255,255,255,0.12)', 'var(--text-muted)'),
        'BSよしもと': ('#f5a623',              '#f5a623'),
        'J:COM BS': ('#a0a0e044',             '#a0a0e0'),
    }
    all_top10_rows = '<tr><th>順位</th><th>局</th><th>番組</th><th style="text-align:right">放送日時</th><th style="text-align:right">視聴量</th></tr>'
    for p in data['top10_all']:
        is_yoshi = p['ch'] == 'BSよしもと'
        bg, fg = ch_badge.get(p['ch'], ('rgba(255,255,255,0.1)', 'var(--text-muted)'))
        row_bg = ' style="background:rgba(245,166,35,0.06);"' if is_yoshi else ''
        top3_cls = ' top3' if p['rank'] <= 3 else ''
        all_top10_rows += f'''
        <tr{row_bg}>
          <td><span class="rank-num{top3_cls}">{p["rank"]}</span></td>
          <td><span style="font-size:10px;padding:2px 6px;border-radius:2px;background:{bg};color:{fg};">{p["ch"]}</span></td>
          <td><div class="rank-title">{p["title"]}</div></td>
          <td class="rank-val" style="font-size:12px;">{p["time"]}</td>
          <td class="rank-val">{p["val"]:.2f}<span>%</span></td>
        </tr>'''

    # ── デモグラバー ──
    demo_colors = ['#f5a623','#e8782a','#c4a43e',
                   'rgba(245,166,35,0.55)','rgba(245,166,35,0.45)','rgba(245,166,35,0.25)']
    demo_html = ''
    for i, d in enumerate(data['demos']):
        color = demo_colors[i] if i < len(demo_colors) else '#f5a623'
        pct = int(d['val'] / d['max'] * 100) if d['max'] > 0 else 0
        demo_html += f'''
        <div class="demo-item">
          <div class="demo-header">
            <span>{d["label"]}</span>
            <span class="demo-val">{d["val"]:.4f}%</span>
          </div>
          <div class="demo-bar-bg">
            <div class="demo-bar-fill" style="width:{pct}%;background:{color}"></div>
          </div>
        </div>'''

    return {
        'rankTable':    top10_rows,
        'allRankTable': all_top10_rows,
        'demoList':     demo_html,
    }


def build_jimoto_scene_section(sheet_data):
    """スプレッドシートの最高視聴シーン一覧をHTMLで生成"""
    if not sheet_data:
        return ''
    max_dev = max(r['devices'] for r in sheet_data) if sheet_data else 0
    rows_html = ''
    for row in sheet_data:
        is_best = row['devices'] == max_dev
        star = '&#127942; ' if is_best else ''
        color = 'color:var(--accent)' if is_best else 'color:var(--text-primary)'
        content = row['peak_content'][:35] if row['peak_content'] else '-'
        rows_html += (
            f'<tr>'
            f'<td><span style="font-weight:700;{color};">{star}{row["day"]} {row["date"]}</span></td>'
            f'<td style="color:var(--text-muted);">{row["peak_time"]}</td>'
            f'<td style="color:var(--text-primary);">{content}</td>'
            f'<td style="text-align:right;font-weight:700;{color};">{row["devices"]}台</td>'
            f'<td style="text-align:right;">{row["people"]:,}人</td>'
            f'</tr>'
        )
    return (
        '<div class="chart-block" style="margin-top:16px;">'
        '<div class="chart-title">今週の最高視聴シーン</div>'
        '<div class="chart-desc">各日の最高視聴タイムとコンテンツ</div>'
        '<table class="rank-table" style="margin-top:12px;font-size:11px;">'
        '<tr><th>放送日</th><th>時刻</th><th>コンテンツ</th>'
        '<th style="text-align:right;">機器数</th>'
        '<th style="text-align:right;">推計人数</th></tr>'
        + rows_html +
        '</table></div>'
    )
