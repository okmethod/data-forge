"""国勢調査 職業（大分類）×男女別就業者数 固有のクレンジング。

就業状態等基本集計の時系列データ製品「職業（大分類），
男女別就業者数及び人口構成比［職業別］（15歳以上就業者）」を配布用の1枚テーブルへ整形する。
産業（industry.py）と軸構造が完全同型で、本モジュールは
industry.py を職業向けに写したもの（設計思想は industry.py と共通）。
**帳票の事実（軸の採否・呼称/区分数/statsDataId＝occupation.md「分類体系の呼称（SSoT）」・年カバレッジ・保存則）は
docs/distributions/occupation.md が正典**（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **分類改訂で2セグメント併存**（major12/major10）。同符号でも中身が違い 10↔12 はコード写像できず union
  しない。2005 は両版にあるが総数不一致（再集計で境界ケース移動）で橋渡しできず別セグメント扱い。
- **cleaner 本体は共通**（age5year と同型。全国表は area 軸なし→00000/全国/level1 を合成／都道府県表は
  area=47都道府県(level2) をそのまま採る）で、`national` フラグと `classes`（採用大分類コード→名称）で分岐。
- 「分類不能の職業」が実カテゴリで存在＝**不詳の導出注入は不要**（総数==Σ大分類 が閉じる。major10 表の
  再掲210〜240 は `classes` 非収載＝自動除外）。

出力スキーマは industry と同型の10列（industry→occupation）。列は clean_occupation の select が正典。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import (
    SEX,
    area_axis_cols,
    code_name_cols,
    exclude_imputed_version_expr,
    int_value_expr,
    year_from_time_code_expr,
)

# 表章項目(tab): 334=就業者数（採用）。構成比(2020_45)は count から導出可能ゆえ捨てる。
_TAB_WORKERS = "334"


# cat01 職業大分類（major12。定義は docs occupation.md SSoT）→ 名称。総数(100)＋大分類(110〜220)。
# 220=分類不能の職業（実カテゴリ）。中間集計（再掲）は無くフラット。コードは e-Stat のまま採る。
OCCUPATION_MAJOR12 = {
    "100": "総数",
    "110": "Ａ管理的職業従事者",
    "120": "Ｂ専門的・技術的職業従事者",
    "130": "Ｃ事務従事者",
    "140": "Ｄ販売従事者",
    "150": "Ｅサービス職業従事者",
    "160": "Ｆ保安職業従事者",
    "170": "Ｇ農林漁業従事者",
    "180": "Ｈ生産工程従事者",
    "190": "Ｉ輸送・機械運転従事者",
    "200": "Ｊ建設・採掘従事者",
    "210": "Ｋ運搬・清掃・包装等従事者",
    "220": "Ｌ分類不能の職業",
}

# cat01 職業大分類（major10。定義は docs occupation.md SSoT）→ 名称。総数(100)＋大分類(110〜200)。
# 200=分類不能の職業（実カテゴリ）。
# 原表には（再掲）1〜4(210〜240)が併存するが、class map に載せない＝Σ大分類で二重計上しないよう自動除外する。
# 同符号でも major12 と中身が違う（A=専門技術等）。
OCCUPATION_MAJOR10 = {
    "100": "総数",
    "110": "Ａ専門的・技術的職業従事者",
    "120": "Ｂ管理的職業従事者",
    "130": "Ｃ事務従事者",
    "140": "Ｄ販売従事者",
    "150": "Ｅサービス職業従事者",
    "160": "Ｆ保安職業従事者",
    "170": "Ｇ農林漁業作業者",
    "180": "Ｈ運輸・通信従事者",
    "190": "Ｉ生産工程・労務作業者",
    "200": "Ｊ分類不能の職業",
}


def clean_occupation(tidy: pl.DataFrame, *, national: bool, classes: dict[str, str]) -> pl.DataFrame:
    """職業大分類×男女別就業者数の tidy → 配布用10列へ写像する（全国/都道府県・major12/10 共通）。

    引数:
        national … True で全国表(area軸なし)＝00000/全国/level1 を合成。
                   False で都道府県表＝area軸(47県, level2)をそのまま採る。
        classes  … 採用する職業大分類コード→名称（OCCUPATION_MAJOR12 or OCCUPATION_MAJOR10）。
                   ここに無いコード（major10 表の再掲210〜240 等）は filter で自動除外される。

    手順: tab=334(就業者数。構成比は捨てる) で絞り、cat01→職業大分類・cat02→男女へ写像する。
    2015/2020 は「不詳補完値」版(time_code 末尾 000010)が併存するため通常版(000000)に統一する
    （industry・age5year・labor_force と同方針。major10 表には不詳補完値版は無いが無害）。分類不能を含む
    大分類で「総数 == Σ大分類」が閉じるため不詳の導出注入は行わない（industry と同じ）。
    """
    df = (
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS)
        .filter(pl.col("cat01_code").is_in(list(classes)))  # 職業大分類（再掲は非収載＝除外）
        .filter(pl.col("cat02_code").is_in(list(SEX)))  # 男女
        .filter(exclude_imputed_version_expr())
    )
    return df.select(
        *area_axis_cols(national),
        *code_name_cols("cat02_code", SEX, "sex"),
        pl.col("cat01_code").alias("occupation_code"),
        pl.col("cat01_code").replace_strict(classes).alias("occupation"),
        # time_code 例: "2020000000" の先頭4桁が年
        year_from_time_code_expr(),
        int_value_expr().alias("workers"),
    ).with_columns(is_current_expr())


def clean_major12_national(tidy: pl.DataFrame) -> pl.DataFrame:
    """major12 全国表(0003410408)用 cleaner（area 軸なし → 全国行を合成、1995-2020）。"""
    return clean_occupation(tidy, national=True, classes=OCCUPATION_MAJOR12)


def clean_major12_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """major12 都道府県表(0003410411)用 cleaner（area=47都道府県、2005-2020）。"""
    return clean_occupation(tidy, national=False, classes=OCCUPATION_MAJOR12)


def clean_major10_national(tidy: pl.DataFrame) -> pl.DataFrame:
    """major10 全国表(0003410409)用 cleaner（area 軸なし → 全国合成、1950-2005）。"""
    return clean_occupation(tidy, national=True, classes=OCCUPATION_MAJOR10)


def clean_major10_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """major10 都道府県表(0003410412)用 cleaner（area=47都道府県、1980-2005）。"""
    return clean_occupation(tidy, national=False, classes=OCCUPATION_MAJOR10)
