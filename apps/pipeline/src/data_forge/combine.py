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

from typing import Literal

import polars as pl

Mode = Literal["union", "intersection", "grid"]

# 時系列テーブルの粒度（この3列で一意でなければ二重計上を疑う）
GRAIN = ["area_code", "sex_code", "year"]


def combine_years(frames: list[pl.DataFrame], *, mode: Mode = "union") -> pl.DataFrame:
    """同一スキーマの年次フレーム群を時系列テーブルへ結合する。"""
    df = pl.concat(frames, how="vertical")
    _assert_grain(df)

    if mode == "union":
        out = df
    elif mode == "intersection":
        out = _intersection(df)
    elif mode == "grid":
        out = _grid(df)
    else:  # pragma: no cover - Literal で型的には到達しない
        raise ValueError(f"未知の結合モード: {mode!r}")

    return out.sort("area_code", "year", "sex_code")


def _assert_grain(df: pl.DataFrame) -> None:
    """(area_code, sex_code, year) の重複が無いことを保証する。

    年ごとの cleaner が別の分類軸を取りこぼすと行が多重化するため、
    二重計上を静かに通さずここで明確に失敗させる。
    """
    dup = df.group_by(GRAIN).len().filter(pl.col("len") > 1)
    if dup.height:
        sample = dup.head(3).to_dicts()
        raise ValueError(
            f"粒度違反: (area_code, sex_code, year) が重複 {dup.height} 件（例: {sample}）。"
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
    """area_code × year × sex の全格子を作り、欠損 (area, year) を null 行で明示する。

    地域属性（area_name / area_level / is_current）はその地域が存在した年の値のみ
    埋まり、存在しない年は null になる（＝その年に無かったことを表す）。
    """
    areas = df.select("area_code").unique()
    years = df.select("year").unique()
    sexes = df.select("sex_code", "sex").unique()
    keys = areas.join(years, how="cross").join(sexes, how="cross")
    out = keys.join(df, on=["area_code", "year", "sex_code", "sex"], how="left")
    return out.select(df.columns)  # 入力の列順（共通スキーマ順）へ揃える
