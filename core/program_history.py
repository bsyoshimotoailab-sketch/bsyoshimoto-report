#!/usr/bin/env python3
"""
program_history.py
E2A から番組別週次実績を生成する
"""
import re


def build_program_weekly(df_e2a, year: int, week_num: int,
                          week_start, week_end) -> list:
    """
    E2Aから番組別週次実績を生成する。

    Returns: list of dicts — 1番組 1エントリ
    {
      year, week_num, week_start, week_end,
      program_title, normalized_title,
      broadcast_count, total_viewing_ppl, total_viewing_devices,
      avg_viewing_ppl, max_viewing_ppl,
      broadcast_dates, time_slots,
    }
    """
    import pandas as pd
    from core.promo_report import normalize_program_name

    name_col   = df_e2a.attrs.get('name_col', 'title')
    metric_col = 'Unnamed: 12' if 'Unnamed: 12' in df_e2a.columns else 'Unnamed: 13'
    date_cols  = [c for c in df_e2a.columns if
                  re.search(r'\d{1,2}/\d{1,2}', str(c)) or
                  re.fullmatch(r'\d{8}', str(c).strip())]

    ppl_df = df_e2a[df_e2a[metric_col].str.strip() == 'value_1_31'].copy()
    dev_df = df_e2a[df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12'].copy()

    ws_str = week_start.strftime('%Y/%m/%d') if hasattr(week_start, 'strftime') else str(week_start or '')
    we_str = week_end.strftime('%Y/%m/%d')   if hasattr(week_end,   'strftime') else str(week_end   or '')

    records = []
    for title in ppl_df[name_col].dropna().unique():
        title_str = str(title).strip()
        if not title_str:
            continue

        ppl_rows = ppl_df[ppl_df[name_col] == title]
        day_ppls        = []
        broadcast_dates = []
        for col in date_cols:
            v = pd.to_numeric(ppl_rows[col], errors='coerce').dropna()
            pos = v[v > 0]
            if not pos.empty:
                day_ppls.append(int(float(pos.sum()) * 1000))
                broadcast_dates.append(str(col))

        total_ppl       = sum(day_ppls)
        broadcast_count = len(day_ppls)
        avg_ppl         = int(total_ppl / broadcast_count) if broadcast_count else 0
        max_ppl         = max(day_ppls) if day_ppls else 0

        dev_rows  = dev_df[dev_df[name_col] == title]
        total_dev = 0
        for col in date_cols:
            v = pd.to_numeric(dev_rows[col], errors='coerce').dropna()
            total_dev += int(v[v > 0].sum())

        records.append({
            'year':                   year,
            'week_num':               week_num,
            'week_start':             ws_str,
            'week_end':               we_str,
            'program_title':          title_str,
            'normalized_title':       normalize_program_name(title_str),
            'broadcast_count':        broadcast_count,
            'total_viewing_ppl':      total_ppl,
            'total_viewing_devices':  total_dev,
            'avg_viewing_ppl':        avg_ppl,
            'max_viewing_ppl':        max_ppl,
            'broadcast_dates':        ','.join(broadcast_dates),
            'time_slots':             '',
        })

    return records
