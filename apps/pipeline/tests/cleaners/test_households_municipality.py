"""世帯の種類別 世帯数・世帯人員 市区町村版 cleaner（households_municipality）の単体テスト。

年ごとに違う軸割当（世帯の種類が cat01/cat02・測度が tab 分離/cat 混載/単一値）・全域/DID 潰し・
世帯人員の非対称同居（2015/2020 のみ）・不詳/人口行の除外を、手組み tidy で回帰ガードする。
各年の実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「世帯の種類・人員」節が正典。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_all_years_share_schema … 全年 cleaner が households.py マクロと同一の9列・同一 dtype を出す
        （combine_years の縦積みが通る前提）。
    test_1985_maps_types_members_null … 素の cat01 3種別・世帯数のみ（世帯人員 null）。
    test_2000_drops_did … 全域/DID=cat01 を全域(00700)で潰す。
    test_2010_takes_household_codes_only … cat02 混載から世帯数3種別のみ採り 人口・不詳(006) を落とす。
    test_2015_joins_two_measures … cat02 融合から世帯数と世帯人員を別々に写像し横並びにする。
    test_2020_splits_measures_by_tab … tab で世帯数/世帯人員を分け横並びにする。
"""

import polars as pl

from data_forge.sources.estat import households, households_municipality

_COLUMNS = [
    "area_code",
    "area_name",
    "area_level",
    "household_type_code",
    "household_type",
    "year",
    "households",
    "household_members",
    "is_current",
]


def _base(**kw) -> dict:
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "time_code": "2020000000"}
    row.update(kw)
    return row


def test_all_years_share_schema() -> None:
    """全年 cleaner が macro households と同一の9列・dtype を出す（combine_years の縦積み前提）。"""
    frames = {
        1985: households_municipality.clean_1985(
            pl.DataFrame([_base(cat01_code=c, value="1") for c in ("000", "001", "002")])
        ),
        2010: households_municipality.clean_2010(
            pl.DataFrame([_base(cat01_code="00710", cat02_code=c, value="1") for c in ("003", "004", "005")])
        ),
        2015: households_municipality.clean_2015(
            pl.DataFrame(
                [_base(cat01_code="00710", cat02_code=c, value="1") for c in ("200", "210", "220", "300", "310", "320")]
            )
        ),
        2020: households_municipality.clean_2020(
            pl.DataFrame(
                [_base(tab_code=t, cat01_code=c, value="1") for t in ("2020_13", "2020_22") for c in ("0", "1", "2")]
            )
        ),
    }
    macro = households.clean_households(
        pl.DataFrame(
            [
                {
                    "tab_code": "040",
                    "cat01_code": "100",
                    "area_code": "00000",
                    "area_name": "全国",
                    "area_level": "1",
                    "time_code": "2020000000",
                    "value": "1",
                }
            ]
        )
    )
    for year, df in frames.items():
        assert df.columns == _COLUMNS, f"{year}: 列不一致"
        assert df.schema == macro.schema, f"{year}: dtype がマクロと不一致（縦積み不可）"


def test_1985_maps_types_members_null() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="000", value="100"),
            _base(cat01_code="001", value="90"),
            _base(cat01_code="002", value="10"),
        ]
    )
    df = households_municipality.clean_1985(tidy)
    by = {r["household_type_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120"}
    assert by["100"]["households"] == 100 and by["100"]["household_type"] == "総数"
    assert by["110"]["households"] == 90 and by["120"]["households"] == 10
    assert all(r["household_members"] is None for r in by.values())  # 世帯人員は 1985 に無い


def test_2000_drops_did() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="00700", cat02_code="000", value="100"),  # 全域（採る）
            _base(cat01_code="00701", cat02_code="000", value="55"),  # 人口集中地区（落とす）
        ]
    )
    df = households_municipality.clean_2000(tidy)
    assert df.height == 1
    assert df.row(0, named=True)["households"] == 100


def test_2010_takes_household_codes_only() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="00710", cat02_code="000", value="9999"),  # （人口）総数＝落とす
            _base(cat01_code="00710", cat02_code="003", value="100"),  # 世帯数 総数
            _base(cat01_code="00710", cat02_code="004", value="90"),  # 一般
            _base(cat01_code="00710", cat02_code="005", value="10"),  # 施設
            _base(cat01_code="00710", cat02_code="006", value="3"),  # 世帯の種類不詳＝落とす
            _base(cat01_code="00711", cat02_code="003", value="7"),  # DID＝落とす
        ]
    )
    df = households_municipality.clean_2010(tidy)
    by = {r["household_type_code"]: r["households"] for r in df.iter_rows(named=True)}
    assert by == {"100": 100, "110": 90, "120": 10}  # 人口・不詳・DID は不採用


def test_2015_joins_two_measures() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="00710", cat02_code="010", value="9999"),  # （人口）総数＝落とす
            _base(cat01_code="00710", cat02_code="200", value="100"),  # 世帯数 総数
            _base(cat01_code="00710", cat02_code="210", value="90"),  # 世帯数 一般
            _base(cat01_code="00710", cat02_code="220", value="10"),  # 世帯数 施設
            _base(cat01_code="00710", cat02_code="300", value="250"),  # 世帯人員 総数
            _base(cat01_code="00710", cat02_code="310", value="230"),  # 世帯人員 一般
            _base(cat01_code="00710", cat02_code="320", value="20"),  # 世帯人員 施設
        ]
    )
    df = households_municipality.clean_2015(tidy)
    total = df.filter(pl.col("household_type_code") == "100").row(0, named=True)
    assert total["households"] == 100 and total["household_members"] == 250
    assert df.filter(pl.col("household_type_code") == "110").row(0, named=True)["household_members"] == 230


def test_2020_splits_measures_by_tab() -> None:
    tidy = pl.DataFrame(
        [
            _base(tab_code="2020_13", cat01_code="0", value="100"),  # 世帯数 総数
            _base(tab_code="2020_13", cat01_code="1", value="90"),
            _base(tab_code="2020_13", cat01_code="2", value="10"),
            _base(tab_code="2020_22", cat01_code="0", value="250"),  # 世帯人員 総数
            _base(tab_code="2020_22", cat01_code="1", value="230"),
            _base(tab_code="2020_22", cat01_code="2", value="20"),
        ]
    )
    df = households_municipality.clean_2020(tidy)
    total = df.filter(pl.col("household_type_code") == "100").row(0, named=True)
    assert total["households"] == 100 and total["household_members"] == 250
