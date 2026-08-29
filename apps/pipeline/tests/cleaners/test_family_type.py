"""世帯の家族類型16区分別 世帯数・世帯人員 cleaner（family_type）の単体テスト。

一般世帯数(tab=6)・一般世帯人員(tab=7)の横並び束ね／1世帯当たり人員(1390)・世帯数割合(1930)の除外／
家族類型の写像と family_type_level の付与／家族類型不詳(999)の導出注入と保存則
（総数=110+280+290+不詳）を手組み tidy で検証する。
"""

import polars as pl

from data_forge.sources.estat import family_type

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


def _row(*, tab, ftype, value, level="2", area="00000", area_name="全国", area_level="1", time="2020000000"):
    return {
        "tab_code": tab,
        "cat01_code": ftype,
        "cat01_level": level,
        "area_code": area,
        "area_name": area_name,
        "area_level": area_level,
        "time_code": time,
        "value": str(value),
    }


def _tidy() -> pl.DataFrame:
    # 総数(105/260) > 110+280+290(100/250) ゆえ不詳(999)=5世帯/10人が導出注入される。
    # 110 = 核家族(120) + 核家族以外(170)（120/170 は 110 の内訳＝不詳の減算には含めない）。
    rows = [
        _row(tab="6", ftype="100", value=105, level="1"),
        _row(tab="7", ftype="100", value=260, level="1"),
        _row(tab="6", ftype="110", value=70, level="2"),
        _row(tab="7", ftype="110", value=200, level="2"),
        _row(tab="6", ftype="120", value=50, level="3"),
        _row(tab="6", ftype="170", value=20, level="3"),
        _row(tab="6", ftype="280", value=10, level="2"),
        _row(tab="7", ftype="280", value=25, level="2"),
        _row(tab="6", ftype="290", value=20, level="2"),
        _row(tab="7", ftype="290", value=25, level="2"),
        # 捨てられるべき行: 1世帯当たり人員 / 世帯数割合（どちらも導出可能）
        _row(tab="1390", ftype="100", value=2.5, level="1"),
        _row(tab="1930", ftype="290", value=20.0, level="2"),
    ]
    return pl.DataFrame(rows)


def test_schema_and_two_measures():
    df = family_type.clean_family_type(_tidy())
    assert df.columns == _COLUMNS
    total = df.filter(pl.col("family_type_code") == "100").row(0, named=True)
    assert total["households"] == 105
    assert total["household_members"] == 260
    assert total["family_type_level"] == 1
    assert total["year"] == 2020
    assert total["area_code"] == "00000"
    assert total["is_current"] is True


def test_drops_ratio_rows():
    df = family_type.clean_family_type(_tidy())
    # 1390（1世帯当たり人員）/ 1930（世帯数割合）は測定量に現れない（households/members の2つだけ）。
    assert "household_size" not in df.columns
    assert "household_ratio" not in df.columns
    # 世帯数割合(1930)だけを持つ行は tab フィルタで落ち、単独世帯(290)の households は実数の20。
    single = df.filter(pl.col("family_type_code") == "290").row(0, named=True)
    assert single["households"] == 20
    assert single["family_type_level"] == 2


def test_injects_unknown_and_closes_total():
    df = family_type.clean_family_type(_tidy())
    unknown = df.filter(pl.col("family_type_code") == "999").row(0, named=True)
    assert unknown["family_type"] == "家族類型不詳"
    assert unknown["family_type_level"] == 2
    # 不詳 = 総数 − (110 + 280 + 290)。households: 105-100=5 / members: 260-250=10。
    assert unknown["households"] == 5
    assert unknown["household_members"] == 10


def test_family_type_tree_conservation():
    df = family_type.clean_family_type(_tidy())
    hh = {
        r["family_type_code"]: r["households"]
        for r in df.filter(pl.col("area_code") == "00000").iter_rows(named=True)
    }
    # 総数(100) == 親族のみ(110) + 非親族(280) + 単独(290) + 不詳(999)
    assert hh["110"] + hh["280"] + hh["290"] + hh["999"] == hh["100"]
    # 親族のみ(110) == 核家族(120) + 核家族以外(170)
    assert hh["120"] + hh["170"] == hh["110"]


def test_prefecture_keeps_area_and_null_on_missing_measure():
    tidy = pl.DataFrame(
        [
            _row(tab="6", ftype="100", value=50, level="1", area="01000", area_name="北海道", area_level="2"),
            # 世帯人員(7)は欠落 → household_members は null
            _row(tab="6", ftype="100", value="-", level="1", area="02000", area_name="青森県", area_level="2"),
        ]
    )
    df = family_type.clean_family_type(tidy)
    hokkaido = df.filter(pl.col("area_code") == "01000").row(0, named=True)
    assert hokkaido["area_level"] == 2
    assert hokkaido["households"] == 50
    assert hokkaido["household_members"] is None  # tab=7 行なし → 左結合で null
    aomori = df.filter(pl.col("area_code") == "02000").row(0, named=True)
    assert aomori["households"] is None  # 欠損記号 "-" は null
