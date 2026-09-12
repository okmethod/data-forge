"""年齢5歳階級×男女別人口 cleaner（age5）の単体テスト。

全国表(area軸なし→合成)と都道府県表(area軸あり)の写像・共通粒度への畳み込み
（85+終端／全国のみ細分320-370は310へ畳む・再掲380-400は捨てる）・不詳補完値(time 000010)の除外・
年齢不詳の導出注入（Σ5歳階級+不詳==総数）を手組み tidy で検証する。
マクロ系列は 47県固定＝合併なし・area master 非経由ゆえ、age5year.py が保存則を恒等成立させる。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_national_schema_and_area_synthesis
        スキーマ・全国合成。全国表(380)へ 00000/全国/level1 を合成。
    test_prefecture_keeps_area_and_has_no_national
        都道府県表(381)は area=47県・全国行なし。
    test_national_folds_85plus_subdivisions
        85+細分の畳み込み。全国表のみの 85+細分(320-370) を 85歳以上(310) へ合算し共通粒度へ揃える。
    test_national_drops_recategory_and_imputed
        不要行の除去。(再掲)3区分(380-400)・不詳補完値(末尾000010)を落とす。
    test_national_injects_age_unknown
        年齢保存（不詳導出注入）。全地域・全年で Σ(5歳階級) + 不詳 == 総数（不詳=総数−Σ）。実データ違反 0。
    test_national_sex_conservation
        男女保存。男 + 女 == 総数。実データ違反は広島県 1925 年 80〜84歳の 1 セル（50 人）のみ＝
        原資料固有の差分（加工由来でない・将来 CONSERVATION_DIFFS 相当で受容）。
"""

import polars as pl

from data_forge.sources.estat import age5year

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
    # 旧回型（85歳以上を 310 で直接持つ）: 総数100 / 0-4=30 / 5-9=25 / 85+(310)=40 → Σ5歳階級=95, 不詳=5。
    rows = [
        _row(sex="総数", age="100", value=100),
        _row(sex="総数", age="110", value=30),
        _row(sex="総数", age="120", value=25),
        _row(sex="総数", age="310", value=40),
        # 捨てられるべき行:
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


def _national_tidy_subdivided() -> pl.DataFrame:
    # 令和型（310 を持たず 85+ を 320-370 に細分）: 総数100 / 0-4=30 / 5-9=25 /
    # 85-89(320)=20 / 90-94(330)=15 / 95+(340)=5 → 畳んだ 85+(310)=40, Σ5歳階級=95, 不詳=5。
    rows = [
        _row(sex="総数", age="100", value=100),
        _row(sex="総数", age="110", value=30),
        _row(sex="総数", age="120", value=25),
        _row(sex="総数", age="320", value=20),
        _row(sex="総数", age="330", value=15),
        _row(sex="総数", age="340", value=5),
        _row(sex="総数", age="380", value=55),  # （再掲）15歳未満 → 除外
    ]
    return pl.DataFrame(rows)


def test_national_folds_85plus_subdivisions():
    df = age5year.clean_national(_national_tidy_subdivided())
    codes = set(df.filter(pl.col("sex_code") == "0")["age_class_code"].to_list())
    # 85+細分(320-370)は個別に残らず 310 へ畳まれる。
    assert codes.isdisjoint({"320", "330", "340", "350", "360", "370"})
    assert "310" in codes
    row310 = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "310")).row(0, named=True)
    assert row310["population"] == 40  # 20+15+5
    assert row310["age_class"] == "85歳以上"
    # 畳み込み後も年齢保存: 不詳 = 総数100 − Σ5歳階級(30+25+40)=5。
    unknown = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)
    assert unknown["population"] == 5


def test_national_schema_and_area_synthesis():
    df = age5year.clean_national(_national_tidy())
    assert df.columns == _COLUMNS
    nat = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100")).row(0, named=True)
    assert nat["area_code"] == "00000"  # area 軸なし → 全国を合成
    assert nat["area_name"] == "全国"
    assert nat["area_level"] == 1
    assert nat["population"] == 100
    assert nat["year"] == 2020
    assert nat["is_current"] is True


def test_national_drops_recategory_and_imputed():
    df = age5year.clean_national(_national_tidy())
    codes = set(df.filter(pl.col("sex_code") == "0")["age_class_code"].to_list())
    # 再掲(380)は採らない。85+(310)は残る。
    assert "380" not in codes
    assert "310" in codes
    # 5歳階級合計は不詳補完値(999→time000010の30)を混ぜず 30+25+40=95。
    parts = df.filter((pl.col("sex_code") == "0") & pl.col("age_class_code").is_in(["110", "120", "310"]))[
        "population"
    ].sum()
    assert parts == 95


def test_national_injects_age_unknown():
    df = age5year.clean_national(_national_tidy())
    unknown = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)
    assert unknown["population"] == 5  # 総数100 − Σ5歳階級95
    assert unknown["age_class"] == "年齢不詳"
    # 年齢保存: Σ5歳階級 + 不詳 == 総数
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0]
    non_total = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") != "100"))["population"].sum()
    assert non_total == total


def test_national_sex_conservation():
    df = age5year.clean_national(_national_tidy())
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
    df = age5year.clean_prefecture(tidy)
    assert df.columns == _COLUMNS
    row = df.filter(pl.col("age_class_code") == "100").row(0, named=True)
    assert row["area_code"] == "01000"  # area 軸をそのまま採る（全国は合成しない）
    assert row["area_level"] == 2
    assert df.filter(pl.col("area_code") == "00000").height == 0
    # 不詳 = 200 − (120+70) = 10
    unknown = df.filter(pl.col("age_class_code") == "999").row(0, named=True)
    assert unknown["population"] == 10
