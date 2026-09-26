"""職業大分類×男女別就業者数 市区町村版 cleaner（occupation_municipality）の単体テスト。

市区町村版（2015=0003176482）は職業分類コードがマクロ（occupation.OCCUPATION_MAJOR12 の 100〜220）と
別体系（cat01・0000/0010/0100…）で、年別マップでマクロコードへ写像して縫合する。男女は cat02・4桁体系。
割合(%)行の除外と、総数==Σ大分類（不詳注入なし）を回帰ガードする。
実 statsDataId・軸コードは docs/sources/estat-census-catalog.md「職業（大分類）」節が正典。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_shares_schema_with_macro … macro occupation(major12) と同一の10列・同一 dtype を出す。
    test_2015_maps_and_drops_rate … cat01 をマクロコードへ写像し・男女(cat02)を写像し・割合行を除外する。
    test_2015_conservation … 「分類不能(L=220)」を含む大分類で 総数 == Σ大分類 が閉じる。
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
