#!/usr/bin/env python3
"""
promo_report.py
番宣効果検証ロジック
"""
import re
from datetime import datetime, date as _date


def to_date_safe(v):
    """pandas.Timestamp / datetime / date / str を datetime.date に統一。変換不能なら None"""
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
    """
    番宣期間文字列から (start_date, end_date) を返す。
    例: "5/12〜5/18", "2026/5/12〜5/18"
    解析失敗時は (None, None)
    """
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


def _get_past_avg(program: str, past_summaries: list) -> tuple:
    """
    過去summaryから同一番組の視聴人数平均を返す。
    Returns: (past_avg_ppl: int | None, past_weeks: int)
    """
    if not past_summaries:
        return None, 0

    norm_prog = normalize_program_name(program)
    past_ppls = []

    for s in past_summaries:
        for item in s.get('promo_items', []):
            if normalize_program_name(item.get('program', '')) == norm_prog:
                ppl = item.get('viewing_ppl', 0)
                if ppl and ppl > 0:
                    past_ppls.append(ppl)
                break  # 1 summary に同番組は1エントリ

    if not past_ppls:
        return None, 0
    return int(sum(past_ppls) / len(past_ppls)), len(past_ppls)


def _compute_judgment(viewing_ppl: int, past_avg_ppl, past_weeks: int) -> tuple:
    """
    Returns (judgment: str, judgment_detail: str, change_rate: float | None)
    """
    if viewing_ppl == 0:
        return '判定保留', '今週視聴データなし', None
    if not past_avg_ppl or past_avg_ppl == 0:
        return '今週実績のみ', '比較対象不足', None
    change_rate = (viewing_ppl - past_avg_ppl) / past_avg_ppl * 100
    detail = f'過去{past_weeks}週平均比 {change_rate:+.1f}%'
    if change_rate >= 20:
        return '◎ 効果あり', detail, change_rate
    elif change_rate >= 5:
        return '○ やや効果あり', detail, change_rate
    elif change_rate >= -5:
        return '△ 横ばい', detail, change_rate
    else:
        return '× 効果見えず', detail, change_rate


def build_promo_items(df_e2a, excel_path: str, week_start=None, week_end=None,
                      past_summaries=None) -> dict:
    """
    番宣ExcelとE2A CSVを照合してpromo結果dictを返す。

    Returns: {
        'matched':        [item, ...],  # 完全一致・候補一致 + 今週番宣期間に重なる
        'unmatched':      [item, ...],  # 不一致（要確認リスト）
        'unknown_period': [item, ...],  # 番宣期間空欄の番組
        'summary': {
            'total_promo':  int,
            'csv_matched':  int,
            'effect_found': int,
            'pending':      int,
            'needs_check':  int,
        }
    }
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

        # 番宣期間が空欄 → unknown_period へ（メイン表に出さない）
        period_clean = period if period not in ('nan', '—', '', 'None') else ''
        if not period_clean:
            norm = normalize_program_name(program)
            mt = '不一致'
            if norm in e2a_norm_map:
                mt = '完全一致'
            elif len(norm) >= 4:
                cands = [orig for key, orig in e2a_norm_map.items()
                         if norm[:8] in key or key[:8] in norm]
                if cands:
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
                    continue  # 今週と重ならない → スキップ

        # 番組名照合
        norm = normalize_program_name(program)
        match_type  = '不一致'
        match_title = ''
        if norm in e2a_norm_map:
            match_type  = '完全一致'
            match_title = e2a_norm_map[norm]
        elif len(norm) >= 4:
            cands = [orig for key, orig in e2a_norm_map.items()
                     if norm[:8] in key or key[:8] in norm]
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

        # 過去比較と判定
        past_avg_ppl, past_weeks = _get_past_avg(program, past_summaries)
        judgment, judgment_detail, change_rate = _compute_judgment(
            viewing_ppl, past_avg_ppl, past_weeks
        )

        item = {
            'program':         program,
            'period':          period_clean,
            'spots':           spots_val,
            'material':        material_val,
            'viewing_ppl':     viewing_ppl,
            'viewing_dev':     viewing_dev,
            'match_type':      match_type,
            'match_title':     match_title,
            'past_avg_ppl':    past_avg_ppl,
            'past_weeks':      past_weeks,
            'change_rate':     change_rate,
            'judgment':        judgment,
            'judgment_detail': judgment_detail,
            'comment':         judgment,  # 後方互換
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
