"""国勢調査 産業大分類×男女別就業者数 市区町村版（industry のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「産業（大分類）」表。同じ table_name "industry" に
同居する全国／都道府県の回次跨マクロ（単一 ID・industry.py）と対をなし、市区町村まで下りる。
着手＝2015（0003175084・唯一「男女×産業大分類×市区町村」の軽量2次元 marginal が揃う年）。

**帳票の事実は docs/sources/estat-census-catalog.md「産業（大分類）」節が正典**
（ここには再掲しない＝ドリフト防止）＝年別 statsDataId・軸割当/コード体系・分類区分数の断層・muni_levels。

Note（実装判断のみ）:
- **産業分類コードが年で違う**: 市区町村版（2015=cat05・0000/0010/0080…）はマクロの産業コード
  （100〜330＝industry.INDUSTRY の鍵）と別体系。
  年別マップでマクロコードへ写像して縫合する（family_type ミクロと同型。コードは getStatsData の実コードで確定する）。
- **分類は3体系**: 15区分(1995/2000) → 19区分A-S(2005) → 20区分A-T(2010-2020)。
  2015 は 20区分A-T でマクロ（現行20区分）と同ツリー＝写像は1:1。
  旧体系年（〜2005）は着手時に別マップ／別セグメント判断。
- **周辺のみ・不詳注入なし**: 「分類不能の産業(T)」が実カテゴリゆえ 総数==Σ大分類 が閉じる
  （industry マクロと同じ。lv2 中分類「うち農業」・再掲第1/2/3次・割合(%)行はマップ非収載＝自動除外）。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ10列（industry.py マクロと同一）。列は _finalize の select が正典。grain＝area×sex×industry×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.industry import INDUSTRY
from data_forge.sources.estat.transform import (
    SEX_MUNI,
    area_passthrough_cols,
    code_name_cols,
    exclude_imputed_version_expr,
    int_value_expr,
    year_from_time_code_expr,
)

# 表章項目(tab): "1"=15歳以上就業者数（2015 市区町村版は単一 tab）。
_TAB_WORKERS = "1"

# 産業分類_2015（cat05・大分類 lv1）→ マクロ industry.INDUSTRY の鍵（100〜330）。
# lv2 中分類（0020「うち農業」等）・再掲第1/2/3次(3570-3590)・割合(%)(3600〜)はマップ非収載＝自動除外。
_IND_2015 = {
    "0000": "100",  # 総数
    "0010": "120",  # A 農業，林業
    "0080": "130",  # B 漁業
    "0130": "150",  # C 鉱業，採石業，砂利採取業
    "0160": "160",  # D 建設業
    "0190": "170",  # E 製造業
    "1360": "190",  # F 電気・ガス・熱供給・水道業
    "1420": "200",  # G 情報通信業
    "1590": "210",  # H 運輸業，郵便業
    "1760": "220",  # I 卸売業，小売業
    "2250": "230",  # J 金融業，保険業
    "2320": "240",  # K 不動産業，物品賃貸業
    "2400": "250",  # L 学術研究，専門・技術サービス業
    "2610": "260",  # M 宿泊業，飲食サービス業
    "2720": "270",  # N 生活関連サービス業，娯楽業
    "2910": "280",  # O 教育，学習支援業
    "3020": "290",  # P 医療，福祉
    "3190": "300",  # Q 複合サービス事業
    "3240": "310",  # R サービス業（他に分類されないもの）
    "3480": "320",  # S 公務（他に分類されるものを除く）
    "3540": "330",  # T 分類不能の産業
}


def _finalize(df: pl.DataFrame, *, ind_col: str, ind_map: dict[str, str], sex_col: str) -> pl.DataFrame:
    """産業分類コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。"""
    return (
        df.filter(pl.col(ind_col).is_in(list(ind_map)))
        .filter(pl.col(sex_col).is_in(list(SEX_MUNI)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, SEX_MUNI, "sex"),
            pl.col(ind_col).replace_strict(ind_map).alias("industry_code"),
            pl.col(ind_col).replace_strict(ind_map).replace_strict(INDUSTRY).alias("industry"),
            year_from_time_code_expr(),
            int_value_expr().alias("workers"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "sex_code", "industry_code", "year")
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003175084）用。産業=cat05・男女=cat01・tab=1（就業者数のみ）・area=level4/6。"""
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS),
        ind_col="cat05_code",
        ind_map=_IND_2015,
        sex_col="cat01_code",
    )
