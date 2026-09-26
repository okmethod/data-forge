"""国勢調査 職業大分類×男女別就業者数 市区町村版（occupation のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「職業（大分類）」表。産業（industry_municipality.py）と
軸構造が完全同型で、本モジュールはそれを職業向けに写したもの。
同じ table_name "occupation_major12" に同居する全国／都道府県の回次跨マクロ（単一 ID・occupation.py）と対をなす。
着手＝2015（0003176482・軽量2次元 marginal が揃う年）。

**帳票の事実は docs/sources/estat-census-catalog.md「職業（大分類）」節が正典**
（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **職業分類コードが年で違う**: 市区町村版（2015=cat01・0000/0010/0100…）はマクロの職業コード
  （100〜220＝occupation.OCCUPATION_MAJOR12 の鍵）と別体系。年別マップでマクロコードへ写像して縫合する。
- **分類は2体系**: 10区分A-J(1995-2005＝major10) → 12区分(2010-2020＝major12)。
  2015 は major12 でマクロ major12 と同ツリー＝写像は1:1（→ table_name も "occupation_major12"）。
  major10 年は別 family。
- **周辺のみ・不詳注入なし**: 「分類不能の職業(L)」が実カテゴリゆえ 総数==Σ大分類 が閉じる
  （割合(%)行(3020〜)はマップ非収載＝自動除外）。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ10列（occupation.py マクロと同一）。列は _finalize の select が正典。
grain＝area×sex×occupation×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.occupation import OCCUPATION_MAJOR12
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

# 職業分類_2015（cat01・大分類 lv1）→ マクロ occupation.OCCUPATION_MAJOR12 の鍵（100〜220）。
# 割合(%)行(3020〜3130)はマップ非収載＝自動除外。
_OCC_2015 = {
    "0000": "100",  # 総数
    "0010": "110",  # A 管理的職業従事者
    "0100": "120",  # B 専門的・技術的職業従事者
    "0860": "130",  # C 事務従事者
    "1100": "140",  # D 販売従事者
    "1280": "150",  # E サービス職業従事者
    "1640": "160",  # F 保安職業従事者
    "1720": "170",  # G 農林漁業従事者
    "1880": "180",  # H 生産工程従事者
    "2420": "190",  # I 輸送・機械運転従事者
    "2610": "200",  # J 建設・採掘従事者
    "2820": "210",  # K 運搬・清掃・包装等従事者
    "2990": "220",  # L 分類不能の職業
}


def _finalize(df: pl.DataFrame, *, occ_col: str, occ_map: dict[str, str], sex_col: str) -> pl.DataFrame:
    """職業分類コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。"""
    return (
        df.filter(pl.col(occ_col).is_in(list(occ_map)))
        .filter(pl.col(sex_col).is_in(list(SEX_MUNI)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, SEX_MUNI, "sex"),
            pl.col(occ_col).replace_strict(occ_map).alias("occupation_code"),
            pl.col(occ_col).replace_strict(occ_map).replace_strict(OCCUPATION_MAJOR12).alias("occupation"),
            year_from_time_code_expr(),
            int_value_expr().alias("workers"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "sex_code", "occupation_code", "year")
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003176482）用。職業=cat01・男女=cat02・tab=1（就業者数のみ）・area=level4/6。"""
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS),
        occ_col="cat01_code",
        occ_map=_OCC_2015,
        sex_col="cat02_code",
    )
