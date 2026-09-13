"""国勢調査 世帯の種類別 世帯数・世帯人員 市区町村版（households のミクロ系列）のクレンジング。

各回の人口等基本集計（回次別）の市区町村「世帯の種類別」表。
同じ table_name "households" に同居する全国／都道府県のみの
回次跨マクロ（単一 ID・1960-2020／households.py）と対をなし、
市区町村（旧市区町村 level7 を含む年もある）まで下りる。
対象＝1985〜2020 の各回。
1980 は「一般世帯／施設等の世帯」体系の市区町村世帯数表が e-Stat に無く欠＝ミクロは1985始まり。
根拠は下記カタログ節。

**帳票の事実は docs/sources/estat-census-catalog.md「世帯の種類・人員」節が正典**
（ここには再掲しない＝ドリフト防止）
＝年別の statsDataId・軸割当/コード体系・世帯人員/旧市区町村カバレッジの非対称・DID 潰し・muni_levels 上書き。

Note（実装判断のみ）:
- **年別 cleaner**: 世帯の種類の軸割当（cat01 or cat02）・測度の持ち方（tab 分離 / cat 混載 / 単一値）・
  全域/DID 軸の有無が年ごとに違うため `clean_<year>` を年別に持つ。マップは getStatsData の実コードで確定。
- **世帯人員は 2015/2020 のみ**取れる（他年は世帯数のみ）＝age5year の国籍軸と同じ**非対称同居**。
  household_members 列を常に持ち、取れる年だけ埋め・他年は null（マクロ households.py とスキーマ一致）。
- **不詳は導出注入しない**（悉皆だが「世帯の種類不詳」は年により総数へ埋込 or 独立コード）。
  1990-2005 の総数(不詳を含む)・2010 の独立不詳(006) は総数側に残し内訳(一般/施設)だけ採る
  ＝Σ内訳 ≤ 総数（差≒不詳規模。age5year の埋込不詳と同思想）。1985/2015/2020 は不詳なしで総数==一般+施設。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す
  （level7＝旧市区町村・2010以降のみ／is_current で識別）。全国(level1)・県(level2) 行も含む年は
  scope 分離せず素通しする（ミクロ配布は市区町村主眼だが県 rollup 検算のため県/全国も残す）。

出力スキーマ 9 列（households.py マクロと同一）。列は _finalize の select が正典。
grain＝area×household_type×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import area_passthrough_cols, int_value_expr, year_from_time_code_expr

# 出力 household_type_code → 名称（households.py マクロと同一）。総数=一般+施設（不詳は総数に内包・内訳に立てない）。
HOUSEHOLD_TYPE = {"100": "総数", "110": "一般世帯", "120": "施設等の世帯"}

# 全域/DID 軸を持つ年の「全域」コード（2000/2005=00700・2010=00710）。DID(…701/…711) は潰す。
_WHOLE_2000 = "00700"
_WHOLE_2010 = "00710"

# 世帯の種類 入力コード → 出力コード（不詳コードは載せず自動除外）。
_TYPE_STD = {"000": "100", "001": "110", "002": "120"}  # 1985/1990/1995/2000/2005（cat 直下）
_TYPE_2010 = {"003": "100", "004": "110", "005": "120"}  # 2010 は cat02 に人口と混載（006=不詳は除外）
_TYPE_2020 = {"0": "100", "1": "110", "2": "120"}  # 2020 は cat01 が世帯の種類単独
# 2015 は cat02 に測度×種類が融合（200番台=世帯数・300番台=世帯人員）。
_HH_2015 = {"200": "100", "210": "110", "220": "120"}
_MEM_2015 = {"300": "100", "310": "110", "320": "120"}

_JOIN_KEYS = ["area_code", "time_code", "household_type_code"]


def _finalize(df: pl.DataFrame) -> pl.DataFrame:
    """household_type_code / households / household_members / time_code を持つ中間 DF を配布用9列へ写像する。

    area 3列（code/name/level）と time_code は入力にそのまま残っている前提。
    """
    return (
        df.select(
            *area_passthrough_cols(),
            pl.col("household_type_code"),
            pl.col("household_type_code").replace_strict(HOUSEHOLD_TYPE).alias("household_type"),
            year_from_time_code_expr(),
            pl.col("households"),
            pl.col("household_members"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "household_type_code", "year")
    )


def _households_only(
    tidy: pl.DataFrame,
    *,
    type_col: str,
    type_map: dict[str, str],
    whole_col: str | None = None,
    whole_code: str | None = None,
) -> pl.DataFrame:
    """世帯数のみ（世帯人員なし）の年を配布用9列へ写像する。household_members は null 注入。

    `whole_col`/`whole_code` を渡すと全域/DID 軸を全域コードで潰す（2000/2005/2010）。
    """
    df = tidy
    if whole_col is not None:
        df = df.filter(pl.col(whole_col) == whole_code)
    df = df.filter(pl.col(f"{type_col}_code").is_in(list(type_map)))
    df = df.with_columns(
        pl.col(f"{type_col}_code").replace_strict(type_map).alias("household_type_code"),
        int_value_expr().alias("households"),
        pl.lit(None, dtype=pl.Int64).alias("household_members"),
    )
    return _finalize(df)


def clean_1985(tidy: pl.DataFrame) -> pl.DataFrame:
    """1985（0000030448）用。世帯の種類=cat01(000総数/001一般/002施設)・世帯数のみ・DID 軸なし・不詳なし。"""
    return _households_only(tidy, type_col="cat01", type_map=_TYPE_STD)


def clean_1990(tidy: pl.DataFrame) -> pl.DataFrame:
    """1990（0000031400）用。cat01(000総数(不詳を含む)/001/002)・世帯数のみ・DID なし。不詳は総数に内包。"""
    return _households_only(tidy, type_col="cat01", type_map=_TYPE_STD)


def clean_1995(tidy: pl.DataFrame) -> pl.DataFrame:
    """1995（0000032218）用。1990 と同型（cat01・総数不詳内包・世帯数のみ）。"""
    return _households_only(tidy, type_col="cat01", type_map=_TYPE_STD)


def clean_2000(tidy: pl.DataFrame) -> pl.DataFrame:
    """2000（0000032964）用。全域/DID=cat01・種類=cat02(000総数(不詳含)/001/002)・世帯数のみ。全域で DID を潰す。"""
    return _households_only(tidy, type_col="cat02", type_map=_TYPE_STD, whole_col="cat01_code", whole_code=_WHOLE_2000)


def clean_2005(tidy: pl.DataFrame) -> pl.DataFrame:
    """2005（0000033786）用。2000 と同型（全域/DID=cat01・種類=cat02・総数不詳内包・世帯数のみ）。"""
    return _households_only(tidy, type_col="cat02", type_map=_TYPE_STD, whole_col="cat01_code", whole_code=_WHOLE_2000)


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003038587）用。全域/DID=cat01。cat02 に人口(000-002)と世帯数(003総数/004一般/005施設/006不詳)が混載。

    世帯数の3種別だけ採り（不詳006は載せず自動除外）人口行を落とす。世帯人員はこの表に無い。全域(00710) で DID を潰す。
    """
    return _households_only(tidy, type_col="cat02", type_map=_TYPE_2010, whole_col="cat01_code", whole_code=_WHOLE_2010)


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003149040）用。全域/DID=cat01。cat02 に測度×種類が融合（世帯数=200/210/220・世帯人員=300/310/320）。

    世帯数群と世帯人員群を別々に写像し household_type で左結合して2測度を横並びにする。人口(010-040)は除外。
    全域(00710) で DID を潰す。
    """
    df = tidy.filter(pl.col("cat01_code") == _WHOLE_2010)
    households = df.filter(pl.col("cat02_code").is_in(list(_HH_2015))).with_columns(
        pl.col("cat02_code").replace_strict(_HH_2015).alias("household_type_code"),
        int_value_expr().alias("households"),
    )
    members = df.filter(pl.col("cat02_code").is_in(list(_MEM_2015))).select(
        *_JOIN_KEYS[:2],
        pl.col("cat02_code").replace_strict(_MEM_2015).alias("household_type_code"),
        int_value_expr().alias("household_members"),
    )
    return _finalize(households.join(members, on=_JOIN_KEYS, how="left"))


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003445098）用。世帯の種類=cat01(0総数/1一般/2施設)・測度=tab(2020_13世帯数/2020_22世帯人員)・DID なし。

    tab で世帯数と世帯人員を分け household_type で左結合して横並びにする（households.py マクロと同じ束ね方）。
    """
    base = tidy.filter(pl.col("cat01_code").is_in(list(_TYPE_2020))).with_columns(
        pl.col("cat01_code").replace_strict(_TYPE_2020).alias("household_type_code")
    )
    households = base.filter(pl.col("tab_code") == "2020_13").with_columns(int_value_expr().alias("households"))
    members = base.filter(pl.col("tab_code") == "2020_22").select(
        *_JOIN_KEYS, int_value_expr().alias("household_members")
    )
    return _finalize(households.join(members, on=_JOIN_KEYS, how="left"))
