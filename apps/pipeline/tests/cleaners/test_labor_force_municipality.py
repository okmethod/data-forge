"""労働力状態×男女別人口 市区町村版 cleaner（labor_force_municipality）の単体テスト。

市区町村版（2015=0003174622）は労働力状態コードがマクロ（labor_force.LABOR_STATUS の 100〜140＋999）と
別体系（cat02・0000/0010/0020…）で、年別マップでマクロコードへ写像して縫合する。男女は cat04・4桁体系。
マクロと違い**2015/2010/2020 は不詳(999)を直接コードで持つ＝導出注入しない**点、非労働力内訳/就業者内訳/
率行の除外、保存（総数 == 労働力人口 + 非労働力人口 + 不詳）を回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「労働力状態」節が正典。

2020（0003450558・全市区町村版）は労働力状態×年齢×男女クロスで、年齢総数（cat02='00'）スライスで
労働力状態marginalを復元する。労働力状態は cat03・1桁、男女は cat01・1桁体系で不詳は直接コード(3)。
2010（0003052121）は同クロスで、年齢総数（cat03='000'）×DID全域（cat01='00710'）スライスで復元する。
労働力状態は cat02・3桁、男女は cat04・3桁体系で不詳は直接コード(017)。
2005（0000033948）は配偶関係×男女×年齢×労働力状態クロスで、配偶総数(cat02='000')×年齢総数(cat04='515')
×全域(cat01='00700')スライスで復元する。労働力状態は cat05・3桁、男女は cat03・3桁体系。
**2005 は不詳の独立コードが無く総数に内包されるため、マクロと同じく 総数−労働力−非労働力で 999 を導出注入する**。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro labor_force と同一の10列・同一 dtype を出す。
    test_2015_maps_and_drops_subitems … cat02 をマクロコードへ写像し・男女(cat04)を写像し・
        非労働力内訳/就業者内訳/率行を除外し・不詳(0170→999)を直接写像する（導出注入なし）。
    test_2015_conservation … 総数 == 労働力人口 + 非労働力人口 + 不詳（就業者/失業者は再掲で足さない）。
    test_2020_maps_and_marginalizes … cat03(1桁)写像・男女(cat01 1桁)写像・年齢別(cat02≠'00')の脱落・
        不詳(3→999)の直接写像（導出注入なし）を確かめる。
    test_2010_maps_and_marginalizes … cat02(3桁)写像・男女(cat04 3桁)写像・年齢別(cat03≠'000')/
        DID別(cat01≠'00710')の脱落・不詳(017→999)の直接写像を確かめる。
    test_2005_injects_unknown … cat05(3桁)写像・男女(cat03 3桁)写像し・不詳(999)を
        総数−労働力−非労働力で導出注入する（独立コードが無い年）。
"""

import polars as pl

from data_forge.sources.estat import labor_force, labor_force_municipality


def _base(**kw) -> dict:
    row = {"area_code": "01100", "area_name": "市A", "area_level": "4", "tab_code": "4", "time_code": "2015000000"}
    row.update(kw)
    return row


def test_shares_schema_with_macro() -> None:
    """2015 ミクロ cleaner が macro labor_force と同一の10列・dtype を出す。"""
    micro = labor_force_municipality.clean_2015(
        pl.DataFrame([_base(cat04_code="0000", cat02_code=c, value="1") for c in ("0000", "0010", "0170")])
    )
    macro = labor_force.clean_labor_force(
        pl.DataFrame(
            [
                {
                    "tab_code": "320",
                    "cat01_code": c,
                    "cat02_code": "100",
                    "area_code": "01000",
                    "area_name": "北海道",
                    "area_level": "2",
                    "time_code": "2015000000",
                    "value": "1",
                }
                for c in ("100", "110", "140")
            ]
        )
    )
    assert micro.columns == macro.columns
    assert micro.schema == macro.schema, "dtype がマクロと不一致（縦積み不可）"


def test_2015_maps_and_drops_subitems() -> None:
    tidy = pl.DataFrame(
        [
            _base(cat04_code="0000", cat02_code="0000", value="200"),  # 総数 → 100
            _base(cat04_code="0000", cat02_code="0010", value="120"),  # 労働力人口 → 110
            _base(cat04_code="0000", cat02_code="0020", value="115"),  # 就業者(再掲) → 120
            _base(cat04_code="0000", cat02_code="0030", value="90"),  # 就業者内訳(主に仕事)＝落とす
            _base(cat04_code="0000", cat02_code="0120", value="5"),  # 完全失業者(再掲) → 130
            _base(cat04_code="0000", cat02_code="0130", value="70"),  # 非労働力人口 → 140
            _base(cat04_code="0000", cat02_code="0140", value="30"),  # 非労働力内訳(家事)＝落とす
            _base(cat04_code="0000", cat02_code="0170", value="10"),  # 不詳 → 999（直接）
            _base(cat04_code="0000", cat02_code="0180", value="60"),  # 労働力率(%)＝落とす
        ]
    )
    df = labor_force_municipality.clean_2015(tidy)
    by = {r["labor_status_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120", "130", "140", "999"}  # 内訳/率は不採用
    assert by["999"]["population"] == 10 and by["999"]["labor_status"] == "労働力状態不詳"  # 直接写像（導出でない）


def test_2015_conservation() -> None:
    """総数 == 労働力人口 + 非労働力人口 + 不詳（就業者120/失業者130 は労働力人口の再掲で足さない）。"""
    tidy = pl.DataFrame(
        [
            _base(cat04_code="0000", cat02_code="0000", value="200"),  # 総数
            _base(cat04_code="0000", cat02_code="0010", value="120"),  # 労働力人口
            _base(cat04_code="0000", cat02_code="0130", value="70"),  # 非労働力人口
            _base(cat04_code="0000", cat02_code="0170", value="10"),  # 不詳
        ]
    )
    df = labor_force_municipality.clean_2015(tidy)
    by = {r["labor_status_code"]: r["population"] for r in df.iter_rows(named=True)}
    assert by["100"] == by["110"] + by["140"] + by["999"] == 200


def _base_2020(**kw) -> dict:
    """2020 労働力状態×年齢×男女クロスの行（tab=2020_01・cat02=年齢・cat02='00'が年齢総数＝marginal）。"""
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "2020_01",
        "cat02_code": "00",  # 年齢総数（既定＝労働力状態marginal）
        "time_code": "2020000000",
    }
    row.update(kw)
    return row


def _base_2010(**kw) -> dict:
    """2010 労働力状態×年齢×男女クロスの行（tab=320・cat01=DID・cat02=労働力状態・cat03=年齢・cat04=男女）。

    既定は DID全域(cat01='00710')・年齢総数(cat03='000')＝労働力状態marginal。
    """
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "320",
        "cat01_code": "00710",  # DID 全域（人口集中地区 00711 は落とす）
        "cat03_code": "000",  # 年齢 総数
        "time_code": "2010000000",
    }
    row.update(kw)
    return row


def _base_2005(**kw) -> dict:
    """2005 配偶関係×男女×年齢×労働力状態クロスの行（cat01=DID・cat02=配偶・cat03=男女・cat04=年齢・cat05=労働力）。

    既定は全域(cat01='00700')・配偶総数(cat02='000')・年齢総数(cat04='515')＝労働力状態marginal。
    """
    row = {
        "area_code": "01100",
        "area_name": "市A",
        "area_level": "4",
        "tab_code": "1",
        "cat01_code": "00700",  # 全域
        "cat02_code": "000",  # 配偶関係 総数
        "cat04_code": "515",  # 年齢 総数（15歳以上）
        "time_code": "2005000000",
    }
    row.update(kw)
    return row


def test_2020_maps_and_marginalizes() -> None:
    """cat03(1桁)写像・男女(cat01 1桁)写像・年齢別(cat02≠'00')の脱落・不詳(3→999)の直接写像。"""
    tidy = pl.DataFrame(
        [
            _base_2020(cat01_code="0", cat03_code="0", value="200"),  # 総数 → 100
            _base_2020(cat01_code="0", cat03_code="1", value="120"),  # 労働力人口 → 110
            _base_2020(cat01_code="0", cat03_code="11", value="115"),  # 就業者(再掲 lv2) → 120
            _base_2020(cat01_code="0", cat03_code="111", value="90"),  # 就業者内訳(lv3)＝落とす
            _base_2020(cat01_code="0", cat03_code="12", value="5"),  # 完全失業者(再掲) → 130
            _base_2020(cat01_code="0", cat03_code="2", value="70"),  # 非労働力人口 → 140
            _base_2020(cat01_code="0", cat03_code="21", value="30"),  # 非労働力内訳(家事)＝落とす
            _base_2020(cat01_code="0", cat03_code="3", value="10"),  # 不詳 → 999（直接）
            # 年齢別（cat02≠'00'）は marginal 復元で落とす。
            _base_2020(cat01_code="0", cat03_code="1", cat02_code="01", value="999"),
        ]
    )
    df = labor_force_municipality.clean_2020(tidy)
    by = {r["labor_status_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120", "130", "140", "999"}
    assert by["999"]["population"] == 10 and by["999"]["labor_status"] == "労働力状態不詳"  # 直接写像（導出でない）
    assert by["100"]["population"] == by["110"]["population"] + by["140"]["population"] + by["999"]["population"]
    assert df["year"][0] == 2020


def test_2010_maps_and_marginalizes() -> None:
    """cat02(3桁)写像・男女(cat04 3桁)写像・年齢別(cat03≠'000')/DID別(cat01≠'00710')の脱落・不詳(017→999)直接。"""
    tidy = pl.DataFrame(
        [
            _base_2010(cat04_code="000", cat02_code="000", value="200"),  # 総数 → 100
            _base_2010(cat04_code="000", cat02_code="001", value="120"),  # 労働力人口 → 110
            _base_2010(cat04_code="000", cat02_code="002", value="115"),  # 就業者(再掲 lv2) → 120
            _base_2010(cat04_code="000", cat02_code="003", value="90"),  # 就業者内訳(lv3)＝落とす
            _base_2010(cat04_code="000", cat02_code="012", value="5"),  # 完全失業者(再掲) → 130
            _base_2010(cat04_code="000", cat02_code="013", value="70"),  # 非労働力人口 → 140
            _base_2010(cat04_code="000", cat02_code="014", value="30"),  # 非労働力内訳(家事)＝落とす
            _base_2010(cat04_code="000", cat02_code="017", value="10"),  # 不詳 → 999（直接）
            # 年齢別（cat03≠'000'）・DID（00711）は marginal 復元で落とす。
            _base_2010(cat04_code="000", cat02_code="001", cat03_code="203", value="999"),
            _base_2010(cat04_code="000", cat02_code="001", cat01_code="00711", value="888"),
        ]
    )
    df = labor_force_municipality.clean_2010(tidy)
    by = {r["labor_status_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120", "130", "140", "999"}
    assert by["999"]["population"] == 10  # 直接写像（導出でない）
    assert by["100"]["population"] == by["110"]["population"] + by["140"]["population"] + by["999"]["population"]
    assert df["year"][0] == 2010


def test_2005_injects_unknown() -> None:
    """cat05(3桁)写像・男女(cat03 3桁)写像し・不詳(999)を 総数−労働力−非労働力で導出注入する。"""
    tidy = pl.DataFrame(
        [
            _base_2005(cat03_code="000", cat05_code="000", value="200"),  # 総数（不詳含む） → 100
            _base_2005(cat03_code="000", cat05_code="001", value="120"),  # 労働力人口 → 110
            _base_2005(cat03_code="000", cat05_code="002", value="115"),  # 就業者(再掲) → 120
            _base_2005(cat03_code="000", cat05_code="003", value="90"),  # 就業者内訳(lv3)＝落とす
            _base_2005(cat03_code="000", cat05_code="012", value="5"),  # 完全失業者(再掲) → 130
            _base_2005(cat03_code="000", cat05_code="013", value="70"),  # 非労働力人口 → 140
            _base_2005(cat03_code="000", cat05_code="014", value="30"),  # 非労働力内訳(家事)＝落とす
        ]
    )
    df = labor_force_municipality.clean_2005(tidy)
    by = {r["labor_status_code"]: r for r in df.iter_rows(named=True)}
    assert set(by) == {"100", "110", "120", "130", "140", "999"}  # 999 は導出注入で出現
    # 不詳 = 総数 200 − 労働力110(120) − 非労働力140(70) = 10（直接コードが無いので導出）。
    assert by["999"]["population"] == 10 and by["999"]["labor_status"] == "労働力状態不詳"
    assert by["100"]["population"] == by["110"]["population"] + by["140"]["population"] + by["999"]["population"]
    assert df["year"][0] == 2005
