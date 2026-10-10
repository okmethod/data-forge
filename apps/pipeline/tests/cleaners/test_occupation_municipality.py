"""職業大分類×男女別就業者数 市区町村版 cleaner（occupation_municipality）の単体テスト。

市区町村版（2015=0003176482）は職業分類コードがマクロ（occupation.OCCUPATION_MAJOR12 の 100〜220）と
別体系（cat01・0000/0010/0100…）で、年別マップでマクロコードへ写像して縫合する。男女は cat02・4桁体系。
割合(%)行の除外と、総数==Σ大分類（不詳注入なし）を回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「職業（大分類）」節が正典。

2020（0003450542）は産業×職業クロス表（industry 2020 と同一表）で、産業総数（cat02='0'）スライスで
職業marginalを復元する。職業は cat03・令和型 A〜L の英字直接、男女は cat01・1桁体系（0/1/2）で 2015 と別。
2010（0003067223）は産業×職業×従業上の地位クロス表で、産業総数（cat04='000'）×地位総数（cat02='000'）
スライスで職業marginalを復元する。職業は cat03・数字コード、男女は cat01・3桁体系。
2005（0003024287）は職業新分類×男女の軽量2次元 marginal。新分類は 12区分＝major12 と同ツリーで
2010 と同一コード体系（職業は cat02・数字コード、男女は cat01・3桁体系）。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro occupation(major12) と同一の10列・同一 dtype を出す。
    test_2015_maps_and_drops_rate … cat01 をマクロコードへ写像し・男女(cat02)を写像し・割合行を除外する。
    test_2015_conservation … 「分類不能(L=220)」を含む大分類で 総数 == Σ大分類 が閉じる。
    test_2020_maps_and_marginalizes … cat03(A〜L)写像・男女(cat01 1桁)写像・産業別(cat02≠'0')の脱落を確かめる。
    test_2010_maps_and_marginalizes … cat03(数字)写像・男女(cat01 3桁)写像・産業別(cat04≠'000')/
        地位別(cat02≠'000')の脱落を確かめる。
    test_2005_maps_and_conserves … cat02(数字・2010 と同一)写像・男女(cat01 3桁)写像・総数==Σ大分類。
"""

import polars as pl

from data_forge.sources.estat import occupation, occupation_municipality


def _base(**kw) -> dict:
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "tab_code": "1", "time_code": "2015000000"}
    row.update(kw)
    return row


def test_shares_schema_with_macro() -> None:
    """2015 ミクロ cleaner が macro occupation(major12) と同一の10列・dtype を出す。"""
    micro = occupation_municipality.clean_2015(
        pl.DataFrame([_base(cat02_code="0000", cat01_code=c, value="1") for c in ("0000", "0010", "2990")])
    )
    macro = occupation.clean_major12_prefecture(
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
                for c in ("100", "110", "220")
            ]
        )
    )
    assert micro.columns == macro.columns
    assert micro.schema == macro.schema, "dtype がマクロと不一致（縦積み不可）"


def test_2015_maps_and_drops_rate() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat02_code="0000", cat01_code="0000", value="100"),  # 総数 → 100
            _base(cat02_code="0000", cat01_code="0010", value="40"),  # A管理的 → 110
            _base(cat02_code="0000", cat01_code="2990", value="6"),  # L分類不能 → 220
            _base(cat02_code="0000", cat01_code="3020", value="7"),  # 割合(%)＝落とす
            _base(cat02_code="0020", cat01_code="0000", value="45"),  # 女×総数
        ]
    )
    df = occupation_municipality.clean_2015(tidy)
    by = {(r["sex_code"], r["occupation_code"]): r for r in df.iter_rows(named=True)}
    assert {k[1] for k in by} == {"100", "110", "220"}  # 割合は不採用
    assert by[("0", "110")]["workers"] == 40 and by[("0", "110")]["occupation"] == "Ａ管理的職業従事者"
    assert by[("2", "100")]["workers"] == 45 and by[("2", "100")]["sex"] == "女"


def test_2015_conservation() -> None:
    """総数 == Σ大分類（分類不能を含む・不詳導出注入しない）。"""
    tidy = pl.DataFrame(
        [
            _base(cat02_code="0000", cat01_code="0000", value="100"),  # 総数
            _base(cat02_code="0000", cat01_code="0010", value="60"),  # A → 110
            _base(cat02_code="0000", cat01_code="0100", value="34"),  # B → 120
            _base(cat02_code="0000", cat01_code="2990", value="6"),  # L分類不能 → 220
        ]
    )
    df = occupation_municipality.clean_2015(tidy)
    total = df.filter(pl.col("occupation_code") == "100")["workers"][0]
    parts = df.filter(pl.col("occupation_code") != "100")["workers"].sum()
    assert total == parts == 100


def _base_2020(**kw) -> dict:
    """2020 産業×職業クロス表の行（tab=2020_05・cat02=産業・cat02='0'が産業総数＝職業marginal）。"""
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "2020_05",
        "cat02_code": "0",  # 産業総数（既定＝職業marginal）
        "time_code": "2020000000",
    }
    row.update(kw)
    return row


def _base_2010(**kw) -> dict:
    """2010 産業×職業×従業上の地位クロス表の行（tab=340・cat02=地位・cat03=職業・cat04=産業・cat01=男女）。

    既定は産業総数(cat04='000')・地位総数(cat02='000')＝職業marginal。
    """
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "340",
        "cat02_code": "000",  # 従業上の地位 総数
        "cat04_code": "000",  # 産業 総数
        "time_code": "2010000000",
    }
    row.update(kw)
    return row


def _base_2005(**kw) -> dict:
    """2005 職業新分類×男女 市区町村の行（tab=1・cat01=男女3桁・cat02=職業数字コード）。"""
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "tab_code": "1", "time_code": "2005000000"}
    row.update(kw)
    return row


def test_2020_maps_and_marginalizes() -> None:
    """cat03(A〜L)写像・男女(cat01 1桁)写像・産業別(cat02≠'0')の脱落を確かめる。"""
    tidy = pl.DataFrame(
        [
            _base_2020(cat01_code="0", cat03_code="0", value="100"),  # 総数×産業総数 → 100
            _base_2020(cat01_code="0", cat03_code="A", value="40"),  # A管理的 → 110
            _base_2020(cat01_code="0", cat03_code="L", value="6"),  # L分類不能 → 220
            _base_2020(cat01_code="1", cat03_code="0", value="55"),  # 男×総数
            # 産業別（cat02≠'0'）は marginal 復元で落とす（残すと二重計上）。
            _base_2020(cat01_code="0", cat03_code="A", cat02_code="E", value="999"),
        ]
    )
    df = occupation_municipality.clean_2020(tidy)
    by = {(r["sex_code"], r["occupation_code"]): r for r in df.iter_rows(named=True)}
    assert {k[1] for k in by} == {"100", "110", "220"}
    assert by[("0", "110")]["workers"] == 40 and by[("0", "110")]["occupation"] == "Ａ管理的職業従事者"
    assert by[("1", "100")]["workers"] == 55 and by[("1", "100")]["sex"] == "男"
    assert df["year"][0] == 2020


def test_2010_maps_and_marginalizes() -> None:
    """cat03(数字)写像・男女(cat01 3桁)写像・産業別(cat04≠'000')/地位別(cat02≠'000')の脱落を確かめる。"""
    tidy = pl.DataFrame(
        [
            _base_2010(cat01_code="000", cat03_code="000", value="100"),  # 総数×産業総数×地位総数 → 100
            _base_2010(cat01_code="000", cat03_code="001", value="40"),  # A管理的 → 110
            _base_2010(cat01_code="000", cat03_code="299", value="6"),  # L分類不能 → 220
            _base_2010(cat01_code="001", cat03_code="000", value="55"),  # 男×総数
            # 産業別（cat04≠'000'）・地位別（cat02≠'000'）は marginal 復元で落とす。
            _base_2010(cat01_code="000", cat03_code="001", cat04_code="018", value="999"),
            _base_2010(cat01_code="000", cat03_code="001", cat02_code="002", value="888"),
        ]
    )
    df = occupation_municipality.clean_2010(tidy)
    by = {(r["sex_code"], r["occupation_code"]): r for r in df.iter_rows(named=True)}
    assert {k[1] for k in by} == {"100", "110", "220"}
    assert by[("0", "110")]["workers"] == 40 and by[("0", "110")]["occupation"] == "Ａ管理的職業従事者"
    assert by[("1", "100")]["workers"] == 55 and by[("1", "100")]["sex"] == "男"
    assert df["year"][0] == 2010


def test_2005_maps_and_conserves() -> None:
    """cat02(数字・2010 と同一体系)写像・男女(cat01 3桁)写像・総数==Σ大分類（軽量marginal）。"""
    tidy = pl.DataFrame(
        [
            _base_2005(cat01_code="000", cat02_code="000", value="100"),  # 総数 → 100
            _base_2005(cat01_code="000", cat02_code="001", value="60"),  # A管理的 → 110
            _base_2005(cat01_code="000", cat02_code="010", value="34"),  # B専門技術 → 120
            _base_2005(cat01_code="000", cat02_code="299", value="6"),  # L分類不能 → 220
            _base_2005(cat01_code="001", cat02_code="000", value="55"),  # 男×総数
        ]
    )
    df = occupation_municipality.clean_2005(tidy)
    by = {(r["sex_code"], r["occupation_code"]): r for r in df.iter_rows(named=True)}
    assert by[("0", "110")]["workers"] == 60 and by[("0", "110")]["occupation"] == "Ａ管理的職業従事者"
    assert by[("1", "100")]["workers"] == 55 and by[("1", "100")]["sex"] == "男"
    assert df["year"][0] == 2005
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") == "100"))["workers"][0]
    parts = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") != "100"))["workers"].sum()
    assert total == parts == 100
