"""crosswalk / aggregate_to_base: 各年アトム × rollup(base_year) の2ビュー（＝時間軸の合併集約）。

行政階層（都道府県 / 地方ブロック）への上位集約＝直交する空間軸は [spatial_rollup.py] に分離。
両者は fact スキーマ内省ユーティリティ（`cat_code_cols`／`measure_cols`／`sum_measure_expr`）を共用する。
本モジュールが area 内の共有置き場であり、spatial_rollup が import する。

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

from data_forge.area.levels import is_current_expr
from data_forge.area.mapping import rollup


def cat_code_cols(df: pl.DataFrame) -> list[str]:
    """分類軸のコード列（area_code / base_code 以外の `*_code`）を返す。

    例: population → `["sex_code"]` ／ population_by_age → `["sex_code", "age_class_code"]`。
    集約の group キー・ソートキーはこの軸で構成し、名称列（`sex` / `age_class`）は畳み込み時に
    `.first()` で運ぶ（各群内で一定）。出力スキーマは固定表を持たず入力 `atom_fact` の列構成を
    そのまま踏襲するので、population(8列) と population_by_age(10列) を同じコードで畳める。
    """
    return [c for c in df.columns if c.endswith("_code") and c not in ("area_code", "base_code")]


# 集約で合算対象にしない列（area/年/来歴などのメタ）。分類軸のコード列と名称列は別途除く。
_NON_MEASURE_META = frozenset(
    {"area_code", "base_code", "area_name", "area_level", "year", "is_current", "data_status"}
)


def measure_cols(df: pl.DataFrame) -> list[str]:
    """合算対象の測度列（メタ・分類軸コード・分類軸名称 以外の数値列）を返す。

    population(1列) だけでなく households / household_members(2列) のように
    測度が複数ある fact も fact 非依存で畳むための一般化（`cat_code_cols` と対になる）。
    分類軸の名称列（sex_code↔sex 等）はコード列から導いて除外するので、測度として拾われない。
    """
    cat_labels = {c.removesuffix("_code") for c in cat_code_cols(df)}
    return [c for c in df.columns if c not in _NON_MEASURE_META and not c.endswith("_code") and c not in cat_labels]


def sum_measure_expr(col: str) -> pl.Expr:
    """測度列を group 内で合算する Expr。全 null の群（その年に無い測度）は 0 でなく null を保つ。

    household_members は 2015/2020 のみ実在し他年は null。
    素の sum は全 null 群を 0 にして「値0」と「未計測」を混同するため、
    非 null が1つも無い群は null に落とす。
    population のように常時非 null な測度では素の sum と等価（後方互換）。
    """
    return pl.when(pl.col(col).count() == 0).then(None).otherwise(pl.col(col).sum()).alias(col)


def _base_year(atom_fact: pl.DataFrame, base_year: int | None) -> int:
    return base_year if base_year is not None else max(atom_fact.get_column("year").to_list())


def attach_crosswalk(atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None) -> pl.DataFrame:
    """各年アトムを畳まず、後継コード列 base_code・base_name を同梱して返す（入力列＋2列）。

    畳む/畳まないを配布時に固定しない「非固定」ビュー。利用者は area_code のまま使えば
    原境界（合併前の実態保持）、`GROUP BY base_code` すれば前方 rollup 相当（連続時系列）。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（入力スキーマは fact 依存）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 後継先の基準年（既定=atom_fact の最新年）。

    返り値の列 = 入力列 ＋ base_code（後継先コード。未合併/未整備は area_code と同値）
    ＋ base_name（base_year 時点の後継先名称。幽霊 base ユニットでは null）。
    """
    base = _base_year(atom_fact, base_year)
    roll = rollup(events, base_year=base)
    base_names = (
        atom_fact.filter(pl.col("year") == base)
        .select(pl.col("area_code").alias("base_code"), pl.col("area_name").alias("base_name"))
        .unique(subset="base_code")
    )
    sort_keys = ["area_code", "year", *cat_code_cols(atom_fact)]
    return (
        atom_fact.join(roll, left_on="area_code", right_on="code", how="left")
        .with_columns(pl.coalesce("base_code", "area_code").alias("base_code"))
        .join(base_names, on="base_code", how="left")
        .select(*atom_fact.columns, "base_code", "base_name")
        .sort(sort_keys)
    )


def aggregate_to_base(atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None) -> pl.DataFrame:
    """アトム時系列を base_year 境界の自治体時系列へ畳む（入力と同じスキーマで返す）。

    = attach_crosswalk を base_code で実際に合算した確定ビュー。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（入力スキーマは fact 依存）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 集約の基準年（既定=atom_fact の最新年）。
    """
    base = _base_year(atom_fact, base_year)
    cw = attach_crosswalk(atom_fact, events, base_year=base)

    cat_codes = cat_code_cols(atom_fact)
    cat_labels = [c.removesuffix("_code") for c in cat_codes]  # sex_code→sex / age_class_code→age_class
    agg = cw.group_by(["base_code", "year", *cat_codes]).agg(
        *(sum_measure_expr(m) for m in measure_cols(atom_fact)),
        *(pl.col(lbl).first().alias(lbl) for lbl in cat_labels),
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
        .with_columns(is_current_expr())
        .select(atom_fact.columns)
        .sort(["area_code", "year", *cat_codes])
    )
