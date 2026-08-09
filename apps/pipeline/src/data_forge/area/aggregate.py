"""crosswalk / aggregate_to_base: 各年アトム × rollup(base_year) の2ビュー。

Design A（実データで人口保存を実証済み）:
    1. fact = 各年のアトム（現行境界の最finest分割。atoms.extract_atoms）。
    2. rollup = 施行年 ≤ base_year の合併イベントで code→base_code（mapping.rollup）。

この rollup を「畳んで確定するか／畳まず後継コードを付けるだけか」で2ビューに分ける:
    attach_crosswalk:
        各アトムを畳まず、後継コード列 base_code（＋ base_name）を同梱して返す。
        利用者が `GROUP BY base_code` すれば前方 rollup 相当、area_code のままなら原境界。
        畳む/畳まないを配布時に固定しない。
    aggregate_to_base:
        crosswalk を base_code で実際に合算した確定ビュー。
        （= attach_crosswalk + GROUP BY base_code）
        name/level は base_year 時点のアトム値で統一する。

各年のアトムは国土を過不足なく1回覆い、rollup は各アトム→単一 base_code の関数なので、二重計上は起きない。
イベント未整備で消滅アトムが自分自身に留まる場合は「幽霊 base ユニット」として残る。
（reconcile が検出＝クッション候補）
base_year は集約パラメータに外出しするので、2025 投入後も過去の基準年ビューを据え置ける。
combine と相互非依存で、cli.py が clean→atoms→combine→(crosswalk|aggregate) と配線する。
"""

import polars as pl

from data_forge.area.mapping import rollup

_OBSOLETE_AREA_LEVEL = 7  # 旧市区町村（現存でない）

# 出力スキーマ（単年 fact と揃える）
_OUT_COLS = [
    "area_code",
    "area_name",
    "area_level",
    "sex_code",
    "sex",
    "year",
    "population",
    "is_current",
]


def _base_year(atom_fact: pl.DataFrame, base_year: int | None) -> int:
    return base_year if base_year is not None else max(atom_fact.get_column("year").to_list())


def attach_crosswalk(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
    """各年アトムを畳まず、後継コード列 base_code・base_name を同梱して返す（10列）。

    畳む/畳まないを配布時に固定しない「非固定」ビュー。利用者は area_code のまま使えば
    原境界（合併前の実態保持）、`GROUP BY base_code` すれば前方 rollup 相当（連続時系列）。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（8列）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 後継先の基準年（既定=atom_fact の最新年）。

    返り値の列 = 入力8列 ＋ base_code（後継先コード。未合併/未整備は area_code と同値）
    ＋ base_name（base_year 時点の後継先名称。幽霊 base ユニットでは null）。
    """
    base = _base_year(atom_fact, base_year)
    roll = rollup(events, base_year=base)
    base_names = (
        atom_fact.filter(pl.col("year") == base)
        .select(pl.col("area_code").alias("base_code"), pl.col("area_name").alias("base_name"))
        .unique(subset="base_code")
    )
    return (
        atom_fact.join(roll, left_on="area_code", right_on="code", how="left")
        .with_columns(pl.coalesce("base_code", "area_code").alias("base_code"))
        .join(base_names, on="base_code", how="left")
        .select(*_OUT_COLS, "base_code", "base_name")
        .sort("area_code", "year", "sex_code")
    )


def aggregate_to_base(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
    """アトム時系列を base_year 境界の自治体時系列へ畳む（8列スキーマで返す）。

    = attach_crosswalk を base_code で実際に合算した確定ビュー。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（8列）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 集約の基準年（既定=atom_fact の最新年）。
    """
    base = _base_year(atom_fact, base_year)
    cw = attach_crosswalk(atom_fact, events, base_year=base)

    agg = cw.group_by(["base_code", "year", "sex_code"]).agg(
        pl.col("population").sum().alias("population"),
        pl.col("sex").first().alias("sex"),
    )

    # name/level は base_year 時点のアトム（＝基準年に現存する自治体）から与える
    base_attrs = (
        atom_fact.filter(pl.col("year") == base)
        .select(
            pl.col("area_code").alias("base_code"),
            pl.col("area_name"),
            pl.col("area_level"),
        )
        .unique(subset="base_code")
    )

    return (
        agg.join(base_attrs, on="base_code", how="left")
        .rename({"base_code": "area_code"})
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
        .select(_OUT_COLS)
        .sort("area_code", "year", "sex_code")
    )
