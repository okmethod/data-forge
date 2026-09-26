"""労働力状態×男女別人口 市区町村版 cleaner（labor_force_municipality）の単体テスト。

市区町村版（2015=0003174622）は労働力状態コードがマクロ（labor_force.LABOR_STATUS の 100〜140＋999）と
別体系（cat02・0000/0010/0020…）で、年別マップでマクロコードへ写像して縫合する。男女は cat04・4桁体系。
マクロと違い**不詳(999)を直接コード(0170)で持つ＝導出注入しない**点、非労働力内訳/就業者内訳/率行の除外、
保存（総数 == 労働力人口 + 非労働力人口 + 不詳）を回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「労働力状態」節が正典。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro labor_force と同一の10列・同一 dtype を出す。
    test_2015_maps_and_drops_subitems … cat02 をマクロコードへ写像し・男女(cat04)を写像し・
        非労働力内訳/就業者内訳/率行を除外し・不詳(0170→999)を直接写像する（導出注入なし）。
    test_2015_conservation … 総数 == 労働力人口 + 非労働力人口 + 不詳（就業者/失業者は再掲で足さない）。
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
