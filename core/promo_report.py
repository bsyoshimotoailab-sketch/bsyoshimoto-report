#!/usr/bin/env python3
"""
promo_report.py
番宣効果検証ロジック
"""
import re
from datetime import datetime, date as _date


def to_date_safe(v):
    """pandas.Timestamp / datetime / date / str を datetime.date に統一"""
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


def normalize_program_name(name: str) -> str:
    """番組名を正規化（スペース・記号ゆれを吸収）"""
    if not isinstance(name, str):
        return ''
    name = name.strip()
    name = name.replace('　', '').replace(' ', '')
    name = name.replace('（', '(').replace('）', ')')
    name = name.replace('【', '[').replace('】', ']')
    name = name.replace('・', '').replace('～', '〜')
    return name


def _parse_promo_period(period_str: str):
    """番宣期間文字列から (start_date, end_date) を返す。解析失敗時は (None, None)"""
    if not isinstance(period_str, str) or not period_str.strip() or period_str == 'nan':
        return None, None
    year = datetime.now().year
    m = re.search(r'(\d{1,2}/\d{1,2})[〜～\-]+(\d{1,2}/\d{1,2})', period_str)
    if m:
        try:
            start = datetime.strptime(f"{year}/{m.group(1)}", '%Y/%m/%d').date()
            end   = datetime.strptime(f"{year}/{m.group(2)}", '%Y/%m/%d').date()
            if end < start:
                end = end.replace(year=year + 1)
            return start, end
        except ValueError:
            pass
    return None, None


def _get_past_avg_from_history(normalized_title: str, prog_hist_df,
                                current_year: int, current_week_num: int,
                                n_weeks: int) -> tuple:
    """
    program_history_df から直近N週の視聴人数平均を返す。
    Returns: (avg_ppl: int | None, weeks_used: int)
    """
    if prog_hist_df is None or prog_hist_df.empty:
        return None, 0
    if 'normalized_title' not in prog_hist_df.columns:
        return None, 0

    df = prog_hist_df[prog_hist_df['normalized_title'] == normalized_title].copy()
    if df.empty:
        return None, 0

    # 現在週を除外
    cur_yr = int(current_year or 0)
    cur_wk = int(current_week_num or 0)
    if cur_yr and cur_wk:
        df = df[~((df['year'].astype(int) == cur_yr) & (df['week_num'].astype(int) == cur_wk))]

    df = df.sort_values(['year', 'week_num'], ascending=False).head(n_weeks)
    if df.empty:
        return None, 0

    valid = df['total_viewing_ppl'].dropna()
    valid = valid[valid > 0]
    if valid.empty:
        return None, 0
    return int(valid.mean()), len(valid)


def _get_past_avg_from_summaries(program: str, past_summaries: list,
                                  n_weeks: int = None) -> tuple:
    """
    summary dicts から同一番組の視聴人数平均を返す（フォールバック用）。
    Returns: (avg_ppl: int | None, weeks_used: int)
    """
    if not past_summaries:
        return None, 0
    norm = normalize_program_name(program)
    sorted_sums = sorted(
        past_summaries,
        key=lambda s: (s.get('year', 0), s.get('week_num', 0)),
        reverse=True,
    )
    if n_weeks:
        sorted_sums = sorted_sums[:n_weeks]
    ppls = []
    for s in sorted_sums:
        for item in s.get('promo_items', []):
            if normalize_program_name(item.get('program', '')) == norm:
                ppl = item.get('viewing_ppl', 0) or item.get('current_viewing_ppl', 0)
                if ppl and ppl > 0:
                    ppls.append(ppl)
                break
    if not ppls:
        return None, 0
    return int(sum(ppls) / len(ppls)), len(ppls)


def _compute_judgment(viewing_ppl: int,
                       past_4w_avg, past_4w_weeks: int,
                       past_13w_avg, past_13w_weeks: int) -> tuple:
    """
    Returns: (judgment, judgment_detail, diff_4w_pct, diff_13w_pct)
    判定は過去4週平均を優先、なければ13週平均を使う。
    """
    if viewing_ppl == 0:
        return '判定保留', '今週視聴データなし', None, None

    diff_4w  = (
        (viewing_ppl - past_4w_avg)  / past_4w_avg  * 100
        if past_4w_avg and past_4w_avg > 0 else None
    )
    diff_13w = (
        (viewing_ppl - past_13w_avg) / past_13w_avg * 100
        if past_13w_avg and past_13w_avg > 0 else None
    )

    primary_diff  = diff_4w  if diff_4w  is not None else diff_13w
    primary_weeks = past_4w_weeks if diff_4w is not None else past_13w_weeks

    if primary_diff is None:
        return '今週実績のみ', '比較対象不足', None, None

    detail = f'過去{primary_weeks}週平均比 {primary_diff:+.1f}%'
    if primary_diff >= 20:
        return '◎ 効果あり',    detail, diff_4w, diff_13w
    elif primary_diff >= 5:
        return '○ やや効果あり', detail, diff_4w, diff_13w
    elif primary_diff >= -5:
        return '△ 横ばい',      detail, diff_4w, diff_13w
    else:
        return '× 効果見えず',   detail, diff_4w, diff_13w


def build_promo_items(df_e2a, excel_path: str,
                      week_start=None, week_end=None,
                      past_summaries=None,
                      program_history_df=None,
                      current_year=None,
                      current_week_num=None) -> dict:
    """
    番宣ExcelとE2A CSVを照合してpromo結果dictを返す。

    Returns: {
        'matched':        [item, ...],  # 完全一致・候補一致 + 今週番宣期間に重なる
        'unmatched':      [item, ...],  # 不一致（要確認リスト）
        'unknown_period': [item, ...],  # 番宣期間空欄
        'summary': {
            'total_promo': int, 'csv_matched': int,
            'effect_found': int, 'pending': int, 'needs_check': int,
        }
    }

    各 item の比較フィールド:
        past_4w_avg_ppl, past_4w_weeks,
        past_13w_avg_ppl, past_13w_weeks,
        diff_4w_pct, diff_13w_pct,
        judgment, judgment_detail,
        # 後方互換
        past_avg_ppl (= past_4w_avg_ppl), past_weeks (= past_4w_weeks),
        change_rate  (= diff_4w_pct), comment (= judgment)
    """
    import pandas as pd

    try:
        xl = pd.read_excel(excel_path, sheet_name='サマリー', dtype=str).dropna(subset=['番組名'])
    except Exception as e:
        msg = str(e)
        if 'サマリー' in msg or 'Worksheet' in msg or 'sheet' in msg.lower():
            raise ValueError(
                "番宣Excelにシート「サマリー」が見つかりません。シート名を確認してください。"
            )
        raise

    name_col   = df_e2a.attrs.get('name_col', 'title')
    metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
    date_cols  = [c for c in df_e2a.columns if
                  re.search(r'\d{1,2}/\d{1,2}', str(c)) or
                  re.fullmatch(r'\d{8}', str(c).strip())]

    ppl_df = df_e2a[df_e2a[metric_col].str.strip() == 'value_1_31'].copy()
    dev_df = df_e2a[df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12'].copy()

    e2a_norm_map = {}
    for t in df_e2a[name_col].dropna().unique():
        key = normalize_program_name(t)
        if key:
            e2a_norm_map[key] = t

    ws_date = to_date_safe(week_start)
    we_date = to_date_safe(week_end)

    # 現在年・週を確定
    cur_year = current_year or (we_date.year if we_date else datetime.now().year)
    cur_wk   = current_week_num or 0

    matched        = []
    unmatched      = []
    unknown_period = []

    for _, row in xl.iterrows():
        program  = str(row.get('番組名', '')).strip()
        period   = str(row.get('重点強化期間', '')).strip()
        spots    = str(row.get('SPOT回数', row.get('放送回数', ''))).strip()
        material = str(row.get('制作素材', '')).strip()

        if not program or program == 'nan':
            continue

        spots_val    = spots    if spots    not in ('nan', '') else '—'
        material_val = material if material not in ('nan', '') else '—'

        # 番宣期間が空欄 → unknown_period
        period_clean = period if period not in ('nan', '—', '', 'None') else ''
        if not period_clean:
            norm = normalize_program_name(program)
            mt = '不一致'
            if norm in e2a_norm_map:
                mt = '完全一致'
            elif len(norm) >= 4:
                if any(norm[:8] in k or k[:8] in norm for k in e2a_norm_map):
                    mt = '候補一致'
            unknown_period.append({
                'program': program, 'period': '—',
                'spots': spots_val, 'material': material_val,
                'match_type': mt, 'comment': '番宣期間未設定',
            })
            continue

        # 今週との重なりチェック
        p_start, p_end = _parse_promo_period(period_clean)
        p_start = to_date_safe(p_start)
        p_end   = to_date_safe(p_end)
        if ws_date and we_date and p_start and p_end:
            if isinstance(we_date, _date) and isinstance(p_start, _date):
                if we_date < p_start or ws_date > p_end:
                    continue

        # 番組名照合
        norm = normalize_program_name(program)
        match_type  = '不一致'
        match_title = ''
        if norm in e2a_norm_map:
            match_type  = '完全一致'
            match_title = e2a_norm_map[norm]
        elif len(norm) >= 4:
            cands = [orig for k, orig in e2a_norm_map.items()
                     if norm[:8] in k or k[:8] in norm]
            if cands:
                match_type  = '候補一致'
                match_title = cands[0]

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

        # 過去比較（program_history_df → past_summaries の優先順）
        norm_title = normalize_program_name(program)

        past_4w_avg, past_4w_weeks = _get_past_avg_from_history(
            norm_title, program_history_df, cur_year, cur_wk, 4)
        if past_4w_avg is None:
            past_4w_avg, past_4w_weeks = _get_past_avg_from_summaries(
                program, past_summaries, 4)

        past_13w_avg, past_13w_weeks = _get_past_avg_from_history(
            norm_title, program_history_df, cur_year, cur_wk, 13)
        if past_13w_avg is None:
            past_13w_avg, past_13w_weeks = _get_past_avg_from_summaries(
                program, past_summaries, 13)

        judgment, j_detail, diff_4w, diff_13w = _compute_judgment(
            viewing_ppl, past_4w_avg, past_4w_weeks, past_13w_avg, past_13w_weeks,
        )

        item = {
            # 基本情報
            'program':            program,
            'period':             period_clean,
            'spots':              spots_val,
            'material':           material_val,
            'match_type':         match_type,
            'match_title':        match_title,
            'normalized_title':   norm_title,
            # 今週実績
            'viewing_ppl':            viewing_ppl,  # 後方互換
            'viewing_dev':            viewing_dev,  # 後方互換
            'current_viewing_ppl':    viewing_ppl,
            'current_viewing_devices': viewing_dev,
            # 過去比較
            'past_4w_avg_ppl':    past_4w_avg,
            'past_4w_weeks':      past_4w_weeks,
            'past_13w_avg_ppl':   past_13w_avg,
            'past_13w_weeks':     past_13w_weeks,
            'diff_4w_pct':        diff_4w,
            'diff_13w_pct':       diff_13w,
            # 後方互換
            'past_avg_ppl':       past_4w_avg,
            'past_weeks':         past_4w_weeks,
            'change_rate':        diff_4w,
            # 判定
            'judgment':           judgment,
            'judgment_detail':    j_detail,
            'comment':            judgment,
        }

        if match_type in ('完全一致', '候補一致'):
            matched.append(item)
        else:
            unmatched.append(item)

    effect_found = sum(1 for i in matched if i['judgment'] in ('◎ 効果あり', '○ やや効果あり'))
    pending      = sum(1 for i in matched if i['judgment'] in ('判定保留', '今週実績のみ'))

    return {
        'matched':        matched,
        'unmatched':      unmatched,
        'unknown_period': unknown_period,
        'summary': {
            'total_promo':  len(matched) + len(unmatched),
            'csv_matched':  len(matched),
            'effect_found': effect_found,
            'pending':      pending,
            'needs_check':  len(unmatched),
        },
    }
