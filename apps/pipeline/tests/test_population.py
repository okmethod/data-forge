"""人口パイプラインのクレンジング単体テスト。

汎用 transform（コード名称解決）は実サンプル fixture で、
population 固有のクレンジング（level→is_current・int化・欠損処理）は
手組みの tidy DF で検証する。
"""

import json
from pathlib import Path

import polars as pl

from data_forge.sources.estat import population, transform

FIXTURE = Path(__file__).parent / "fixtures" / "estat_population_sample.json"


def _load_raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_extract_meta():
    meta = transform.extract_meta(_load_raw())
    assert meta.source == "estat"
    assert meta.dataset_id == "0003445078"
    assert meta.provider == "総務省"
    assert meta.attributes["stat_name"] == "国勢調査"
    assert meta.attributes["survey_date"] == "202010"
    assert meta.citation.startswith("出典：政府統計の総合窓口(e-Stat)")


def test_to_tidy_resolves_names():
    tidy = transform.to_tidy(_load_raw())
    # 4軸 × (code,name,level) + unit + value 列が揃う
    for axis in ("tab", "cat01", "area", "time"):
        assert f"{axis}_code" in tidy.columns
        assert f"{axis}_name" in tidy.columns
        assert f"{axis}_level" in tidy.columns

    # 全国(00000) のコードが名称解決されている
    zenkoku = tidy.filter(pl.col("area_code") == "00000")
    assert zenkoku.height == 1
    assert zenkoku["area_name"][0] == "全国"
    assert zenkoku["value"][0] == "126146099"


def test_clean_from_fixture():
    tidy = transform.to_tidy(_load_raw())
    df = population.clean(tidy)

    assert df.columns == [
        "area_code",
        "area_name",
        "area_level",
        "sex_code",
        "sex",
        "year",
        "population",
        "is_current",
    ]
    row = df.filter(pl.col("area_code") == "00000").row(0, named=True)
    assert row["population"] == 126_146_099  # 文字列→Int64
    assert row["sex"] == "総数"
    assert row["year"] == 2020
    assert row["is_current"] is True  # level1（全国）は現存扱い


def test_clean_handles_levels_and_missing():
    """level7（旧市区町村）フラグと欠損記号の null 化を手組み tidy で検証。"""
    tidy = pl.DataFrame(
        {
            "tab_code": ["2020_01", "2020_01"],
            "tab_name": ["人口", "人口"],
            "tab_level": ["", ""],
            "cat01_code": ["0", "0"],
            "cat01_name": ["総数", "総数"],
            "cat01_level": ["1", "1"],
            "area_code": ["01303", "0120B"],
            "area_name": ["当別町", "（旧：函館市）"],
            "area_level": ["6", "7"],
            "time_code": ["2020000000", "2020000000"],
            "time_name": ["2020年", "2020年"],
            "time_level": ["1", "1"],
            "unit": ["人", "人"],
            "value": ["17456", "-"],  # 2件目は欠損記号
        }
    )
    df = population.clean(tidy).sort("area_code")

    current = df.filter(pl.col("area_code") == "01303").row(0, named=True)
    assert current["is_current"] is True
    assert current["population"] == 17456

    obsolete = df.filter(pl.col("area_code") == "0120B").row(0, named=True)
    assert obsolete["is_current"] is False  # level7 は旧自治体
    assert obsolete["population"] is None  # "-" は null
