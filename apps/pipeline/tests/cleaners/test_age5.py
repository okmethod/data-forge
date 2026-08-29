"""年齢5歳階級×男女別人口 cleaner（age5）の単体テスト。

全国表(area軸なし→合成)と都道府県表(area軸あり)の写像・共通粒度の絞り込み
（85+終端／全国のみ細分320-370と再掲380-400を捨てる）・不詳補完値(time 000010)の除外・
年齢不詳の導出注入（Σ5歳階級+不詳==総数）を手組み tidy で検証する。
"""

import polars as pl

from data_forge.sources.estat import age5

# 男女コード（cat01）: 100=総数/110=男/120=女。年齢コード（cat02）は e-Stat のまま。
_SEX = {"総数": "100", "男": "110", "女": "120"}


def _row(*, sex, age, value, time="2020000000", area=None):
    r = {
        "tab_code": "020",
        "cat01_code": _SEX[sex],
        "cat02_code": age,
        "time_code": time,
        "value": str(value),
    }
    if area is not None:
        r |= {"area_code": area, "area_name": f"県{area}", "area_level": "2"}
    return r


_COLUMNS = [
    "area_code",
    "area_name",
    "area_level",
    "sex_code",
    "sex",
    "age_class_code",
    "age_class",
    "year",
    "population",
    "is_current",
]


def _national_tidy() -> pl.DataFrame:
    # 総数: 総数100 / 0-4=30 / 5-9=25 / 85+=40 → Σ5歳階級=95, 不詳=5。
    rows = [
        _row(sex="総数", age="100", value=100),
        _row(sex="総数", age="110", value=30),
        _row(sex="総数", age="120", value=25),
        _row(sex="総数", age="310", value=40),
        # 捨てられるべき行:
        _row(sex="総数", age="320", value=10),  # 全国のみの85+細分(85-89) → 除外
        _row(sex="総数", age="380", value=55),  # （再掲）15歳未満 → 除外
        _row(sex="総数", age="110", value=999, time="2020000010"),  # 不詳補完値 → 除外
        # 男女（男女保存の確認用: 男+女=総数）
        _row(sex="男", age="100", value=48),
        _row(sex="女", age="100", value=52),
        # 別の tab（割合024/性比1120）混入 → 除外
        {
            "tab_code": "024",
            "cat01_code": "100",
            "cat02_code": "100",
            "time_code": "2020000000",
            "value": "12.3",
        },
    ]
    return pl.DataFrame(rows)


def test_national_schema_and_area_synthesis():
    df = age5.clean_national(_national_tidy())
    assert df.columns == _COLUMNS
    nat = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100")).row(0, named=True)
    assert nat["area_code"] == "00000"  # area 軸なし → 全国を合成
    assert nat["area_name"] == "全国"
    assert nat["area_level"] == 1
    assert nat["population"] == 100
    assert nat["year"] == 2020
    assert nat["is_current"] is True


def test_national_drops_finer_and_recategory_and_imputed():
    df = age5.clean_national(_national_tidy())
    codes = set(df.filter(pl.col("sex_code") == "0")["age_class_code"].to_list())
    # 85+細分(320)・再掲(380)は採らない。85+(310)は残る。
    assert "320" not in codes and "380" not in codes
    assert "310" in codes
    # 5歳階級合計は不詳補完値(999→time000010の30)を混ぜず 30+25+40=95。
    parts = df.filter((pl.col("sex_code") == "0") & pl.col("age_class_code").is_in(["110", "120", "310"]))[
        "population"
    ].sum()
    assert parts == 95


def test_national_injects_age_unknown():
    df = age5.clean_national(_national_tidy())
    unknown = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)
    assert unknown["population"] == 5  # 総数100 − Σ5歳階級95
    assert unknown["age_class"] == "年齢不詳"
    # 年齢保存: Σ5歳階級 + 不詳 == 総数
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0]
    non_total = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") != "100"))["population"].sum()
    assert non_total == total


def test_national_sex_conservation():
    df = age5.clean_national(_national_tidy())
    by_sex = {
        r["sex_code"]: r["population"] for r in df.filter(pl.col("age_class_code") == "100").iter_rows(named=True)
    }
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 男48 + 女52 == 総数100


def test_prefecture_keeps_area_and_has_no_national():
    tidy = pl.DataFrame(
        [
            _row(sex="総数", age="100", value=200, area="01000"),
            _row(sex="総数", age="110", value=120, area="01000"),
            _row(sex="総数", age="310", value=70, area="01000"),
        ]
    )
    df = age5.clean_prefecture(tidy)
    assert df.columns == _COLUMNS
    row = df.filter(pl.col("age_class_code") == "100").row(0, named=True)
    assert row["area_code"] == "01000"  # area 軸をそのまま採る（全国は合成しない）
    assert row["area_level"] == 2
    assert df.filter(pl.col("area_code") == "00000").height == 0
    # 不詳 = 200 − (120+70) = 10
    unknown = df.filter(pl.col("age_class_code") == "999").row(0, named=True)
    assert unknown["population"] == 10
