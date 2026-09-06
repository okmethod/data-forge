"""国勢調査 従業地・通学地集計（昼夜間人口）固有のクレンジング。

「常住地又は従業地・通学地別人口（夜間人口・昼間人口）」時系列ファミリー
（statsDataId 0003412192〜197 / 0004003060、1990〜2020）を配布用の1枚テーブルへ整形する。
**帳票の事実（軸 cat01 の内訳・年カバレッジ・採る2総数・保存則）は
docs/distributions/daynight.md が正典**（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- area 軸は JIS コード・全国(00000)行ありで population_by_age 系と同型＝地域マスタ（アトム軸スタースキーマ）を
  無改修で再利用でき、area 集約の `*_code` 自動判別に乗る「3例目」（新規 area 対応は不要）。
- cat01 の多数の内訳から**2つの総数だけ**を採る: 常住地総数(夜間人口)→daynight_code="0"／
  従業地・通学地総数(昼間人口)→daynight_code="1"。
- **"0"=夜間**に割り当てるのは reconcile の総数スライス（全 `*_code`=="0"）を population と同じ
  「居住人口の保存」に一致させ、クロスファクト検算を成立させるため。0/1 は sex/age のような入れ子でなく
  畳んで総数にならない**並列な2母集団**（reconcile が population 系と異なる要点）。

出力スキーマは8列。列は clean_daynight_population の select が正典。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import code_name_cols, int_value, year_from_time_code

# cat01（常住地又は従業地・通学地による人口）の2総数 → (daynight_code, daynight名称)。
# 通勤流動の内訳（110〜230）は年で非同型なので採らない。
DAYNIGHT = {
    "100": ("0", "夜間人口（常住地）"),
    "180": ("1", "昼間人口（従業地・通学地）"),
}


def clean_daynight_population(tidy: pl.DataFrame) -> pl.DataFrame:
    """昼夜間人口の tidy → area × year × 昼夜間 の配布用8列へ写像する（全年共通）。

    cat01=100(夜間人口)/180(昼間人口) だけを採り daynight_code(0/1) へ写像する。
    本表は全国(00000)行を持つため national 復元は不要（population_by_age と異なる）。
    tab 軸は単一（020 人口）なので絞り込み不要。
    """
    return (
        tidy.filter(pl.col("cat01_code").is_in(list(DAYNIGHT)))
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            *code_name_cols("cat01_code", DAYNIGHT, "daynight"),
            year_from_time_code(),
            int_value().alias("population"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "daynight_code")
    )
