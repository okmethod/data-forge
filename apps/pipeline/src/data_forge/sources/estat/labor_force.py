"""国勢調査 労働力状態（3区分）×男女別人口 固有のクレンジング。

就業状態等基本集計の時系列データ製品「労働力状態（3区分），男女別人口及び労働力率（15歳以上）」
（全国 0003412175 / 都道府県 0003412176、昭和25年〜令和2年＝1950〜2020）を配布用の1枚テーブルへ
整形する。回次跨（cross-census 編纂）で year 軸を1帳票内に持ち（単一 ID で全年）、area は全国(level1)／
47都道府県(level2)固定＝合併なし＝**area master 不要の低コスト fact**。人口等基本集計とは別の親
（就業状態等基本集計）に属す点が population 族と異なる（sources/estat-census-catalog.md（就業状態等基本集計節） 参照）。

2表は軸構造が完全同型（tab=320人口/1240率・cat01=労働力状態5コード・cat02=男女100/110/120・
time=1950〜2020）で、**全国表も実 area 軸(00000/全国/level1)を持つ**ため age5 のような全国合成すら不要。
差は area のコード集合だけ（全国表=00000 の1件／都道府県表=47県）なので **cleaner は両表で 1 個**。

tab は 320(15歳以上人口)のみ採り、1240(労働力率)は捨てる。労働力率 = 労働力人口 / (労働力人口 +
非労働力人口) で count から導出可能だから（households の「1世帯当たり人員」不採用と同思想）。

労働力状態(cat01)は入れ子構造:
    総数(100) = 労働力人口(110) + 非労働力人口(140) + 労働力状態不詳
    労働力人口(110) = 就業者(120) + 完全失業者(130)   （120/130 は 110 の再掲）
不詳は cat01 に独立コードが無いため、各回で **総数 − 労働力人口 − 非労働力人口** として導出注入する
（近年は無視できず 2020 全国は約1,170万人）。これにより「労働力人口 + 非労働力人口 + 不詳 == 総数」が
全地域・全年で恒等成立する（age5 の年齢不詳と同じ人口保存の閉じ方）。

出力スキーマ（age5 と同型の10列。age_class を labor_status に差し替えただけ）:
    area_code(str) / area_name(str) / area_level(int) /
    sex_code(str) / sex(str) / labor_status_code(str) / labor_status(str) /
    year(int) / population(Int64) / is_current(bool)
"""

import polars as pl

# area @level=7 は「旧市区町村（合併消滅）」。本表には出現しないが規約統一のため保持する。
_OBSOLETE_AREA_LEVEL = 7

# 表章項目(tab): 320=15歳以上人口（採用）/ 1240=労働力率（率は count から導出可能ゆえ捨てる）。
_TAB_POPULATION = "320"

# cat02（男女_時系列）→ (sex_code, sex名称)。コード体系は age5.SEX と同じ 100/110/120。
SEX = {"100": ("0", "総数"), "110": ("1", "男"), "120": ("2", "女")}

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
    （age5・population_by_age と同方針。補完版を混ぜると方法論の継ぎ目で二重計上になる）。
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
        # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
        pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False).alias("population"),
    ).with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
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
