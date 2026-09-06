"""国勢調査 年齢（5歳階級）×男女別人口 固有のクレンジング。

時系列データ製品「年齢（5歳階級），男女別人口及び人口性比」（全国 0003410380 / 都道府県 0003410381、
1920〜2020）を配布用の1枚テーブルへ整形する。単一 ID で一世紀を持つ（連番 ID でない）ため cleaner は
全年 1 個・area は全国のみ／47都道府県固定＝合併なし＝**area master 不要の低コスト fact**。
**帳票の事実（軸の採否・85+細分/再掲コード・年カバレッジ・保存則）は
docs/distributions/age5year.md が正典**（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **全国/都道府県で cleaner を分ける**（clean_national は area 軸なし→00000/全国/level1 を合成／
  clean_prefecture は area=47都道府県(level2) をそのまま採る）。
- 全国表の 85+ 細分(320-370)は共通終端「85歳以上」(310)へ**畳む**。
  全国表は 2005 以降 310 を持たず 320-370 のみで 85+ を提供する回がある
  ＝畳まないと 85+ が5歳階級合計から抜け、導出注入する年齢不詳へ誤流入して不詳が二重に膨らむ。
  県表は 310 を直接持ち 320-370 を持たない＝畳み対象なし。
- 年齢不詳は cat02 に独立コードが無いため **総数 − 5歳階級合計** として導出注入する
  （population_by_age と同じ人口保存の閉じ方・実装は _inject_age_unknown）。

出力スキーマは population_by_age と同型の10列。
列は clean_age5 の select が正典。
"""

import polars as pl

# area @level=7 は「旧市区町村（合併消滅）」。本表には出現しないが規約統一のため保持する。
_OBSOLETE_AREA_LEVEL = 7

# cat01（男女_時系列）→ (sex_code, sex名称)。コード体系は population.SEX_2005 と同じ 100/110/120。
SEX = {"100": ("0", "総数"), "110": ("1", "男"), "120": ("2", "女")}

# cat02（年齢5歳階級_時系列）で全国・都道府県 両表に共通存在するコードのみ採用。
# 85歳以上(310)を終端とし、全国のみの細分(320-370)と（再掲）15歳未満/15-64/65+(380-400)は捨てる。
# age_class_code は e-Stat の cat02 コードをそのまま採る（3桁ゼロ埋め＝辞書順＝年齢昇順・出所が追える）。
AGE5 = {
    "100": "総数",
    "110": "0〜4歳",
    "120": "5〜9歳",
    "130": "10〜14歳",
    "150": "15〜19歳",
    "160": "20〜24歳",
    "170": "25〜29歳",
    "180": "30〜34歳",
    "190": "35〜39歳",
    "200": "40〜44歳",
    "210": "45〜49歳",
    "220": "50〜54歳",
    "230": "55〜59歳",
    "240": "60〜64歳",
    "250": "65〜69歳",
    "260": "70〜74歳",
    "280": "75〜79歳",
    "290": "80〜84歳",
    "310": "85歳以上",
}
_AGE_TOTAL = "100"  # 総数（不詳導出の被減数）
_AGE_UNKNOWN = ("999", "年齢不詳")  # 導出注入行（310 より後にソートされる）
# 全国表のみ 85歳以上を細分する回（2005-2020）のコード（85〜89…110歳以上）。共通粒度 85歳以上(310)へ畳む。
_AGE5_85PLUS_PARTS = ("320", "330", "340", "350", "360", "370")


def clean_age5(tidy: pl.DataFrame, *, national: bool) -> pl.DataFrame:
    """5歳階級×男女別人口の tidy → 配布用10列へ写像する（全国/都道府県 共通）。

    引数:
        national … True で全国表(380, area軸なし)＝00000/全国/level1 を合成。
                   False で都道府県表(381)＝area軸(47県, level2)をそのまま採る。

    手順: tab=020(人口。割合024/性比1120は捨てる) で絞り、cat01→男女・cat02→年齢5歳階級へ
    写像し（85歳以上までの共通粒度・細分/再掲は除外）、最後に年齢不詳を導出注入する。
    """
    df = (
        tidy.filter(pl.col("tab_code") == "020")
        .filter(pl.col("cat01_code").is_in(list(SEX)))  # 男女
        # 5歳階級＋総数＋（全国表の）85+細分を採る。再掲(380-400)は含めない。
        .filter(pl.col("cat02_code").is_in([*AGE5, *_AGE5_85PLUS_PARTS]))
        # 2015/2020 は「不詳補完値」版(time_code 末尾 000010)が併存する。population_by_age と
        # 同方針で通常版(000000)に統一する（補完版を混ぜると方法論の継ぎ目が生じ二重計上になる）。
        .filter(pl.col("time_code").str.slice(4) == "000000")
        # 85+細分(320-370)を共通粒度の 85歳以上(310)へ畳む（畳んだ後 AGE5 の名称写像が通る）。
        .with_columns(
            pl.when(pl.col("cat02_code").is_in(_AGE5_85PLUS_PARTS))
            .then(pl.lit("310"))
            .otherwise(pl.col("cat02_code"))
            .alias("cat02_code")
        )
    )
    if national:
        area_cols = [
            pl.lit("00000").alias("area_code"),
            pl.lit("全国").alias("area_name"),
            pl.lit(1).cast(pl.Int8).alias("area_level"),
        ]
    else:
        area_cols = [
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
        ]
    fact = (
        df.select(
            *area_cols,
            pl.col("cat01_code").replace_strict({k: v[0] for k, v in SEX.items()}).alias("sex_code"),
            pl.col("cat01_code").replace_strict({k: v[1] for k, v in SEX.items()}).alias("sex"),
            pl.col("cat02_code").alias("age_class_code"),
            pl.col("cat02_code").replace_strict(AGE5).alias("age_class"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            # value は文字列。数字以外（"-" 等の欠損記号）は null に落とす
            pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False).alias("population"),
        )
        # 310 へ畳んだ 85+細分を1行へ合算する（全 null の単一セルは null を保つ＝0 に化けさせない）。
        .group_by(
            ["area_code", "area_name", "area_level", "sex_code", "sex", "age_class_code", "age_class", "year"],
            maintain_order=True,
        )
        .agg(
            pl.when(pl.col("population").is_null().all())
            .then(None)
            .otherwise(pl.col("population").sum())
            .alias("population")
        )
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
    )
    return _inject_age_unknown(fact)


def clean_national(tidy: pl.DataFrame) -> pl.DataFrame:
    """全国表(0003410380)用 cleaner（area 軸なし → 全国行を合成）。"""
    return clean_age5(tidy, national=True)


def clean_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """都道府県表(0003410381)用 cleaner（area=47都道府県）。"""
    return clean_age5(tidy, national=False)


def _inject_age_unknown(fact: pl.DataFrame) -> pl.DataFrame:
    """年齢不詳行（age_class_code=999）= 総数 − Σ(5歳階級) を area×sex×year 毎に導出注入する。"""
    bracket_codes = [c for c in AGE5 if c != _AGE_TOTAL]  # 110〜310（総数を除く各5歳階級）
    parts = (
        fact.filter(pl.col("age_class_code").is_in(bracket_codes))
        .group_by("area_code", "sex_code", "year")
        .agg(pl.col("population").sum().alias("_part"))
    )
    unknown = (
        fact.filter(pl.col("age_class_code") == _AGE_TOTAL)
        .join(parts, on=["area_code", "sex_code", "year"], how="left")
        .with_columns(
            pl.lit(_AGE_UNKNOWN[0]).alias("age_class_code"),
            pl.lit(_AGE_UNKNOWN[1]).alias("age_class"),
            (pl.col("population") - pl.col("_part").fill_null(0)).alias("population"),
        )
        .select(fact.columns)
    )
    return pl.concat([fact, unknown]).sort("area_code", "sex_code", "age_class_code")
