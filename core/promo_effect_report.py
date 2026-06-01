#!/usr/bin/env python3
"""
promo_effect_report.py
番宣効果判定レポート専用モジュール
（週次レポートとは完全に独立した処理）
"""
import re
import unicodedata
from datetime import datetime, date as _date


# ══════════════════════════════════════════════════════════
# 番組名正規化（全角→半角・付加表記除去・記号統一）
# ══════════════════════════════════════════════════════════

_STRIP_SUFFIX = re.compile(
    r'[\s　（(【\[]*(?:再放送|字幕版?|終映?|初回?|字|再|新|HD|SD)[）)】\]]*[\s　]*$'
)


def normalize_program_title(name: str) -> str:
    """
    番組名を正規化する。
    - NFKC正規化（全角英数→半角、全角スペース→半角）
    - 末尾の付加表記除去（再放送・字幕・終・初・字・再・新）
    - 括弧・記号・スペース除去
    """
    if not isinstance(name, str):
        return ''
    name = name.strip()
    name = _STRIP_SUFFIX.sub('', name)
    name = unicodedata.normalize('NFKC', name)
    name = re.sub(r'[【】\[\]（）()\s　・〜～〜★☆◆◇●○□■▲△▼▽「」『』、。]', '', name)
    return name.strip()


# ══════════════════════════════════════════════════════════
# 日付ユーティリティ
# ══════════════════════════════════════════════════════════

def _to_date(v):
    """pandas.Timestamp / datetime / date / str → datetime.date or None"""
    import pandas as pd
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _parse_promo_period(period_str: str):
    """番宣期間文字列 → (start_date, end_date)。解析失敗時は (None, None)"""
    if not isinstance(period_str, str) or not period_str.strip() or period_str == 'nan':
        return None, None
    year = datetime.now().year
    m = re.search(r'(\d{1,2}/\d{1,2})[〜～\-]+(\d{1,2}/\d{1,2})', period_str)
    if m:
        try:
            start = datetime.strptime(f'{year}/{m.group(1)}', '%Y/%m/%d').date()
            end   = datetime.strptime(f'{year}/{m.group(2)}', '%Y/%m/%d').date()
            if end < start:
                end = end.replace(year=year + 1)
            return start, end
        except ValueError:
            pass
    return None, None


# ══════════════════════════════════════════════════════════
# 履歴データ読み込み（詳細デバッグ情報付き）
# ══════════════════════════════════════════════════════════

def load_program_history(root_id: str):
    """
    Drive保管庫 05_番組別履歴/ から番組別履歴DataFrameを読み込む。
    normalized_title を新しい正規化関数で再計算する。

    Returns: (df: pd.DataFrame, debug: dict)
    debug keys:
        folder_found: bool
        row_count: int
        week_count: int
        program_count: int
        weeks: list[str]
        error: str | None
    """
    import pandas as pd

    debug = {
        'folder_found': False,
        'row_count': 0,
        'week_count': 0,
        'program_count': 0,
        'weeks': [],
        'error': None,
    }

    try:
        from core.history_store import get_archive_folder, load_program_history_df

        folder_id = get_archive_folder(root_id, 'program')
        debug['folder_found'] = folder_id is not None

        df = load_program_history_df(root_id)
        if df.empty:
            debug['error'] = '05_番組別履歴/ に program_weekly_*.json が見つからないか、すべて空です'
            return df, debug

        # normalized_title を最新の正規化関数で再計算（表記ゆれを吸収）
        if 'program_title' in df.columns:
            df = df.copy()
            df['normalized_title'] = df['program_title'].apply(normalize_program_title)

        debug['row_count'] = len(df)
        if 'year' in df.columns and 'week_num' in df.columns:
            weeks_df = df[['year', 'week_num']].drop_duplicates()
            debug['week_count'] = len(weeks_df)
            debug['weeks'] = sorted([
                f"{int(r['year'])}W{int(r['week_num']):02d}"
                for _, r in weeks_df.iterrows()
            ])
        if 'program_title' in df.columns:
            debug['program_count'] = df['program_title'].nunique()

        return df, debug

    except Exception as e:
        debug['error'] = str(e)
        import pandas as pd
        return pd.DataFrame(), debug


# ══════════════════════════════════════════════════════════
# 過去平均計算
# ══════════════════════════════════════════════════════════

def _get_past_avg(norm_title: str, prog_hist_df, cur_year: int, cur_wk: int, n_weeks: int):
    """
    直近N週平均視聴人数を返す。
    Returns: (avg_ppl: int | None, weeks_used: int, debug_msg: str)
    """
    if prog_hist_df is None or prog_hist_df.empty:
        return None, 0, 'DataFrame空'
    if 'normalized_title' not in prog_hist_df.columns:
        return None, 0, 'normalized_title列なし'

    df = prog_hist_df[prog_hist_df['normalized_title'] == norm_title].copy()
    if df.empty:
        all_titles = prog_hist_df['normalized_title'].dropna().unique()
        short = norm_title[:5] if len(norm_title) >= 5 else norm_title
        cands = [t for t in all_titles if short and (short in t or (len(t) >= 5 and t[:5] in norm_title))][:3]
        cand_str = '、'.join(cands) if cands else 'なし'
        return None, 0, f'履歴に番組なし（類似候補: {cand_str}）'

    cur_y = int(cur_year or 0)
    cur_w = int(cur_wk or 0)
    if cur_y and cur_w:
        df = df[~((df['year'].astype(int) == cur_y) &
                  (df['week_num'].astype(int) == cur_w))]

    df = df.sort_values(['year', 'week_num'], ascending=False).head(n_weeks)
    valid = df['total_viewing_ppl'].dropna()
    valid = valid[valid > 0]
    if valid.empty:
        return None, 0, f'{len(df)}週分あるが視聴人数が全て0または欠損'
    return int(valid.mean()), len(valid), 'OK'


def _find_similar_titles(norm_title: str, prog_hist_df) -> list:
    """Streamlit要確認表示用：類似番組名候補を返す"""
    if prog_hist_df is None or prog_hist_df.empty:
        return []
    if 'normalized_title' not in prog_hist_df.columns:
        return []
    all_norms = prog_hist_df['normalized_title'].dropna().unique()
    if 'program_title' in prog_hist_df.columns:
        norm_to_title = dict(zip(
            prog_hist_df['normalized_title'].fillna(''),
            prog_hist_df['program_title'].fillna(''),
        ))
    else:
        norm_to_title = {t: t for t in all_norms}

    short = norm_title[:5] if len(norm_title) >= 5 else norm_title
    if not short:
        return []
    matched = [norm_to_title.get(t, t)
               for t in all_norms
               if short in t or (len(t) >= 5 and t[:5] in norm_title)]
    return matched[:5]


# ══════════════════════════════════════════════════════════
# 判定ロジック
# ══════════════════════════════════════════════════════════

def judge_promo_effect(viewing_ppl: int, match_type: str,
                        past_4w_avg, past_4w_weeks: int,
                        past_13w_avg, past_13w_weeks: int):
    """
    判定区分: 効果あり / 効果見えず / 判定保留 / 要確認

    Returns: (judgment: str, comment: str, diff_4w_pct: float|None, diff_13w_pct: float|None)
    """
    # 要確認: E2A照合不可
    if match_type == '不一致':
        return ('要確認',
                '番宣リスト上の番組名が視聴データ側と一致していません。番組名表記の確認が必要です。',
                None, None)

    diff_4w  = ((viewing_ppl - past_4w_avg)  / past_4w_avg  * 100
                if past_4w_avg  and past_4w_avg  > 0 else None)
    diff_13w = ((viewing_ppl - past_13w_avg) / past_13w_avg * 100
                if past_13w_avg and past_13w_avg > 0 else None)

    # 判定保留: 視聴データ0
    if viewing_ppl == 0:
        return ('判定保留',
                '今週の視聴データが0です。放送実績を確認してください。',
                None, None)

    # 判定保留: 過去比較データなし
    if diff_4w is None and diff_13w is None:
        return ('判定保留',
                '番組照合はできていますが、比較に必要な過去履歴が不足しているため判定保留です。',
                None, None)

    # 主比較値の決定（4週優先）
    primary = diff_4w if diff_4w is not None else diff_13w
    prim_wk  = past_4w_weeks if diff_4w is not None else past_13w_weeks

    # 効果あり: +20%以上
    if (diff_4w is not None and diff_4w >= 20) or (diff_13w is not None and diff_13w >= 20):
        best     = max(v for v in [diff_4w, diff_13w] if v is not None)
        best_wk  = past_4w_weeks if diff_4w == best else past_13w_weeks
        return ('効果あり',
                f'過去{best_wk}週平均比 {best:+.1f}%。'
                '過去平均を大きく上回っており、番宣効果が出た可能性があります。',
                diff_4w, diff_13w)

    # 効果見えず: +10%未満またはマイナス
    if primary < 10:
        return ('効果見えず',
                f'過去{prim_wk}週平均比 {primary:+.1f}%。'
                '過去平均と同水準または下回っており、現時点では明確な上積みは確認できません。',
                diff_4w, diff_13w)

    # 判定保留: +10%以上+20%未満（微増、追加観察）
    return ('判定保留',
            f'過去{prim_wk}週平均比 {primary:+.1f}%。'
            '増加傾向ですが、明確な効果判定には追加観察が必要です。',
            diff_4w, diff_13w)


# ══════════════════════════════════════════════════════════
# 番宣効果アイテム構築
# ══════════════════════════════════════════════════════════

def build_promo_effect_items(df_e2a, excel_path: str, prog_hist_df,
                              week_start=None, week_end=None,
                              cur_year: int = None, cur_week_num: int = None) -> dict:
    """
    番宣ExcelとE2A・履歴を照合して効果判定結果を返す。

    Returns: {
        'effect':      [item, ...],
        'no_effect':   [item, ...],
        'pending':     [item, ...],
        'needs_check': [item, ...],
        'all_items':   [item, ...],
        'summary':     dict,
        'hist_debug':  {program: {'4w': str, '13w': str}},
    }
    """
    import pandas as pd

    try:
        xl = pd.read_excel(excel_path, sheet_name='サマリー', dtype=str).dropna(subset=['番組名'])
    except Exception as e:
        msg = str(e)
        if 'サマリー' in msg or 'Worksheet' in msg or 'sheet' in msg.lower():
            raise ValueError('番宣Excelにシート「サマリー」が見つかりません。シート名を確認してください。')
        raise

    name_col   = df_e2a.attrs.get('name_col', 'title')
    metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
    date_cols  = [c for c in df_e2a.columns if
                  re.search(r'\d{1,2}/\d{1,2}', str(c)) or
                  re.fullmatch(r'\d{8}', str(c).strip())]

    ppl_df = df_e2a[df_e2a[metric_col].str.strip() == 'value_1_31'].copy()
    dev_df = df_e2a[df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12'].copy()

    # E2A番組名マップ: normalized_title → 元のタイトル
    e2a_norm_map: dict = {}
    for t in df_e2a[name_col].dropna().unique():
        key = normalize_program_title(str(t))
        if key:
            e2a_norm_map[key] = str(t)

    ws_date = _to_date(week_start)
    we_date = _to_date(week_end)
    cur_y   = int(cur_year or (we_date.year if we_date else datetime.now().year))
    cur_w   = int(cur_week_num or 0)

    effect_list    = []
    no_effect_list = []
    pending_list   = []
    needs_check    = []
    all_items      = []
    hist_debug: dict = {}

    for _, row in xl.iterrows():
        program  = str(row.get('番組名', '')).strip()
        period   = str(row.get('重点強化期間', '')).strip()
        spots    = str(row.get('SPOT回数', row.get('放送回数', ''))).strip()
        material = str(row.get('制作素材', '')).strip()

        if not program or program == 'nan':
            continue

        spots_val    = spots    if spots    not in ('nan', '') else '—'
        material_val = material if material not in ('nan', '') else '—'
        norm         = normalize_program_title(program)

        # 番宣期間未設定 → 要確認
        period_clean = period if period not in ('nan', '—', '', 'None') else ''
        if not period_clean:
            sim  = _find_similar_titles(norm, prog_hist_df)
            item = {
                'program': program, 'period': '（未設定）',
                'spots': spots_val, 'material': material_val,
                'match_type': '不一致', 'match_title': '',
                'normalized_title': norm,
                'viewing_ppl': 0, 'viewing_dev': 0,
                'past_4w_avg_ppl': None, 'past_4w_weeks': 0,
                'past_13w_avg_ppl': None, 'past_13w_weeks': 0,
                'diff_4w_pct': None, 'diff_13w_pct': None,
                'judgment': '要確認',
                'comment': '番宣期間が設定されていません。Excelの「重点強化期間」列を確認してください。',
                'similar_titles': sim,
            }
            needs_check.append(item)
            all_items.append(item)
            continue

        # 今週との重なりチェック（どちらかが None の場合はスキップせず続行）
        p_start, p_end = _parse_promo_period(period_clean)
        p_start = _to_date(p_start)
        p_end   = _to_date(p_end)
        if ws_date and we_date and p_start and p_end:
            if we_date < p_start or ws_date > p_end:
                continue

        # E2A番組名照合
        match_type  = '不一致'
        match_title = ''
        if norm in e2a_norm_map:
            match_type  = '完全一致'
            match_title = e2a_norm_map[norm]
        elif len(norm) >= 4:
            cands = [(k, v) for k, v in e2a_norm_map.items()
                     if norm[:8] in k or k[:8] in norm]
            if cands:
                match_type  = '候補一致'
                match_title = cands[0][1]

        # 視聴データ集計
        viewing_ppl = 0
        viewing_dev = 0
        if match_title:
            try:
                ppl_rows = ppl_df[ppl_df[name_col] == match_title]
                for col in date_cols:
                    v = pd.to_numeric(ppl_rows[col], errors='coerce').dropna()
                    viewing_ppl += int(float(v[v > 0].sum()) * 1000)
                dev_rows = dev_df[dev_df[name_col] == match_title]
                for col in date_cols:
                    v = pd.to_numeric(dev_rows[col], errors='coerce').dropna()
                    viewing_dev += int(v[v > 0].sum())
            except Exception:
                pass

        # 過去比較
        past_4w,  past_4w_wk,  d4_dbg  = _get_past_avg(norm, prog_hist_df, cur_y, cur_w, 4)
        past_13w, past_13w_wk, d13_dbg = _get_past_avg(norm, prog_hist_df, cur_y, cur_w, 13)
        hist_debug[program] = {
            '正規化後': norm,
            '4w': d4_dbg,
            '13w': d13_dbg,
        }

        # 効果判定
        judgment, comment, diff_4w, diff_13w = judge_promo_effect(
            viewing_ppl, match_type,
            past_4w, past_4w_wk,
            past_13w, past_13w_wk,
        )

        # 要確認の場合は類似候補を補足
        similar = []
        if match_type == '不一致':
            similar = _find_similar_titles(norm, prog_hist_df)
            if similar:
                comment += f'　類似候補: {", ".join(similar[:3])}'

        item = {
            'program':           program,
            'period':            period_clean,
            'spots':             spots_val,
            'material':          material_val,
            'match_type':        match_type,
            'match_title':       match_title,
            'normalized_title':  norm,
            'viewing_ppl':       viewing_ppl,
            'viewing_dev':       viewing_dev,
            'past_4w_avg_ppl':   past_4w,
            'past_4w_weeks':     past_4w_wk,
            'past_13w_avg_ppl':  past_13w,
            'past_13w_weeks':    past_13w_wk,
            'diff_4w_pct':       diff_4w,
            'diff_13w_pct':      diff_13w,
            'judgment':          judgment,
            'comment':           comment,
            'similar_titles':    similar,
        }
        all_items.append(item)

        if judgment == '効果あり':
            effect_list.append(item)
        elif judgment == '効果見えず':
            no_effect_list.append(item)
        elif judgment == '判定保留':
            pending_list.append(item)
        else:
            needs_check.append(item)

    hist_ok = sum(
        1 for it in all_items
        if it.get('past_4w_avg_ppl') is not None or it.get('past_13w_avg_ppl') is not None
    )

    return {
        'effect':      effect_list,
        'no_effect':   no_effect_list,
        'pending':     pending_list,
        'needs_check': needs_check,
        'all_items':   all_items,
        'summary': {
            'total_promo':   len(all_items),
            'csv_matched':   sum(1 for i in all_items if i['match_type'] in ('完全一致', '候補一致')),
            'hist_compared': hist_ok,
            'effect_found':  len(effect_list),
            'no_effect':     len(no_effect_list),
            'pending':       len(pending_list),
            'needs_check':   len(needs_check),
        },
        'hist_debug': hist_debug,
    }


# ══════════════════════════════════════════════════════════
# 番宣効果判定レポート専用HTML生成
# ══════════════════════════════════════════════════════════

def build_promo_effect_html(result: dict, week_range: str,
                             week_num: int, year: int) -> str:
    """
    週次レポートテンプレートを一切使わない番宣効果判定専用HTML。
    """
    sm          = result['summary']
    all_items   = result['all_items']
    effect      = result['effect']
    no_effect   = result['no_effect']
    pending     = result['pending']
    needs_check = result['needs_check']

    # 総評コメント自動生成
    total   = sm['total_promo']
    csv_ok  = sm['csv_matched']
    hist_ok = sm['hist_compared']
    eff_cnt = sm['effect_found']
    neff    = sm['no_effect']
    pend    = sm['pending']
    chk     = sm['needs_check']
    overview = (
        f'今週は番宣対象{total}件のうち、視聴データ（CSV）照合できた番組は{csv_ok}件でした。'
        f'過去履歴との比較が可能だった番組は{hist_ok}件で、'
        f'うち{eff_cnt}件は過去平均を大きく上回り「効果あり」と判定しました。'
    )
    if neff:
        overview += f'　{neff}件は増加が確認できず「効果見えず」と判定しました。'
    if pend:
        overview += f'　{pend}件は履歴不足などにより判定保留です。'
    if chk:
        overview += f'　{chk}件は番組名不一致・期間未設定により要確認です。'

    JCOLOR = {
        '効果あり':   '#4ade80',
        '効果見えず': '#f87171',
        '判定保留':   '#fbbf24',
        '要確認':     '#7a7a8c',
    }

    def _ppl(v):
        return f'{v:,}人' if v and v > 0 else '—'

    def _pct(v):
        if v is None:
            return '—'
        c = '#4ade80' if v >= 0 else '#f87171'
        return f'<span style="color:{c};font-weight:700;">{v:+.1f}%</span>'

    TH = '''<thead><tr style="border-bottom:1px solid #f5a623;background:#141418;">
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;letter-spacing:1px;white-space:nowrap;">番組名</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">番宣期間</th>
      <th style="text-align:center;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">SPOT</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">今週視聴人数</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">過去4週平均</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">4週比</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">過去13週平均</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">13週比</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;white-space:nowrap;">判定</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;">コメント</th>
    </tr></thead>'''

    def _rows(items):
        if not items:
            return ('<tr><td colspan="10" style="padding:12px;color:#7a7a8c;'
                    'text-align:center;font-size:11px;">該当なし</td></tr>')
        out = ''
        for i in items:
            jc = JCOLOR.get(i['judgment'], '#d0ccc8')
            cmt = (i.get('comment') or '')[:60]
            out += f'''<tr style="border-bottom:1px solid #2a2a35;">
              <td style="padding:5px 8px;font-size:11px;color:#f0ede8;">{i["program"]}</td>
              <td style="padding:5px 8px;font-size:10px;color:#f5a623;white-space:nowrap;">{i["period"]}</td>
              <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;text-align:center;">{i["spots"]}</td>
              <td style="padding:5px 8px;font-size:11px;font-weight:700;color:#60d4a0;text-align:right;">{_ppl(i.get("viewing_ppl"))}</td>
              <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;text-align:right;">{_ppl(i.get("past_4w_avg_ppl"))}</td>
              <td style="padding:5px 8px;text-align:right;">{_pct(i.get("diff_4w_pct"))}</td>
              <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;text-align:right;">{_ppl(i.get("past_13w_avg_ppl"))}</td>
              <td style="padding:5px 8px;text-align:right;">{_pct(i.get("diff_13w_pct"))}</td>
              <td style="padding:5px 8px;font-size:10px;font-weight:700;color:{jc};white-space:nowrap;">{i["judgment"]}</td>
              <td style="padding:5px 8px;font-size:9px;color:#a0a0b0;max-width:180px;">{cmt}</td>
            </tr>'''
        return out

    def _section(title_text, color, items):
        label_html = (
            f'<div style="font-size:9px;letter-spacing:3px;color:{color};'
            f'border-bottom:2px solid {color};padding-bottom:6px;margin-bottom:10px;">'
            f'{title_text} ({len(items)}件)</div>'
        )
        tbl = f'''<div style="overflow-x:auto;margin-bottom:8px;">
          <table style="width:100%;border-collapse:collapse;">{TH}
            <tbody>{_rows(items)}</tbody>
          </table></div>'''
        return label_html + tbl

    # KPIカード HTML
    kpi_cards = ''
    for lbl, val, col in [
        ('番宣対象',     total,   '#f0ede8'),
        ('CSV照合成功',  csv_ok,  '#f5a623'),
        ('履歴比較成功', hist_ok, '#60a5fa'),
        ('効果あり',     eff_cnt, '#4ade80'),
        ('効果見えず',   neff,    '#f87171'),
        ('判定保留',     pend,    '#fbbf24'),
        ('要確認',       chk,     '#7a7a8c'),
    ]:
        kpi_cards += f'''<div style="background:#1c1c22;border:1px solid #2a2a35;border-radius:6px;
                            padding:12px 10px;text-align:center;">
          <div style="font-size:8px;letter-spacing:2px;color:#7a7a8c;margin-bottom:4px;">{lbl}</div>
          <div style="font-size:26px;font-weight:700;color:{col};">{val}</div>
          <div style="font-size:8px;color:#7a7a8c;">件</div>
        </div>'''

    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>BSよしもと 番宣効果判定レポート {year} W{week_num:02d}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Noto Sans JP", "Hiragino Kaku Gothic Pro", "Meiryo", sans-serif;
    background: #141418;
    color: #d0ccc8;
    font-size: 12px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .page {{
    width: 257mm;
    min-height: 182mm;
    padding: 14mm 14mm;
    background: #141418;
    margin: 0 auto;
    page-break-after: always;
  }}
  .page:last-child {{ page-break-after: auto; }}
  @page {{
    size: A4 landscape;
    margin: 0;
  }}
  @media print {{
    body {{ background: #141418; }}
    .page {{ page-break-after: always; }}
  }}
</style>
</head>
<body>

<!-- ═══ P1: 表紙 ═══════════════════════════════════ -->
<div class="page">
  <div style="border-left:5px solid #f5a623;padding:0 0 0 18px;margin-bottom:24px;">
    <div style="font-size:9px;letter-spacing:5px;color:#f5a623;margin-bottom:6px;">
      PROMOTION EFFECT JUDGEMENT REPORT
    </div>
    <div style="font-size:24px;font-weight:700;color:#f0ede8;line-height:1.3;">
      BSよしもと 番宣効果判定レポート
    </div>
    <div style="font-size:13px;color:#a0a0b0;margin-top:6px;">
      {year}年 第{week_num}週（{week_range}）
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:20px;">
    {kpi_cards}
  </div>

  <div style="background:#1c1c22;border-left:4px solid #f5a623;border-radius:4px;
              padding:14px 18px;">
    <div style="font-size:9px;letter-spacing:3px;color:#f5a623;margin-bottom:8px;">総評</div>
    <div style="font-size:12px;color:#d0ccc8;line-height:1.9;">{overview}</div>
  </div>
</div>

<!-- ═══ P2: 全件テーブル ═══════════════════════════ -->
<div class="page">
  <div style="font-size:9px;letter-spacing:4px;color:#f5a623;border-bottom:1px solid #f5a623;
              padding-bottom:6px;margin-bottom:14px;">全件 効果判定テーブル（{len(all_items)}件）</div>
  <div style="overflow-x:auto;">
  <table style="width:100%;border-collapse:collapse;">
    {TH}
    <tbody>{_rows(all_items)}</tbody>
  </table>
  </div>
</div>

<!-- ═══ P3: 判定別セクション ══════════════════════ -->
<div class="page">
  {_section("効果あり",   "#4ade80", effect)}
  {_section("効果見えず", "#f87171", no_effect)}
  {_section("判定保留",   "#fbbf24", pending)}
  {_section("要確認",     "#7a7a8c", needs_check)}
  <div style="margin-top:28px;padding-top:12px;border-top:1px solid #2a2a35;
              font-size:8px;color:#4a4a5a;text-align:center;">
    BSよしもと 編成制作局 ／ 視聴データ: REGZA ／ 生成: {generated_at}
  </div>
</div>

</body>
</html>'''
