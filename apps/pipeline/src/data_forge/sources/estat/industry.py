"""国勢調査 産業（大分類）×男女別就業者数 固有のクレンジング。

就業状態等基本集計の時系列データ製品「産業（大分類），男女別就業者数及び人口構成比［産業別］
（15歳以上就業者）」（全国 0003410395 / 都道府県 0003410398）を配布用の1枚テーブルへ整形する。
**帳票の事実（軸の採否・年カバレッジ非対称・保存則・不詳補完版の統一）は
docs/distributions/industry.md が正典**（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **cleaner 本体は共通・national フラグで分岐**（age5year と同型。全国表は area 軸なし→00000/全国/level1
  を合成／都道府県表は area=47都道府県(level2) をそのまま採る）。
- 「分類不能の産業」が実カテゴリで存在＝**不詳の導出注入は不要**（総数==Σ大分類 が閉じる。labor_force/
  age5year のように総数−Σ で不詳を作らない）。

出力スキーマは age5year と同型の10列（age_class→industry・population→workers）。
列は clean_industry の select が正典。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.transform import SEX, area_axis_cols, code_name_cols, int_value

# 表章項目(tab): 334=就業者数（採用）。構成比(2020_44)は count から導出可能ゆえ捨てる。
_TAB_WORKERS = "334"


# cat01（産業大分類2015）→ 名称。総数(100)＋大分類20区分(120〜330)。330=分類不能の産業（実カテゴリ）。
# （再掲）第1次/第2次/第3次は大分類から導出可能ゆえ載せない（→捨てる）。コードは e-Stat のまま採る。
INDUSTRY = {
    "100": "総数",
    "120": "Ａ農業，林業",
    "130": "Ｂ漁業",
    "150": "Ｃ鉱業，採石業，砂利採取業",
    "160": "Ｄ建設業",
    "170": "Ｅ製造業",
    "190": "Ｆ電気・ガス・熱供給・水道業",
    "200": "Ｇ情報通信業",
    "210": "Ｈ運輸業，郵便業",
    "220": "Ｉ卸売業，小売業",
    "230": "Ｊ金融業，保険業",
    "240": "Ｋ不動産業，物品賃貸業",
    "250": "Ｌ学術研究，専門・技術サービス業",
    "260": "Ｍ宿泊業，飲食サービス業",
    "270": "Ｎ生活関連サービス業，娯楽業",
    "280": "Ｏ教育，学習支援業",
    "290": "Ｐ医療，福祉",
    "300": "Ｑ複合サービス事業",
    "310": "Ｒサービス業（他に分類されないもの）",
    "320": "Ｓ公務（他に分類されるものを除く）",
    "330": "Ｔ分類不能の産業",
}


def clean_industry(tidy: pl.DataFrame, *, national: bool) -> pl.DataFrame:
    """産業大分類×男女別就業者数の tidy → 配布用10列へ写像する（全国/都道府県 共通）。

    引数:
        national … True で全国表(0003410395, area軸なし)＝00000/全国/level1 を合成。
                   False で都道府県表(0003410398)＝area軸(47県, level2)をそのまま採る。

    手順: tab=334(就業者数。構成比は捨てる) で絞り、cat01→産業大分類・cat02→男女へ写像する
    （再掲の第1/2/3次産業は INDUSTRY 非掲載＝除外）。2015/2020 は「不詳補完値」版(time_code
    末尾 000010)が併存するため通常版(000000)に統一する（age5year・labor_force と同方針）。
    分類不能(330)を含む大分類で「総数 == Σ大分類」が閉じるため不詳の導出注入は行わない。
    """
    df = (
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS)
        .filter(pl.col("cat01_code").is_in(list(INDUSTRY)))  # 産業大分類（再掲を除外）
        .filter(pl.col("cat02_code").is_in(list(SEX)))  # 男女
        .filter(pl.col("time_code").str.slice(4) == "000000")  # 不詳補完値版を除外
    )
    return df.select(
        *area_axis_cols(national),
        *code_name_cols("cat02_code", SEX, "sex"),
        pl.col("cat01_code").alias("industry_code"),
        pl.col("cat01_code").replace_strict(INDUSTRY).alias("industry"),
        # time_code 例: "2020000000" の先頭4桁が年
        pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year"),
        int_value().alias("workers"),
    ).with_columns(is_current_expr())


def clean_national(tidy: pl.DataFrame) -> pl.DataFrame:
    """全国表(0003410395)用 cleaner（area 軸なし → 全国行を合成、1995-2020）。"""
    return clean_industry(tidy, national=True)


def clean_prefecture(tidy: pl.DataFrame) -> pl.DataFrame:
    """都道府県表(0003410398)用 cleaner（area=47都道府県、2005-2020）。"""
    return clean_industry(tidy, national=False)
