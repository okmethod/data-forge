"""国勢調査 従業地・通学地集計（昼夜間人口）固有のクレンジング。

「常住地又は従業地・通学地別人口（夜間人口・昼間人口）」時系列ファミリー
（statsDataId 0003412192〜197 / 0004003060、1990〜2020）を配布用の1枚テーブルへ整形する。
IDは年齢3区分ファミリー(0003412413〜420)の同世代・直前連番で、area 軸は JIS コード・
全国(00000)行ありと同型（＝地域マスタ〈アトム軸スタースキーマ〉をそのまま再利用でき、
population_by_age と同じく area 集約の `*_code` 自動判別に無改修で乗る「3例目」）。

軸 cat01「常住地又は従業地・通学地による人口」は通勤流動の内訳を多数持つが、内訳コード
集合は年で非同型（2000=11・2020=14）なので、全年で安定して存在し経年比較可能な2つの
「総数」だけを採る（内訳は割合同様に捨てる）:
    100 = 常住地による人口_総数（夜間人口）      → daynight_code="0"
    180 = 従業地・通学地による人口_総数（昼間人口）→ daynight_code="1"

daynight_code="0" を夜間人口（＝常住地人口＝通常の居住人口）へ割り当てるのは、reconcile の
「総数スライス（全 `*_code`=="0"）」が population と同じ「居住人口の保存」を指すようにするため
（＝夜間人口の全国値は population ファクトと一致する＝クロスファクト検算になる）。
sex/age のような入れ子（0=総数, 内訳が 0 へ合算）ではなく、0（夜間）と 1（昼間）は
畳んで総数にはならない並列な2母集団である点が population_by_age と異なる。

出力スキーマ（8列）:
    area_code(str) / area_name(str) / area_level(int) /
    daynight_code(str) / daynight(str) / year(int) /
    population(Int64) / is_current(bool)
"""

import polars as pl

# area @level=7 は「旧市区町村（合併消滅）」。現存自治体と区別する（population と同じ規約）。
_OBSOLETE_AREA_LEVEL = 7

# cat01（常住地又は従業地・通学地による人口）の2総数 → (daynight_code, daynight名称)。
# 通勤流動の内訳（110〜230）は年で非同型なので採らない。
DAYNIGHT = {
    "100": ("0", "夜間人口（常住地）"),
    "180": ("1", "昼間人口（従業地・通学地）"),
}


def clean_daynight_population(tidy: pl.DataFrame) -> pl.DataFrame:
    """昼夜間人口の tidy → area × year × 昼夜間 の配布用8列へ写像する（全年共通）。

    cat01=100(夜間人口)/180(昼間人口) だけを採り daynight_code(0/1) へ写像する。
    本表は全国(00000)行を持つため national 復元は不要（population_by_age と異なる）。
    tab 軸は単一（020 人口）なので絞り込み不要。
    """
    return (
        tidy.filter(pl.col("cat01_code").is_in(list(DAYNIGHT)))
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            pl.col("cat01_code")
            .replace_strict({k: v[0] for k, v in DAYNIGHT.items()})
            .alias("daynight_code"),
            pl.col("cat01_code")
            .replace_strict({k: v[1] for k, v in DAYNIGHT.items()})
            .alias("daynight"),
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            pl.col("value")
            .str.replace_all(r"[^0-9-]", "")
            .cast(pl.Int64, strict=False)
            .alias("population"),
        )
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
        .sort("area_code", "daynight_code")
    )
