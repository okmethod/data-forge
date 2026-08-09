"""和解（reconcile）: 人口保存チェックと「孤児アトム」検出。

堀（moat）の駆動役。parsed イベントだけでは埋まらない箇所を機械的にフラグし、
人手 overrides（クッション）で埋める運用を支える。

2 つの検査:
    - national_conservation … 各年、アトム合計 == 全国total か（アトム抽出の健全性）。
    - orphans … base_year までに消滅したのに rollup 先が base_year に無いアトム
                （＝合併イベント未整備）。人口降順で「次に埋める候補」を返す。
"""

import polars as pl

from data_forge.area.mapping import rollup


def national_conservation(atom_fact: pl.DataFrame, national: pl.DataFrame) -> pl.DataFrame:
    """各年で「アトム合計（総数）== 全国total」を検査した表を返す。

    引数:
        atom_fact … 各年アトムの時系列（8列）。
        national  … 全国行のみ（area_code=='00000'）を含む DF（year/sex_code/population）。
    """
    atom_sum = (
        atom_fact.filter(pl.col("sex_code") == "0")
        .group_by("year")
        .agg(pl.col("population").fill_null(0).sum().alias("atom_sum"))
    )
    nat = national.filter(pl.col("sex_code") == "0").select(
        "year", pl.col("population").alias("national")
    )
    return (
        nat.join(atom_sum, on="year", how="left")
        .with_columns((pl.col("national") - pl.col("atom_sum")).alias("diff"))
        .with_columns((pl.col("diff") == 0).alias("ok"))
        .sort("year")
    )


def orphans(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
    """rollup 後も base_year に存在しないアトム（＝イベント未整備）を人口降順で返す。

    列: area_code / area_name / last_year / last_population / base_code。
    base_code は現状の（未整備な）rollup 先。ここを overrides で正しい後継へ向ける。
    """
    years = atom_fact.get_column("year").unique().to_list()
    base = base_year if base_year is not None else max(years)

    base_codes = set(atom_fact.filter(pl.col("year") == base).get_column("area_code").to_list())
    roll = rollup(events, base_year=base)

    # 各アトムの最終出現年・その年の総数人口・名称
    last = (
        atom_fact.filter(pl.col("sex_code") == "0")
        .sort("year")
        .group_by("area_code")
        .agg(
            pl.col("year").max().alias("last_year"),
            pl.col("population").last().alias("last_population"),
            pl.col("area_name").last().alias("area_name"),
        )
    )
    mapped = last.join(roll, left_on="area_code", right_on="code", how="left").with_columns(
        pl.coalesce("base_code", "area_code").alias("base_code")
    )
    return (
        mapped.filter(~pl.col("base_code").is_in(list(base_codes)))
        .select("area_code", "area_name", "last_year", "last_population", "base_code")
        .sort("last_population", descending=True, nulls_last=True)
    )
