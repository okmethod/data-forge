"""世帯の家族類型（16区分）別 一般世帯数 市区町村版 cleaner（family_type_municipality）の単体テスト。

市区町村版は家族類型に別軸（世帯人員の人数）が交差する重い表なので、その軸を総数で周辺化し、
マクロ「16区分A_時系列」コード（100〜290/999）へ写像して縫合する。
（再掲）R1/R2/R3 の除外・不詳(cat02 "4"→999)の直接写像・世帯人員の null 注入・level 写像を手組み tidy で回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「家族類型」節が正典。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro family_type と同一の9列・同一 dtype を出す（縦積み前提）。
    test_2020_marginalizes_and_maps … 世帯人員(cat01)を総数で周辺化し cat02 をマクロコードへ写像・
        再掲(R*)除外・不詳(4→999)・世帯人員 null・level 写像を確かめる。
    test_2005_two_measures_and_injects_unknown … tab で世帯数/世帯人員を分け、lv4詳細を無視し、
        不詳(999)を 総数−親族のみ−非親族−単独 で導出注入する。
    test_2010_marginalizes_by_housing … 住宅の所有(cat02)を総数(000)で周辺化する。
    test_2015_double_filter_and_explicit_unknown … 全域(cat01)・世帯人員総数(cat03)で二重に絞り、
        不詳(0330→999)を直接写像・世帯人員 null。
"""

import polars as pl

from data_forge.sources.estat import family_type, family_type_municipality

_COLUMNS = [
    "area_code",
    "area_name",
    "area_level",
    "family_type_code",
    "family_type",
    "family_type_level",
    "year",
    "households",
    "household_members",
    "is_current",
]


def _base(**kw) -> dict:
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "time_code": "2020000000"}
    row.update(kw)
    return row


def test_shares_schema_with_macro() -> None:
    """2020 ミクロ cleaner が macro family_type と同一の9列・dtype を出す（combine_years の縦積み前提）。"""
    micro = family_type_municipality.clean_2020(
        pl.DataFrame([_base(cat01_code="0", cat02_code=c, value="1") for c in ("0", "1", "11", "4")])
    )
    macro = family_type.clean_family_type(
        pl.DataFrame(
            [
                {
                    "tab_code": "6",
                    "cat01_code": c,
                    "cat01_level": lv,
                    "area_code": "00000",
                    "area_name": "全国",
                    "area_level": "1",
                    "time_code": "2020000000",
                    "value": "1",
                }
                for c, lv in (("100", "1"), ("110", "2"), ("280", "2"), ("290", "2"))
            ]
        )
    )
    assert micro.columns == _COLUMNS
    assert micro.schema == macro.schema, "dtype がマクロと不一致（縦積み不可）"


def test_2020_marginalizes_and_maps() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="0", cat02_code="0", value="100"),  # 世帯人員総数×総数 → 100
            _base(cat01_code="1", cat02_code="0", value="40"),  # 世帯人員1人＝周辺化で落とす
            _base(cat01_code="0", cat02_code="1", value="70"),  # 親族のみ → 110
            _base(cat01_code="0", cat02_code="11", value="60"),  # 核家族 → 120
            _base(cat01_code="0", cat02_code="111", value="30"),  # 夫婦のみ → 130
            _base(cat01_code="0", cat02_code="3", value="25"),  # 単独 → 290
            _base(cat01_code="0", cat02_code="4", value="5"),  # 不詳 → 999
            _base(cat01_code="0", cat02_code="R1", value="9"),  # （再掲）3世代＝落とす
        ]
    )
    df = family_type_municipality.clean_2020(tidy)
    by = {r["family_type_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120", "130", "290", "999"}  # 周辺化外・再掲は不採用
    assert by["100"]["households"] == 100 and by["100"]["family_type"] == "総数"
    assert by["999"]["households"] == 5 and by["999"]["family_type"] == "家族類型不詳"
    assert by["100"]["family_type_level"] == 1
    assert by["110"]["family_type_level"] == 2 and by["120"]["family_type_level"] == 3
    assert by["130"]["family_type_level"] == 4 and by["999"]["family_type_level"] == 2
    assert all(r["household_members"] is None for r in by.values())  # 世帯人員はこの表に無い


def test_2005_two_measures_and_injects_unknown() -> None:
    tidy = pl.DataFrame(
        [
            # 世帯数(tab=6): 総数100 = 親族のみ70 + 非親族5 + 単独20 + 不詳(導出=5)
            _base(tab_code="6", cat01_code="0010", value="100"),  # 総数 → 100
            _base(tab_code="6", cat01_code="0020", value="70"),  # 親族のみ → 110
            _base(tab_code="6", cat01_code="0040", value="30"),  # 夫婦のみ → 130
            _base(tab_code="6", cat01_code="0100", value="9"),  # lv4詳細(夫の親)＝無視
            _base(tab_code="6", cat01_code="0310", value="5"),  # 非親族 → 280
            _base(tab_code="6", cat01_code="0320", value="20"),  # 単独 → 290
            _base(tab_code="6", cat01_code="0330", value="8"),  # （再掲）3世代＝落とす
            # 世帯人員(tab=7)
            _base(tab_code="7", cat01_code="0010", value="250"),  # 総数
            _base(tab_code="7", cat01_code="0020", value="200"),
            _base(tab_code="7", cat01_code="0310", value="10"),
            _base(tab_code="7", cat01_code="0320", value="20"),
        ]
    )
    df = family_type_municipality.clean_2005(tidy)
    by = {r["family_type_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "130", "280", "290", "999"}  # lv4詳細・再掲は不採用
    assert by["100"]["households"] == 100 and by["100"]["household_members"] == 250
    assert by["110"]["households"] == 70 and by["110"]["household_members"] == 200
    # 不詳(999) = 総数 − 親族のみ − 非親族 − 単独（両測度とも導出）
    assert by["999"]["households"] == 100 - 70 - 5 - 20
    assert by["999"]["household_members"] == 250 - 200 - 10 - 20


def test_2010_marginalizes_by_housing() -> None:
    tidy = pl.DataFrame(
        [
            _base(tab_code="6", cat02_code="000", cat01_code="0010", value="100"),  # 住居総数（採る）
            _base(tab_code="6", cat02_code="013", cat01_code="0010", value="88"),  # 住宅に住む世帯（落とす）
            _base(tab_code="6", cat02_code="000", cat01_code="0020", value="70"),  # 親族のみ
            _base(tab_code="6", cat02_code="000", cat01_code="0310", value="5"),  # 非親族
            _base(tab_code="6", cat02_code="000", cat01_code="0320", value="20"),  # 単独
            _base(tab_code="7", cat02_code="000", cat01_code="0010", value="250"),
            _base(tab_code="7", cat02_code="000", cat01_code="0020", value="200"),
            _base(tab_code="7", cat02_code="000", cat01_code="0310", value="10"),
            _base(tab_code="7", cat02_code="000", cat01_code="0320", value="20"),
        ]
    )
    df = family_type_municipality.clean_2010(tidy)
    by = {r["family_type_code"]: r["households"] for r in df.iter_rows(named=True)}
    assert by["100"] == 100  # 住居総数のみ（住宅に住む世帯は周辺化で落とす）
    assert by["999"] == 100 - 70 - 5 - 20  # 導出注入


def test_2015_double_filter_and_explicit_unknown() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="00710", cat03_code="0000", cat02_code="0000", value="100"),  # 全域×世帯人員総数×総数
            _base(cat01_code="00711", cat03_code="0000", cat02_code="0000", value="55"),  # DID＝落とす
            _base(cat01_code="00710", cat03_code="0020", cat02_code="0000", value="30"),  # 世帯人員1人＝周辺化で落とす
            _base(cat01_code="00710", cat03_code="0000", cat02_code="0010", value="70"),  # 親族のみ → 110
            _base(cat01_code="00710", cat03_code="0000", cat02_code="0330", value="5"),  # 不詳 → 999
            _base(cat01_code="00710", cat03_code="0000", cat02_code="0340", value="9"),  # （再掲）3世代＝落とす
        ]
    )
    df = family_type_municipality.clean_2015(tidy)
    by = {r["family_type_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "999"}  # DID・周辺化外・再掲は不採用
    assert by["100"]["households"] == 100
    assert by["999"]["households"] == 5 and by["999"]["family_type"] == "家族類型不詳"
    assert all(r["household_members"] is None for r in by.values())  # 2015 軽量表は世帯数のみ
