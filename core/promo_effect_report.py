#!/usr/bin/env python3
"""
promo_effect_report.py
番宣効果判定レポート v3
E1A_HM_番組単位YYYYMMDD.csv（日別）を使い週合計 → 過去4週平均と比較する。
"""
import io
import re
import unicodedata
from datetime import datetime, date as _date, timedelta


# ══════════════════════════════════════════════════════════
# 番組名正規化
# ══════════════════════════════════════════════════════════

_STRIP_SUFFIX = re.compile(
    r'[\s　（(【\[]*(?:再放送|字幕版?|終映?|初回?|字|再|新|HD|SD)[）)】\]]*[\s　]*$'
)

def normalize_program_title(name: str) -> str:
    """NFKC + 付加表記除去 + 記号/スペース除去（基本正規化）"""
    if not isinstance(name, str):
        return ''
    name = name.strip()
    name = _STRIP_SUFFIX.sub('', name)
    name = unicodedata.normalize('NFKC', name)
    name = re.sub(r'[【】\[\]（）()\s　・〜～★☆◆◇●○□■▲△▼▽「」『』、。！!？?…]', '', name)
    return name.strip()


def normalize_for_match(name: str) -> str:
    """照合用強化正規化: ワク枠/番宣/話数表記も除去する"""
    if not isinstance(name, str):
        return ''
    n = name.strip()
    # ワク枠/番宣 プレフィックス除去
    n = re.sub(r'^(?:ワク枠?|個別番宣|番宣)\s*[「『]?', '', n)
    # 末尾 番宣/個別番宣サフィックス除去
    n = re.sub(r'[」』]?\s*(?:個別番宣|番宣)\s*$', '', n)
    # 末尾「仮」除去
    n = re.sub(r'\s*仮\s*$', '', n)
    # 末尾「…」除去
    n = re.sub(r'[…]+$', '', n)
    # 話数表記除去（末尾）
    n = re.sub(r'\s*(?:前編|中編|後編|前半|後半|[#＃][0-9０-９]+)\s*$', '', n)
    return normalize_program_title(n)


# ══════════════════════════════════════════════════════════
# エイリアス辞書（normalize_for_match 後キー）
# ══════════════════════════════════════════════════════════

_NORM_ALIAS: dict = {
    '第一芸人文芸部俺の推し本': ['第一芸人文芸部'],
    'マヂカルラブリー村上の本気でカルチャーをラブしてリスペクトする会': [
        'マヂカルラブリー村上本気でカルチャーをラブしてリスペクトする会',
    ],
    'ガクテンソク奥田の歴史雑談': ['ガクテンソク奥田歴史雑談'],
    'ガクテンソク奥田歴史雑談': ['ガクテンソク奥田の歴史雑談'],
    '東野岡村の旅猿26プライベートでごめんなさい': ['東野岡村の旅猿26'],
    '東野岡村の旅猿26': ['東野岡村の旅猿26プライベートでごめんなさい'],
}


# ══════════════════════════════════════════════════════════
# 非番組行フィルタ
# ══════════════════════════════════════════════════════════

_NON_PROGRAM_RE = re.compile(
    r'（案）|＜考え方＞|SPOTのヤマ|ターゲット(?:の差別化)?|YouTubeを含む|SNS活用|'
    r'考え方|差別化|強化方針|方針|ポイント|狙い|メモ|説明|備考|'
    r'^[\s　]*[▶◆※●■▲]'
)


def _is_non_program(name: str) -> tuple:
    """Returns (True, reason) or (False, '')"""
    if not isinstance(name, str):
        return True, 'nan/非文字列'
    n = name.strip()
    if not n or n == 'nan':
        return True, '空白行'
    if _NON_PROGRAM_RE.search(n):
        return True, '説明行キーワード含む'
    # 長文説明行（30文字超 かつ 読点・全角スペースを含む）
    if len(n) > 30 and re.search(r'[、。　]', n):
        return True, '長文説明行'
    return False, ''


# ══════════════════════════════════════════════════════════
# 日付ユーティリティ
# ══════════════════════════════════════════════════════════

def _to_date(v):
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


def _parse_promo_period(period_str: str, ref_year: int = None):
    """番宣期間文字列 → (start_date, end_date)"""
    if not isinstance(period_str, str):
        return None, None
    s = period_str.strip()
    if not s or s in ('nan', 'None', '—', '-', 'ー'):
        return None, None

    year = ref_year or datetime.now().year

    def _d(mo, da):
        try:
            return _date(year, int(mo), int(da))
        except (ValueError, TypeError):
            return None

    SEP = r'[〜～\-→~]'

    full_ranges = re.findall(
        rf'(\d{{1,2}})/(\d{{1,2}})\s*(?:or\d+)?\s*{SEP}+\s*(\d{{1,2}})/(\d{{1,2}})',
        s,
    )
    if full_ranges:
        starts = [_d(m[0], m[1]) for m in full_ranges]
        ends   = [_d(m[2], m[3]) for m in full_ranges]
        starts = [d for d in starts if d]
        ends   = [d for d in ends   if d]
        if starts:
            start = min(starts)
            end   = max(ends) if ends else None
            if end and end < start:
                end = end.replace(year=year + 1)
            return start, end

    m = re.search(
        rf'(\d{{1,2}})/(\d{{1,2}})\s*(?:or\d+)?\s*{SEP}+\s*(\d{{1,2}})(?!\s*/\d)',
        s,
    )
    if m:
        start = _d(m.group(1), m.group(2))
        end   = _d(m.group(1), m.group(3))
        if start:
            if end and end < start:
                end = None
            return start, end

    m = re.search(
        rf'(\d{{1,2}})/(\d{{1,2}})\s*(?:or\d+)?\s*{SEP}',
        s,
    )
    if m:
        start = _d(m.group(1), m.group(2))
        return start, None

    m = re.search(r'(\d{1,2})/(\d{1,2})', s)
    if m:
        start = _d(m.group(1), m.group(2))
        return start, None

    return None, None


# ══════════════════════════════════════════════════════════
# E1A 番組単位 CSV 読み込み・視聴人数抽出
# ══════════════════════════════════════════════════════════

def load_e1a_bangumi(raw_bytes: bytes):
    """
    E1A_HM_番組単位YYYYMMDD.csv をバイト列から読み込む。
    E2A と同形式（UTF-16 TSV）。BSよしもとにフィルタ。
    """
    import pandas as pd

    YOSHIMOTO = 'BSよしもと'
    EXCLUDE = ['テレビショッピング', 'お買い物情報', 'ショップチャンネル', 'ウェザーニュース']

    try:
        df = pd.read_csv(io.BytesIO(raw_bytes), encoding='utf-16', sep='\t',
                         dtype=str, low_memory=False)
    except Exception:
        # フォールバック: utf-8
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding='utf-8-sig', sep='\t',
                             dtype=str, low_memory=False)
        except Exception:
            df = pd.read_csv(io.BytesIO(raw_bytes), encoding='utf-8', sep=',',
                             dtype=str, low_memory=False)

    ch_col = next((c for c in df.columns if 'CH' in str(c) and '枝番' in str(c)), None)
    if ch_col:
        df = df[df[ch_col].str.strip() == YOSHIMOTO].copy()

    name_col = next((c for c in df.columns if str(c).strip() == 'title'), None)
    if name_col:
        for ex in EXCLUDE:
            df = df[~df[name_col].str.contains(ex, na=False)]

    df.attrs['name_col'] = name_col or 'title'
    return df


def _get_date_cols(df) -> list:
    return [c for c in df.columns if
            re.search(r'\d{1,2}/\d{1,2}', str(c)) or
            re.fullmatch(r'\d{8}', str(c).strip())]


def _get_metric_col(df) -> str:
    for candidate in ('Unnamed: 12', 'Unnamed: 13'):
        if candidate in df.columns:
            return candidate
    return ''


def build_e1a_norm_map(e1a_dfs: list) -> dict:
    """
    E1A DataFrames のリストから「正規化タイトル → 元タイトル」マップを作る。
    """
    norm_map: dict = {}
    for df in e1a_dfs:
        name_col = df.attrs.get('name_col', 'title')
        if name_col not in df.columns:
            continue
        for t in df[name_col].dropna().unique():
            t_str = str(t).strip()
            if not t_str:
                continue
            key = normalize_for_match(t_str)
            if key and key not in norm_map:
                norm_map[key] = t_str
    return norm_map


def _find_match(norm_promo: str, e1a_norm_map: dict) -> tuple:
    """Returns (match_type, original_title)"""
    if norm_promo in e1a_norm_map:
        return '完全一致', e1a_norm_map[norm_promo]

    for alias in _NORM_ALIAS.get(norm_promo, []):
        if alias in e1a_norm_map:
            return 'エイリアス一致', e1a_norm_map[alias]

    # 部分一致（正規化後8文字以上）
    if len(norm_promo) >= 8:
        for k, v in e1a_norm_map.items():
            if norm_promo[:8] in k or k[:8] in norm_promo:
                return '部分一致', v

    # 短い名前の包含一致（4文字以上）
    if len(norm_promo) >= 4:
        for k, v in e1a_norm_map.items():
            if norm_promo in k or k in norm_promo:
                return '部分一致', v

    return '不一致', ''


def get_weekly_viewers(match_title: str, e1a_dfs: list) -> int:
    """
    複数の日別 E1A DataFrames から指定番組の週合計視聴人数を返す。
    value_1_31 × 1000 を各日合計する。
    """
    import pandas as pd
    total = 0
    for df in e1a_dfs:
        name_col = df.attrs.get('name_col', 'title')
        if name_col not in df.columns:
            continue
        metric_col = _get_metric_col(df)
        if not metric_col:
            continue
        date_cols = _get_date_cols(df)
        if not date_cols:
            continue

        ppl_rows = df[
            (df[metric_col].str.strip() == 'value_1_31') &
            (df[name_col] == match_title)
        ]
        for col in date_cols:
            v = pd.to_numeric(ppl_rows[col], errors='coerce').dropna()
            v = v[v > 0]
            if not v.empty:
                total += int(float(v.sum()) * 1000)
    return total


def compute_past_4w_avg(norm_promo: str, match_title: str,
                         past_weeks_e1a: dict) -> tuple:
    """
    過去4週の E1A DataFrames から週平均を計算する。

    past_weeks_e1a: {week_label: [df, ...]}
    Returns: (avg_viewers: int|None, weeks_used: int, weekly_totals: list)
    """
    weekly_totals = []
    for week_label, dfs in sorted(past_weeks_e1a.items()):
        if not dfs:
            continue
        # match_title が既に判明している場合はそのまま使用
        t = match_title
        if not t:
            past_map = build_e1a_norm_map(dfs)
            _, t = _find_match(norm_promo, past_map)
        if not t:
            continue
        total = get_weekly_viewers(t, dfs)
        if total > 0:
            weekly_totals.append(total)

    if not weekly_totals:
        return None, 0, []

    avg = int(sum(weekly_totals) / len(weekly_totals))
    return avg, len(weekly_totals), weekly_totals


# ══════════════════════════════════════════════════════════
# 判定ロジック
# ══════════════════════════════════════════════════════════

def judge_promo_effect(viewing_ppl: int, match_type: str,
                        past_4w_avg, past_4w_weeks: int):
    """
    Returns: (judgment, comment, diff_pct)

    判定基準:
      効果あり  : 今週 >= 過去4週平均 × 120%
      微増      : 今週 >= 過去4週平均 × 105%（120%未満）
      効果見えず: 今週 < 過去4週平均 × 105%
      判定保留  : 比較可能週2週未満 または 番組名照合不可
    """
    if match_type == '不一致':
        return ('判定保留',
                '番組名照合ができませんでした。番宣リストの番組名表記を確認してください。',
                None)

    if viewing_ppl == 0:
        return ('判定保留',
                '今週の視聴データが0または取得できませんでした。',
                None)

    if past_4w_avg is None or past_4w_weeks < 2:
        wk = past_4w_weeks or 0
        return ('判定保留',
                f'比較可能な過去データが{wk}週分しかありません（2週以上必要）。',
                None)

    diff_pct = (viewing_ppl - past_4w_avg) / past_4w_avg * 100 if past_4w_avg > 0 else None

    if diff_pct is None:
        return ('判定保留', '過去4週平均が0のため比較できません。', None)

    if diff_pct >= 20.0:
        return ('効果あり',
                f'過去4週平均比 {diff_pct:+.1f}%。番宣効果が出た可能性があります。',
                diff_pct)
    elif diff_pct >= 5.0:
        return ('微増',
                f'過去4週平均比 {diff_pct:+.1f}%。小幅な増加が見られます。継続監視を推奨します。',
                diff_pct)
    else:
        return ('効果見えず',
                f'過去4週平均比 {diff_pct:+.1f}%。今週は番宣効果を確認できませんでした。',
                diff_pct)


# ══════════════════════════════════════════════════════════
# 番宣効果アイテム構築
# ══════════════════════════════════════════════════════════

def build_promo_effect_items(promo_items: list,
                              current_e1a_dfs: list,
                              past_weeks_e1a: dict,
                              week_start=None,
                              week_end=None,
                              cur_year: int = None,
                              cur_week_num: int = None,
                              # 後方互換（使用しない）
                              df_e2a=None,
                              prog_hist_df=None,
                              e2a_filename: str = '') -> dict:
    """
    番宣リストと E1A 日別CSVを照合して効果判定結果を返す。

    Parameters
    ----------
    promo_items    : load_ai_promo_tab() の戻り値
    current_e1a_dfs: 今週の E1A 日別 DataFrame リスト（7本）
    past_weeks_e1a : 過去4週の E1A DataFrames dict {week_label: [df, ...]}
    week_start/end : 対象週
    """
    ws_date = _to_date(week_start)
    we_date = _to_date(week_end)
    ref_yr  = cur_year or (we_date.year if we_date else datetime.now().year)

    # 今週の E1A から番組名正規化マップを構築
    current_norm_map = build_e1a_norm_map(current_e1a_dfs)

    target_items       = []
    out_of_range       = []
    period_unparseable = []
    period_unset       = []
    effect_list        = []
    slight_increase_list = []
    no_effect_list     = []
    pending_list       = []
    unmatched_list     = []
    non_program_count  = 0
    promo_total        = 0
    debug_unmatched    = []

    for row in promo_items:
        program  = str(row.get('番組名', '')).strip()
        period   = str(row.get('重点強化期間', '')).strip()
        spots    = str(row.get('SPOT回数', row.get('放送回数', ''))).strip()
        material = str(row.get('制作素材', '')).strip()

        is_skip, _ = _is_non_program(program)
        if is_skip or program == 'nan':
            non_program_count += 1
            continue

        promo_total += 1
        spots_val    = spots    if spots    not in ('nan', '') else '—'
        material_val = material if material not in ('nan', '') else '—'
        norm         = normalize_for_match(program)
        period_clean = period if period not in ('nan', '—', '', 'None') else ''

        # ── 期間未設定 ──────────────────────────────────────────
        if not period_clean:
            period_unset.append(_make_item(
                program=program, period='（未設定）', spots=spots_val,
                material=material_val, norm=norm,
                parsed_start=None, parsed_end=None,
                match_type='—', match_title='',
                viewing_ppl=0, past_4w_avg=None, past_4w_weeks=0,
                weekly_totals=[], diff_pct=None,
                judgment='期間未設定',
                comment='重点強化期間が設定されていません。',
                category='unset',
            ))
            continue

        # ── 期間解析 ────────────────────────────────────────────
        p_start, p_end = _parse_promo_period(period_clean, ref_yr)

        if p_start is None:
            period_unparseable.append(_make_item(
                program=program, period=period_clean, spots=spots_val,
                material=material_val, norm=norm,
                parsed_start=None, parsed_end=None,
                match_type='—', match_title='',
                viewing_ppl=0, past_4w_avg=None, past_4w_weeks=0,
                weekly_totals=[], diff_pct=None,
                judgment='期間解析不可',
                comment=f'「{period_clean}」を解析できません。MM/DD〜MM/DD 形式で入力してください。',
                category='unparseable',
            ))
            continue

        # ── 対象週チェック ───────────────────────────────────────
        if ws_date is not None:
            if p_end is not None and p_end < ws_date:
                out_of_range.append(_make_item(
                    program=program, period=period_clean, spots=spots_val,
                    material=material_val, norm=norm,
                    parsed_start=p_start, parsed_end=p_end,
                    match_type='対象外', match_title='',
                    viewing_ppl=0, past_4w_avg=None, past_4w_weeks=0,
                    weekly_totals=[], diff_pct=None,
                    judgment='対象外',
                    comment=f'番宣期間終了({p_end})。今週({ws_date}〜{we_date})より前。',
                    category='out_of_range',
                ))
                continue

        if we_date is not None and p_start > we_date:
            continue  # 未開始

        # ── E1A 照合 ────────────────────────────────────────────
        match_type, match_title = _find_match(norm, current_norm_map)

        # ── 今週視聴人数 ────────────────────────────────────────
        viewing_ppl = 0
        if match_title:
            viewing_ppl = get_weekly_viewers(match_title, current_e1a_dfs)

        # ── 過去4週平均 ─────────────────────────────────────────
        past_4w_avg, past_4w_wk, weekly_totals = compute_past_4w_avg(
            norm, match_title, past_weeks_e1a,
        )

        # ── 判定 ────────────────────────────────────────────────
        judgment, comment, diff_pct = judge_promo_effect(
            viewing_ppl, match_type, past_4w_avg, past_4w_wk,
        )

        item = _make_item(
            program=program, period=period_clean, spots=spots_val,
            material=material_val, norm=norm,
            parsed_start=p_start, parsed_end=p_end,
            match_type=match_type, match_title=match_title,
            viewing_ppl=viewing_ppl, past_4w_avg=past_4w_avg,
            past_4w_weeks=past_4w_wk, weekly_totals=weekly_totals,
            diff_pct=diff_pct, judgment=judgment, comment=comment,
            category='target',
        )
        target_items.append(item)

        if judgment == '効果あり':
            effect_list.append(item)
        elif judgment == '微増':
            slight_increase_list.append(item)
        elif judgment == '効果見えず':
            no_effect_list.append(item)
        else:
            pending_list.append(item)
            if match_type == '不一致':
                unmatched_list.append(item)
                debug_unmatched.append(program)

    csv_ok = sum(1 for it in target_items
                 if it['match_type'] in ('完全一致', 'エイリアス一致', '部分一致'))

    return {
        'target_items':        target_items,
        'all_items':           target_items,
        'out_of_range':        out_of_range,
        'period_unparseable':  period_unparseable,
        'period_unset':        period_unset,
        'effect':              effect_list,
        'slight_increase':     slight_increase_list,
        'no_effect':           no_effect_list,
        'pending':             pending_list,
        'unmatched':           unmatched_list,
        'needs_check':         unmatched_list,
        'debug_unmatched':     debug_unmatched,
        'current_norm_map':    current_norm_map,
        'summary': {
            'excel_total':          promo_total,
            'non_program_excluded': non_program_count,
            'out_of_range':         len(out_of_range),
            'period_unparseable':   len(period_unparseable),
            'period_unset':         len(period_unset),
            'target_total':         len(target_items),
            'csv_matched':          csv_ok,
            'effect_found':         len(effect_list),
            'slight_increase':      len(slight_increase_list),
            'no_effect':            len(no_effect_list),
            'pending':              len(pending_list),
            'unmatched':            len(unmatched_list),
            'needs_check':          len(unmatched_list),
            'total_promo':          len(target_items),
            'hist_compared':        csv_ok,
            'pdf_ok':               len(target_items) > 0,
        },
    }


def _make_item(*, program, period, spots, material, norm,
               parsed_start, parsed_end,
               match_type, match_title,
               viewing_ppl, past_4w_avg, past_4w_weeks,
               weekly_totals, diff_pct, judgment, comment, category):
    return {
        'program':          program,
        'period':           period,
        'spots':            spots,
        'material':         material,
        'normalized_title': norm,
        'parsed_start':     str(parsed_start) if parsed_start else '',
        'parsed_end':       (str(parsed_end) if parsed_end
                             else ('（終了日なし）' if parsed_start else '')),
        'match_type':       match_type,
        'match_title':      match_title,
        'viewing_ppl':      viewing_ppl,
        'past_4w_avg_ppl':  past_4w_avg,
        'past_4w_weeks':    past_4w_weeks,
        'past_4w_weekly_totals': weekly_totals,
        'diff_4w_pct':      diff_pct,
        # 後方互換
        'past_13w_avg_ppl': None,
        'past_13w_weeks':   0,
        'diff_13w_pct':     None,
        'judgment':         judgment,
        'comment':          comment,
        'compare_reason':   comment,
        'category':         category,
        'similar_titles':   [],
        'ppl_source':       'E1A',
        'ppl_source_file':  'E1A_HM_番組単位*.csv',
        'ppl_source_week':  '',
        'is_memo_derived':  False,
        'promo_source':     'AI判定用_AUTO (Sheets)',
        # 後方互換キー（hist_unavail 等で参照される可能性）
        'e2a_norm':         norm,
        'hist_key':         norm,
        'viewing_dev':      0,
    }


# ══════════════════════════════════════════════════════════
# 後方互換: load_program_history_master（週次レポートから呼ばれる場合用）
# ══════════════════════════════════════════════════════════

def load_program_history_master(root_id: str):
    import io as _io, pandas as pd
    debug = {
        'folder_found': False, 'files_found': [], 'csv_filename': None,
        'source': 'program_history_MASTER.csv', 'row_count': 0,
        'week_count': 0, 'program_count': 0, 'weeks': [], 'columns': [],
        'ppl_column': None, 'error': None,
    }
    try:
        from core.history_store import get_archive_folder
        from core.drive_helper import list_files_in_folder, download_file
        folder_id = get_archive_folder(root_id, 'program')
        debug['folder_found'] = folder_id is not None
        if folder_id is None:
            debug['error'] = '05_番組別履歴フォルダが見つかりません。'
            return pd.DataFrame(), debug
        all_files = list_files_in_folder(folder_id)
        debug['files_found'] = [f['name'] for f in all_files]
        master_files = [f for f in all_files if f['name'] == 'program_history_MASTER.csv']
        if not master_files:
            debug['error'] = 'program_history_MASTER.csv が見つかりません。'
            return pd.DataFrame(), debug
        debug['csv_filename'] = master_files[0]['name']
        raw = download_file(master_files[0]['id'])
        df = pd.read_csv(_io.BytesIO(raw), encoding='utf-8-sig', dtype=str)
        debug['columns'] = list(df.columns)
        for col in ('year', 'week', 'viewers', 'air_count'):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        name_col = 'program_name' if 'program_name' in df.columns else None
        if name_col:
            df['normalized_title'] = df[name_col].apply(
                lambda x: normalize_for_match(str(x)) if isinstance(x, str) else ''
            )
        debug['ppl_column'] = 'viewers' if 'viewers' in df.columns else None
        debug['row_count'] = len(df)
        if 'year' in df.columns and 'week' in df.columns:
            wdf = df[['year', 'week']].drop_duplicates().dropna()
            debug['week_count'] = len(wdf)
            debug['weeks'] = sorted([
                f"{int(r['year'])}W{int(r['week']):02d}" for _, r in wdf.iterrows()
            ])
        if name_col:
            debug['program_count'] = df[name_col].nunique()
        return df, debug
    except Exception as e:
        import traceback
        debug['error'] = f'{e}\n{traceback.format_exc()[:400]}'
        import pandas as pd
        return pd.DataFrame(), debug


def load_program_history(root_id: str):
    return load_program_history_master(root_id)


# ══════════════════════════════════════════════════════════
# PDF HTML 生成
# ══════════════════════════════════════════════════════════

def build_promo_effect_html(result: dict, week_range: str,
                             week_num: int, year: int) -> str:
    sm             = result['summary']
    effect         = result['effect']
    slight         = result.get('slight_increase', [])
    no_effect      = result['no_effect']
    pending        = result['pending']
    unmatched      = result.get('unmatched', [])
    out_of_range   = result.get('out_of_range', [])
    period_unset   = result.get('period_unset', [])

    eff_cnt    = sm['effect_found']
    slight_cnt = sm.get('slight_increase', 0)
    neff_cnt   = sm['no_effect']
    pend_cnt   = sm['pending']
    total      = sm['target_total']
    matched    = sm['csv_matched']

    # 総評テキスト
    watch_list = [it['program'] for it in effect + slight]
    overview_parts = [
        f'今週の判定対象番組は{total}件。',
        f'E1A照合成功: {matched}件。',
    ]
    if eff_cnt:
        overview_parts.append(f'【効果あり】{eff_cnt}件 — 番宣効果が確認できました。')
    if slight_cnt:
        overview_parts.append(f'【微増】{slight_cnt}件 — 小幅な上乗せが見られます。')
    if neff_cnt:
        overview_parts.append(f'【効果見えず】{neff_cnt}件。')
    if pend_cnt:
        overview_parts.append(f'【判定保留】{pend_cnt}件（過去データ不足・照合不可等）。')
    overview = '　'.join(overview_parts)

    JCOLOR = {
        '効果あり':   '#4ade80',
        '微増':       '#60d4a0',
        '効果見えず': '#f87171',
        '判定保留':   '#fbbf24',
        '対象外':     '#7a7a8c',
    }

    def _ppl(v):
        return f'{v:,}人' if v and v > 0 else '—'

    def _pct(v):
        if v is None:
            return '—'
        c = '#4ade80' if v >= 0 else '#f87171'
        return f'<span style="color:{c};font-weight:700;">{v:+.1f}%</span>'

    def _item_row(i):
        jc  = JCOLOR.get(i['judgment'], '#d0ccc8')
        cmt = (i.get('comment') or '')[:70]
        p4  = i.get('past_4w_avg_ppl')
        d4  = i.get('diff_4w_pct')
        return f'''<tr style="border-bottom:1px solid #2a2a35;">
          <td style="padding:5px 8px;font-size:11px;color:#f0ede8;">{i["program"]}</td>
          <td style="padding:5px 8px;font-size:10px;color:#f5a623;white-space:nowrap;">{i["period"]}</td>
          <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;text-align:center;">{i["spots"]}</td>
          <td style="padding:5px 8px;font-size:11px;font-weight:700;color:#60d4a0;text-align:right;">{_ppl(i.get("viewing_ppl"))}</td>
          <td style="padding:5px 8px;font-size:10px;color:#d0ccc8;text-align:right;">{_ppl(p4)}</td>
          <td style="padding:5px 8px;text-align:right;">{_pct(d4)}</td>
          <td style="padding:5px 8px;font-size:10px;font-weight:700;color:{jc};white-space:nowrap;">{i["judgment"]}</td>
          <td style="padding:5px 8px;font-size:9px;color:#a0a0b0;max-width:200px;">{cmt}</td>
        </tr>'''

    TH = '''<thead><tr style="border-bottom:1px solid #f5a623;background:#141418;">
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;">番組名</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;">番宣期間</th>
      <th style="text-align:center;padding:6px 8px;color:#a0a0b0;font-size:9px;">SPOT</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;">今週視聴人数</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;">過去4週平均</th>
      <th style="text-align:right;padding:6px 8px;color:#a0a0b0;font-size:9px;">4週平均比</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;">判定</th>
      <th style="text-align:left;padding:6px 8px;color:#a0a0b0;font-size:9px;">コメント</th>
    </tr></thead>'''

    def _section(title_text, color, items):
        if not items:
            return ''
        rows = ''.join(_item_row(i) for i in items)
        return f'''
        <div style="margin-bottom:20px;">
          <div style="font-size:9px;letter-spacing:3px;color:{color};
                      border-bottom:2px solid {color};padding-bottom:6px;margin-bottom:10px;">
            {title_text}（{len(items)}件）
          </div>
          <div style="overflow-x:auto;">
          <table style="width:100%;border-collapse:collapse;">{TH}
          <tbody>{rows}</tbody></table></div>
        </div>'''

    # KPIカード
    kpi_data = [
        ('効果あり',   eff_cnt,    '#4ade80'),
        ('微増',       slight_cnt, '#60d4a0'),
        ('効果見えず', neff_cnt,   '#f87171'),
        ('判定保留',   pend_cnt,   '#fbbf24'),
        ('判定対象',   total,      '#f0ede8'),
        ('照合成功',   matched,    '#60a5fa'),
    ]
    kpi_cards = ''.join(
        f'''<div style="background:#1c1c22;border:1px solid #2a2a35;border-radius:6px;
                        padding:12px 10px;text-align:center;">
          <div style="font-size:8px;letter-spacing:2px;color:#7a7a8c;margin-bottom:4px;">{lbl}</div>
          <div style="font-size:26px;font-weight:700;color:{col};">{val}</div>
          <div style="font-size:8px;color:#7a7a8c;">件</div>
        </div>'''
        for lbl, val, col in kpi_data
    )

    # 今週注目番組リスト
    watch_html = ''
    if watch_list:
        items_html = ''.join(
            f'<li style="padding:3px 0;font-size:12px;color:#f0ede8;">'
            f'<span style="color:#4ade80;margin-right:8px;">▶</span>{p}</li>'
            for p in watch_list
        )
        watch_html = f'''
        <div style="background:#1c1c22;border-left:4px solid #4ade80;border-radius:4px;
                    padding:14px 18px;margin-top:16px;">
          <div style="font-size:9px;letter-spacing:3px;color:#4ade80;margin-bottom:8px;">
            今週注目番組（効果あり＋微増）
          </div>
          <ul style="list-style:none;padding:0;margin:0;">{items_html}</ul>
        </div>'''

    # 期間未設定件数
    unset_note = ''
    if period_unset:
        unset_note = (
            f'<div style="margin-top:8px;font-size:9px;color:#7a7a8c;">'
            f'除外した行: 期間未設定 {len(period_unset)}件 / '
            f'対象外（期間終了済み） {len(out_of_range)}件</div>'
        )

    # 要確認（小さく末尾に）
    unmatched_rows = ''
    if unmatched:
        rows = ''.join(
            f'<tr><td style="padding:4px 8px;font-size:10px;color:#d0ccc8;">{i["program"]}</td>'
            f'<td style="padding:4px 8px;font-size:10px;color:#f5a623;">{i["period"]}</td>'
            f'<td style="padding:4px 8px;font-size:9px;color:#a0a0b0;">{i["comment"][:60]}</td></tr>'
            for i in unmatched
        )
        unmatched_rows = f'''
        <div style="margin-top:20px;padding-top:12px;border-top:1px solid #2a2a35;">
          <div style="font-size:9px;letter-spacing:2px;color:#7a7a8c;margin-bottom:8px;">
            番組名照合不可（要確認）{len(unmatched)}件
          </div>
          <table style="width:100%;border-collapse:collapse;font-size:10px;">
            <thead><tr style="border-bottom:1px solid #2a2a35;">
              <th style="text-align:left;padding:4px 8px;color:#7a7a8c;">番組名</th>
              <th style="text-align:left;padding:4px 8px;color:#7a7a8c;">番宣期間</th>
              <th style="text-align:left;padding:4px 8px;color:#7a7a8c;">コメント</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>'''

    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    return f'''<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<title>BSよしもと 番宣効果判定レポート {year} W{week_num:02d}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:"Noto Sans JP","Hiragino Kaku Gothic Pro","Meiryo",sans-serif;
        background:#141418;color:#d0ccc8;font-size:12px;
        -webkit-print-color-adjust:exact;print-color-adjust:exact;}}
  .page{{width:257mm;min-height:182mm;padding:14mm 14mm;background:#141418;
         margin:0 auto;page-break-after:always;}}
  .page:last-child{{page-break-after:auto;}}
  @page{{size:A4 landscape;margin:0;}}
  @media print{{body{{background:#141418;}}.page{{page-break-after:always;}}}}
</style></head><body>

<!-- PAGE 1: サマリー -->
<div class="page">
  <div style="border-left:5px solid #f5a623;padding:0 0 0 18px;margin-bottom:20px;">
    <div style="font-size:9px;letter-spacing:5px;color:#f5a623;margin-bottom:6px;">PROMOTION EFFECT JUDGEMENT REPORT</div>
    <div style="font-size:24px;font-weight:700;color:#f0ede8;line-height:1.3;">BSよしもと 番宣効果判定レポート</div>
    <div style="font-size:13px;color:#a0a0b0;margin-top:6px;">{year}年 第{week_num}週（{week_range}）</div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:16px;">{kpi_cards}</div>

  <div style="background:#1c1c22;border-left:4px solid #f5a623;border-radius:4px;padding:14px 18px;">
    <div style="font-size:9px;letter-spacing:3px;color:#f5a623;margin-bottom:8px;">総評</div>
    <div style="font-size:12px;color:#d0ccc8;line-height:1.9;">{overview}</div>
  </div>

  {watch_html}
  {unset_note}

  <div style="margin-top:16px;font-size:8px;color:#4a4a5a;text-align:right;">
    生成: {generated_at} ／ データ: E1A_HM_番組単位（日別）×7日 ＋ 過去4週
  </div>
</div>

<!-- PAGE 2: 判定詳細 -->
<div class="page">
  <div style="font-size:9px;letter-spacing:4px;color:#f5a623;border-bottom:1px solid #f5a623;
              padding-bottom:6px;margin-bottom:16px;">
    番宣効果 詳細判定（{total}件）
  </div>

  {_section("効果あり","#4ade80",effect)}
  {_section("微増","#60d4a0",slight)}
  {_section("効果見えず","#f87171",no_effect)}
  {_section("判定保留","#fbbf24",
    [i for i in pending if i["match_type"] != "不一致"])}

  {unmatched_rows}

  <div style="margin-top:20px;padding-top:12px;border-top:1px solid #2a2a35;
              font-size:8px;color:#4a4a5a;text-align:center;">
    BSよしもと 編成制作局 ／ 視聴データ: REGZA E1A_HM_番組単位 ／ 生成: {generated_at}
  </div>
</div>

</body></html>'''
