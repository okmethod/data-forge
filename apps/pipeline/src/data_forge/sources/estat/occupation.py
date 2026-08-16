"""国勢調査 職業（大分類）×男女別就業者数 固有のクレンジング。

就業状態等基本集計の時系列データ製品「職業（大分類），男女別就業者数及び人口構成比
［職業別］（15歳以上就業者）」（全国 0003410408＝平成7年〜令和2年／都道府県 0003410411＝
平成17年〜令和2年）を配布用の1枚テーブルへ整形する。産業（industry.py）と軸構造が完全同型
（tab=334就業者数/構成比・cat01=大分類2015・cat02=男女・全国表 area 軸なし）で、
本モジュールは industry.py を職業向けに写したもの。設計思想の詳細は industry.py と共通。

**age5 と同型（全国表が area 軸を持たない）**：全国表(0003410408)は area 軸なし→00000/全国/level1 を
合成し、都道府県表(0003410411)は area=47都道府県(level2)をそのまま採る。差は area のコード集合と年の
カバレッジ（全国 1995-2020／県 2005-2020）だけなので **cleaner 本体は共通・national フラグで分岐**。

tab は 334(就業者数)のみ採り、構成比(2020_45)は捨てる（構成比 = 各職業÷総数 で count から導出可能）。

職業大分類(cat01)は 総数(100) と大分類12区分(110〜220。220=分類不能の職業)。産業と違い（再掲）の
中間集計は無く、大分類はフラットな12区分。「分類不能」が実カテゴリとして存在する＝**不詳の導出注入は
不要**で「総数 == Σ大分類（分類不能含む）」が原資料で恒等成立する（保存則として検証する）。

出力スキーマ（industry と同型の10列。industry を occupation に差し替えただけ）:
    area_code(str) / area_name(str) / area_level(int) /
    sex_code(str) / sex(str) / occupation_code(str) / occupation(str) /
    year(int) / workers(Int64) / is_current(bool)
"""

import polars as pl

# area @level=7 は「旧市区町村（合併消滅）」。本表には出現しないが規約統一のため保持する。
_OBSOLETE_AREA_LEVEL = 7

# 表章項目(tab): 334=就業者数（採用）。構成比(2020_45)は count から導出可能ゆえ捨てる。
_TAB_WORKERS = "334"

# cat02（男女_時系列）→ (sex_code, sex名称)。コード体系は industry.SEX と同じ 100/110/120。
SEX = {"100": ("0", "総数"), "110": ("1", "男"), "120": ("2", "女")}

# cat01（職業大分類2015）→ 名称。総数(100)＋大分類12区分(110〜220)。220=分類不能の職業（実カテゴリ）。
# 産業と違い（再掲）の中間集計は無い。コードは e-Stat のまま採る。
OCCUPATION = {
    "100": "総数",
    "110": "Ａ管理的職業従事者",
    "120": "Ｂ専門的・技術的職業従事者",
    "130": "Ｃ事務従事者",
    "140": "Ｄ販売従事者",
    "150": "Ｅサービス職業従事者",
    "160": "Ｆ保安職業従事者",
    "170": "Ｇ農林漁業従事者",
    "180": "Ｈ生産工程従事者",
    "190": "Ｉ輸送・機械運転従事者",
    "200": "Ｊ建設・採掘従事者",
    "210": "Ｋ運搬・清掃・包装等従事者",
    "220": "Ｌ分類不能の職業",
}


def clean_occupation(tidy: pl.DataFrame, *, national: bool) -> pl.DataFrame:
    """職業大分類×男女別就業者数の tidy → 配布用10列へ写像する（全国/都道府県 共通）。

    引数:
        national … True で全国表(0003410408, area軸なし)＝00000/全国/level1 を合成。
                   False で都道府県表(0003410411)＝area軸(47県, level2)をそのまま採る。

    手順: tab=334(就業者数。構成比は捨てる) で絞り、cat01→職業大分類・cat02→男女へ写像する。
    2015/2020 は「不詳補完値」版(time_code 末尾 000010)が併存するため通常版(000000)に統一する
    （industry・age5・labor_force と同方針）。分類不能(220)を含む大分類で「総数 == Σ大分類」が
    閉じるため不詳の導出注入は行わない（industry と同じ）。
    """
    df = (
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS)
        .filter(pl.col("cat01_code").is_in(list(OCCUPATION)))  # 職業大分類
        .filter(pl.col("cat02_code").is_in(list(SEX)))  # 男女
        .filter(pl.col("time_code").str.slice(4) == "000000")  # 不詳補完値版を除外
    )
    if national:
        area_cols = [
            pl.lit("00000").alias("area_code"),
            pl.lit("全国").alias("area_name"),
            pl.lit(1).cast(pl.Int8).alias("area_level"),
        ]
    else:
        area_cols = [
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
        ]
    return df.select(
        *area_cols,
        pl.col("cat02_code").replace_strict({k: v[0] for k, v in SEX.items()}).alias("sex_code"),
        pl.col("cat02_code").replace_strict({k: v[1] for k, v in SEX.items()}).alias("sex"),
        pl.col("cat01_code").alias("occupation_code"),
        pl.col("cat01_code").replace_strict(OCCUPATION).alias("occupation"),
        # time_code 例: "2020000000" の先頭4桁が年
        pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
        # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
        pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False).alias("workers"),
    ).with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))


def clean_national(tidy: pl.DataFrame) -> pl.DataFrame:
    """全国表(0003410408)用 cleaner（area 軸なし → 全国行を合成、1995-2020）。"""
    return clean_occupation(tidy, national=True)


def clean_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """都道府県表(0003410411)用 cleaner（area=47都道府県、2005-2020）。"""
    return clean_occupation(tidy, national=False)
