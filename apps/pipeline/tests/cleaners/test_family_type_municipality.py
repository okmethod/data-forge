"""世帯の家族類型（16区分）別 一般世帯数 市区町村版 cleaner（family_type_municipality）の単体テスト。

市区町村版は家族類型に別軸（世帯人員の人数）が交差する重い表なので、その軸を総数で周辺化し、
マクロ「16区分A_時系列」コード（100〜290/999）へ写像して縫合する。（再掲）R1/R2/R3 の除外・
不詳(cat02 "4"→999)の直接写像・世帯人員の null 注入・level 写像を手組み tidy で回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「家族類型」節が正典。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro family_type と同一の9列・同一 dtype を出す（縦積み前提）。
    test_2020_marginalizes_and_maps … 世帯人員(cat01)を総数で周辺化し cat02 をマクロコードへ写像・
        再掲(R*)除外・不詳(4→999)・世帯人員 null・level 写像を確かめる。
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
