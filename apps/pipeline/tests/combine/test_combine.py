"""複数年結合（時系列化）の合成層テスト。

union / intersection / grid の各正規化モードと、二重計上を防ぐ粒度ガードを検証する。
"""

import polars as pl
import pytest

from data_forge.derive import combine_years, union_areas

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
    df = combine_years([_age_frame(2015, "A", 100), _age_frame(2020, "B", 200)], mode="grid", grain=_AGE_GRAIN)
    # 2 area × 2 year × 2 age × 1 sex = 8 行
    assert df.height == 8
    a2020 = df.filter((pl.col("area_code") == "A") & (pl.col("year") == 2020) & (pl.col("age_class_code") == "0")).row(
        0, named=True
    )
    assert a2020["population"] is None


# --- union_areas（射影フロー: 既製時系列の disjoint な area パーティションを縦積み）----------
def _area_frame(area: str, year: int, pop: int) -> pl.DataFrame:
    # 1 地域 × 総数(sex=0) × 1 年の最小フレーム（各 upstream が全年を持つ想定）
    return pl.DataFrame(
        {
            "area_code": [area],
            "area_name": [area],
            "area_level": [1],
            "sex_code": ["0"],
            "sex": ["総数"],
            "year": [year],
            "population": [pop],
            "is_current": [True],
        }
    )


def test_union_areas_stacks_disjoint_partitions():
    # 全国(00000) と 県(01000) は各々全年を持つ disjoint パーティション → 縦積みで全行保持
    national = pl.concat([_area_frame("00000", 1920, 100), _area_frame("00000", 2020, 200)])
    pref = pl.concat([_area_frame("01000", 1920, 10), _area_frame("01000", 2020, 20)])
    df = union_areas([national, pref])
    assert df.height == 4
    assert set(df["area_code"]) == {"00000", "01000"}
    # sort は combine_years と同一（area_code, year 昇順）
    assert df["area_code"].to_list() == ["00000", "00000", "01000", "01000"]
    assert df["year"].to_list() == [1920, 2020, 1920, 2020]


def test_union_areas_matches_combine_years_union_on_disjoint():
    # disjoint 入力なら union_areas は combine_years(mode="union") と出力等価（age5 の等価性担保）
    national = pl.concat([_area_frame("00000", 1920, 100), _area_frame("00000", 2020, 200)])
    pref = pl.concat([_area_frame("01000", 1920, 10), _area_frame("01000", 2020, 20)])
    assert union_areas([national, pref]).equals(combine_years([national, pref], mode="union"))


def test_union_areas_rejects_overlapping_partitions():
    # 同一 area×sex×year が2 upstream に → パーティションが disjoint でない＝粒度違反
    a = _area_frame("00000", 2020, 100)
    b = _area_frame("00000", 2020, 100)
    with pytest.raises(ValueError, match="粒度違反"):
        union_areas([a, b])


def test_union_areas_with_age_grain():
    # grain に age_class_code を含む形（age5 相当）でも disjoint 判定が正しい
    national = _age_frame(2020, "00000", 100)
    pref = _age_frame(2020, "01000", 50)
    df = union_areas([national, pref], grain=_AGE_GRAIN)
    assert df.height == 4  # 2 area × 2 age(総数/年少)
    assert set(df["area_code"]) == {"00000", "01000"}
