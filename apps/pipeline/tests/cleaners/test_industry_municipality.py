"""産業大分類×男女別就業者数 市区町村版 cleaner（industry_municipality）の単体テスト。

市区町村版（2015=0003175084）は産業分類コードがマクロ（industry.INDUSTRY の 100〜330）と別体系
（cat05・0000/0010/0080…）で、年別マップでマクロコードへ写像して縫合する。男女は cat01・4桁体系。
lv2 中分類（うち農業）・再掲第1/2/3次・割合(%)行の除外と、総数==Σ大分類（不詳注入なし）を回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「産業（大分類）」節が正典。

2020（0003450542）は産業×職業クロス表で、純カウントの軽量2次元表が廃止されたため
職業総数（cat03='0'）スライスで産業marginalを復元する。
産業は cat02・令和型 A〜T の英字直接、男女は cat01・1桁体系（0/1/2）で 2015 と別体系。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro industry と同一の10列・同一 dtype を出す（縦積み前提）。
    test_2015_maps_and_drops_recap … cat05 をマクロコードへ写像し、男女(cat01)を写像し、
        中分類/再掲/割合行を除外する。
    test_2015_conservation … 「分類不能(T=330)」を含む大分類で 総数 == Σ大分類 が閉じる（不詳注入なし）。
    test_2020_maps_and_marginalizes … cat02(A〜T)をマクロコードへ写像し、男女(cat01 1桁)を写像し、
        職業総数(cat03='0')以外の職業別行を落として産業marginalを復元し、中間集計/再掲を除外する。
    test_2020_conservation … 2020 も「分類不能(T=330)」含む大分類で 総数 == Σ大分類 が閉じる。
"""

import polars as pl

from data_forge.sources.estat import industry, industry_municipality


def _base(**kw) -> dict:
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "tab_code": "1", "time_code": "2015000000"}
    row.update(kw)
    return row


def _base_2020(**kw) -> dict:
    """2020 産業×職業クロス表の行（tab=2020_05・cat03=職業・cat03='0'が職業総数）。"""
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "2020_05",
        "cat03_code": "0",  # 職業総数（既定＝産業marginal）
        "time_code": "2020000000",
    }
    row.update(kw)
    return row


def test_shares_schema_with_macro() -> None:
    """2015 ミクロ cleaner が macro industry と同一の10列・dtype を出す（combine_years の縦積み前提）。"""
    micro = industry_municipality.clean_2015(
        pl.DataFrame([_base(cat01_code="0000", cat05_code=c, value="1") for c in ("0000", "0010", "3540")])
    )
    macro = industry.clean_prefecture(
        pl.DataFrame(
            [
                {
                    "tab_code": "334",
                    "cat01_code": c,
                    "cat02_code": "100",
                    "area_code": "01000",
                    "area_name": "北海道",
                    "area_level": "2",
                    "time_code": "2015000000",
                    "value": "1",
                }
                for c in ("100", "120", "330")
            ]
        )
    )
    assert micro.columns == macro.columns
    assert micro.schema == macro.schema, "dtype がマクロと不一致（縦積み不可）"


def test_2015_maps_and_drops_recap() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat01_code="0000", cat05_code="0000", value="100"),  # 総数 → 100
            _base(cat01_code="0000", cat05_code="0010", value="40"),  # A農業林業 → 120
            _base(cat01_code="0000", cat05_code="0020", value="9"),  # lv2 うち農業＝落とす
            _base(cat01_code="0000", cat05_code="3540", value="6"),  # T分類不能 → 330
            _base(cat01_code="0000", cat05_code="3570", value="49"),  # 再掲第1次＝落とす
            _base(cat01_code="0000", cat05_code="3600", value="7"),  # 割合(%)＝落とす
            _base(cat01_code="0010", cat05_code="0000", value="55"),  # 男×総数
        ]
    )
    df = industry_municipality.clean_2015(tidy)
    by = {(r["sex_code"], r["industry_code"]): r for r in df.iter_rows(named=True)}
    assert {k[1] for k in by} == {"100", "120", "330"}  # 中分類・再掲・割合は不採用
    assert by[("0", "100")]["industry"] == "総数"
    assert by[("0", "120")]["workers"] == 40 and by[("0", "120")]["industry"] == "Ａ農業，林業"
    assert by[("1", "100")]["workers"] == 55 and by[("1", "100")]["sex"] == "男"


def test_2015_conservation() -> None:
    """総数 == Σ大分類（分類不能を含む・不詳導出注入しない）。"""
    tidy = pl.DataFrame(
        [
            _base(cat01_code="0000", cat05_code="0000", value="100"),  # 総数
            _base(cat01_code="0000", cat05_code="0010", value="60"),  # A → 120
            _base(cat01_code="0000", cat05_code="0080", value="34"),  # B → 130
            _base(cat01_code="0000", cat05_code="3540", value="6"),  # T分類不能 → 330
        ]
    )
    df = industry_municipality.clean_2015(tidy)
    total = df.filter(pl.col("industry_code") == "100")["workers"][0]
    parts = df.filter(pl.col("industry_code") != "100")["workers"].sum()
    assert total == parts == 100
    assert "999" not in set(df["industry_code"])  # 不詳行は作らない


def test_2020_maps_and_marginalizes() -> None:
    """cat02(A〜T)写像・cat01(1桁)写像・職業別(cat03≠'0')の脱落・中間集計/再掲の除外を確かめる。"""
    tidy = pl.DataFrame(
        [
            _base_2020(cat01_code="0", cat02_code="0", value="100"),  # 総数×職業総数 → 100
            _base_2020(cat01_code="0", cat02_code="A", value="40"),  # A農業林業 → 120
            _base_2020(cat01_code="0", cat02_code="01", value="9"),  # 中間集計 うち農業＝落とす
            _base_2020(cat01_code="0", cat02_code="R1", value="49"),  # 再掲第1次＝落とす
            _base_2020(cat01_code="0", cat02_code="T", value="6"),  # T分類不能 → 330
            _base_2020(cat01_code="1", cat02_code="0", value="55"),  # 男×総数
            # 職業別（cat03≠'0'）は marginal 復元で落とす（残すと二重計上）。
            _base_2020(cat01_code="0", cat02_code="A", cat03_code="B", value="999"),
        ]
    )
    df = industry_municipality.clean_2020(tidy)
    by = {(r["sex_code"], r["industry_code"]): r for r in df.iter_rows(named=True)}
    assert {k[1] for k in by} == {"100", "120", "330"}  # 中間集計・再掲は不採用
    assert by[("0", "120")]["workers"] == 40 and by[("0", "120")]["industry"] == "Ａ農業，林業"
    assert by[("1", "100")]["workers"] == 55 and by[("1", "100")]["sex"] == "男"
    assert df["year"][0] == 2020


def test_2020_conservation() -> None:
    """2020 も 総数 == Σ大分類（分類不能を含む・不詳導出注入しない）。"""
    tidy = pl.DataFrame(
        [
            _base_2020(cat01_code="0", cat02_code="0", value="100"),  # 総数
            _base_2020(cat01_code="0", cat02_code="A", value="60"),  # A → 120
            _base_2020(cat01_code="0", cat02_code="B", value="34"),  # B → 130
            _base_2020(cat01_code="0", cat02_code="T", value="6"),  # T分類不能 → 330
        ]
    )
    df = industry_municipality.clean_2020(tidy)
    total = df.filter(pl.col("industry_code") == "100")["workers"][0]
    parts = df.filter(pl.col("industry_code") != "100")["workers"].sum()
    assert total == parts == 100
    assert "999" not in set(df["industry_code"])
