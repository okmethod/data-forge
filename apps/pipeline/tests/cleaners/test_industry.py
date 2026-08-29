"""産業大分類×男女別就業者数 cleaner（industry）の単体テスト。

tab=334(就業者数)への絞り込み（構成比の除外）・cat01→産業大分類/cat02→男女の写像・
（再掲）第1/2/3次産業の除外・不詳補完値(time 000010)の除外・全国合成(national=True で
00000/全国/level1)を手組み tidy で検証する。分類不能(330)が実カテゴリのため不詳注入は無く、
「総数(100) == Σ大分類(120〜330)」が保存則として閉じることを確認する。
"""

import polars as pl

from data_forge.sources.estat import industry

# 男女コード(cat02): 100=総数/110=男/120=女。産業大分類(cat01)は e-Stat のまま。
_SEX = {"総数": "100", "男": "110", "女": "120"}


def _row(*, sex, ind, value, time="2020000000", area="01000"):
    return {
        "tab_code": "334",
        "cat01_code": ind,
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
    "industry_code",
    "industry",
    "year",
    "workers",
    "is_current",
]


def _tidy() -> pl.DataFrame:
    # 総数(男女): 総数100=100 = 農業120:40 + 製造170:35 + 分類不能330:25
    rows = [
        _row(sex="総数", ind="100", value=100),
        _row(sex="総数", ind="120", value=40),
        _row(sex="総数", ind="170", value=35),
        _row(sex="総数", ind="330", value=25),  # 分類不能（実カテゴリ・保存則に含む）
        # 男女保存の確認用（総数のみ）
        _row(sex="男", ind="100", value=60),
        _row(sex="女", ind="100", value=40),
        # 捨てられるべき行:
        _row(sex="総数", ind="110", value=40),  # （再掲）第1次産業 → 除外
        _row(sex="総数", ind="120", value=999, time="2020000010"),  # 不詳補完値 → 除外
        {  # 構成比tab混入 → 除外
            "tab_code": "2020_44",
            "cat01_code": "100",
            "cat02_code": "100",
            "time_code": "2020000000",
            "value": "100.0",
            "area_code": "01000",
            "area_name": "県01000",
            "area_level": "2",
        },
    ]
    return pl.DataFrame(rows)


def test_schema_and_mapping():
    df = industry.clean_prefecture(_tidy())
    assert df.columns == _COLUMNS
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("industry_code") == "100")).row(0, named=True)
    assert total["area_code"] == "01000"
    assert total["area_level"] == 2
    assert total["industry"] == "総数"
    assert total["workers"] == 100
    assert total["year"] == 2020
    assert total["is_current"] is True


def test_drops_recap_rate_and_imputed():
    df = industry.clean_prefecture(_tidy())
    # （再掲）第1次産業(110) は捨てる
    assert df.filter(pl.col("industry_code") == "110").height == 0
    # 構成比tab は列に残らない・不詳補完値(time000010)を混ぜていない
    nogyo = df.filter((pl.col("sex_code") == "0") & (pl.col("industry_code") == "120")).row(0, named=True)
    assert nogyo["workers"] == 40


def test_no_unknown_injection_and_conservation():
    df = industry.clean_prefecture(_tidy())
    # 分類不能が実カテゴリなので導出注入(999)は無い
    assert df.filter(pl.col("industry_code") == "999").height == 0
    # 保存則: 総数(100) == Σ大分類(120〜330、分類不能含む)
    parts = df.filter((pl.col("sex_code") == "0") & (pl.col("industry_code") != "100"))["workers"].sum()
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("industry_code") == "100"))["workers"][0]
    assert parts == total  # 40 + 35 + 25 == 100


def test_sex_conservation():
    df = industry.clean_prefecture(_tidy())
    by_sex = {r["sex_code"]: r["workers"] for r in df.filter(pl.col("industry_code") == "100").iter_rows(named=True)}
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 男60 + 女40 == 総数100


def test_national_synthesizes_area():
    # national=True は area 軸なし tidy に 00000/全国/level1 を合成する
    tidy = pl.DataFrame(
        [
            {"tab_code": "334", "cat01_code": "100", "cat02_code": "100", "time_code": "1995000000", "value": "500"},
        ]
    )
    df = industry.clean_national(tidy)
    row = df.row(0, named=True)
    assert row["area_code"] == "00000"
    assert row["area_name"] == "全国"
    assert row["area_level"] == 1
    assert row["year"] == 1995
    assert row["workers"] == 500
