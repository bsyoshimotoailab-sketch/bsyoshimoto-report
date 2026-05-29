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
    name = name.replace('　', '').replace(' ', '')    # 全角・半角スペース削除
    name = name.replace('（', '(').replace('）', ')')  # 括弧を半角統一
    name = name.replace('【', '[').replace('】', ']')
    name = name.replace('・', '').replace('～', '〜')
    return name


def _parse_promo_period(period_str: str):
    """
    番宣期間文字列から (start_date, end_date) を返す。
    例: "5/12〜5/18", "2026/5/12〜5/18", "5/12-5/18"
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


def build_promo_items(df_e2a, excel_path: str, week_start=None, week_end=None) -> list:
    """
    番宣ExcelとE2A CSVを照合してpromo_itemsリストを返す。

    Returns: list of dict {
        program, period, spots, material,
        viewing_ppl, viewing_dev,
        match_type ('完全一致'|'候補一致'|'不一致'),
        match_title, comment
    }
    """
    import pandas as pd

    # Excel読み込み（シートなし・読み込み失敗を明示）
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

    # E2A から視聴行を事前抽出
    ppl_df = df_e2a[df_e2a[metric_col].str.strip() == 'value_1_31'].copy()
    dev_df = df_e2a[df_e2a[metric_col].str.strip() == 'E1A_HM_ツールヒント用列値_視聴機器数_12'].copy()

    # E2A 番組名を正規化してマップ化（正規化後 → 元の番組名）
    e2a_titles   = df_e2a[name_col].dropna().unique().tolist()
    e2a_norm_map = {}
    for t in e2a_titles:
        key = normalize_program_name(t)
        if key:
            e2a_norm_map[key] = t

    # week_start/end を date 型に統一
    ws_date = to_date_safe(week_start)
    we_date = to_date_safe(week_end)

    items = []
    for _, row in xl.iterrows():
        program  = str(row.get('番組名', '')).strip()
        period   = str(row.get('重点強化期間', '')).strip()
        spots    = str(row.get('SPOT回数', row.get('放送回数', ''))).strip()
        material = str(row.get('制作素材', '')).strip()

        if not program or program == 'nan':
            continue

        # 番宣期間チェック（今週と重ならなければスキップ）
        period_comment = None
        if ws_date and we_date and period not in ('nan', '—', ''):
            p_start, p_end = _parse_promo_period(period)
            # date 型に揃える（_parse_promo_period は既に date を返すが念のため）
            p_start = to_date_safe(p_start)
            p_end   = to_date_safe(p_end)
            if p_start and p_end:
                if we_date < p_start or ws_date > p_end:
                    continue
            else:
                period_comment = '番宣期間を確認してください'

        # 番組名照合
        norm = normalize_program_name(program)
        match_type  = '不一致'
        match_title = ''

        if norm in e2a_norm_map:
            match_type  = '完全一致'
            match_title = e2a_norm_map[norm]
        elif len(norm) >= 4:
            candidates = [
                orig for key, orig in e2a_norm_map.items()
                if norm[:8] in key or key[:8] in norm
            ]
            if candidates:
                match_type  = '候補一致'
                match_title = candidates[0]

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

        # 判定コメント
        if period_comment:
            comment = period_comment
        elif viewing_ppl > 0:
            tag     = '✅' if match_type == '完全一致' else '⚠️ 候補'
            comment = f'{tag} {viewing_ppl:,}人 / {viewing_dev:,}台'
        elif match_title:
            comment = '今週未放送（または視聴データなし）'
        else:
            comment = 'CSVに番組が見つかりません'

        items.append({
            'program':     program,
            'period':      period   if period   not in ('nan', '') else '—',
            'spots':       spots    if spots    not in ('nan', '') else '—',
            'material':    material if material not in ('nan', '') else '—',
            'viewing_ppl': viewing_ppl,
            'viewing_dev': viewing_dev,
            'match_type':  match_type,
            'match_title': match_title,
            'comment':     comment,
        })

    return items
