"""労働力状態（3区分）×男女別人口 cleaner（labor_force）の単体テスト。

tab=320(人口)への絞り込み（率1240の除外）・cat01→労働力状態/cat02→男女の写像・
不詳補完値(time 000010)の除外・労働力状態不詳の導出注入（労働力人口+非労働力人口+不詳==総数）・
就業者/完全失業者が労働力人口の再掲である点（不詳の減算に含めない）を手組み tidy で検証する。
全国表・都道府県表は同一 cleaner なので area 軸ありの tidy 1 本で確認する。
"""

import polars as pl

from data_forge.sources.estat import labor_force

# 男女コード(cat02): 100=総数/110=男/120=女。労働力状態(cat01)は e-Stat のまま。
_SEX = {"総数": "100", "男": "110", "女": "120"}


def _row(*, sex, status, value, time="2020000000", area="01000"):
    return {
        "tab_code": "320",
        "cat01_code": status,
        "cat02_code": _SEX[sex],
        "time_code": time,
        "value": str(value),
        "area_code": area,
        "area_name": f"県{area}",
        "area_level": "2",
    }


_COLUMNS = [
    "area_code",
    "area_name",
    "area_level",
    "sex_code",
    "sex",
    "labor_status_code",
    "labor_status",
    "year",
    "population",
    "is_current",
]


def _tidy() -> pl.DataFrame:
    # 総数(男女): 総数100=200 / 労働力人口110=120 (=就業者120:100 + 完全失業者130:20) / 非労働力人口140=70
    #   → 不詳 = 200 − 120 − 70 = 10
    rows = [
        _row(sex="総数", status="100", value=200),
        _row(sex="総数", status="110", value=120),
        _row(sex="総数", status="120", value=100),  # 就業者（110の再掲）
        _row(sex="総数", status="130", value=20),  # 完全失業者（110の再掲）
        _row(sex="総数", status="140", value=70),
        # 男女保存の確認用（総数のみ）
        _row(sex="男", status="100", value=96),
        _row(sex="女", status="100", value=104),
        # 捨てられるべき行:
        _row(sex="総数", status="110", value=999, time="2020000010"),  # 不詳補完値 → 除外
        # 率(tab=1240)混入 → 除外
        {
            "tab_code": "1240",
            "cat01_code": "100",
            "cat02_code": "100",
            "time_code": "2020000000",
            "value": "62.1",
            "area_code": "01000",
            "area_name": "県01000",
            "area_level": "2",
        },
    ]
    return pl.DataFrame(rows)


def test_schema_and_mapping():
    df = labor_force.clean_labor_force(_tidy())
    assert df.columns == _COLUMNS
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("labor_status_code") == "100")).row(0, named=True)
    assert total["area_code"] == "01000"
    assert total["area_level"] == 2
    assert total["labor_status"] == "総数"
    assert total["population"] == 200
    assert total["year"] == 2020
    assert total["is_current"] is True


def test_drops_rate_tab_and_imputed():
    df = labor_force.clean_labor_force(_tidy())
    # tab=1240(率)は列に残らない（population はすべて count 由来）
    force = df.filter((pl.col("sex_code") == "0") & (pl.col("labor_status_code") == "110")).row(0, named=True)
    assert force["population"] == 120  # 不詳補完値(time000010)を混ぜていない


def test_injects_labor_unknown_and_conservation():
    df = labor_force.clean_labor_force(_tidy())
    unknown = df.filter((pl.col("sex_code") == "0") & (pl.col("labor_status_code") == "999")).row(0, named=True)
    assert unknown["labor_status"] == "労働力状態不詳"
    assert unknown["population"] == 10  # 総数200 − 労働力人口120 − 非労働力人口70（就業者/失業者は再掲で引かない）
    # 3区分保存: 労働力人口(110) + 非労働力人口(140) + 不詳(999) == 総数(100)
    parts = df.filter((pl.col("sex_code") == "0") & pl.col("labor_status_code").is_in(["110", "140", "999"]))[
        "population"
    ].sum()
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("labor_status_code") == "100"))["population"][0]
    assert parts == total


def test_labor_force_subtotal_conservation():
    df = labor_force.clean_labor_force(_tidy())
    # 労働力人口内訳保存: 就業者(120) + 完全失業者(130) == 労働力人口(110)
    sub = df.filter((pl.col("sex_code") == "0") & pl.col("labor_status_code").is_in(["120", "130"]))["population"].sum()
    force = df.filter((pl.col("sex_code") == "0") & (pl.col("labor_status_code") == "110"))["population"][0]
    assert sub == force


def test_sex_conservation():
    df = labor_force.clean_labor_force(_tidy())
    by_sex = {
        r["sex_code"]: r["population"] for r in df.filter(pl.col("labor_status_code") == "100").iter_rows(named=True)
    }
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 男96 + 女104 == 総数200
