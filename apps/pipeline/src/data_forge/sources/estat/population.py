"""人口テーブル（国勢調査 男女別人口）固有のクレンジング。

transform.to_tidy() のロング形式を配布用の1枚テーブルへ整形する。同名「男女別人口」でも
e-Stat のスキーマ設計は年（テーブル世代）で全く異なる。実例が3変種揃ったので、パース差を
1つのパラメータ化 cleaner `clean_population` に集約し、年ごとの違いは設定（男女を持つ軸・
コード対応・事前フィルタ）だけで吸収する（＝年関数を増やさない）。

年ごとの構造の違い（すべて同一の出力スキーマへ写像する）:
    - 1990(0003412415)/1995(0003412416): 同型の「年齢3区分,男女別人口及び年齢別割合」表。
      area 構造は 2000/2005 と同型（level3=市区町村・level4=区）だが、男女は cat02。
      年齢3区分(cat01)・表章項目tab(020人口/105割合)を持つため tab=020・cat01=100(年齢総数) で絞る。
      本表は全国(00000)行を持たない（都道府県始まり）→ 他年と揃え 47都道府県合計から全国行を復元する。
    - 2000(0003391075): 2005表と同一ファミリー（平成12年版）。cat01=100/110/120・DID軸なし・area level3=市区町村。
    - 2005(0003408216): cat01に測定項目＋男女が融合（人口_総数/男/女=100/110/120）・DID軸なし。
    - 2010/2015(平成型, 0003038587/0003149040): tab軸なし・cat01=全域/人口集中地区(DID)・
      cat02に表章事項＋男女が統合（人口の総数/男/女コードは年で異なる）。全域のみ採用。
    - 2020(令和型, 0003445078): tab=人口・cat01=男女(0/1/2)。

出力スキーマ:
    area_code(str) / area_name(str) / area_level(int) /
    sex_code(str) / sex(str) / year(int) /
    population(Int64) / is_current(bool)

NOTE: area_name / area_level は年（テーブル世代）で意味・表記が異なる（例: 2005は level3=市区町村・
名称が「北海道札幌市」形式、2020は level4=市/6=市区町村）。年またぎで信頼できるのは area_code のみ。
多年の正規化（合併の後継自治体への集約や area 属性の統一）は地域マスタ(crosswalk)で行う想定。
is_current: area 階層が 7（旧市区町村・合併消滅）でないもの（level7 は 2020型のみ存在）。
"""

from collections.abc import Callable, Sequence

import polars as pl

# area @level=7 は「旧市区町村（2000年時点の廃止自治体）」。現存自治体と区別する。
_OBSOLETE_AREA_LEVEL = 7

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
            pl.col(axis_code)
            .replace_strict({k: v[0] for k, v in sex_by_code.items()})
            .alias("sex_code"),
            pl.col(axis_code)
            .replace_strict({k: v[1] for k, v in sex_by_code.items()})
            .alias("sex"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
            pl.col("value")
            .str.replace_all(r"[^0-9-]", "")
            .cast(pl.Int64, strict=False)
            .alias("population"),
        )
        .with_columns(
            (pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"),
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


def _prepend_national_from_prefectures(fact: pl.DataFrame) -> pl.DataFrame:
    """全国(00000)行を持たない表向けに、47都道府県(level2)合計から全国行を復元して先頭に付ける。

    他年（全国行あり。cli の人口保存チェックは fact の area_code=="00000" を national とみなす）と
    出力を揃えるための復元。平成2/7年の「年齢3区分,男女別人口」表がこれに該当する。
    """
    national = (
        fact.filter(pl.col("area_level") == 2)
        .group_by("sex_code", "sex", "year")
        .agg(pl.col("population").sum())
        .select(
            pl.lit("00000").alias("area_code"),
            pl.lit("全国").alias("area_name"),
            pl.lit(1).cast(pl.Int8).alias("area_level"),
            pl.col("sex_code"),
            pl.col("sex"),
            pl.col("year"),
            pl.col("population"),
            pl.lit(True).alias("is_current"),
        )
    )
    return pl.concat([national, fact]).sort("area_code", "sex_code")


def _clean_age3class_table(tidy: pl.DataFrame) -> pl.DataFrame:
    """平成2年(0003412415)/平成7年(0003412416) の同型表 → 男女別総人口。

    「年齢3区分,男女別人口及び年齢別割合」表。男女は cat02（コード体系は 2005 の cat01 と
    同じ 100/110/120）で、tab=020(人口)・cat01=100(年齢総数) で絞る。本表は全国(00000)行が
    無い（都道府県始まり）ため、47都道府県(level2)合計から全国行を復元する。
    公表値との一致: 1990=123,611,167 / 1995=125,570,246。
    """
    fact = clean_population(
        tidy,
        sex_axis="cat02",
        sex_by_code=SEX_2005,
        filters=[("tab_code", "020"), ("cat01_code", "100")],
    )
    return _prepend_national_from_prefectures(fact)


# 年ごとの cleaner（構造の違いは設定のみ）。
# 1990/1995 は同型（全国行なし・年齢3区分×男女）→ 共通 cleaner を流用。
clean_1990 = _clean_age3class_table
clean_1995 = _clean_age3class_table
# 2000表(0003391075)は2005表と同一ファミリー（cat01=100/110/120）なので設定を流用。
clean_2000 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2005)
clean_2005 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2005)  # cat01に測定項目融合
clean_2010 = _year_cleaner(sex_axis="cat02", sex_by_code=SEX_2010, filters=[_DID_WHOLE])
clean_2015 = _year_cleaner(sex_axis="cat02", sex_by_code=SEX_2015, filters=[_DID_WHOLE])
clean_2020 = _year_cleaner(sex_axis="cat01", sex_by_code=SEX_2020)  # 令和型
