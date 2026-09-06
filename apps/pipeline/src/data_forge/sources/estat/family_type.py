"""国勢調査 世帯の家族類型（16区分）別 一般世帯数・世帯人員 固有のクレンジング。

時系列データ製品「世帯の家族類型（16区分）別一般世帯数及び世帯人員 － 全国，都道府県」
（0003414255、新分類区分・1995〜2020）を配布用の1枚テーブルへ整形する。households.py の世帯種類版
（0003410420）と**同型の single-ID fact**（全国＋47都道府県が単一 ID に同居・合併なし＝area master 不要）。
households との差は tab コード（6/7 ⇔ 040/050）と分類軸（3フラット→20コードの4階層ツリー）の2点。
**帳票の事実（分類ツリー・家族類型不詳(999)の導出注入）は
docs/distributions/family_type.md「家族類型ツリー…導出注入」節が正典**（ここには再掲しない＝ドリフト防止）。

軸構造:
    tab   … 6=一般世帯数 / 7=一般世帯人員 / 1390=1世帯当たり人員 / 1930=世帯数割合
    cat01（世帯の家族類型16区分A_時系列）… 20コードのツリー（下記 FAMILY_TYPE）。
            @level 1〜4 を family_type_level に保持し、下流が粒度を選べるようにする。
    area  … 00000=全国(level1) ＋ 47都道府県(level2)。旧市区町村(level7)も DID も持たない。
    time  … 1995〜2020（6時点）

Note（実装判断のみ）:
- 単一 ID に全国＋都道府県が同居＝**射影不要・cleaner 1 個**で、scope 引数で全国/県を排他分離する。
- 2測定量（一般世帯数・一般世帯人員）を1行へ横並び。1世帯当たり人員(1390)・世帯数割合(1930)は導出可能ゆえ不採用。
- 家族類型不詳(999)を **総数−親族のみ−非親族−単独** で導出注入（labor_force と同型・実装は _inject_unknown）。

出力スキーマは households の8列＋family_type_level の9列。列は clean_family_type の select が正典。
"""

import polars as pl

from data_forge.sources.estat.transform import int_value, scope_area

# area @level=7 は「旧市区町村（合併消滅）」。本表には出現しないが規約統一のため保持する。
_OBSOLETE_AREA_LEVEL = 7

# cat01（世帯の家族類型16区分A_時系列）→ 名称。20コードのツリー（@level は cat01_level から採る）。
FAMILY_TYPE = {
    "100": "総数",
    "110": "親族のみの世帯",
    "120": "核家族世帯",
    "130": "夫婦のみの世帯",
    "140": "夫婦と子供から成る世帯",
    "150": "男親と子供から成る世帯",
    "160": "女親と子供から成る世帯",
    "170": "核家族以外の世帯",
    "180": "夫婦と両親から成る世帯",
    "190": "夫婦とひとり親から成る世帯",
    "200": "夫婦，子供と両親から成る世帯",
    "210": "夫婦，子供とひとり親から成る世帯",
    "220": "夫婦と他の親族（親，子供を含まない）から成る世帯",
    "230": "夫婦，子供と他の親族（親を含まない）から成る世帯",
    "240": "夫婦，親と他の親族（子供を含まない）から成る世帯",
    "250": "夫婦，子供，親と他の親族から成る世帯",
    "260": "兄弟姉妹のみから成る世帯",
    "270": "他に分類されない親族のみの世帯",
    "280": "非親族を含む世帯",
    "290": "単独世帯",
}

# 総数(100)の level-2 直下区分。不詳導出の減数（120/170 は 110 の内訳＝再掲ゆえ含めない）。
_FT_TOTAL = "100"  # 総数（不詳導出の被減数）
_FT_LEVEL2_PARTS = ["110", "280", "290"]  # 親族のみ／非親族／単独（level-2 の直下区分）
_FT_UNKNOWN = ("999", "家族類型不詳")  # 導出注入行（290 より後にソートされる）
_FT_UNKNOWN_LEVEL = 2

# tab（表章項目）。1世帯当たり人員(1390)・世帯数割合(1930)は households/members から導出可能ゆえ採らない。
_TAB_HOUSEHOLDS = "6"  # 一般世帯数（単位: 世帯）
_TAB_MEMBERS = "7"  # 一般世帯人員（単位: 人）


def clean_family_type(tidy: pl.DataFrame, *, scope: str = "all") -> pl.DataFrame:
    """世帯の家族類型別 世帯数・世帯人員の tidy → 配布用9列へ写像する。

    家族類型（cat01）を分類軸に採り、一般世帯数(tab=6)と一般世帯人員(tab=7)を
    area×family_type×year の同一行へ横並びに束ねる。ツリーの階層は family_type_level に保持し、
    最後に家族類型不詳(999)を導出注入する。
    scope で配布時の地理粒度を排他選択する: national=全国 / prefecture=47都道府県 / all=両方。
    """
    base = tidy.filter(pl.col("cat01_code").is_in(list(FAMILY_TYPE)))
    keys = ["area_code", "area_name", "area_level", "cat01_code", "cat01_level", "time_code"]
    households = base.filter(pl.col("tab_code") == _TAB_HOUSEHOLDS).select(*keys, int_value().alias("households"))
    members = base.filter(pl.col("tab_code") == _TAB_MEMBERS).select(*keys, int_value().alias("household_members"))
    fact = (
        households.join(members, on=keys, how="left")
        .select(
            pl.col("area_code"),
            pl.col("area_name"),
            pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
            pl.col("cat01_code").alias("family_type_code"),
            pl.col("cat01_code").replace_strict(FAMILY_TYPE).alias("family_type"),
            pl.col("cat01_level").cast(pl.Int8, strict=False).alias("family_type_level"),
            # time_code 例: "2020000000" の先頭4桁が年
            pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
            pl.col("households"),
            pl.col("household_members"),
        )
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
    )
    result = _inject_unknown(fact).sort("area_code", "family_type_code", "year")
    return scope_area(result, scope)


def _inject_unknown(fact: pl.DataFrame) -> pl.DataFrame:
    """家族類型不詳行(999) = 総数(100) − 親族のみ(110) − 非親族(280) − 単独(290) を area×year 毎に導出注入する。

    120/170（核家族/核家族以外）は 110 の内訳＝再掲なので減算に含めない（含めると二重に引く）。
    両測定量（households / household_members）とも同式で残差を求める。
    """
    parts = (
        fact.filter(pl.col("family_type_code").is_in(_FT_LEVEL2_PARTS))
        .group_by("area_code", "year")
        .agg(
            pl.col("households").sum().alias("_hh_part"),
            pl.col("household_members").sum().alias("_mem_part"),
        )
    )
    unknown = (
        fact.filter(pl.col("family_type_code") == _FT_TOTAL)
        .join(parts, on=["area_code", "year"], how="left")
        .with_columns(
            pl.lit(_FT_UNKNOWN[0]).alias("family_type_code"),
            pl.lit(_FT_UNKNOWN[1]).alias("family_type"),
            pl.lit(_FT_UNKNOWN_LEVEL).cast(pl.Int8).alias("family_type_level"),
            (pl.col("households") - pl.col("_hh_part").fill_null(0)).alias("households"),
            (pl.col("household_members") - pl.col("_mem_part").fill_null(0)).alias("household_members"),
        )
        .select(fact.columns)
    )
    return pl.concat([fact, unknown])
