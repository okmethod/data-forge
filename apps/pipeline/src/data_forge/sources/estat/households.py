"""国勢調査 世帯の種類別 世帯数・世帯人員 固有のクレンジング。

時系列データ製品「世帯の種類別世帯数及び世帯人員 － 全国，都道府県」
（0003410420、その1＝一般世帯及び施設等の世帯・1960〜2020）を配布用の1枚テーブルへ整形する。
全国＋47都道府県が単一 ID に同居する **single-ID fact**（合併なし＝area master 不要・age5year.py と同性格）。
**帳票の事実（軸の採否＝1390 不採用・DID 除外・保存則）は docs/distributions/households.md が正典**
（ここには再掲しない＝ドリフト防止）。

軸構造:
    tab  … 040=世帯数 / 050=世帯人員 / 1390=1世帯当たり人員
    cat01（世帯の種類）… 100=総数 / 110=一般世帯 / 120=施設等の世帯（総数=一般+施設）
    area … 00000=全国(level1) ＋ 47都道府県(level2)。level2 には 00100=人口集中地区 /
           00200=人口集中地区以外 も混在するが地理単位でないため捨てる。
    time … 1960〜2020（1965 欠。実在する年のみ運ぶ）

Note（実装判断のみ）:
- 単一 ID に全国＋都道府県が同居＝**射影不要・cleaner 1 個**で、scope 引数で全国/県を排他分離する。
- 2測定量（世帯数・世帯人員）を1行へ横並び。1世帯当たり人員(1390)は導出可能ゆえ不採用。
- 悉皆カウントで cat01 に不詳区分が無いため**不詳の導出注入は行わない**（family_type/labor_force と異なる）。

出力スキーマは8列（population 系から sex→household_type・単一 population→2測定量へ差し替え）。
列は clean_households の select が正典。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import (
    area_passthrough_cols,
    int_value_expr,
    scope_area,
    year_from_time_code_expr,
)

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


def clean_households(tidy: pl.DataFrame, *, scope: str = "all") -> pl.DataFrame:
    """世帯の種類別 世帯数・世帯人員の tidy → 配布用8列へ写像する。

    引数:
        scope … 配布時の地理粒度を排他選択する: national=全国 / prefecture=47都道府県 / all=両方。

    手順: 世帯の種類（cat01）を分類軸に採り、世帯数(tab=040)と世帯人員(tab=050)を
          area×household_type×year の同一行へ横並びに束ねる。DID 行は除外する。
    """
    base = tidy.filter(pl.col("cat01_code").is_in(list(HOUSEHOLD_TYPE)) & ~pl.col("area_code").is_in(_DID_AREA_CODES))
    keys = ["area_code", "area_name", "area_level", "cat01_code", "time_code"]
    households = base.filter(pl.col("tab_code") == _TAB_HOUSEHOLDS).select(*keys, int_value_expr().alias("households"))
    members = base.filter(pl.col("tab_code") == _TAB_MEMBERS).select(*keys, int_value_expr().alias("household_members"))
    fact = households.join(members, on=keys, how="left")
    result = (
        fact.select(
            *area_passthrough_cols(),
            pl.col("cat01_code").alias("household_type_code"),
            pl.col("cat01_code").replace_strict(HOUSEHOLD_TYPE).alias("household_type"),
            # time_code 例: "2020000000" の先頭4桁が年
            year_from_time_code_expr(),
            pl.col("households"),
            pl.col("household_members"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "household_type_code", "year")
    )
    return scope_area(result, scope)
