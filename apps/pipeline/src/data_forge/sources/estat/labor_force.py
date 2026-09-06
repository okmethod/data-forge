"""国勢調査 労働力状態（3区分）×男女別人口 固有のクレンジング。

就業状態等基本集計の時系列データ製品「労働力状態（3区分），男女別人口及び労働力率（15歳以上）」
（全国 0003412175 / 都道府県 0003412176、1950〜2020）を配布用の1枚テーブルへ整形する。
**帳票の事実（軸の採否・労働力状態ツリー・保存則・不詳補完版の統一）は
docs/distributions/labor_force.md が正典**（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **全国表も実 area 軸(00000/全国/level1)を持つ**ため age5year のような全国合成すら不要＝差は area の
  コード集合だけ（全国=00000 の1件／県=47県）で **cleaner は両表で 1 個**。
- 労働力状態不詳は cat01 に独立コードが無いため **総数 − 労働力人口 − 非労働力人口** として導出注入する
  （age5year の年齢不詳と同じ人口保存の閉じ方・実装は _inject_labor_unknown）。

出力スキーマは age5year と同型の10列（age_class→labor_status）。列は clean_labor_force の select が正典。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import SEX, int_value

# 表章項目(tab): 320=15歳以上人口（採用）/ 1240=労働力率（率は count から導出可能ゆえ捨てる）。
_TAB_POPULATION = "320"


# cat01（労働力状態3区分_時系列）→ 名称。総数(100)＝労働力人口(110)+非労働力人口(140)+不詳、
# 労働力人口(110)＝就業者(120)+完全失業者(130)（120/130 は 110 の再掲）。コードは e-Stat のまま採る。
LABOR_STATUS = {
    "100": "総数",
    "110": "労働力人口",
    "120": "就業者",
    "130": "完全失業者",
    "140": "非労働力人口",
}
_LABOR_TOTAL = "100"  # 総数（不詳導出の被減数）
_LABOR_FORCE = "110"  # 労働力人口（不詳導出の減数その1）
_NON_LABOR = "140"  # 非労働力人口（不詳導出の減数その2）
_LABOR_UNKNOWN = ("999", "労働力状態不詳")  # 導出注入行（140 より後にソートされる）


def clean_labor_force(tidy: pl.DataFrame) -> pl.DataFrame:
    """労働力状態×男女別人口の tidy → 配布用10列へ写像する（全国/都道府県 共通）。

    手順: tab=320(人口。率1240は捨てる) で絞り、cat01→労働力状態・cat02→男女へ写像し
    （area は両表とも実軸をそのまま採る）、最後に労働力状態不詳を導出注入する。
    2015/2020 は「不詳補完値」版(time_code 末尾 000010)が併存するため通常版(000000)に統一する
    （age5year・population_by_age と同方針。補完版を混ぜると方法論の継ぎ目で二重計上になる）。
    """
    df = (
        tidy.filter(pl.col("tab_code") == _TAB_POPULATION)
        .filter(pl.col("cat01_code").is_in(list(LABOR_STATUS)))  # 労働力状態
        .filter(pl.col("cat02_code").is_in(list(SEX)))  # 男女
        .filter(pl.col("time_code").str.slice(4) == "000000")  # 不詳補完値版を除外
    )
    fact = df.select(
        pl.col("area_code"),
        pl.col("area_name"),
        pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
        pl.col("cat02_code").replace_strict({k: v[0] for k, v in SEX.items()}).alias("sex_code"),
        pl.col("cat02_code").replace_strict({k: v[1] for k, v in SEX.items()}).alias("sex"),
        pl.col("cat01_code").alias("labor_status_code"),
        pl.col("cat01_code").replace_strict(LABOR_STATUS).alias("labor_status"),
        # time_code 例: "2020000000" の先頭4桁が年
        pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
        int_value().alias("population"),
    ).with_columns(is_current_expr())
    return _inject_labor_unknown(fact)


def _inject_labor_unknown(fact: pl.DataFrame) -> pl.DataFrame:
    """労働力状態不詳行(999) = 総数(100) − 労働力人口(110) − 非労働力人口(140) を area×sex×year 毎に導出注入する。

    就業者(120)/完全失業者(130) は労働力人口(110)の再掲なので減算に含めない（含めると二重に引く）。
    """
    parts = (
        fact.filter(pl.col("labor_status_code").is_in([_LABOR_FORCE, _NON_LABOR]))
        .group_by("area_code", "sex_code", "year")
        .agg(pl.col("population").sum().alias("_part"))
    )
    unknown = (
        fact.filter(pl.col("labor_status_code") == _LABOR_TOTAL)
        .join(parts, on=["area_code", "sex_code", "year"], how="left")
        .with_columns(
            pl.lit(_LABOR_UNKNOWN[0]).alias("labor_status_code"),
            pl.lit(_LABOR_UNKNOWN[1]).alias("labor_status"),
            (pl.col("population") - pl.col("_part").fill_null(0)).alias("population"),
        )
        .select(fact.columns)
    )
    return pl.concat([fact, unknown]).sort("area_code", "sex_code", "labor_status_code")
