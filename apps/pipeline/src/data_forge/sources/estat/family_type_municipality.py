"""国勢調査 世帯の家族類型（16区分）別 一般世帯数 市区町村版（family_type のミクロ系列）のクレンジング。

各回の人口等基本集計（回次別）の市区町村「世帯の家族類型」表。
同じ table_name "family_type" に同居する全国／都道府県のみの
回次跨マクロ（単一 ID・1995-2020／family_type.py）と対をなし、市区町村まで下りる。

**帳票の事実は docs/sources/estat-census-catalog.md「家族類型」節が正典**
（ここには再掲しない＝ドリフト防止）＝年別の statsDataId・軸割当/コード体系・分類区分数の非対称・
DID 潰し・muni_levels 上書き。

Note（実装判断のみ）:
- **年別 cleaner**: 市区町村版は家族類型の**区分数がコード体系ごと年で違う**（2020=16区分/24コード・
  1995=32区分・2000=34区分・2005=22区分）。マクロ「16区分A_時系列」コード（100〜290/999）へ写像して縫合する。
  マップは getStatsData の実コードで確定する（getMetaInfo と食い違う年がある＝age5year ミクロと同じ罠）。
- **交差軸の周辺化**: 市区町村版は家族類型に別軸（世帯人員/住宅の所有 等）が交差する重い表なので、
  その軸を「総数」で絞り家族類型×area の周辺分布を復元する（households ミクロの tab 分離と同型）。
- **世帯人員は取れる年のみ**（2020 の軽量表 0003445080 は一般世帯数のみ）＝household_members は null。
  age5year の国籍軸・households の世帯人員と同じ**非対称同居**（列は常に持ち他年で埋める）。
- **家族類型不詳**は市区町村版が独立コードで直接持つ年がある（2020=cat02 "4"）＝マクロのような
  総数−Σ内訳の導出注入は不要でそのまま 999 へ写像する。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ 9 列（family_type.py マクロと同一）。列は _finalize の select が正典。
grain＝area×family_type×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.family_type import _FT_UNKNOWN, FAMILY_TYPE
from data_forge.sources.estat.transform import (
    area_passthrough_cols,
    int_value_expr,
    year_from_time_code_expr,
)

# 市区町村版 cat02（世帯の家族類型）コード → マクロ「16区分A_時系列」コード（family_type.FAMILY_TYPE の鍵）。
# ツリーは同一16区分で、コード体系だけが違う（市区町村版=0/1/11/111…、マクロ=100/110/120…）。
# （再掲）R1/R2/R3（3世代/高齢夫婦/高齢単独）はマップに含めず自動除外する。
_MUNI_TO_MACRO = {
    "0": "100",  # 総数
    "1": "110",  # 親族のみの世帯
    "11": "120",  # 核家族世帯
    "111": "130",  # 夫婦のみの世帯
    "112": "140",  # 夫婦と子供から成る世帯
    "113": "150",  # 男親と子供から成る世帯
    "114": "160",  # 女親と子供から成る世帯
    "12": "170",  # 核家族以外の世帯
    "1201": "180",  # 夫婦と両親から成る世帯
    "1202": "190",  # 夫婦とひとり親から成る世帯
    "1203": "200",  # 夫婦，子供と両親から成る世帯
    "1204": "210",  # 夫婦，子供とひとり親から成る世帯
    "1205": "220",  # 夫婦と他の親族（親，子供を含まない）から成る世帯
    "1206": "230",  # 夫婦，子供と他の親族（親を含まない）から成る世帯
    "1207": "240",  # 夫婦，親と他の親族（子供を含まない）から成る世帯
    "1208": "250",  # 夫婦，子供，親と他の親族から成る世帯
    "1209": "260",  # 兄弟姉妹のみから成る世帯
    "1210": "270",  # 他に分類されない世帯
    "2": "280",  # 非親族を含む世帯
    "3": "290",  # 単独世帯
    "4": _FT_UNKNOWN[0],  # 家族類型「不詳」（市区町村版は独立コードで直接持つ＝導出注入不要）
}

# マクロ code → family_type_level（0003414255 cat01_level を実測。ツリー正典＝family_type.FAMILY_TYPE）。
# 100=総数(1) / 110・280・290・999=総数直下(2) / 120・170=核家族・核家族以外(3) / 残りの内訳(4)。
_MACRO_LEVEL = {"100": 1, "110": 2, "280": 2, "290": 2, _FT_UNKNOWN[0]: 2, "120": 3, "170": 3}
_MACRO_LEVEL |= {c: 4 for c in FAMILY_TYPE if c not in _MACRO_LEVEL and c != "100"}

# family_type_code → 名称（マクロ FAMILY_TYPE ＋ 不詳）。
_FT_NAME = {**FAMILY_TYPE, _FT_UNKNOWN[0]: _FT_UNKNOWN[1]}


def _finalize(df: pl.DataFrame) -> pl.DataFrame:
    """family_type_code / value / time_code を持つ中間 DF を配布用9列へ写像する（世帯人員は null 注入）。

    area 3列（code/name/level）と time_code は入力にそのまま残っている前提。
    """
    return (
        df.select(
            *area_passthrough_cols(),
            pl.col("family_type_code"),
            pl.col("family_type_code").replace_strict(_FT_NAME).alias("family_type"),
            pl.col("family_type_code").replace_strict(_MACRO_LEVEL).cast(pl.Int8).alias("family_type_level"),
            year_from_time_code_expr(),
            int_value_expr().alias("households"),
            pl.lit(None, dtype=pl.Int64).alias("household_members"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "family_type_code", "year")
    )


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003445080）用。家族類型=cat02・世帯人員の人数=cat01（"0"総数で周辺化）・tab=一般世帯数のみ。

    cat01（世帯人員の人数）を総数で絞り、cat02（世帯の家族類型）をマクロコードへ写像する。
    世帯人員（測度）はこの表に無い＝household_members は null。
    """
    df = tidy.filter(
        (pl.col("cat01_code") == "0") & pl.col("cat02_code").is_in(list(_MUNI_TO_MACRO))
    ).with_columns(pl.col("cat02_code").replace_strict(_MUNI_TO_MACRO).alias("family_type_code"))
    return _finalize(df)
