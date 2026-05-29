#!/usr/bin/env python3
"""
backfill_history.py
archive / Ratings-archive フォルダ内の過去E2A CSVから番組別週次実績を再構築する
"""
from datetime import timedelta, datetime


def build_history_from_archive(folder_id: str) -> dict:
    """
    Drive の archive 系フォルダから E2A CSV を全件読み込み番組別週次実績を再構築する。

    Returns: {
        'weekly': {
            (year, week_num): {
                'records':    list,       # build_program_weekly の出力
                'summary':    dict|None,  # E1A+ランキングが揃った週のみ
                'week_start': date,
                'week_end':   date,
                'week_range': str,
            }
        },
        'e2a_count':     int,
        'success_count': int,
        'skipped':       [(name, reason), ...],
    }
    """
    from core.drive_helper import get_all_archive_csvs, download_to_tempfile
    from core.generate_report import load_e2a, detect_week_info
    from core.program_history import build_program_weekly

    csv_sets = get_all_archive_csvs(folder_id)
    e2a_files = sorted(
        [f for f in csv_sets['e2a'] if f['date'] is not None],
        key=lambda x: x['date'],
    )
    e1a_files  = csv_sets['e1a']
    rank_files = csv_sets['rank']

    weekly: dict = {}
    skipped: list = []

    for entry in e2a_files:
        name     = entry['name']
        week_end = entry['date']
        week_start = week_end - timedelta(days=6)
        year       = week_end.year

        try:
            tmp = download_to_tempfile(entry['id'], suffix='.csv')
            df_e2a = load_e2a(tmp)
        except Exception as ex:
            skipped.append((name, f'読み込みエラー: {ex}'))
            continue

        try:
            week_num, week_range = detect_week_info(df_e2a)
        except Exception:
            week_num   = week_end.isocalendar()[1]
            week_range = (f'{week_start.month}/{week_start.day}'
                          f'〜{week_end.month}/{week_end.day}')

        try:
            records = build_program_weekly(df_e2a, year, week_num, week_start, week_end)
        except Exception as ex:
            skipped.append((name, f'番組履歴生成エラー: {ex}'))
            continue

        summary = None
        try:
            summary = _try_build_summary(
                df_e2a, year, week_num, week_range, week_start, week_end,
                e1a_files, rank_files,
            )
        except Exception:
            pass

        key = (year, week_num)
        if key in weekly:
            weekly[key]['records'] = records
            if summary:
                weekly[key]['summary'] = summary
        else:
            weekly[key] = {
                'records':    records,
                'summary':    summary,
                'week_start': week_start,
                'week_end':   week_end,
                'week_range': week_range,
            }

    return {
        'weekly':        weekly,
        'e2a_count':     len(e2a_files),
        'success_count': len(weekly),
        'skipped':       skipped,
    }


def _try_build_summary(df_e2a, year, week_num, week_range,
                        week_start, week_end,
                        e1a_files, rank_files) -> dict:
    """E1A（5本以上）とランキングが揃っていればサマリーを生成して返す"""
    from core.drive_helper import download_to_tempfile
    from core.generate_report import (
        load_e1a, load_ranking, analyze_e1a, analyze_ranking,
        calculate_total_ppl,
    )

    e1a_in_week = [
        f for f in e1a_files
        if f['date'] is not None and week_start <= f['date'] <= week_end
    ]
    if len(e1a_in_week) < 5:
        raise ValueError(f'E1Aが{len(e1a_in_week)}本しかありません（5本以上必要）')

    rank_match = [f for f in rank_files if f['date'] == week_end]
    if not rank_match:
        raise ValueError(f'ランキングCSVが見つかりません（{week_end}）')

    e1a_paths = [download_to_tempfile(f['id'], suffix='.csv') for f in e1a_in_week]
    rank_path = download_to_tempfile(rank_match[0]['id'], suffix='.csv')

    df_e1a   = load_e1a(e1a_paths)
    rank_df  = load_ranking(rank_path)
    e1a_data = analyze_e1a(df_e1a)
    rank_data = analyze_ranking(rank_df)
    total_ppl, total_count = calculate_total_ppl(df_e2a)

    return {
        'year':                year,
        'week_num':            week_num,
        'week_start':          week_start.strftime('%Y/%m/%d'),
        'week_end':            week_end.strftime('%Y/%m/%d'),
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
