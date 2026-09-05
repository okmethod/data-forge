"""年齢5歳階級×男女別人口 市区町村版 cleaner（age5_municipality）の単体テスト。

各回で **軸割当（どの catNN が男女／年齢か）もコード体系も違う**点、
余分軸（出生の月・全域/DID）を総数コードで潰す点、100歳以上まで保持する点、
年齢不詳は実コードをそのまま採る（導出注入しない）点、
そして **nationality 軸**（総数=0/日本人=1）を手組み tidy で検証する。
特に 2015 は男女=cat03・年齢=cat02 と入れ替わる（getMetaInfo と食い違う実データ形）ため重点的に見る。
nationality は年で扱いが違う: 1980/1985=総数のみ定数注入・1990/1995=日本人のみ定数注入・
2010/2015/2020=国籍軸を残して総数と日本人を両方出す。ミクロ系列は合併畳込を伴うため、
本 cleaner の年別テスト＋ area module（tests/area/test_area.py）＋実データで担保する。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_2020_age_unknown_is_real_not_injected / test_1990_japanese_constant_and_no_unknown
        年齢保存。Σ(5歳階級) + 不詳 == 総数（全 area×sex 違反 0）。
        不詳は原表の実コードを採用・1990/1995 は原表に不詳無し（導出注入しない）。
    test_2020_is_current_flags_obsolete_municipality
        合併畳込。level7 の is_current=false（印西市 12231 総人口 2000:79,780→2020:102,609 と連続）。
    男女保存（男 + 女 == 総数・全 area×age 違反 0）も併せて確認する。

実データ横断で確認済み（回帰ガード）:
    全国＝47都道府県合計 … 各回 diff=0（2020=126,146,099 等・公表値一致）。
    クロスファクト検算（別製品クロス照合）… 市区町村→県 rollup == マクロ系列
    population_by_age5_prefecture(0003410381) が 47県×各年で diff=0。
"""

import polars as pl

from data_forge.sources.estat import age5year_municipality

_COLUMNS = [
    "area_code",
    "area_name",
    "area_level",
    "sex_code",
    "sex",
    "nationality_code",
    "nationality",
    "age_class_code",
    "age_class",
    "year",
    "population",
    "is_current",
]


def _area(area: str, level: str) -> dict:
    return {"area_code": area, "area_name": f"地域{area}", "area_level": level}


def _by_sex(df: pl.DataFrame, age: str = "100", nat: str = "0") -> dict[str, int]:
    """指定年齢階級・国籍の {sex_code: population}（男女保存の確認用。既定は総数国籍）。"""
    rows = df.filter((pl.col("age_class_code") == age) & (pl.col("nationality_code") == nat)).iter_rows(named=True)
    return {r["sex_code"]: r["population"] for r in rows}


# --- 2020（令和型）: 男女=cat02(0/1/2)・年齢=cat03(00-22)・国籍=cat01(0総数) --------
def _row_2020(*, area, level, kokuseki, sex, age, value):
    return {
        "tab_code": "2020_01",
        "cat01_code": kokuseki,  # 国籍
        "cat02_code": sex,  # 男女
        "cat03_code": age,  # 年齢
        "time_code": "2020000000",
        "value": str(value),
        **_area(area, level),
    }


def test_2020_schema_axes_and_both_nationalities():
    rows = [
        # 国籍総数(0)
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="00", value=100),
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="01", value=30),  # 0-4 → 110
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="21", value=5),  # 100歳以上 → 310
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="22", value=8),  # 不詳 → 999
        _row_2020(area="00000", level="1", kokuseki="0", sex="1", age="00", value=48),  # 男
        _row_2020(area="00000", level="1", kokuseki="0", sex="2", age="00", value=52),  # 女
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="R1", value=999),  # 再掲 → 除外
        # 国籍=日本人(1) は捨てず nationality=日本人 として残す
        _row_2020(area="00000", level="1", kokuseki="1", sex="0", age="00", value=90),
    ]
    df = age5year_municipality.clean_2020(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    assert "R1" not in df["age_class_code"].to_list()  # 再掲は落ちる
    # 総数・日本人の両方が出る
    assert set(df["nationality_code"].to_list()) == {"0", "1"}
    # 総数(nationality=0) 総数×総数=100・日本人(nationality=1)=90（混ざらない）
    assert (
        df.filter(
            (pl.col("nationality_code") == "0") & (pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100")
        )["population"][0]
        == 100
    )
    jpn = df.filter(pl.col("nationality_code") == "1")
    assert jpn["nationality"][0] == "日本人"
    assert jpn.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 90
    # 100歳以上を保持（総数側）
    c100 = df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "310")).row(0, named=True)
    assert c100["age_class"] == "100歳以上" and c100["population"] == 5
    # 男女保存（総数国籍）
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]


def test_2020_age_unknown_is_real_not_injected():
    # 不詳(22)は実コード。総数−Σ とは無関係に、生値がそのまま出る（注入なら 100-30-5=65 になるが 8 のはず）。
    rows = [
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="00", value=100),
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="01", value=30),
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="21", value=5),
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="22", value=8),
    ]
    df = age5year_municipality.clean_2020(pl.DataFrame(rows))
    unknown = df.filter(pl.col("age_class_code") == "999").row(0, named=True)
    assert unknown["population"] == 8  # 生値。導出注入(65)ではない
    assert unknown["age_class"] == "年齢不詳"


def test_2020_is_current_flags_obsolete_municipality():
    rows = [
        _row_2020(area="12231", level="4", kokuseki="0", sex="0", age="00", value=100),  # 現存市
        _row_2020(area="0120B", level="7", kokuseki="0", sex="0", age="00", value=50),  # 旧市区町村
    ]
    df = age5year_municipality.clean_2020(pl.DataFrame(rows))
    flags = {r["area_code"]: r["is_current"] for r in df.iter_rows(named=True)}
    assert flags["12231"] is True
    assert flags["0120B"] is False  # level7 → is_current=False


# --- 2015（★軸入替）: 男女=cat03(0000/0010/0020)・年齢=cat02(0000/1180-1490)・国籍=cat04・出生月=cat05 ---
def _row_2015(*, area, level, did, age, kokuseki, tsuki, sex, value):
    return {
        "tab_code": "020",
        "cat01_code": did,  # 全域/DID
        "cat02_code": age,  # ★年齢
        "cat03_code": sex,  # ★男女
        "cat04_code": kokuseki,  # 国籍
        "cat05_code": tsuki,  # 出生の月
        "time_code": "2015000000",
        "value": str(value),
        **_area(area, level),
    }


def test_2015_swapped_axes_and_extra_collapse():
    base = {"area": "00000", "level": "1", "did": "00710", "kokuseki": "0000", "tsuki": "0000"}
    rows = [
        _row_2015(**base, age="0000", sex="0000", value=200),  # 総数
        _row_2015(**base, age="1180", sex="0000", value=60),  # 0-4 → 110
        _row_2015(**base, age="1460", sex="0000", value=7),  # 100歳以上 → 310
        _row_2015(**base, age="1490", sex="0000", value=9),  # 不詳 → 999
        _row_2015(**base, age="0000", sex="0010", value=97),  # 男
        _row_2015(**base, age="0000", sex="0020", value=103),  # 女
        # 潰されるべき: DID(00711)・出生月1月-3月(0010) は捨てられる。日本人(0150) は nationality として残す
        _row_2015(
            area="00000", level="1", did="00711", kokuseki="0000", tsuki="0000", age="0000", sex="0000", value=11
        ),
        _row_2015(
            area="00000", level="1", did="00710", kokuseki="0150", tsuki="0000", age="0000", sex="0000", value=12
        ),
        _row_2015(
            area="00000", level="1", did="00710", kokuseki="0000", tsuki="0010", age="0000", sex="0000", value=13
        ),
    ]
    df = age5year_municipality.clean_2015(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 男女が cat03 から正しく解決される（入替に耐える・総数国籍）
    by_sex = _by_sex(df)
    assert by_sex["0"] == 200 and by_sex["1"] == 97 and by_sex["2"] == 103
    # 年齢が cat02 から解決され 100歳以上を保持（総数国籍）
    assert (
        df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "310")).row(0, named=True)[
            "population"
        ]
        == 7
    )
    # DID/出生月は潰され総数(100)は 200 のまま。日本人(0150) は nationality=日本人 の 12 として残る
    assert by_sex["0"] == 200
    jpn = df.filter(pl.col("nationality_code") == "1")
    assert jpn["nationality"][0] == "日本人"
    assert jpn.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 12
    # 不詳は実コード（総数国籍）
    assert (
        df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)[
            "population"
        ]
        == 9
    )


# --- 2000（0000032965・各歳表だが5歳階級の再掲コードを内包）: 全域/DID=cat01・国籍=cat02・年齢=cat03・男女=cat04 ---
def _row_2000(*, area, level, did, kokuseki, age, sex, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": kokuseki,  # 国籍
        "cat03_code": age,  # 年齢（各歳＋5歳階級再掲）
        "cat04_code": sex,  # 男女
        "time_code": "2000000000",
        "value": str(value),
        **_area(area, level),
    }


def test_2000_picks_age5_recap_drops_single_year_and_both_nationalities():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        # 国籍総数(000)・5歳階級の再掲コード
        _row_2000(**base, kokuseki="000", age="T01", sex="000", value=200),  # 総数 → 100
        _row_2000(**base, kokuseki="000", age="200", sex="000", value=50),  # 0-4 → 110
        _row_2000(**base, kokuseki="000", age="216", sex="000", value=12),  # 80-84 → 270
        _row_2000(**base, kokuseki="000", age="500", sex="000", value=4),  # 100歳以上 → 310
        _row_2000(**base, kokuseki="000", age="900", sex="000", value=9),  # 不詳 → 999
        _row_2000(**base, kokuseki="000", age="T01", sex="001", value=96),  # 男
        _row_2000(**base, kokuseki="000", age="T01", sex="002", value=104),  # 女
        # 各歳（000=0歳・005=5歳）は age_map 非収載で落ちる
        _row_2000(**base, kokuseki="000", age="000", sex="000", value=11),
        _row_2000(**base, kokuseki="000", age="005", sex="000", value=13),
        # DID(00701) は潰される。日本人(001) は nationality=日本人 として残る
        _row_2000(area="00000", level="1", did="00701", kokuseki="000", age="T01", sex="000", value=7),
        _row_2000(area="00000", level="1", did="00700", kokuseki="001", age="T01", sex="000", value=180),
    ]
    df = age5year_municipality.clean_2000(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 各歳（0歳/5歳）は落ち、5歳階級の再掲だけ残る
    assert set(df.filter(pl.col("nationality_code") == "0")["age_class_code"].to_list()) == {
        "100",
        "110",
        "270",
        "310",
        "999",
    }
    # 総数・日本人の両方が出る
    assert set(df["nationality_code"].to_list()) == {"0", "1"}
    # 不詳(900→999)は実コードで保持
    assert (
        df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)[
            "population"
        ]
        == 9
    )
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    # DID 潰し（総数=200 のまま）・男女保存
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 96+104==200
    # 日本人(001→"1")の総数=180
    jpn = df.filter(pl.col("nationality_code") == "1")
    assert jpn["nationality"][0] == "日本人"
    assert jpn.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 180


# --- 2005（0000033783・2000 同型）: 全域/DID=cat01・国籍=cat02・年齢=cat03・男女×出生月=cat04（000/001/006）---
def _row_2005(*, area, level, did, kokuseki, age, sex, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": kokuseki,  # 国籍
        "cat03_code": age,  # 年齢（各歳＋5歳階級再掲）
        "cat04_code": sex,  # 男女×出生月（男女総数は 000/001/006）
        "time_code": "2005000000",
        "value": str(value),
        **_area(area, level),
    }


def test_2005_picks_age5_recap_maps_sex_births_no_age_unknown():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        # 国籍総数(000)・5歳階級の再掲コード（2005 は年齢不詳(900)を持たない）
        _row_2005(**base, kokuseki="000", age="T01", sex="000", value=200),  # 総数 → 100
        _row_2005(**base, kokuseki="000", age="200", sex="000", value=50),  # 0-4 → 110
        _row_2005(**base, kokuseki="000", age="216", sex="000", value=12),  # 80-84 → 270
        _row_2005(**base, kokuseki="000", age="500", sex="000", value=4),  # 100歳以上 → 310
        _row_2005(**base, kokuseki="000", age="T01", sex="001", value=96),  # 男（総数）
        _row_2005(**base, kokuseki="000", age="T01", sex="006", value=104),  # 女（総数）
        # 各歳（000=0歳）は age_map 非収載で落ちる
        _row_2005(**base, kokuseki="000", age="000", sex="000", value=11),
        # 出生月クロス（cat04=002=男の1〜3月 等）は sex_map 非収載で落ちる
        _row_2005(**base, kokuseki="000", age="T01", sex="002", value=25),
        # DID(00701) は潰される。日本人(001) は nationality=日本人 として残る
        _row_2005(area="00000", level="1", did="00701", kokuseki="000", age="T01", sex="000", value=7),
        _row_2005(area="00000", level="1", did="00700", kokuseki="001", age="T01", sex="000", value=180),
    ]
    df = age5year_municipality.clean_2005(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 各歳・出生月クロスは落ち、5歳階級の再掲だけ残る（不詳 999 は存在しない）
    assert set(df.filter(pl.col("nationality_code") == "0")["age_class_code"].to_list()) == {
        "100",
        "110",
        "270",
        "310",
    }
    # 総数・日本人の両方が出る
    assert set(df["nationality_code"].to_list()) == {"0", "1"}
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    # DID 潰し（総数=200 のまま）・男女保存（001→男, 006→女）
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 96+104==200
    # 日本人(001→"1")の総数=180
    jpn = df.filter(pl.col("nationality_code") == "1")
    assert jpn["nationality"][0] == "日本人"
    assert jpn.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 180


# --- 2010: 男女=cat02(000/001/002)・年齢=cat03(000/200-219/600/999)・国籍=cat04・出生月=cat05 -------
def _row_2010(*, area, level, did, sex, age, kokuseki, tsuki, value):
    return {
        "tab_code": "020",
        "cat01_code": did,
        "cat02_code": sex,  # 男女
        "cat03_code": age,  # 年齢
        "cat04_code": kokuseki,
        "cat05_code": tsuki,
        "time_code": "2010000000",
        "value": str(value),
        **_area(area, level),
    }


def test_2010_axes_and_both_nationalities():
    base = {"area": "00000", "level": "1", "did": "00710", "tsuki": "000"}
    rows = [
        # 国籍総数(000)
        _row_2010(**base, kokuseki="000", sex="000", age="000", value=150),  # 総数
        _row_2010(**base, kokuseki="000", sex="000", age="200", value=40),  # 0-4 → 110
        _row_2010(**base, kokuseki="000", sex="000", age="600", value=3),  # 100歳以上 → 310
        _row_2010(**base, kokuseki="000", sex="000", age="999", value=6),  # 不詳
        _row_2010(**base, kokuseki="000", sex="001", age="000", value=73),  # 男
        _row_2010(**base, kokuseki="000", sex="002", age="000", value=77),  # 女
        # 国籍=日本人(100) は nationality=日本人 として残す
        _row_2010(**base, kokuseki="100", sex="000", age="000", value=140),
    ]
    df = age5year_municipality.clean_2010(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    assert set(df["nationality_code"].to_list()) == {"0", "1"}
    assert (
        df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "310")).row(0, named=True)[
            "age_class"
        ]
        == "100歳以上"
    )
    by_sex = _by_sex(df)  # 総数国籍
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 73+77==150
    assert (
        df.filter((pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "999")).row(0, named=True)[
            "population"
        ]
        == 6
    )  # 実コード
    # 日本人(100→"1")の総数=140
    assert (
        df.filter(
            (pl.col("nationality_code") == "1") & (pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100")
        )["population"][0]
        == 140
    )


# --- 1980（最単純型）: tab 軸なし・cat01=全域/DID・cat02=男女(000/001/002)・cat03=年齢(000/001-022) ---
# 国籍/出生の月クロス無し。年齢コードは 3 桁だが体系は 2020 と同型（100歳以上・不詳あり）。
def _row_1980(*, area, level, did, sex, age, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": sex,  # 男女
        "cat03_code": age,  # 年齢
        "time_code": "1980000000",
        "value": str(value),
        **_area(area, level),
    }


def test_1980_no_tab_axis_and_did_collapse():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        _row_1980(**base, sex="000", age="000", value=200),  # 総数
        _row_1980(**base, sex="000", age="001", value=50),  # 0-4 → 110
        _row_1980(**base, sex="000", age="017", value=12),  # 80-84 → 270
        _row_1980(**base, sex="000", age="021", value=4),  # 100歳以上 → 310
        _row_1980(**base, sex="000", age="022", value=9),  # 不詳 → 999
        _row_1980(**base, sex="001", age="000", value=96),  # 男
        _row_1980(**base, sex="002", age="000", value=104),  # 女
        # 潰されるべき: DID(00701) は捨てられる（cat01=全域 のみ採る）
        _row_1980(area="00000", level="1", did="00701", sex="000", age="000", value=11),
    ]
    df = age5year_municipality.clean_1980(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 1980 は総人口のみ＝nationality は総数(0) を定数注入
    assert set(df["nationality_code"].to_list()) == {"0"}
    assert df["nationality"][0] == "総数"
    codes = set(df.filter(pl.col("sex_code") == "0")["age_class_code"].to_list())
    assert {"100", "110", "270", "310", "999"} <= codes
    # 100歳以上・80-84 の名称が正しい（3桁コードの写像確認）
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    assert df.filter(pl.col("age_class_code") == "270").row(0, named=True)["age_class"] == "80〜84歳"
    # DID は潰され、総数(100)は全域の 200 のまま（11 は混ざらない）
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    # 男女保存
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 96+104==200


def test_1980_age_unknown_is_real_not_injected():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        _row_1980(**base, sex="000", age="000", value=200),
        _row_1980(**base, sex="000", age="001", value=50),
        _row_1980(**base, sex="000", age="022", value=9),
    ]
    df = age5year_municipality.clean_1980(pl.DataFrame(rows))
    unknown = df.filter(pl.col("age_class_code") == "999").row(0, named=True)
    assert unknown["population"] == 9  # 生値。導出注入(200-50=150)ではない
    assert unknown["age_class"] == "年齢不詳"


# --- 1985（1980 と +1 コードずれ・平均年齢/中位数を含む）: tab 軸なし・cat02=男女・cat03=年齢(001総数/002-023) ---
def _row_1985(*, area, level, did, sex, age, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": sex,  # 男女
        "cat03_code": age,  # 年齢（001=総数・002=0-4…・023=不詳・024/025=平均/中位）
        "time_code": "1985000000",
        "value": str(value),
        **_area(area, level),
    }


def test_1985_code_offset_and_stats_rows_excluded():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        _row_1985(**base, sex="000", age="001", value=200),  # 総数 → 100
        _row_1985(**base, sex="000", age="002", value=50),  # 0-4 → 110（1980 と +1 ずれ）
        _row_1985(**base, sex="000", age="018", value=12),  # 80-84 → 270
        _row_1985(**base, sex="000", age="022", value=4),  # 100歳以上 → 310
        _row_1985(**base, sex="000", age="023", value=9),  # 不詳 → 999
        _row_1985(**base, sex="001", age="001", value=96),  # 男
        _row_1985(**base, sex="002", age="001", value=104),  # 女
        # 平均年齢(024)・年齢中位数(025)＝人口でない統計量は age_map 非収載で落ちる
        _row_1985(**base, sex="000", age="024", value=41),
        _row_1985(**base, sex="000", age="025", value=39),
        # DID(00701) は潰される
        _row_1985(area="00000", level="1", did="00701", sex="000", age="001", value=11),
    ]
    df = age5year_municipality.clean_1985(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 平均年齢/中位数は age_class_code に混入しない
    assert set(df["age_class_code"].to_list()) <= {"100", "110", "270", "310", "999"}
    assert df.filter(pl.col("age_class_code") == "110").row(0, named=True)["age_class"] == "0〜4歳"
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    # DID 潰し（総数=200 のまま）・男女保存
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]
    # 不詳は実コード（生値9・注入でない）
    assert df.filter(pl.col("age_class_code") == "999").row(0, named=True)["population"] == 9


# --- 1990（日本人人口・不詳コード無し）: tab 軸なし・cat02=男女・cat03=年齢(000総数/001-021・不詳無し) ---
def _row_1990(*, area, level, did, sex, age, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": sex,  # 男女
        "cat03_code": age,  # 年齢（000=総数・001=0-4…021=100歳以上・不詳コード無し）
        "time_code": "1990000000",
        "value": str(value),
        **_area(area, level),
    }


def test_1990_japanese_constant_and_no_unknown():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        _row_1990(**base, sex="000", age="000", value=200),  # 総数 → 100
        _row_1990(**base, sex="000", age="001", value=50),  # 0-4 → 110
        _row_1990(**base, sex="000", age="021", value=4),  # 100歳以上 → 310
        _row_1990(**base, sex="001", age="000", value=96),  # 男
        _row_1990(**base, sex="002", age="000", value=104),  # 女
        # DID(00701) は潰される
        _row_1990(area="00000", level="1", did="00701", sex="000", age="000", value=11),
    ]
    df = age5year_municipality.clean_1990(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 1990 は日本人人口のみ＝nationality=日本人(1) を定数注入
    assert set(df["nationality_code"].to_list()) == {"1"}
    assert df["nationality"][0] == "日本人"
    # 年齢不詳(999)は原表に無い＝出力に現れない
    assert "999" not in df["age_class_code"].to_list()
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    # DID 潰し・男女保存
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    by_sex = _by_sex(df, nat="1")
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 96+104==200


# --- 1995（日本人人口・★軸入替）: 男女=cat03・年齢=cat02(T01総数/200-219/500=100歳以上・不詳無し) ---
def _row_1995(*, area, level, did, sex, age, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": age,  # ★年齢
        "cat03_code": sex,  # ★男女
        "time_code": "1995000000",
        "value": str(value),
        **_area(area, level),
    }


def test_1995_swapped_axes_japanese_and_100plus_code():
    base = {"area": "00000", "level": "1", "did": "00700"}
    rows = [
        _row_1995(**base, sex="000", age="T01", value=200),  # 総数 → 100
        _row_1995(**base, sex="000", age="200", value=50),  # 0-4 → 110
        _row_1995(**base, sex="000", age="216", value=12),  # 80-84 → 270
        _row_1995(**base, sex="000", age="500", value=4),  # 100歳以上 → 310（★飛びコード 500）
        _row_1995(**base, sex="001", age="T01", value=96),  # 男（cat03）
        _row_1995(**base, sex="002", age="T01", value=104),  # 女
        # DID(00701) は潰される
        _row_1995(area="00000", level="1", did="00701", sex="000", age="T01", value=11),
    ]
    df = age5year_municipality.clean_1995(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    assert set(df["nationality_code"].to_list()) == {"1"}  # 日本人のみ
    # 軸入替: 男女は cat03 から解決
    by_sex = _by_sex(df, nat="1")
    assert by_sex["0"] == 200 and by_sex["1"] == 96 and by_sex["2"] == 104
    # 年齢は cat02 から解決。T01→総数・500→100歳以上・216→80〜84
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    assert df.filter(pl.col("age_class_code") == "270").row(0, named=True)["age_class"] == "80〜84歳"
    # 不詳は原表に無い
    assert "999" not in df["age_class_code"].to_list()
    # DID 潰し
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200


# --- 1990/1995 総数（各歳表 00401・0000031401/0000032219）: 全域/DID=cat01・年齢=cat02・男女=cat03・国籍軸なし ---
def _row_1990_1995_total(*, area, level, did, sex, age, year, value):
    return {
        "cat01_code": did,  # 全域/DID
        "cat02_code": age,  # 年齢（各歳＋5歳階級再掲・900不詳あり）
        "cat03_code": sex,  # 男女
        "time_code": f"{year}000000",
        "value": str(value),
        **_area(area, level),
    }


def test_1990_1995_total_picks_age5_recap_injects_total_nationality():
    base = {"area": "00000", "level": "1", "did": "00700", "year": 1990}
    rows = [
        _row_1990_1995_total(**base, sex="000", age="T01", value=200),  # 総数 → 100
        _row_1990_1995_total(**base, sex="000", age="200", value=50),  # 0-4 → 110
        _row_1990_1995_total(**base, sex="000", age="216", value=12),  # 80-84 → 270
        _row_1990_1995_total(**base, sex="000", age="500", value=4),  # 100歳以上 → 310（★飛びコード 500）
        _row_1990_1995_total(**base, sex="000", age="900", value=9),  # 不詳 → 999（各歳表 00401 は不詳あり）
        _row_1990_1995_total(**base, sex="001", age="T01", value=96),  # 男（cat03）
        _row_1990_1995_total(**base, sex="002", age="T01", value=104),  # 女
        # 各歳（000=0歳）は age_map 非収載で落ちる
        _row_1990_1995_total(**base, sex="000", age="000", value=11),
        # DID(00701) は潰される
        _row_1990_1995_total(area="00000", level="1", did="00701", sex="000", age="T01", year=1990, value=7),
    ]
    df = age5year_municipality.clean_1990_1995_total(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 国籍軸なし＝総数(0) を定数注入（日本人版 clean_1990/1995 とは別ソース）
    assert set(df["nationality_code"].to_list()) == {"0"}
    assert df["nationality"][0] == "総数"
    # 各歳は落ち、5歳階級の再掲と不詳(900→999)だけ残る（日本人版と違い不詳コードを持つ）
    assert set(df["age_class_code"].to_list()) == {"100", "110", "270", "310", "999"}
    assert df.filter(pl.col("age_class_code") == "999").row(0, named=True)["population"] == 9
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    # 軸割当: 男女は cat03・年齢は cat02（日本人版 1990 の 男女=cat02/年齢=cat03 とは違う）
    assert df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0] == 200
    by_sex = _by_sex(df)  # 既定 nat="0"
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 96+104==200
