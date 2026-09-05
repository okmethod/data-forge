"""国勢調査 世帯の種類別 世帯数・世帯人員 固有のクレンジング。

時系列データ製品「世帯の種類別世帯数及び世帯人員 － 全国，都道府県」
（0003410420、その1＝一般世帯及び施設等の世帯・1960〜2020）を配布用の1枚テーブルへ整形する。
回次跨（cross-census 編纂）で year 軸を1帳票内に持ち、area は全国(level1)＋47都道府県(level2)固定
＝合併なし＝**area master 不要の低コスト fact**（age5.py と同性格）。単一 ID に全国も都道府県も
含むため射影（ProjectedDataset）も不要で、cleaner 1 個の単独 Dataset で完結する。

軸構造:
    tab  … 040=世帯数 / 050=世帯人員 / 1390=1世帯当たり人員
    cat01（世帯の種類）… 100=総数 / 110=一般世帯 / 120=施設等の世帯（総数=一般+施設）
    area … 00000=全国(level1) ＋ 47都道府県(level2)。level2 には 00100=人口集中地区 /
           00200=人口集中地区以外 も混在するが地理単位でないため捨てる。
    time … 1960〜2020（1965 欠。実在する年のみ運ぶ）

2つの基底測定量（世帯数・世帯人員）を1行に横並びで持つ。1世帯当たり人員(1390)は
世帯人員÷世帯数で導出可能ゆえ捨てる（age5 が不詳を導出するのと同じ「基底だけ持ち残りは導出」方針）。
世帯は悉皆カウントで cat01 に不詳区分が無いため、配偶関係表のような不詳処理は不要。

出力スキーマ（8列。population 系から sex→household_type・単一 population→2測定量へ差し替え）:
    area_code(str) / area_name(str) / area_level(int) /
    household_type_code(str) / household_type(str) /
    year(int) / households(Int64) / household_members(Int64) / is_current(bool)
"""

import polars as pl

from data_forge.sources.estat.transform import scope_area

# area @level=7 は「旧市区町村（合併消滅）」。本表には出現しないが規約統一のため保持する。
_OBSOLETE_AREA_LEVEL = 7

# level2 に混じる人口集中地区（DID）系。都道府県と同 level だが地理単位でないため除外する。
_DID_AREA_CODES = ("00100", "00200")

# cat01（世帯の種類_時系列）→ 名称。総数=一般世帯+施設等の世帯。
HOUSEHOLD_TYPE = {
    "100": "総数",
    "110": "一般世帯",
    "120": "施設等の世帯",
}

# tab（表章項目）。1世帯当たり人員(1390)は households/members から導出可能ゆえ採らない。
_TAB_HOUSEHOLDS = "040"  # 世帯数（単位: 世帯）
_TAB_MEMBERS = "050"  # 世帯人員（単位: 人）

def _int_value() -> pl.Expr:
    """value（文字列）を Int64 へ。数字以外（"-" 等の欠損記号）は null に落とす。"""
    return pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False)


def clean_households(tidy: pl.DataFrame, *, scope: str = "all") -> pl.DataFrame:
    """世帯の種類別 世帯数・世帯人員の tidy → 配布用8列へ写像する。

    世帯の種類（cat01）を分類軸に採り、世帯数(tab=040)と世帯人員(tab=050)を
    area×household_type×year の同一行へ横並びに束ねる。DID 行は除外する。
    scope で配布時の地理粒度を排他選択する: national=全国 / prefecture=47都道府県 / all=両方。
    """
    base = tidy.filter(pl.col("cat01_code").is_in(list(HOUSEHOLD_TYPE)) & ~pl.col("area_code").is_in(_DID_AREA_CODES))
    keys = ["area_code", "area_name", "area_level", "cat01_code", "time_code"]
    households = base.filter(pl.col("tab_code") == _TAB_HOUSEHOLDS).select(*keys, _int_value().alias("households"))
    members = base.filter(pl.col("tab_code") == _TAB_MEMBERS).select(*keys, _int_value().alias("household_members"))
    fact = households.join(members, on=keys, how="left")
    result = (
        fact.select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            pl.col("cat01_code").alias("household_type_code"),
            pl.col("cat01_code").replace_strict(HOUSEHOLD_TYPE).alias("household_type"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            pl.col("households"),
            pl.col("household_members"),
        )
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
        .sort("area_code", "household_type_code", "year")
    )
    return scope_area(result, scope)
