"""派生データセット（複数年結合＝時系列化）の合成層。

各年のクロスセクション（年ごとに別 statsDataId）を、各年専用 cleaner が
同一スキーマへ写像済みの状態で受け取り、年を1次元に持つ時系列テーブルへ縦結合する。
ソースに依存しない（area_code / sex_code / year の共通スキーマにのみ依存）。

area コード正規化の方針は年をまたぐ地域集合の差（市町村合併・市部/郡部・DID等）を
どう扱うかで、`mode` として選べる:

    union        … 全部表示。ある年にしか無い地域もその年の行として残す（単純縦積み）。
    intersection … 共通のみ。全年に存在する area_code だけ残す（比較可能な地域に限定）。
    grid         … 欠損明示。area_code × year × sex の全格子を作り、
                   データが無い (area, year) は population=null の行として明示する。
"""

from collections.abc import Sequence
from typing import Literal

import polars as pl

Mode = Literal["union", "intersection", "grid"]

# 時系列テーブルの既定の粒度（この列群で一意でなければ二重計上を疑う）。
# fact 毎に軸が増える場合（例: population_by_age は age_class_code を足す）は
# combine_years(..., grain=[...]) で後方互換に上書きする。
GRAIN = ["area_code", "sex_code", "year"]

# grid モードで「地域×年」と直交させる分類軸を成す、area/年/値でない属性列。
# code とその名称（sex_code↔sex, age_class_code↔age_class 等）が 1:1 で対になるため、
# grain を明示しなくても DF の列構成から自動判別できる。
_NON_CATEGORY_COLS = {
    "area_code",
    "area_name",
    "area_level",
    "year",
    "population",
    "is_current",
    "data_status",  # 来歴列（provenance）は分類軸ではない。grid の cross 対象から除く。
}


def combine_years(
    frames: list[pl.DataFrame], *, mode: Mode = "union", grain: Sequence[str] = GRAIN
) -> pl.DataFrame:
    """同一スキーマの年次フレーム群を時系列テーブルへ結合する。

    `grain` はこの結合表を一意に定める列群（既定＝area×sex×year）。fact 毎に
    分類軸が増える場合だけ明示的に渡す（例: 年齢区分を持つ表なら age_class_code を追加）。
    """
    grain = list(grain)
    df = pl.concat(frames, how="vertical")
    _assert_grain(df, grain)

    if mode == "union":
        out = df
    elif mode == "intersection":
        out = _intersection(df)
    elif mode == "grid":
        out = _grid(df)
    else:  # pragma: no cover - Literal で型的には到達しない
        raise ValueError(f"未知の結合モード: {mode!r}")

    sort_keys = ["area_code", "year", *(c for c in grain if c not in ("area_code", "year"))]
    return out.sort(sort_keys)


def union_areas(frames: list[pl.DataFrame], *, grain: Sequence[str] = GRAIN) -> pl.DataFrame:
    """既製の時系列フレーム群を area 軸で縦結合する（射影フロー＝ProjectedDataset）。

    各フレームは既に全年を持つ disjoint な area パーティション（例: 全国＋都道府県）。
    combine_years と違い年の縫合はせず単純 union する。`grain` の重複は「パーティションが
    disjoint でない（同一キーが複数 upstream に）」ことの検出に使い、combine_years(union) と
    同一の sort キーで整列する（＝disjoint 入力なら両者は出力等価）。
    """
    grain = list(grain)
    df = pl.concat(frames, how="vertical")
    _assert_grain(df, grain)
    sort_keys = ["area_code", "year", *(c for c in grain if c not in ("area_code", "year"))]
    return df.sort(sort_keys)


def _assert_grain(df: pl.DataFrame, grain: list[str]) -> None:
    """grain 列群の組で重複が無いことを保証する。

    年ごとの cleaner が別の分類軸を取りこぼすと行が多重化するため、
    二重計上を静かに通さずここで明確に失敗させる。
    """
    dup = df.group_by(grain).len().filter(pl.col("len") > 1)
    if dup.height:
        sample = dup.head(3).to_dicts()
        raise ValueError(
            f"粒度違反: {tuple(grain)} が重複 {dup.height} 件（例: {sample}）。"
            "年次 cleaner が想定外の分類軸を残していないか確認すること。"
        )


def _intersection(df: pl.DataFrame) -> pl.DataFrame:
    """全年に存在する area_code のみへ絞り込む。"""
    n_years = df["year"].n_unique()
    common = (
        df.group_by("area_code")
        .agg(pl.col("year").n_unique().alias("_ny"))
        .filter(pl.col("_ny") == n_years)
        .select("area_code")
    )
    return df.join(common, on="area_code", how="semi")


def _grid(df: pl.DataFrame) -> pl.DataFrame:
    """area_code × year × 分類軸 の全格子を作り、欠損 (area, year) を null 行で明示する。

    分類軸（sex、表によっては age_class など）は area/年/値でない列として自動判別し、
    その全組み合わせと直交させる。地域属性（area_name / area_level / is_current）は
    その地域が存在した年の値のみ埋まり、存在しない年は null になる。
    """
    cat_cols = [c for c in df.columns if c not in _NON_CATEGORY_COLS]
    areas = df.select("area_code").unique()
    years = df.select("year").unique()
    cats = df.select(cat_cols).unique()
    keys = areas.join(years, how="cross").join(cats, how="cross")
    out = keys.join(df, on=["area_code", "year", *cat_cols], how="left")
    return out.select(df.columns)  # 入力の列順（共通スキーマ順）へ揃える
