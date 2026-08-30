"""人口パイプラインのクレンジング単体テスト。

汎用 transform（コード名称解決）は実サンプル fixture で、
population 固有のクレンジング（level→is_current・int化・欠損処理）は
手組みの tidy DF で検証する。年別4変種の cleaner は共通8列への写像をここで担保し、
合併集約・人口保存・速報 splice は共有インフラ側（area / provenance）へ委譲する。
年齢軸を保持する population_by_age（10列）の cleaner も本ファイルで併せて検証する。

検証項目（関数名 ⇄ 何を確かめるか）:
    test_extract_meta
        出典メタ抽出。statsDataId・提供者・調査名・引用文。
    test_to_tidy_resolves_names
        tidy 化（軸解決）。各軸の code/name/level 解決。
    test_clean_from_fixture
        スキーマ・写像。8列・全国総数（2020=126,146,099）。
    test_clean_2015_maps_to_shared_schema
        2015 平成型 → 共通8列（人口性比・人口集中地区を拾わない）。
    test_clean_handles_levels_and_missing
        階層・欠損。level7 の is_current=false・欠損記号 "-" の null 化。
    test_clean_population_prefecture_companion
        都道府県マクロ（回次跨帳票の射影）。世紀マクロ cleaner の写像。
    test_clean_population_by_age_schema_and_national_restore
        （by_age）年齢軸を保持した10列への写像・全国行を都道府県合計から復元。
    test_clean_population_by_age_conservation
        （by_age）年齢保存。年少+生産+老年+不詳 == 総数（不詳=総数−3区分で注入）。男女保存も確認。
    test_clean_by_age_prefecture_companion
        （by_age）都道府県マクロ（回次跨帳票の射影）の写像。

共有インフラ側の委譲先:
    人口保存・合併集約 … tests/area/test_area.py（アトム合計 == 全国total・全9年 diff=0、
        1980 のみ 37 人差＝特別区部の区未定分を KNOWN_DIFFS で受容）。by_age は
        test_aggregate_by_age_folds_and_conserves_age /
        test_national_conservation_by_age_uses_total_slice /
        test_orphans_by_age_dedups_to_total で年齢×男女を保ったまま総数スライスで全国値保存。
    速報 splice … provenance.py（data_status 来歴列・area scope の intersection scoping）。
"""

import json
from pathlib import Path

import polars as pl

from data_forge.sources.estat import population, transform

FIXTURE = Path(__file__).parent.parent / "fixtures" / "estat_population_sample.json"


def _load_raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_extract_meta():
    meta = transform.extract_meta(_load_raw())
    assert meta.source == "estat"
    assert meta.dataset_id == "0003445078"
    assert meta.provider == "総務省"
    assert meta.attributes["stat_name"] == "国勢調査"
    assert meta.attributes["survey_date"] == "202010"
    assert meta.citation.startswith("出典：政府統計の総合窓口(e-Stat)")


def test_to_tidy_resolves_names():
    tidy = transform.to_tidy(_load_raw())
    # 4軸 × (code,name,level) + unit + value 列が揃う
    for axis in ("tab", "cat01", "area", "time"):
        assert f"{axis}_code" in tidy.columns
        assert f"{axis}_name" in tidy.columns
        assert f"{axis}_level" in tidy.columns

    # 全国(00000) のコードが名称解決されている
    zenkoku = tidy.filter(pl.col("area_code") == "00000")
    assert zenkoku.height == 1
    assert zenkoku["area_name"][0] == "全国"
    assert zenkoku["value"][0] == "126146099"


def test_clean_from_fixture():
    tidy = transform.to_tidy(_load_raw())
    df = population.clean_2020(tidy)

    assert df.columns == [
        "area_code",
        "area_name",
        "area_level",
        "sex_code",
        "sex",
        "year",
        "population",
        "is_current",
    ]
    row = df.filter(pl.col("area_code") == "00000").row(0, named=True)
    assert row["population"] == 126_146_099  # 文字列→Int64
    assert row["sex"] == "総数"
    assert row["year"] == 2020
    assert row["is_current"] is True  # level1（全国）は現存扱い


def test_clean_handles_levels_and_missing():
    """level7（旧市区町村）フラグと欠損記号の null 化を手組み tidy で検証。"""
    tidy = pl.DataFrame(
        {
            "tab_code": ["2020_01", "2020_01"],
            "tab_name": ["人口", "人口"],
            "tab_level": ["", ""],
            "cat01_code": ["0", "0"],
            "cat01_name": ["総数", "総数"],
            "cat01_level": ["1", "1"],
            "area_code": ["01303", "0120B"],
            "area_name": ["当別町", "（旧：函館市）"],
            "area_level": ["6", "7"],
            "time_code": ["2020000000", "2020000000"],
            "time_name": ["2020年", "2020年"],
            "time_level": ["1", "1"],
            "unit": ["人", "人"],
            "value": ["17456", "-"],  # 2件目は欠損記号
        }
    )
    df = population.clean_2020(tidy).sort("area_code")

    current = df.filter(pl.col("area_code") == "01303").row(0, named=True)
    assert current["is_current"] is True
    assert current["population"] == 17456

    obsolete = df.filter(pl.col("area_code") == "0120B").row(0, named=True)
    assert obsolete["is_current"] is False  # level7 は旧自治体
    assert obsolete["population"] is None  # "-" は null


def test_clean_2015_maps_to_shared_schema():
    """2015年表（cat01=全域/DID・cat02=表章事項＋男女統合）を共通8列へ写像する。"""
    tidy = pl.DataFrame(
        {
            "cat01_code": ["00710", "00710", "00710", "00710", "00711"],
            "cat01_name": ["全域", "全域", "全域", "全域", "人口集中地区"],
            "cat02_code": ["010", "020", "030", "040", "010"],
            "cat02_name": [
                "（人口）総数",
                "（人口）男",
                "（人口）女",
                "（人口）人口性比",
                "（人口）総数",
            ],
            "area_code": ["00000", "00000", "00000", "00000", "00000"],
            "area_name": ["全国", "全国", "全国", "全国", "全国"],
            "area_level": ["1", "1", "1", "1", "1"],
            "time_code": ["2015000000"] * 5,
            "value": ["127094745", "61841738", "65253007", "94.8", "116137232"],
        }
    )
    df = population.clean_2015(tidy)

    # 人口性比(040)・人口集中地区(00711)は除外され、全域の総数/男/女の3行だけ
    assert df.columns == [
        "area_code",
        "area_name",
        "area_level",
        "sex_code",
        "sex",
        "year",
        "population",
        "is_current",
    ]
    assert df.height == 3
    assert set(zip(df["sex_code"], df["sex"])) == {("0", "総数"), ("1", "男"), ("2", "女")}
    total = df.filter(pl.col("sex_code") == "0").row(0, named=True)
    assert total["population"] == 127_094_745  # DID・人口性比を拾っていない
    assert total["year"] == 2015


# --- population_by_age（年齢3区分×男女別人口）------------------------------------

# 時系列ファミリー表の手組み tidy。県 01/02（level2, 全国行なし）× 男女(cat02) × 年齢(cat01)。
# 各 (県,性) で 総数 ≠ 年少+生産+老年 とし、不詳が非ゼロで導出されることを確かめる。
_AGE_ROWS = {
    # area: {sex: {age: value}}  age 100=総数/110=年少/120=生産/130=老年
    "01000": {
        "100": {"100": 100, "110": 10, "120": 60, "130": 25},  # 不詳=5
        "110": {"100": 48, "110": 5, "120": 30, "130": 12},  # 不詳=1
        "120": {"100": 52, "110": 5, "120": 30, "130": 13},  # 不詳=4
    },
    "02000": {
        "100": {"100": 200, "110": 20, "120": 120, "130": 50},  # 不詳=10
        "110": {"100": 98, "110": 10, "120": 60, "130": 24},  # 不詳=4
        "120": {"100": 102, "110": 10, "120": 60, "130": 26},  # 不詳=6
    },
}


def _age_tidy() -> pl.DataFrame:
    rows: list[dict] = []
    for area, by_sex in _AGE_ROWS.items():
        for sex, by_age in by_sex.items():
            for age, val in by_age.items():
                rows.append(
                    {
                        "tab_code": "020",
                        "cat01_code": age,
                        "cat02_code": sex,
                        "area_code": area,
                        "area_name": f"県{area}",
                        "area_level": "2",
                        "time_code": "2020000000",
                        "value": str(val),
                    }
                )
    # 割合(tab=105)の混入行 → 捨てられることの確認用
    rows.append(
        {
            "tab_code": "105",
            "cat01_code": "130",
            "cat02_code": "100",
            "area_code": "01000",
            "area_name": "県01000",
            "area_level": "2",
            "time_code": "2020000000",
            "value": "25.0",
        }
    )
    return pl.DataFrame(rows)


def test_clean_population_by_age_schema_and_national_restore():
    df = population.clean_population_by_age(_age_tidy())
    assert df.columns == [
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
    # 全国行(00000)が県合計から復元されている（総数・総数 = 100+200 = 300）
    nat = df.filter(
        (pl.col("area_code") == "00000") & (pl.col("sex_code") == "0") & (pl.col("age_class_code") == "0")
    ).row(0, named=True)
    assert nat["population"] == 300
    assert nat["area_name"] == "全国"
    # 割合(105)は採られない（総数(age=0,sex=0)は人口 100 のまま）
    p = df.filter(
        (pl.col("area_code") == "01000") & (pl.col("sex_code") == "0") & (pl.col("age_class_code") == "0")
    ).row(0, named=True)
    assert p["population"] == 100
    assert p["year"] == 2020


def test_clean_population_by_age_conservation():
    df = population.clean_population_by_age(_age_tidy())

    # 年齢保存: 年少+生産+老年+不詳 == 総数（全 area×sex で恒等成立）
    parts = (
        df.filter(pl.col("age_class_code").is_in(["1", "2", "3", "9"]))
        .group_by("area_code", "sex_code")
        .agg(pl.col("population").sum().alias("sum_parts"))
    )
    totals = df.filter(pl.col("age_class_code") == "0").select(
        "area_code", "sex_code", pl.col("population").alias("total")
    )
    merged = totals.join(parts, on=["area_code", "sex_code"])
    assert (merged["sum_parts"] == merged["total"]).all()

    # 不詳(9)が正の導出値として注入されている（県01000・総数 = 100-(10+60+25) = 5）
    unknown = df.filter(
        (pl.col("area_code") == "01000") & (pl.col("sex_code") == "0") & (pl.col("age_class_code") == "9")
    ).row(0, named=True)
    assert unknown["population"] == 5
    assert unknown["age_class"] == "年齢不詳"

    # 男女保存: 男+女 == 総数（各 area×age_class）
    sexes = (
        df.filter(pl.col("sex_code").is_in(["1", "2"]))
        .group_by("area_code", "age_class_code")
        .agg(pl.col("population").sum().alias("mf"))
    )
    stot = df.filter(pl.col("sex_code") == "0").select(
        "area_code", "age_class_code", pl.col("population").alias("total")
    )
    smerged = stot.join(sexes, on=["area_code", "age_class_code"])
    assert (smerged["mf"] == smerged["total"]).all()


def _by_age_longterm_tidy() -> pl.DataFrame:
    """系統B長期表 0003410383 を模した tidy（全国+2県・tab1060実数・cat01=100/105/120/130・男女軸なし）。"""
    area_rows = {
        "00000": {"100": 300, "105": 40, "120": 200, "130": 55},  # 全国（落とされる）
        "01000": {"100": 100, "105": 10, "120": 60, "130": 25},  # 不詳=5
        "02000": {"100": 200, "105": 20, "120": 130, "130": 45},  # 不詳=5
    }
    rows: list[dict] = []
    for area, by_age in area_rows.items():
        for age, val in by_age.items():
            rows.append(
                {
                    "tab_code": "1060",
                    "cat01_code": age,
                    "area_code": area,
                    "area_name": "全国" if area == "00000" else f"県{area}",
                    "area_level": "1" if area == "00000" else "2",
                    "time_code": "2020000000",
                    "value": str(val),
                }
            )
    # 割合(tab=105)の混入 → 捨てられる
    rows.append(
        {
            "tab_code": "105",
            "cat01_code": "130",
            "area_code": "01000",
            "area_name": "県01000",
            "area_level": "2",
            "time_code": "2020000000",
            "value": "25.0",
        }
    )
    # 不詳補完版(time 末尾000010) → 除外される（採ると二重計上）
    rows.append(
        {
            "tab_code": "1060",
            "cat01_code": "100",
            "area_code": "01000",
            "area_name": "県01000",
            "area_level": "2",
            "time_code": "2020000010",
            "value": "999999",
        }
    )
    return pl.DataFrame(rows)


def test_clean_by_age_prefecture_companion():
    df = population.clean_by_age_prefecture(_by_age_longterm_tidy())
    # 旗艦 by_age と同一10列スキーマ
    assert df.columns == [
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
    # 全国(00000)は落とし、47県相当のみ（ここでは2県）
    assert df.filter(pl.col("area_code") == "00000").height == 0
    assert sorted(df["area_code"].unique().to_list()) == ["01000", "02000"]
    # sex は総数固定
    assert df["sex_code"].unique().to_list() == ["0"]
    # cat01=105(0-14) が旗艦ターゲット '1' へ写像される
    child = df.filter((pl.col("area_code") == "01000") & (pl.col("age_class_code") == "1")).row(0, named=True)
    assert child["population"] == 10 and child["age_class"] == "年少人口(0-14)"
    # 不詳補完版(000010)は無視（総数は 100 のまま・999999 を採らない）
    total = df.filter((pl.col("area_code") == "01000") & (pl.col("age_class_code") == "0")).row(0, named=True)
    assert total["population"] == 100
    # 年齢不詳(9)= 総数−(年少+生産+老年)= 100-(10+60+25)=5 が注入される
    unknown = df.filter((pl.col("area_code") == "01000") & (pl.col("age_class_code") == "9")).row(0, named=True)
    assert unknown["population"] == 5 and unknown["age_class"] == "年齢不詳"
    # 年齢保存: 年少+生産+老年+不詳 == 総数
    parts = (
        df.filter(pl.col("age_class_code").is_in(["1", "2", "3", "9"]))
        .group_by("area_code")
        .agg(pl.col("population").sum().alias("s"))
    )
    tot = df.filter(pl.col("age_class_code") == "0").select("area_code", pl.col("population").alias("t"))
    m = tot.join(parts, on="area_code")
    assert (m["s"] == m["t"]).all()


def _pop_longterm_tidy() -> pl.DataFrame:
    """系統B長期表 0003410379 を模した tidy（全国+DID+2県・tab020人口/1120性比・cat01=男女100/110/120）。"""
    rows: list[dict] = []
    areas = {
        "00000": "全国",
        "00100": "人口集中地区",
        "00200": "人口集中地区以外の地区",
        "13000": "東京都",
        "27000": "大阪府",
    }
    for area, name in areas.items():
        for sex, val in {"100": 1000, "110": 490, "120": 510}.items():
            rows.append(
                {
                    "tab_code": "020",
                    "cat01_code": sex,
                    "area_code": area,
                    "area_name": name,
                    "area_level": "1" if area == "00000" else "2",
                    "time_code": "2020000000",
                    "value": str(val),
                }
            )
    # 性比(tab=1120)の混入 → 捨てられる
    rows.append(
        {
            "tab_code": "1120",
            "cat01_code": "100",
            "area_code": "13000",
            "area_name": "東京都",
            "area_level": "2",
            "time_code": "2020000000",
            "value": "96.1",
        }
    )
    return pl.DataFrame(rows)


def test_clean_population_prefecture_companion():
    df = population.clean_population_prefecture(_pop_longterm_tidy())
    # 旗艦 population と同一8列スキーマ
    assert df.columns == ["area_code", "area_name", "area_level", "sex_code", "sex", "year", "population", "is_current"]
    # 全国(00000)・DID(00100/00200)を落とし47県相当のみ（ここでは2県）
    assert sorted(df["area_code"].unique().to_list()) == ["13000", "27000"]
    # 性比(1120)は採られない（総数は人口1000のまま）・男女写像
    tokyo = df.filter((pl.col("area_code") == "13000") & (pl.col("sex_code") == "0")).row(0, named=True)
    assert tokyo["population"] == 1000 and tokyo["sex"] == "総数" and tokyo["year"] == 2020
    assert df["sex_code"].unique().sort().to_list() == ["0", "1", "2"]
