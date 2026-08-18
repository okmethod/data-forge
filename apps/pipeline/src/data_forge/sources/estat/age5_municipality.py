"""国勢調査 年齢（5歳階級）×男女別人口 市区町村版（population_by_age5 の旗艦系列）のクレンジング。

各回の基本集計（系統A）の市区町村5歳階級表。同じ table_name "population_by_age5" に同居する
全国／都道府県のみの世紀 companion（系統B・単一ID・1920-2020／key は _national/_prefecture/
_prefecture_timeseries）と対をなし、市区町村（旧市区町村 level7 を含む年もある）まで下りる代わりに、
年ごとに別 statsDataId・別軸交差で不揃い（census_source_tables §3-3）。

M1 対象＝2010/2015/2020。各年の生表は年齢5歳階級のほかに国籍・出生の月・全域/人口集中地区(DID)
の軸を持ち、**どの catNN が男女／年齢か（軸割当）もコード体系も年ごとに違う**（特に 2015 は
男女=cat03・年齢=cat02 と入れ替わり、getMetaInfo とも食い違う）。よって cleaner は年ごとに
`clean_2010`/`clean_2015`/`clean_2020` を持ち、共通の `_clean` へ tab・軸列名・コード写像・
「余分な軸を総数コードで潰す」フィルタを渡す。1980-2005（昭和型・日本人のみ・県ブロック分割）は後続。

既存 age5（系統B・県表が85歳以上止まり）と違い、市区町村版は **100歳以上まで保持**する
（独自テーブル）。年齢不詳は各回表に実コードで存在するため（2020=22 / 2010,2015=999）、
age5 のような導出注入は不要でそのまま採る。

出力スキーマは age5 と同型の10列（area_level は 1〜7・is_current で level7 を識別）。
合併畳み込み（aggregate_to_base）は共有インフラに委ねる＝clean は全 area level を素直に出す。

出力 age_class_code は 5歳刻みの独自連番（110=0〜4 … 270=80〜84 / 280〜310=85〜89…100歳以上 /
100=総数 / 999=不詳）。系統B age5 の飛び番（140/270 欠番）とは別体系だがテーブルが別なので衝突しない。
"""

import polars as pl

# area @level=7 は「旧市区町村（合併消滅）」。2020 表のみ出現（2010/2015 は持たない）。
_OBSOLETE_AREA_LEVEL = 7

# 出力 age_class_code → 名称（5歳刻み・100歳以上を終端に保持・独自連番）。
AGE_CLASS = {
    "100": "総数",
    "110": "0〜4歳",
    "120": "5〜9歳",
    "130": "10〜14歳",
    "140": "15〜19歳",
    "150": "20〜24歳",
    "160": "25〜29歳",
    "170": "30〜34歳",
    "180": "35〜39歳",
    "190": "40〜44歳",
    "200": "45〜49歳",
    "210": "50〜54歳",
    "220": "55〜59歳",
    "230": "60〜64歳",
    "240": "65〜69歳",
    "250": "70〜74歳",
    "260": "75〜79歳",
    "270": "80〜84歳",
    "280": "85〜89歳",
    "290": "90〜94歳",
    "300": "95〜99歳",
    "310": "100歳以上",
    "999": "年齢不詳",
}
SEX_NAME = {"0": "総数", "1": "男", "2": "女"}

# --- 年別の入力コード → 出力コード写像 -------------------------------------------
# 各回で軸の割当（どの catNN が男女／年齢か）もコード体系も異なるため年ごとに定義する。
# ★注意: getMetaInfo と getStatsData で軸割当・コードが食い違う年がある（2015）ため、
#   マップは必ず getStatsData（to_tidy 出力）の実コードで確定すること（census_source_tables §3-3）。

# 2010（0003038591）: 男女=cat02(000/001/002)・年齢=cat03(000総数/200-219/600/999)。
_SEX_2010 = {"000": "0", "001": "1", "002": "2"}
_AGE_2010 = {
    "000": "100",
    # 200=0〜4 … 216=80〜84 → 110 … 270（110 + i*10）
    **{str(200 + i): str(110 + i * 10) for i in range(17)},
    "217": "280",
    "218": "290",
    "219": "300",
    "600": "310",
    "999": "999",
}

# 2015（0003149862）: ★軸が入れ替わり 男女=cat03(0000/0010/0020)・年齢=cat02(0000総数/1180-1370/1460/1490)。
_SEX_2015 = {"0000": "0", "0010": "1", "0020": "2"}
_AGE_2015 = {
    "0000": "100",
    # 1180=0〜4 … 1340=80〜84 → 110 … 270（110 + (code-1180)）
    **{str(1180 + i * 10): str(110 + i * 10) for i in range(17)},
    "1350": "280",
    "1360": "290",
    "1370": "300",
    "1460": "310",
    "1490": "999",
}

# 2020（0003445162）: 男女=cat02(0/1/2)・年齢=cat03(00総数/01-21/22不詳)。
_SEX_2020 = {"0": "0", "1": "1", "2": "2"}
_AGE_2020 = {
    "00": "100",
    # 01=0〜4 … 17=80〜84 → 110 … 270（110 + (n-1)*10）
    **{f"{i:02d}": str(110 + (i - 1) * 10) for i in range(1, 18)},
    "18": "280",
    "19": "290",
    "20": "300",
    "21": "310",
    "22": "999",
}


def _clean(
    tidy: pl.DataFrame,
    *,
    tab_code: str,
    sex_col: str,
    sex_map: dict[str, str],
    age_col: str,
    age_map: dict[str, str],
    extra_filters: dict[str, str],
) -> pl.DataFrame:
    """各回の市区町村5歳階級表を配布用10列へ写像する（余分軸は総数コードで潰す）。

    手順: tab で人口に絞り、`extra_filters`（国籍・出生の月・全域/DID の総数コード）で
    余分な軸を1点へ潰し、`sex_col`/`age_col`（年で catNN の割当が違う）を共通コードへ写像する。
    再掲(R*)は採用コード集合に無いので自動的に落ちる。年齢不詳は実コードのまま残す（注入しない）。
    """
    df = tidy.filter(pl.col("tab_code") == tab_code)
    for col, code in extra_filters.items():
        df = df.filter(pl.col(col) == code)
    df = df.filter(pl.col(f"{sex_col}_code").is_in(list(sex_map)) & pl.col(f"{age_col}_code").is_in(list(age_map)))
    return df.select(
        pl.col("area_code"),
        pl.col("area_name"),
        pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
        pl.col(f"{sex_col}_code").replace_strict(sex_map).alias("sex_code"),
        pl.col(f"{sex_col}_code").replace_strict({k: SEX_NAME[v] for k, v in sex_map.items()}).alias("sex"),
        pl.col(f"{age_col}_code").replace_strict(age_map).alias("age_class_code"),
        pl.col(f"{age_col}_code").replace_strict({k: AGE_CLASS[v] for k, v in age_map.items()}).alias("age_class"),
        # time_code 例: "2020000000" の先頭4桁が年
        pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
        # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
        pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False).alias("population"),
    ).with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003038591）用。男女=cat02・年齢=cat03。国籍(cat04)・出生の月(cat05)・DID(cat01) を総数で潰す。"""
    return _clean(
        tidy,
        tab_code="020",
        sex_col="cat02",
        sex_map=_SEX_2010,
        age_col="cat03",
        age_map=_AGE_2010,
        extra_filters={"cat01_code": "00710", "cat04_code": "000", "cat05_code": "000"},
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003149862）用。★軸入替: 男女=cat03・年齢=cat02。国籍/出生の月/DID を総数(4桁コード)で潰す。"""
    return _clean(
        tidy,
        tab_code="020",
        sex_col="cat03",
        sex_map=_SEX_2015,
        age_col="cat02",
        age_map=_AGE_2015,
        extra_filters={"cat01_code": "00710", "cat04_code": "0000", "cat05_code": "0000"},
    )


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003445162）用。男女=cat02・年齢=cat03。国籍(cat01) を総数で潰す（出生の月クロス無しのクリーン版）。"""
    return _clean(
        tidy,
        tab_code="2020_01",
        sex_col="cat02",
        sex_map=_SEX_2020,
        age_col="cat03",
        age_map=_AGE_2020,
        extra_filters={"cat01_code": "0"},
    )
