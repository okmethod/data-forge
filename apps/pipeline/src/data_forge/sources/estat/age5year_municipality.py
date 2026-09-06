"""国勢調査 年齢（5歳階級）×男女別人口 市区町村版（age5year のミクロ系列）のクレンジング。

各回の基本集計（回次別）の市区町村5歳階級表。
同じ table_name "age5year" に同居する全国／都道府県のみの
世紀マクロ（回次跨・単一ID・1920-2020／age5year.py）と対をなし、
市区町村（旧市区町村 level7 を含む年もある）まで下りる。
対象＝1980〜2020 の各回。

**帳票の事実は docs/sources/estat-census-catalog.md「年齢（5歳階級）」節が正典**
（ここには再掲しない＝ドリフト防止）
＝年別の statsDataId・軸割当/コード体系・国籍/不詳カバレッジの非対称・2000/2005 の各歳表
採用理由（5歳階級2表の穴で不採用）・muni_levels 上書き。

Note（実装判断のみ）:
- **年別 cleaner**: 軸割当もコード体系も年ごとに違うため cleaner は年別に `clean_<year>` を持ち、共通の
  `_clean` へ tab・軸列名・コード写像・「余分な軸を総数コードで潰す」フィルタ・国籍の扱い（定数注入 or
  軸写像）を渡す。マップは getStatsData の実コードで確定（getMetaInfo と食い違う年がある）。2000/2005 は
  各歳の巨大表から5歳階級の再掲コードだけを拾い、datasets 側でサーバ側絞り込みを掛ける。
- **軸の採否**: grain に載せる軸＝「保存則が閉じる・下流需要がある」もの（area / sex / age_class /
  nationality）のみ。他のクロス軸（全域・DID・出生の月）は総数コードで潰す。★nationality 軸を持つ
  （総数=0 / 日本人=1）点がマクロ（age5year.py＝総人口専用）と非対称で、ミクロ系列のみが担う。
- **不詳は導出注入しない**（回次跨 age5year / 3区分時系列と非対称）。各歳表は国籍カバレッジが非対称で
  母集団保証が弱く `総数−Σ` が偽の不詳を生むため＝実コードがある年はそのまま採り、無い年（1990/1995/2005）
  は空。根拠と per-year の不詳コードは上記カタログ節。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す
  （area_level 1〜7・is_current で level7＝旧市区町村・2020 のみ を識別）。

出力スキーマ 12 列（age5year の10列＋nationality_code/nationality）。
列は各 clean_* の select が正典。
grain＝area×year×sex×nationality×age_class。
age_class_code は 5歳刻みの独自連番（100=総数 / 999=不詳・100歳以上まで保持。全コードは下記 AGE_CLASS）。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import area_passthrough_cols, int_value_expr, year_from_time_code_expr

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
# 出力 nationality_code → 名称（総数=0 / 日本人=1）。国籍軸のある年は写像、無い年は定数注入する。
NATIONALITY_NAME = {"0": "総数", "1": "日本人"}

# --- 年別の入力コード → 出力コード写像 -------------------------------------------
# 各回で軸の割当（どの catNN が男女／年齢か）もコード体系も異なるため年ごとに定義する。
# ★注意: getMetaInfo と getStatsData で軸割当・コードが食い違う年がある（2015）ため、マップは必ず
#   getStatsData（to_tidy 出力）の実コードで確定すること（sources/estat-census-catalog.md「年齢（5歳階級）」節）。

# 1980（0000030127）: tab 軸なし。男女=cat02(000/001/002)・年齢=cat03(000総数/001-021/022不詳)。
# 国籍/出生の月クロス無し・cat01=全域/DID のみ。年齢コードは 3 桁だが体系は 2020 と同型。
_SEX_1980 = {"000": "0", "001": "1", "002": "2"}
_AGE_1980 = {
    "000": "100",
    # 001=0〜4 … 017=80〜84 → 110 … 270（110 + (n-1)*10）
    **{f"{i:03d}": str(110 + (i - 1) * 10) for i in range(1, 18)},
    "018": "280",
    "019": "290",
    "020": "300",
    "021": "310",
    "022": "999",
}

# 1985（0000030449）: tab 軸なし。男女=cat02(000/001/002)・年齢=cat03(001総数/002-022/023不詳)。
# 1980 と同じく国籍/出生の月クロス無し・cat01=全域/DID のみ。ただし年齢コードが 1980 から +1 ずれ
# （001=総数/002=0〜4…022=100歳以上/023=不詳）、末尾に 024=平均年齢・025=年齢中位数（人口でない
# 統計量）を含む＝age_map に載せず自動除外する。
_SEX_1985 = {"000": "0", "001": "1", "002": "2"}
_AGE_1985 = {
    "001": "100",
    # 002=0〜4 … 018=80〜84 → 110 … 270（110 + (n-2)*10）
    **{f"{i:03d}": str(110 + (i - 2) * 10) for i in range(2, 19)},
    "019": "280",
    "020": "290",
    "021": "300",
    "022": "310",
    "023": "999",
    # 024=平均年齢・025=年齢中位数 は人口でない統計量ゆえ載せない（自動除外）。
}

# 1990（0000031405）: tab 軸なし・**日本人人口**（国籍軸なし＝定数注入）。男女=cat02(000/001/002)・
# 年齢=cat03(000総数/001-021)。1980 と同コード体系だが **年齢不詳コードが無い**（22区分＝100歳以上止まり）。
_SEX_1990 = {"000": "0", "001": "1", "002": "2"}
_AGE_1990 = {
    "000": "100",
    # 001=0〜4 … 017=80〜84 → 110 … 270（110 + (n-1)*10）。不詳(999)は原表に無い。
    **{f"{i:03d}": str(110 + (i - 1) * 10) for i in range(1, 18)},
    "018": "280",
    "019": "290",
    "020": "300",
    "021": "310",
}

# 1995（0000032223）: tab 軸なし・**日本人人口**（国籍軸なし＝定数注入）。★軸割当が違う＝男女=cat03・
# 年齢=cat02(T01総数/200-219/500=100歳以上)。1995 も **年齢不詳コードが無い**（22区分）。
_SEX_1995 = {"000": "0", "001": "1", "002": "2"}
_AGE_1995 = {
    "T01": "100",
    # 200=0〜4 … 216=80〜84 → 110 … 270（110 + k*10）。不詳(999)は原表に無い。
    **{str(200 + k): str(110 + k * 10) for k in range(17)},
    "217": "280",
    "218": "290",
    "219": "300",
    "500": "310",
}

# 2000（0000032965）: 全域/DID=cat01(00700/00701)・国籍=cat02(000総数(外国,不詳含む)/001日本人)・
#   年齢=cat03（各歳123 だが **5歳階級の再掲コード** T01/200-219/500=100歳以上/900=不詳 を内包）・
#   男女=cat04(000/001/002)。
#   tab/出生の月 軸なし。★この表だけ「県市区町村」全域を1つに含み（≥20万/<20万の2表分割＝県庁所在市・特別区に
#   穴が空く問題を回避）、政令市の行政区(level5)も持つが aggregate_to_base のアトム抽出（muni_levels={4,6}）が
#   区を落として政令市=1ユニットにする。各歳(000-…)は age_map 非収載で自動除外＝5歳階級だけ残る。
#   巨大表（3.82M行）ゆえ datasets 側でサーバ側絞り込み（cdCat01=00700・cdCat03=5歳コード）を掛け 53万行に抑える。
_SEX_2000 = {"000": "0", "001": "1", "002": "2"}
_NAT_2000 = {"000": "0", "001": "1"}
_AGE_2000 = {**_AGE_1995, "900": "999"}  # 1995 と同型（T01/200-219/500）＋ 年齢不詳(900)

# 2005（0000033783）: 2000（0000032965）と**同型**の各歳表。全域/DID=cat01(00700/00701)・国籍=cat02(000総数/001日本人)・
#   年齢=cat03（各歳だが 5歳階級の再掲コード T01/200-219/500=100歳以上 を内包）・**男女×出生の月**=cat04。
#   cat04 の男女総数は 000/001男/006女 の3コード（他は出生月クロス＝sex_map 非収載で自動除外）で、
#   2000 の cat04=男女(000/001/002) とはここだけ差。
#   ★この表は**年齢不詳の行(900)を持たない**が、総数(T01) に5歳階級へ未分類の残差＝埋め込み不詳が残り
#   **Σ5歳階級 ≤ 総数**（差≒不詳規模。crossfact J2 が known_diff で受容）。
#   age_map は _AGE_1995 と同型（900 を足さない）。
#   巨大表ゆえ datasets 側でサーバ側絞り込み（cdCat01=00700・cdCat03=5歳コード）を掛ける。
_SEX_2005 = {"000": "0", "001": "1", "006": "2"}
_NAT_2005 = {"000": "0", "001": "1"}
_AGE_2005 = dict(_AGE_1995)  # T01/200-219/500=100歳以上（2005 は年齢不詳コードが無い＝900 を含めない）


# 2010（0003038591）: 男女=cat02(000/001/002)・年齢=cat03(000総数/200-219/600/999)。国籍=cat04(000総数/100日本人)。
_SEX_2010 = {"000": "0", "001": "1", "002": "2"}
_NAT_2010 = {"000": "0", "100": "1"}
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
#   国籍=cat04(0000総数/0150日本人)。
_SEX_2015 = {"0000": "0", "0010": "1", "0020": "2"}
_NAT_2015 = {"0000": "0", "0150": "1"}
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

# 2020（0003445162）: 男女=cat02(0/1/2)・年齢=cat03(00総数/01-21/22不詳)。国籍=cat01(0総数/1日本人)。
_SEX_2020 = {"0": "0", "1": "1", "2": "2"}
_NAT_2020 = {"0": "0", "1": "1"}
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
    tab_code: str | None,
    sex_col: str,
    sex_map: dict[str, str],
    age_col: str,
    age_map: dict[str, str],
    extra_filters: dict[str, str],
    nat_col: str | None = None,
    nat_map: dict[str, str] | None = None,
    nat_const: str | None = None,
) -> pl.DataFrame:
    """各回の市区町村5歳階級表を配布用12列へ写像する（余分軸は総数コードで潰す）。

    手順: tab で人口に絞り（`tab_code=None` の年＝tab 軸そのものが無いので絞らない）、
    `extra_filters`（出生の月・全域/DID の総数コード）で余分な軸を1点へ潰し、
    `sex_col`/`age_col`（年で catNN の割当が違う）を共通コードへ写像する。
    再掲(R*)は採用コード集合に無いので自動的に落ちる。年齢不詳は実コードのまま残す（注入しない）。

    国籍(nationality)は2通り: `nat_col`+`nat_map` を渡すと国籍軸を残して総数・日本人を**両方**出す
    （2010/2015/2020）。`nat_const` を渡すと国籍軸が無い年に定数を注入する（総数=1980/1985・
    日本人=1990/1995）。どちらか一方のみ指定する。
    """
    df = tidy if tab_code is None else tidy.filter(pl.col("tab_code") == tab_code)
    for col, code in extra_filters.items():
        df = df.filter(pl.col(col) == code)
    df = df.filter(pl.col(f"{sex_col}_code").is_in(list(sex_map)) & pl.col(f"{age_col}_code").is_in(list(age_map)))
    if nat_col is not None:
        assert nat_map is not None
        df = df.filter(pl.col(f"{nat_col}_code").is_in(list(nat_map)))
        nat_code = pl.col(f"{nat_col}_code").replace_strict(nat_map)
        nat_name = pl.col(f"{nat_col}_code").replace_strict({k: NATIONALITY_NAME[v] for k, v in nat_map.items()})
    else:
        assert nat_const is not None
        nat_code = pl.lit(nat_const)
        nat_name = pl.lit(NATIONALITY_NAME[nat_const])
    return df.select(
        *area_passthrough_cols(),
        pl.col(f"{sex_col}_code").replace_strict(sex_map).alias("sex_code"),
        pl.col(f"{sex_col}_code").replace_strict({k: SEX_NAME[v] for k, v in sex_map.items()}).alias("sex"),
        nat_code.alias("nationality_code"),
        nat_name.alias("nationality"),
        pl.col(f"{age_col}_code").replace_strict(age_map).alias("age_class_code"),
        pl.col(f"{age_col}_code").replace_strict({k: AGE_CLASS[v] for k, v in age_map.items()}).alias("age_class"),
        # time_code 例: "2020000000" の先頭4桁が年
        year_from_time_code_expr(),
        int_value_expr().alias("population"),
    ).with_columns(is_current_expr())


def clean_1980(tidy: pl.DataFrame) -> pl.DataFrame:
    """1980（0000030127）用。tab 軸なし・男女=cat02・年齢=cat03・**総人口**（総数注入）。cat01=全域 で DID 除外。"""
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat02",
        sex_map=_SEX_1980,
        age_col="cat03",
        age_map=_AGE_1980,
        extra_filters={"cat01_code": "00700"},
        nat_const="0",
    )


def clean_1985(tidy: pl.DataFrame) -> pl.DataFrame:
    """1985（0000030449）用。tab 軸なし・男女=cat02・年齢=cat03・**総人口**（総数注入）。cat01=全域 で DID 除外。

    年齢コードは 1980 から +1 ずれ（001=総数）。平均年齢/中位数(024/025)は age_map 非収載で自動除外。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat02",
        sex_map=_SEX_1985,
        age_col="cat03",
        age_map=_AGE_1985,
        extra_filters={"cat01_code": "00700"},
        nat_const="0",
    )


def clean_1990(tidy: pl.DataFrame) -> pl.DataFrame:
    """1990（0000031405）用。tab 軸なし・男女=cat02・年齢=cat03・**日本人人口**（国籍軸なし→日本人を定数注入）。

    総人口版は市区町村フル粒度に存在しない（sources/estat-census-catalog.md（年齢5歳階級節））。年齢不詳コードは原表に無い。
    cat01=全域(00700) で DID を落とす。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat02",
        sex_map=_SEX_1990,
        age_col="cat03",
        age_map=_AGE_1990,
        extra_filters={"cat01_code": "00700"},
        nat_const="1",
    )


def clean_1995(tidy: pl.DataFrame) -> pl.DataFrame:
    """1995（0000032223）用。tab 軸なし・**日本人人口**（日本人を定数注入）。★軸割当: 男女=cat03・年齢=cat02。

    総人口版は市区町村フル粒度に存在しない。年齢不詳コードは原表に無い。cat01=全域(00700) で DID を落とす。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat03",
        sex_map=_SEX_1995,
        age_col="cat02",
        age_map=_AGE_1995,
        extra_filters={"cat01_code": "00700"},
        nat_const="1",
    )


def clean_1990_1995_total(tidy: pl.DataFrame) -> pl.DataFrame:
    """1990/1995 の**総人口** 各歳表（0000031401/0000032219・両年同型）用。国籍軸なし→総数を定数注入。

    日本人版（0000031405/0000032223＝clean_1990/1995）とは**別表**で、こちらは国籍を分けない総人口
    （sources/estat-census-catalog.md「年齢（5歳階級）」節。
    日本人版は 5歳階級表 006、総人口はこの各歳表 00401 という表形式の非対称）。
    形は 2000（0000032965）と同じ各歳表＝年齢軸に 5歳階級の再掲コード（T01/200-219/500=100歳以上/
    900=不詳）を内包し、それだけ拾う（各歳は age_map 非収載で自動除外）。軸割当は 男女=cat03・
    年齢=cat02（日本人版 1990 の 男女=cat02/年齢=cat03 とは違い、1995 日本人版とは同じ）。国籍軸が無いので
    総数(0)を定数注入する（1980/1985 と同方式）。令和型 level4/6 ゆえ datasets 側で muni_levels={4,6} を上書きし、
    巨大表対策にサーバ側絞り込み（cdCat01=00700・cdCat02=5歳コード）を掛ける。全域(cat01=00700) で DID を落とす。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat03",
        sex_map=_SEX_2000,
        age_col="cat02",
        age_map=_AGE_2000,
        extra_filters={"cat01_code": "00700"},
        nat_const="0",
    )


def clean_2000(tidy: pl.DataFrame) -> pl.DataFrame:
    """2000（0000032965）用。tab/出生の月 軸なし。全域/DID=cat01・国籍=cat02・年齢=cat03・男女=cat04。

    全市区町村（政令市の行政区・支庁・郡部の集計行も含む）を1表で持つ各歳表だが、年齢軸に 5歳階級の
    再掲コード（T01/200-219/500=100歳以上/900=不詳）を内包するので age_map で 5歳階級だけ拾う（各歳は自動除外）。
    国籍軸あり＝総数・日本人を両出し。全域(cat01=00700) で DID を落とす。政令市区(level5)や集計行は
    aggregate_to_base のアトム抽出（muni_levels={4,6}）が落とす。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat04",
        sex_map=_SEX_2000,
        age_col="cat03",
        age_map=_AGE_2000,
        extra_filters={"cat01_code": "00700"},
        nat_col="cat02",
        nat_map=_NAT_2000,
    )


def clean_2005(tidy: pl.DataFrame) -> pl.DataFrame:
    """2005（0000033783）用。2000 と同型の各歳表。全域/DID=cat01・国籍=cat02・年齢=cat03・**男女×出生の月**=cat04。

    clean_2000 を流用し cat04 の男女コードだけ 000/001/006（男女の総数）に読み替える
    （出生の月クロスは sex_map 非収載で自動除外）。
    年齢軸に 5歳階級の再掲コード（T01/200-219/500=100歳以上）を内包するので age_map で
    5歳階級だけ拾う（各歳は自動除外）。
    ★この表は年齢不詳の行を持たないが 総数(T01) に埋め込み不詳が残り Σ5歳階級 ≤ 総数
    （差≒不詳規模・crossfact J2 が known_diff で受容）。
    国籍軸あり＝総数・日本人を両出し。全域(cat01=00700) で DID を落とす。
    政令市区(level5)や集計行は aggregate_to_base のアトム抽出（muni_levels={4,6}）が落とす。
    """
    return _clean(
        tidy,
        tab_code=None,
        sex_col="cat04",
        sex_map=_SEX_2005,
        age_col="cat03",
        age_map=_AGE_2005,
        extra_filters={"cat01_code": "00700"},
        nat_col="cat02",
        nat_map=_NAT_2005,
    )


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003038591）用。男女=cat02・年齢=cat03・国籍=cat04（総数/日本人を両出し）。出生の月・DID は総数で潰す。"""
    return _clean(
        tidy,
        tab_code="020",
        sex_col="cat02",
        sex_map=_SEX_2010,
        age_col="cat03",
        age_map=_AGE_2010,
        extra_filters={"cat01_code": "00710", "cat05_code": "000"},
        nat_col="cat04",
        nat_map=_NAT_2010,
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003149862）用。★軸入替: 男女=cat03・年齢=cat02。国籍=cat04（総数/日本人を両出し）。出生月/DID を潰す。"""
    return _clean(
        tidy,
        tab_code="020",
        sex_col="cat03",
        sex_map=_SEX_2015,
        age_col="cat02",
        age_map=_AGE_2015,
        extra_filters={"cat01_code": "00710", "cat05_code": "0000"},
        nat_col="cat04",
        nat_map=_NAT_2015,
    )


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003445162）用。男女=cat02・年齢=cat03・国籍=cat01（総数/日本人を両出し・出生の月クロス無しのクリーン版）。"""
    return _clean(
        tidy,
        tab_code="2020_01",
        sex_col="cat02",
        sex_map=_SEX_2020,
        age_col="cat03",
        age_map=_AGE_2020,
        extra_filters={},
        nat_col="cat01",
        nat_map=_NAT_2020,
    )
