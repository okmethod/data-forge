"""世帯の種類別 世帯数・世帯人員 cleaner（households）の単体テスト。

世帯数(tab=040)・世帯人員(tab=050)の横並び束ね／1世帯当たり人員(1390)と DID 行の除外／
世帯の種類の写像（総数=一般+施設）を手組み tidy で検証する。
本表は area master 不要・不詳注入無しの低コスト fact ゆえ、cleaner の単体テストで担保する。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_household_type_conservation
        保存則（世帯種別）。各 area×year で 総数(100) == 一般世帯(110) + 施設等の世帯(120)
        （世帯数・世帯人員とも）。
    test_schema_and_two_measures
        スキーマ・2測度。8列・households/household_members の同時保持と総数行の値。
    test_drops_avg_and_did_rows
        不要行の除去。1世帯当たり人員(tab 1390)・人口集中地区(area 00100/00200)行を落とす。
    test_prefecture_keeps_area_and_null_on_missing_measure
        欠損の null 化。県で欠測測度・欠損記号 "-" を左結合で null にする。
"""

import polars as pl

from data_forge.sources.estat import households

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


def _row(*, tab, htype, value, area="00000", area_name="全国", level="1", time="2020000000"):
    return {
        "tab_code": tab,
        "cat01_code": htype,
        "area_code": area,
        "area_name": area_name,
        "area_level": level,
        "time_code": time,
        "value": str(value),
    }


def _tidy() -> pl.DataFrame:
    rows = [
        # 全国・総数: 世帯数=100 / 世帯人員=250
        _row(tab="040", htype="100", value=100),
        _row(tab="050", htype="100", value=250),
        # 全国・一般世帯 / 施設等の世帯（総数=一般+施設の保存確認用）
        _row(tab="040", htype="110", value=90),
        _row(tab="050", htype="110", value=230),
        _row(tab="040", htype="120", value=10),
        _row(tab="050", htype="120", value=20),
        # 捨てられるべき行:
        _row(tab="1390", htype="100", value=2.5),  # 1世帯当たり人員 → 導出可能ゆえ除外
        _row(tab="040", htype="100", value=999, area="00100", area_name="人口集中地区", level="2"),
        _row(tab="050", htype="100", value=999, area="00100", area_name="人口集中地区", level="2"),
    ]
    return pl.DataFrame(rows)


def test_schema_and_two_measures():
    df = households.clean_households(_tidy())
    assert df.columns == _COLUMNS
    total = df.filter(pl.col("household_type_code") == "100").row(0, named=True)
    assert total["households"] == 100
    assert total["household_members"] == 250
    assert total["year"] == 2020
    assert total["area_code"] == "00000"
    assert total["is_current"] is True


def test_drops_avg_and_did_rows():
    df = households.clean_households(_tidy())
    # 1390（1世帯当たり人員）は列にも行にも現れない（測定量は households/members の2つだけ）。
    assert "household_size" not in df.columns
    # DID（人口集中地区）行は地理単位でないため除外。
    assert df.filter(pl.col("area_code").is_in(["00100", "00200"])).height == 0


def test_household_type_conservation():
    df = households.clean_households(_tidy())
    by_type = {
        r["household_type_code"]: r["households"]
        for r in df.filter(pl.col("area_code") == "00000").iter_rows(named=True)
    }
    assert by_type["110"] + by_type["120"] == by_type["100"]  # 一般90 + 施設10 == 総数100


def test_prefecture_keeps_area_and_null_on_missing_measure():
    tidy = pl.DataFrame(
        [
            _row(tab="040", htype="100", value=50, area="01000", area_name="北海道", level="2"),
            # 世帯人員(050)は欠落 → household_members は null
            _row(tab="040", htype="100", value="-", area="02000", area_name="青森県", level="2"),
        ]
    )
    df = households.clean_households(tidy)
    hokkaido = df.filter(pl.col("area_code") == "01000").row(0, named=True)
    assert hokkaido["area_level"] == 2
    assert hokkaido["households"] == 50
    assert hokkaido["household_members"] is None  # 050 行なし → 左結合で null
    aomori = df.filter(pl.col("area_code") == "02000").row(0, named=True)
    assert aomori["households"] is None  # 欠損記号 "-" は null
