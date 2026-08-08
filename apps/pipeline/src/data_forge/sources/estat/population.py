"""人口テーブル（国勢調査 男女別人口）固有のクレンジング。

transform.to_tidy() のロング形式（軸: tab/cat01/area/time）を、
配布用の1枚テーブルへ整形する。

出力スキーマ:
    area_code(str) / area_name(str) / area_level(int) /
    sex_code(str) / sex(str) / year(int) /
    population(Int64) / is_current(bool)

is_current: area の階層レベルが 7（旧市区町村・合併消滅）でないもの。
"""

import polars as pl

# area @level=7 は「旧市区町村（2000年時点の廃止自治体）」。現存自治体と区別する。
_OBSOLETE_AREA_LEVEL = 7


def clean(tidy: pl.DataFrame) -> pl.DataFrame:
    """tidy な人口ロング形式を配布用スキーマへ整形する。"""
    return (
        tidy.select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            pl.col("cat01_code").alias("sex_code"),
            pl.col("cat01_name").alias("sex"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
            pl.col("value")
            .str.replace_all(r"[^0-9-]", "")
            .cast(pl.Int64, strict=False)
            .alias("population"),
        )
        .with_columns(
            (pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"),
        )
        .sort("area_code", "sex_code")
    )
