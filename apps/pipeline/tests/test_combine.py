"""複数年結合（時系列化）の合成層テスト。

union / intersection / grid の各正規化モードと、二重計上を防ぐ粒度ガードを検証する。
"""

import polars as pl
import pytest

from data_forge.combine import combine_years

# 共通スキーマの最小フレーム。地域Aは両年、Bは2015のみ、Cは2020のみ（sexは総数だけ）。
_2015 = pl.DataFrame(
    {
        "area_code": ["A", "B"],
        "area_name": ["a", "b"],
        "area_level": [2, 2],
        "sex_code": ["0", "0"],
        "sex": ["総数", "総数"],
        "year": [2015, 2015],
        "population": [100, 20],
        "is_current": [True, True],
    }
)
_2020 = pl.DataFrame(
    {
        "area_code": ["A", "C"],
        "area_name": ["a", "c"],
        "area_level": [2, 2],
        "sex_code": ["0", "0"],
        "sex": ["総数", "総数"],
        "year": [2020, 2020],
        "population": [110, 30],
        "is_current": [True, True],
    }
)


def test_union_keeps_all_areas():
    df = combine_years([_2015, _2020], mode="union")
    # A(2年) + B(2015) + C(2020) = 4 行、全 area を保持
    assert df.height == 4
    assert set(df["area_code"]) == {"A", "B", "C"}


def test_intersection_keeps_only_common_areas():
    df = combine_years([_2015, _2020], mode="intersection")
    # 両年に存在するのは A のみ → 2015/2020 の 2 行
    assert set(df["area_code"]) == {"A"}
    assert df.height == 2


def test_grid_fills_missing_with_null():
    df = combine_years([_2015, _2020], mode="grid")
    # 3 area × 2 year × 1 sex = 6 行、列順は入力どおり
    assert df.height == 6
    assert df.columns == _2015.columns
    # B は 2020 に存在しない → population が null
    b2020 = df.filter((pl.col("area_code") == "B") & (pl.col("year") == 2020)).row(0, named=True)
    assert b2020["population"] is None


def test_grain_guard_rejects_duplicates():
    dup = pl.concat([_2015, _2015])  # 同一年の重複で粒度違反
    with pytest.raises(ValueError, match="粒度違反"):
        combine_years([dup], mode="union")
