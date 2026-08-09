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


# --- 年齢区分を持つ fact（age_class を grain に足す）------------------------------
_AGE_GRAIN = ["area_code", "sex_code", "age_class_code", "year"]


def _age_frame(year: int, area: str, pop: int) -> pl.DataFrame:
    # 1 地域 × 総数(sex=0) × 年齢2区分（総数0/年少1）の最小フレーム
    return pl.DataFrame(
        {
            "area_code": [area, area],
            "area_name": [area, area],
            "area_level": [2, 2],
            "sex_code": ["0", "0"],
            "sex": ["総数", "総数"],
            "age_class_code": ["0", "1"],
            "age_class": ["総数", "年少人口(0-14)"],
            "year": [year, year],
            "population": [pop, pop // 10],
            "is_current": [True, True],
        }
    )


def test_age_grain_allows_multiple_age_classes():
    # age を grain に入れれば同一 area×sex×year で複数 age 行が粒度違反にならない
    df = combine_years([_age_frame(2020, "A", 100)], mode="union", grain=_AGE_GRAIN)
    assert df.height == 2
    assert set(df["age_class_code"]) == {"0", "1"}


def test_age_grain_guard_still_rejects_true_duplicates():
    dup = pl.concat([_age_frame(2020, "A", 100), _age_frame(2020, "A", 100)])
    with pytest.raises(ValueError, match="粒度違反"):
        combine_years([dup], mode="union", grain=_AGE_GRAIN)


def test_grid_crosses_age_class():
    # A は 2015 のみ、B は 2020 のみ → grid で全 (area×year×age) 格子が埋まり欠損は null
    df = combine_years(
        [_age_frame(2015, "A", 100), _age_frame(2020, "B", 200)], mode="grid", grain=_AGE_GRAIN
    )
    # 2 area × 2 year × 2 age × 1 sex = 8 行
    assert df.height == 8
    a2020 = df.filter(
        (pl.col("area_code") == "A") & (pl.col("year") == 2020) & (pl.col("age_class_code") == "0")
    ).row(0, named=True)
    assert a2020["population"] is None
