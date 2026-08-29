"""職業大分類×男女別就業者数 cleaner（occupation）の単体テスト。

tab=334(就業者数)への絞り込み（構成比の除外）・cat01→職業大分類/cat02→男女の写像・
不詳補完値(time 000010)の除外・全国合成(national=True で 00000/全国/level1)を手組み tidy で
検証する。分類不能(220)が実カテゴリのため不詳注入は無く、「総数(100) == Σ大分類(110〜220)」が
保存則として閉じることを確認する（industry と同型・再掲は無い）。
"""

import polars as pl

from data_forge.sources.estat import occupation

# 男女コード(cat02): 100=総数/110=男/120=女。職業大分類(cat01)は e-Stat のまま。
_SEX = {"総数": "100", "男": "110", "女": "120"}


def _row(*, sex, occ, value, time="2020000000", area="01000"):
    return {
        "tab_code": "334",
        "cat01_code": occ,
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
    "occupation_code",
    "occupation",
    "year",
    "workers",
    "is_current",
]


def _tidy() -> pl.DataFrame:
    # 総数(男女): 総数100=100 = 管理110:40 + 事務130:35 + 分類不能220:25
    rows = [
        _row(sex="総数", occ="100", value=100),
        _row(sex="総数", occ="110", value=40),
        _row(sex="総数", occ="130", value=35),
        _row(sex="総数", occ="220", value=25),  # 分類不能（実カテゴリ・保存則に含む）
        # 男女保存の確認用（総数のみ）
        _row(sex="男", occ="100", value=60),
        _row(sex="女", occ="100", value=40),
        # 捨てられるべき行:
        _row(sex="総数", occ="110", value=999, time="2020000010"),  # 不詳補完値 → 除外
        {  # 構成比tab混入 → 除外
            "tab_code": "2020_45",
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
    df = occupation.clean_major12_prefecture(_tidy())
    assert df.columns == _COLUMNS
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") == "100")).row(0, named=True)
    assert total["area_code"] == "01000"
    assert total["area_level"] == 2
    assert total["occupation"] == "総数"
    assert total["workers"] == 100
    assert total["year"] == 2020
    assert total["is_current"] is True


def test_drops_rate_and_imputed():
    df = occupation.clean_major12_prefecture(_tidy())
    # 構成比tab は列に残らない・不詳補完値(time000010)を混ぜていない
    kanri = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") == "110")).row(0, named=True)
    assert kanri["workers"] == 40


def test_no_unknown_injection_and_conservation():
    df = occupation.clean_major12_prefecture(_tidy())
    # 分類不能が実カテゴリなので導出注入(999)は無い
    assert df.filter(pl.col("occupation_code") == "999").height == 0
    # 保存則: 総数(100) == Σ大分類(110〜220、分類不能含む)
    parts = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") != "100"))["workers"].sum()
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") == "100"))["workers"][0]
    assert parts == total  # 40 + 35 + 25 == 100


def test_sex_conservation():
    df = occupation.clean_major12_prefecture(_tidy())
    by_sex = {r["sex_code"]: r["workers"] for r in df.filter(pl.col("occupation_code") == "100").iter_rows(named=True)}
    assert by_sex["1"] + by_sex["2"] == by_sex["0"]  # 男60 + 女40 == 総数100


def test_national_synthesizes_area():
    # national=True は area 軸なし tidy に 00000/全国/level1 を合成する
    tidy = pl.DataFrame(
        [
            {"tab_code": "334", "cat01_code": "100", "cat02_code": "100", "time_code": "1995000000", "value": "500"},
        ]
    )
    df = occupation.clean_major12_national(tidy)
    row = df.row(0, named=True)
    assert row["area_code"] == "00000"
    assert row["area_name"] == "全国"
    assert row["area_level"] == 1
    assert row["year"] == 1995
    assert row["workers"] == 500


def _tidy_major10() -> pl.DataFrame:
    # major10（呼称定義は docs occupation.md SSoT）。総数100=100 = 専門技術110:40 + 事務130:35 + 分類不能200:25。
    # 再掲(210〜240)は class map 非収載で除外される（Σ大分類に二重計上しないこと）。
    rows = [
        _row(sex="総数", occ="100", value=100, time="1980000000"),
        _row(sex="総数", occ="110", value=40, time="1980000000"),
        _row(sex="総数", occ="130", value=35, time="1980000000"),
        _row(sex="総数", occ="200", value=25, time="1980000000"),  # J分類不能（実カテゴリ）
        _row(sex="総数", occ="210", value=999, time="1980000000"),  # （再掲）→ 除外
        _row(sex="総数", occ="240", value=999, time="1980000000"),  # （再掲）→ 除外
    ]
    return pl.DataFrame(rows)


def test_major10_drops_recategorized_and_conserves():
    df = occupation.clean_major10_prefecture(_tidy_major10())
    # 再掲(210/240)は残らない
    assert df.filter(pl.col("occupation_code").is_in(["210", "240"])).height == 0
    # 旧分類名が引かれる（同符号でも major12 と別体系: 110=専門的・技術的）
    senmon = df.filter(pl.col("occupation_code") == "110").row(0, named=True)
    assert senmon["occupation"] == "Ａ専門的・技術的職業従事者"
    # 保存則: 総数(100) == Σ大分類(110〜200・分類不能含む、再掲は除く)
    parts = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") != "100"))["workers"].sum()
    total = df.filter((pl.col("sex_code") == "0") & (pl.col("occupation_code") == "100"))["workers"][0]
    assert parts == total  # 40 + 35 + 25 == 100（再掲は入らない）
