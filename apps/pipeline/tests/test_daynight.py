"""昼夜間人口（従業地・通学地集計）クレンジングの単体テスト。

cat01=100(夜間)/180(昼間) だけを採り daynight_code(0/1) の8列へ写像すること、
内訳コードや欠損記号の扱い、level7 フラグを手組み tidy で検証する。
"""

import polars as pl

from data_forge.sources.estat import daynight


def _tidy(rows: list[dict]) -> pl.DataFrame:
    """(cat01_code, area_code, area_name, area_level, value) の dict 群から最小 tidy を作る。"""
    base = {
        "tab_code": "020",
        "time_code": "2020000000",
        "unit": "人",
    }
    return pl.DataFrame([{**base, **r} for r in rows])


def test_clean_daynight_schema_and_axis_mapping():
    df = daynight.clean_daynight_population(
        _tidy(
            [
                {"cat01_code": "100", "area_code": "00000", "area_name": "全国", "area_level": "1", "value": "126146099"},
                {"cat01_code": "180", "area_code": "00000", "area_name": "全国", "area_level": "1", "value": "126146099"},
                # 通勤流動の内訳（採らない）
                {"cat01_code": "140", "area_code": "00000", "area_name": "全国", "area_level": "1", "value": "999"},
            ]
        )
    )
    assert df.columns == [
        "area_code",
        "area_name",
        "area_level",
        "daynight_code",
        "daynight",
        "year",
        "population",
        "is_current",
    ]
    # 100→0(夜間)/180→1(昼間) の2行だけ。内訳(140)は捨てられる。
    assert set(zip(df["daynight_code"], df["daynight"])) == {
        ("0", "夜間人口（常住地）"),
        ("1", "昼間人口（従業地・通学地）"),
    }
    night = df.filter(pl.col("daynight_code") == "0").row(0, named=True)
    assert night["population"] == 126_146_099  # 文字列→Int64
    assert night["year"] == 2020
    assert night["is_current"] is True


def test_clean_daynight_levels_and_missing():
    df = daynight.clean_daynight_population(
        _tidy(
            [
                {"cat01_code": "100", "area_code": "01303", "area_name": "当別町", "area_level": "6", "value": "17456"},
                {"cat01_code": "180", "area_code": "0120B", "area_name": "（旧：函館市）", "area_level": "7", "value": "-"},
            ]
        )
    ).sort("area_code")

    current = df.filter(pl.col("area_code") == "01303").row(0, named=True)
    assert current["is_current"] is True
    assert current["population"] == 17456

    obsolete = df.filter(pl.col("area_code") == "0120B").row(0, named=True)
    assert obsolete["is_current"] is False  # level7 は旧自治体
    assert obsolete["population"] is None  # "-" は null
