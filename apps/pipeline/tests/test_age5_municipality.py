"""年齢5歳階級×男女別人口 市区町村版 cleaner（age5_municipality）の単体テスト。

各回（2010/2015/2020）で **軸割当（どの catNN が男女／年齢か）もコード体系も違う**点、
余分軸（国籍・出生の月・全域/DID）を総数コードで潰す点、100歳以上まで保持する点、
年齢不詳は実コードをそのまま採る（導出注入しない）点を手組み tidy で検証する。
特に 2015 は男女=cat03・年齢=cat02 と入れ替わる（getMetaInfo と食い違う実データ形）ため重点的に見る。
"""

import polars as pl

from data_forge.sources.estat import age5_municipality as m

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


def _area(area: str, level: str) -> dict:
    return {"area_code": area, "area_name": f"地域{area}", "area_level": level}


def _by_sex(df: pl.DataFrame, age: str = "100") -> dict[str, int]:
    """指定年齢階級の {sex_code: population}（男女保存の確認用）。"""
    rows = df.filter(pl.col("age_class_code") == age).iter_rows(named=True)
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


def test_2020_schema_axes_and_kokuseki_collapse():
    rows = [
        # 全国 総数×総数（国籍総数=0 を採り、日本人=1 は捨てる）
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="00", value=100),
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="01", value=30),  # 0-4 → 110
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="21", value=5),  # 100歳以上 → 310
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="22", value=8),  # 不詳 → 999
        _row_2020(area="00000", level="1", kokuseki="0", sex="1", age="00", value=48),  # 男
        _row_2020(area="00000", level="1", kokuseki="0", sex="2", age="00", value=52),  # 女
        _row_2020(area="00000", level="1", kokuseki="0", sex="0", age="R1", value=999),  # 再掲 → 除外
        # 国籍=日本人(1) の行は捨てられる
        _row_2020(area="00000", level="1", kokuseki="1", sex="0", age="00", value=90),
    ]
    df = m.clean_2020(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    codes = set(df.filter(pl.col("sex_code") == "0")["age_class_code"].to_list())
    assert "R1" not in df["age_class_code"].to_list()  # 再掲は落ちる
    assert {"100", "110", "310", "999"} <= codes
    # 100歳以上を保持し、名称が正しい
    c100 = df.filter(pl.col("age_class_code") == "310").row(0, named=True)
    assert c100["age_class"] == "100歳以上" and c100["population"] == 5
    # 国籍=日本人は潰さず捨てる → 総数(100)は国籍総数の 100 のまま（90 は混ざらない）
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("age_class_code") == "100"))["population"][0]
    assert total == 100
    # 男女保存
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
    df = m.clean_2020(pl.DataFrame(rows))
    unknown = df.filter(pl.col("age_class_code") == "999").row(0, named=True)
    assert unknown["population"] == 8  # 生値。導出注入(65)ではない
    assert unknown["age_class"] == "年齢不詳"


def test_2020_is_current_flags_obsolete_municipality():
    rows = [
        _row_2020(area="12231", level="4", kokuseki="0", sex="0", age="00", value=100),  # 現存市
        _row_2020(area="0120B", level="7", kokuseki="0", sex="0", age="00", value=50),  # 旧市区町村
    ]
    df = m.clean_2020(pl.DataFrame(rows))
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
        # 潰されるべき: DID(00711)・日本人(0150)・出生月1月-3月(0010) はいずれも捨てられる
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
    df = m.clean_2015(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    # 男女が cat03 から正しく解決される（入替に耐える）
    by_sex = _by_sex(df)
    assert by_sex["0"] == 200 and by_sex["1"] == 97 and by_sex["2"] == 103
    # 年齢が cat02 から解決され 100歳以上を保持
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["population"] == 7
    # 余分軸は総数だけ残る → 総数(100)は 200 のまま（DID/日本人/出生月の重複を混ぜない）
    assert by_sex["0"] == 200
    # 不詳は実コード
    assert df.filter(pl.col("age_class_code") == "999").row(0, named=True)["population"] == 9


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


def test_2010_axes_and_100plus_and_unknown():
    base = {"area": "00000", "level": "1", "did": "00710", "kokuseki": "000", "tsuki": "000"}
    rows = [
        _row_2010(**base, sex="000", age="000", value=150),  # 総数
        _row_2010(**base, sex="000", age="200", value=40),  # 0-4 → 110
        _row_2010(**base, sex="000", age="600", value=3),  # 100歳以上 → 310
        _row_2010(**base, sex="000", age="999", value=6),  # 不詳
        _row_2010(**base, sex="001", age="000", value=73),  # 男
        _row_2010(**base, sex="002", age="000", value=77),  # 女
    ]
    df = m.clean_2010(pl.DataFrame(rows))
    assert df.columns == _COLUMNS
    assert df.filter(pl.col("age_class_code") == "310").row(0, named=True)["age_class"] == "100歳以上"
    by_sex = _by_sex(df)
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 73+77==150
    assert df.filter(pl.col("age_class_code") == "999").row(0, named=True)["population"] == 6  # 実コード
