"""国勢調査「人口」grain ファクトのクレンジング（男女別総人口＋年齢3区分×男女＋各マクロ）。

transform.to_tidy() のロング形式を配布用の1枚テーブルへ整形する。
特定統計表に依存しない汎用処理はtransform.py。
本モジュールは「人口」grain の cleaner を集約する（詳細は各関数 docstring が正典）:

- clean_population（男女別総人口・8列）＝ clean_1980..2020/2025速報。
  同名「男女別人口」でも e-Stat のスキーマ設計は年（テーブル世代）で全く異なる（4変種）。
  パース差を1つのパラメータ化 cleaner に集約し、年ごとの違いは
  設定（男女を持つ軸・コード対応・事前フィルタ）だけで吸収する（＝年関数を増やさない）。
  年別の軸構造（4変種の男女の在り処・全国行復元の要否）は
  docs/distributions/population.md「年ごとのスキーマ差」が正典（ここには再掲しない＝ドリフト防止）。
- clean_population_by_age（年齢3区分×男女・10列）＋ _inject_age_unknown＝ clean_population が
  cat01=100 で捨てる年齢軸を保持する拡張。回次跨の時系列ファミリー（全年同型）を1個で処理し、
  年齢不詳を「総数−3区分」で導出注入する。
- clean_by_age_prefecture / clean_population_prefecture＝回次跨の県マクロ（1920〜）。

Note（実装判断のみ）:
- 正規化の契約は「入力パースの共有」ではなく**「共通の出力スキーマへの写像」**。
- 年またぎで信頼できる area キーは area_code のみ。area_name/area_level は年で意味・表記が異なる。
  例: 2005 は level3=市区町村・名称が「北海道札幌市」形式／2020 は level4=市・6=市区町村。
  詳細は上記「年ごとのスキーマ差」。
  多年の正規化（合併の後継自治体への集約や area 属性の統一）は地域マスタ(crosswalk)で行う想定。
  is_current: area 階層が 7（旧市区町村・合併消滅）でないもの（level7 は 2020型のみ）。
- by_age/マクロ を別モジュールへ切らず同居させるのは private helper
  （clean_population・_prepend_national_from_prefectures・SEX_2005 等）を共有するため。
  別モジュール化すると公開せねばならず surface が増える（モジュール分割は「実例が2つ揃ってから」原則で見送り）。

出力スキーマは clean_population が8列・clean_population_by_age が age_class_code/age_class を足した10列。
列は各 clean_* の select が正典。
"""

from collections.abc import Callable, Sequence

import polars as pl

from data_forge.area.levels import always_current_expr, is_current_expr
from data_forge.sources.estat.transform import NATIONAL_AREA_CODE, area_axis_cols, code_name_cols, int_value

# 男女コードマップ: 生の {軸コード → (sex_code, sex名称)}
SexMap = dict[str, tuple[str, str]]

# 年ごとの「男女を持つ軸コード → (sex_code, sex)」。同名でも年でコード体系が異なる。
SEX_2005 = {"100": ("0", "総数"), "110": ("1", "男"), "120": ("2", "女")}  # cat01(測定項目融合)
SEX_2010 = {"000": ("0", "総数"), "001": ("1", "男"), "002": ("2", "女")}  # cat02
SEX_2015 = {"010": ("0", "総数"), "020": ("1", "男"), "030": ("2", "女")}  # cat02
SEX_2020 = {"0": ("0", "総数"), "1": ("1", "男"), "2": ("2", "女")}  # cat01

_DID_WHOLE = ("cat01_code", "00710")  # 平成型: cat01=全域（人口集中地区を除外）


def clean_population(
    tidy: pl.DataFrame,
    *,
    sex_axis: str,
    sex_by_code: SexMap,
    filters: Sequence[tuple[str, str]] = (),
) -> pl.DataFrame:
    """男女別人口の tidy を共通の配布用スキーマへ写像する（全世代共通）。

    引数:
        sex_axis    … 男女を持つ軸名（"cat01" / "cat02" など）。`<sex_axis>_code` を男女へ写像。
        sex_by_code … その軸の {コード → (sex_code, sex)}。人口の総数/男/女のみを列挙する
                      （＝人口性比・世帯数など他の項目コードは自動的に除外される）。
        filters     … 事前の等値フィルタ列（例: 平成型の cat01=全域）。
    """
    axis_code = f"{sex_axis}_code"
    df = tidy
    for col, val in filters:
        df = df.filter(pl.col(col) == val)
    return (
        df.filter(pl.col(axis_code).is_in(list(sex_by_code)))
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            *code_name_cols(axis_code, sex_by_code, "sex"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            int_value().alias("population"),
        )
        .with_columns(
            is_current_expr(),
        )
        .sort("area_code", "sex_code")
    )


def _year_cleaner(
    *, sex_axis: str, sex_by_code: SexMap, filters: Sequence[tuple[str, str]] = ()
) -> Callable[[pl.DataFrame], pl.DataFrame]:
    """レジストリに載せる単項 cleaner（tidy→DF）を生成する。"""

    def _clean(tidy: pl.DataFrame) -> pl.DataFrame:
        return clean_population(tidy, sex_axis=sex_axis, sex_by_code=sex_by_code, filters=filters)

    return _clean


def _prepend_national_from_prefectures(
    fact: pl.DataFrame, *, group_cols: Sequence[str] = ("sex_code", "sex", "year")
) -> pl.DataFrame:
    """全国(00000)行を持たない表向けに、47都道府県(level2)合計から全国行を復元して先頭に付ける。

    他年（全国行あり。cli の人口保存チェックは fact の area_code=="00000" を national とみなす）と
    出力を揃えるための復元。平成2/7年の「年齢3区分,男女別人口」表がこれに該当する。
    `group_cols` は全国合計を取る分類軸（既定＝男女×年。年齢区分を持つ表なら age_class を足す）。
    """
    national = (
        fact.filter(pl.col("area_level") == 2)
        .group_by(list(group_cols))
        .agg(pl.col("population").sum())
        .with_columns(
            *area_axis_cols(national=True),
            always_current_expr(),
        )
        .select(fact.columns)  # 元の列順・列集合へ揃える
    )
    sort_keys = ["area_code", *(c for c in ("sex_code", "age_class_code") if c in fact.columns)]
    return pl.concat([national, fact]).sort(sort_keys)


def _clean_age3class_table(tidy: pl.DataFrame) -> pl.DataFrame:
    """昭和55年(0003412413)/昭和60年(0003412414)/平成2年(0003412415)/平成7年(0003412416) の同型表 → 男女別総人口。

    「年齢3区分,男女別人口及び年齢別割合」表。男女は cat02（コード体系は 2005 の cat01 と
    同じ 100/110/120）で、tab=020(人口)・cat01=100(年齢総数) で絞る。本表は全国(00000)行が
    無い（都道府県始まり）ため、47都道府県(level2)合計から全国行を復元する。
    公表値との一致: 1980=117,060,396 / 1985=121,048,923 / 1990=123,611,167 / 1995=125,570,246。
    """
    fact = clean_population(
        tidy,
        sex_axis="cat02",
        sex_by_code=SEX_2005,
        filters=[("tab_code", "020"), ("cat01_code", "100")],
    )
    return _prepend_national_from_prefectures(fact)


# 年ごとの cleaner（構造の違いは設定のみ）。
# 1980/1985/1990/1995 は同型（全国行なし・年齢3区分×男女）→ 共通 cleaner を流用。
clean_1980 = _clean_age3class_table
clean_1985 = _clean_age3class_table
clean_1990 = _clean_age3class_table
clean_1995 = _clean_age3class_table
# 2000表(0003391075)は2005表と同一ファミリー（cat01=100/110/120）なので設定を流用。
clean_2000 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2005)
clean_2005 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2005)  # cat01に測定項目融合
clean_2010 = _year_cleaner(sex_axis="cat02", sex_by_code=SEX_2010, filters=[_DID_WHOLE])
clean_2015 = _year_cleaner(sex_axis="cat02", sex_by_code=SEX_2015, filters=[_DID_WHOLE])
clean_2020 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2020)  # 令和型
# 2025 人口速報集計(0004050397)は 2020 と同型の令和型。
# （tab=人口単一・cat01=男女0/1/2・全国行あり・time→2025）
# 速報=総人口のみで年齢/昼夜間軸は無い。確定が出たら破棄する。
clean_2025_preliminary = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2020)


# --- population_by_age（年齢3区分×男女別人口）------------------------------------
# 「年齢（3区分），男女別人口及び年齢別割合」時系列ファミリー（statsDataId 0003412413〜420 /
# 0003448299）は全年同型: tab=020(人口)/105(割合)・cat01=年齢3区分・cat02=男女・全国行なし。
# population 用の各年 cleaner が cat01=100 で捨てていた年齢軸を保持し、grain に age_class を足す。
AGE_TS: SexMap = {
    "100": ("0", "総数"),
    "110": ("1", "年少人口(0-14)"),
    "120": ("2", "生産年齢人口(15-64)"),
    "130": ("3", "老年人口(65+)"),
}
_AGE_UNKNOWN = ("9", "年齢不詳")


def clean_population_by_age(tidy: pl.DataFrame) -> pl.DataFrame:
    """時系列ファミリー表の tidy → 年齢3区分×男女別人口（10列）へ写像する（全年共通）。

    population.clean_* が cat01=100 で落としていた年齢軸を保持する拡張版。手順:
        1. tab=020（人口。割合 105 は導出可能なので捨てる）で絞る。
        2. cat02（男女, コード体系は SEX_2005 と同じ 100/110/120）→ sex_code / sex。
        3. cat01（年齢, 100/110/120/130）→ age_class_code / age_class（100 も残す）。
        4. 全国(00000)行を 47都道府県合計から復元（age_class × sex 別に集計）。
        5. 年齢不詳（age_class_code=9）を 総数−(年少+生産+老年) で導出注入。
           時系列ファミリーの cat01 に不詳コードは無く、近年は不詳が無視できないため。
           これにより「年少+生産+老年+不詳 == 総数」が全地域・全年で恒等的に成立する。

    出力スキーマは population の8列に age_class_code / age_class を足した10列。

    設計メモ（population との一本化）: age_class_code=0（総数）スライスは現行 population と
    値一致する（全9年で全国 diff=0 を実証済み）。将来 population を本 fact の総数スライスへ
    一本化し、population.py の異種年 cleaner 群を退役させうる（今は並存＝population 側は据え置き）。
    """
    fact = (
        tidy.filter(pl.col("tab_code") == "020")
        .filter(pl.col("cat02_code").is_in(list(AGE_TS)))  # 男女（コード体系は同じ）
        .filter(pl.col("cat01_code").is_in(list(AGE_TS)))  # 年齢3区分＋総数
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            *code_name_cols("cat02_code", SEX_2005, "sex"),
            *code_name_cols("cat01_code", AGE_TS, "age_class"),
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            int_value().alias("population"),
        )
        .with_columns(is_current_expr())
    )
    fact = _prepend_national_from_prefectures(
        fact, group_cols=("sex_code", "sex", "age_class_code", "age_class", "year")
    )
    return _inject_age_unknown(fact)


def _inject_age_unknown(fact: pl.DataFrame) -> pl.DataFrame:
    """年齢不詳行（age_class_code=9）= 総数 − (年少+生産+老年) を area×sex×year 毎に導出注入する。"""
    parts = (
        fact.filter(pl.col("age_class_code").is_in(["1", "2", "3"]))
        .group_by("area_code", "sex_code", "year")
        .agg(pl.col("population").sum().alias("_part"))
    )
    unknown = (
        fact.filter(pl.col("age_class_code") == "0")
        .join(parts, on=["area_code", "sex_code", "year"], how="left")
        .with_columns(
            pl.lit(_AGE_UNKNOWN[0]).alias("age_class_code"),
            pl.lit(_AGE_UNKNOWN[1]).alias("age_class"),
            (pl.col("population") - pl.col("_part").fill_null(0)).alias("population"),
        )
        .select(fact.columns)
    )
    return pl.concat([fact, unknown]).sort("area_code", "sex_code", "age_class_code")


# --- population_by_age 世紀マクロ（回次跨・都道府県・1920〜2020）--------------------
# 回次跨時系列「年齢（3区分）別人口及び年齢別割合 － 全国，都道府県（大正9年～令和2年）」0003410383。
# ミクロ clean_population_by_age（市区町村・各回別ID・1980〜）とは別ソースの都道府県マクロで、
# age5year.clean_prefecture と同じ役回り（回次跨 raw を1920まで遡る世紀マクロ）。差の要点:
#   - 本表は **男女軸を持たない**（総数のみ）→ sex は総数固定。aging（高齢化率）物語は総数ベースで充足。
#   - tab=1060(実数)/105(割合)。cat01=年齢3区分(100総数/105:0-14/120:15-64/130:65+)。DID 軸なし。
#   - 2015/2020 は不詳補完版(time 末尾000010)が併存 → 通常版(000000)へ統一（age5year/by_age ミクロと同方針）。
#   - 全国(00000)行は落とし **47都道府県のみ**を出す（配布・ダッシュボードは全国=Σ47県で復元＝
#     空間rollup 版と同一シェイプ＝ドロップイン）。
# age_class_code はミクロ AGE_TS と同一ターゲット('0'/'1'/'2'/'3'/'9')へ揃える（cat01 の 0-14 は
# ミクロ=110・本表=105 とコードは違うが写像先は共通）＝ダッシュボード／クロスファクト検算がミクロと一致。
AGE_3CLASS_LT: SexMap = {
    "100": ("0", "総数"),
    "105": ("1", "年少人口(0-14)"),
    "120": ("2", "生産年齢人口(15-64)"),
    "130": ("3", "老年人口(65+)"),
}


def clean_by_age_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """回次跨長期表(0003410383) → 年齢3区分×都道府県マクロ（総数のみ・47県・1920〜2020）。

    ミクロ clean_population_by_age と同じ10列スキーマへ寄せる（sex は総数固定）。手順:
        1. tab=1060（実数。割合105は導出可で捨てる）で絞り、不詳補完版(000010)を除外。
        2. cat01（年齢3区分）→ age_class_code / age_class（ミクロ AGE_TS と同一ターゲット）。
        3. sex は本表に軸が無い＝総数固定（sex_code='0' / sex='総数'）。
        4. 全国(00000)を落とし 47都道府県のみ（全国=Σ県で復元）。
        5. 年齢不詳（age_class_code=9）= 総数−(年少+生産+老年) を導出注入。
    """
    fact = (
        tidy.filter(pl.col("tab_code") == "1060")
        .filter(pl.col("cat01_code").is_in(list(AGE_3CLASS_LT)))
        .filter(pl.col("time_code").str.slice(4) == "000000")
        .filter(pl.col("area_code") != NATIONAL_AREA_CODE)
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            pl.lit("0").alias("sex_code"),
            pl.lit("総数").alias("sex"),
            *code_name_cols("cat01_code", AGE_3CLASS_LT, "age_class"),
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            int_value().alias("population"),
        )
        .with_columns(is_current_expr())
    )
    return _inject_age_unknown(fact)


# --- population 世紀マクロ（回次跨・都道府県・1920〜2020）--------------------------
# 回次跨時系列「男女別人口及び人口性比 － 全国，都道府県（大正9年～令和2年）」0003410379。
# ミクロ population（市区町村・各回別ID・1980〜＋2025速報）とは別ソースの都道府県マクロで、
# age5year.clean_prefecture と同じ役回り（回次跨 raw を1920まで遡る）。要点:
#   - tab=020(人口)/1120(性比)。cat01=男女(100総数/110男/120女＝SEX_2005)。年齢軸なし。
#   - area=全国(00000)＋人口集中地区(00100/00200)＋47県。全国と DID を落とし **47都道府県のみ**
#     （配布・ダッシュボードは全国=Σ47県で復元＝旧・空間rollup 版と同一シェイプ＝ドロップイン）。
#   - 本表に不詳補完版(time 末尾000010)は無い。将来混入しても年重複は combine_years の grain 検査が弾く。
# 2025速報は本マクロには無いため、時系列側（population_prefecture_timeseries）で
# preliminary_upstreams により継ぎ足す（ミクロと同じ splice 機構）。
def clean_population_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """回次跨長期表(0003410379) → 男女別総人口×都道府県マクロ（47県・1920〜2020）。

    ミクロ population と同一8列スキーマ。clean_population（tab=020 で人口のみ・性比1120は除外）を
    流用し、全国(00000)と人口集中地区(00100/00200)を落として47都道府県だけを残す。
    """
    fact = clean_population(
        tidy,
        sex_axis="cat01",
        sex_by_code=SEX_2005,
        filters=[("tab_code", "020")],
    )
    return fact.filter(~pl.col("area_code").is_in(["00000", "00100", "00200"]))
