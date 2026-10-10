"""国勢調査 職業大分類×男女別就業者数 市区町村版（occupation のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「職業（大分類）」表。産業（industry_municipality.py）と
軸構造が完全同型で、本モジュールはそれを職業向けに写したもの。
同じ table_name "occupation_major12" に同居する全国／都道府県の回次跨マクロ（単一 ID・occupation.py）と対をなす。
着手＝2015（0003176482・軽量2次元 marginal が揃う年）。2020/2010 は多次元クロス表の総数スライスで
職業marginalを復元する（2020=産業×職業クロス・2010=産業×職業×従業上の地位クロス）。
2005 は職業新分類の軽量2次元 marginal（0003024287）で、新分類＝12区分＝major12 と同ツリー。

**帳票の事実は docs/sources/estat-census-catalog.md「職業（大分類）」節が正典**
（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **職業分類コードが年で違う**: 市区町村版（2015=cat01・0000/0010/0100…）はマクロの職業コード
  （100〜220＝occupation.OCCUPATION_MAJOR12 の鍵）と別体系。年別マップでマクロコードへ写像して縫合する。
- **分類は2体系**: 旧10区分A-J（major10・参考表 0003410412 のみ＝市区町村版なし）と 12区分（major12）。
  市区町村版は 2005（新分類）/2010/2015/2020 とも 12区分でマクロ major12 と同ツリー＝写像は1:1
  （→ table_name も "occupation_major12"）。
- **多次元クロスからの marginal 復元（2020/2010）**: 純カウントの「男女×職業×市区町村」軽量2次元表は
  2020/2010 に無く、多次元クロス表の総数スライスで職業marginalを復元する（industry 市区町村と同手法）。
  2020＝産業×職業クロス（0003450542＝industry 2020 と同一表）の産業総数（cat02='0'）スライス
  （filters cdCat02='0'）。2010＝産業×職業×従業上の地位クロス（0003067223）の産業総数（cat04='000'）
  ×従業上の地位総数（cat02='000'）スライス（filters cdCat04='000'・cdCat02='000'）。
- **軸コードが年で違う**: 職業=2015 cat01（4桁 0000/0010）／2020 cat03（英字 A〜L）／2010 cat03（数字飛び 001/010…）、
  男女=2015 cat02 SEX_MUNI（4桁）／2020 cat01 SEX_MUNI_2020（1桁）／2010 cat01 SEX_MUNI_2010（3桁）で年別マップ。
- **周辺のみ・不詳注入なし**: 「分類不能の職業(L)」が実カテゴリゆえ 総数==Σ大分類 が閉じる
  （割合(%)行(3020〜)・再掲・中間集計はマップ非収載＝自動除外）。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ10列（occupation.py マクロと同一）。列は _finalize の select が正典。
grain＝area×sex×occupation×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.occupation import OCCUPATION_MAJOR12
from data_forge.sources.estat.transform import (
    SEX_MUNI,
    SEX_MUNI_2010,
    SEX_MUNI_2020,
    area_passthrough_cols,
    code_name_cols,
    exclude_imputed_version_expr,
    int_value_expr,
    year_from_time_code_expr,
)

# 表章項目(tab): "1"=15歳以上就業者数（2015 市区町村版は単一 tab）。2020="2020_05"・2010="340"（就業者数）。
_TAB_WORKERS = "1"
_TAB_WORKERS_2020 = "2020_05"
_TAB_WORKERS_2010 = "340"

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


def _finalize(
    df: pl.DataFrame,
    *,
    occ_col: str,
    occ_map: dict[str, str],
    sex_col: str,
    sex_map: dict[str, tuple[str, str]] = SEX_MUNI,
) -> pl.DataFrame:
    """職業分類コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。

    男女コードは年で体系が違う（2015=4桁 SEX_MUNI／2020=1桁 SEX_MUNI_2020／2010=3桁 SEX_MUNI_2010）ため
    sex_map で差し替える。
    """
    return (
        df.filter(pl.col(occ_col).is_in(list(occ_map)))
        .filter(pl.col(sex_col).is_in(list(sex_map)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, sex_map, "sex"),
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


# 職業分類_2020（cat03・大分類 lv1）→ マクロ occupation.OCCUPATION_MAJOR12 の鍵（100〜220）。
# 2020 市区町村版は令和型で 2015（cat01・4桁）と別体系＝大分類が A〜L の英字直接（産業×職業クロス 0003450542）。
# 中間集計・再掲行はこの軸には無くフラット。マクロ major12 ツリーと 1:1（A管理的=110…L分類不能=220）。
_OCC_2020 = {
    "0": "100",  # 総数
    "A": "110",  # A 管理的職業従事者
    "B": "120",  # B 専門的・技術的職業従事者
    "C": "130",  # C 事務従事者
    "D": "140",  # D 販売従事者
    "E": "150",  # E サービス職業従事者
    "F": "160",  # F 保安職業従事者
    "G": "170",  # G 農林漁業従事者
    "H": "180",  # H 生産工程従事者
    "I": "190",  # I 輸送・機械運転従事者
    "J": "200",  # J 建設・採掘従事者
    "K": "210",  # K 運搬・清掃・包装等従事者
    "L": "220",  # L 分類不能の職業
}


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003450542・産業×職業クロス）用。産業総数(cat02='0')で絞り職業marginalを復元。

    industry 2020 と同一表で、こちらは産業総数スライスを採る（industry は職業総数スライス）。
    職業=cat03（令和型 A〜L）・男女=cat01（1桁 SEX_MUNI_2020）・tab=2020_05（就業者数）・area=level4/6。
    取得は filters cdCat02='0' で産業総数に絞り込む（source_params 側）。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS_2020).filter(pl.col("cat02_code") == "0"),
        occ_col="cat03_code",
        occ_map=_OCC_2020,
        sex_col="cat01_code",
        sex_map=SEX_MUNI_2020,
    )


# 職業分類_2010（cat03・大分類 lv1）→ マクロ occupation.OCCUPATION_MAJOR12 の鍵（100〜220）。
# 2010 は数字コード体系（産業×職業×従業上の地位クロス 0003067223）で 2015（4桁）・2020（英字）と別。
# A〜L の並びはマクロ major12 と同じツリー。中間集計・再掲はこの軸には無い。
_OCC_2010 = {
    "000": "100",  # 総数
    "001": "110",  # A 管理的職業従事者
    "010": "120",  # B 専門的・技術的職業従事者
    "086": "130",  # C 事務従事者
    "110": "140",  # D 販売従事者
    "128": "150",  # E サービス職業従事者
    "164": "160",  # F 保安職業従事者
    "172": "170",  # G 農林漁業従事者
    "188": "180",  # H 生産工程従事者
    "242": "190",  # I 輸送・機械運転従事者
    "261": "200",  # J 建設・採掘従事者
    "282": "210",  # K 運搬・清掃・包装等従事者
    "299": "220",  # L 分類不能の職業
}


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003067223・産業×職業×従業上の地位）用。産業総数×地位総数で絞り職業marginalを復元。

    軽量2次元表が無く、産業×職業×従業上の地位クロスから産業総数（cat04='000'）×従業上の地位総数
    （cat02='000'）スライスを採る。職業=cat03（数字コード）・男女=cat01（3桁 SEX_MUNI_2010）・tab=340。
    取得は filters cdCat04='000'・cdCat02='000' で絞る（source_params 側）。旧市町村 level7 は持たず
    level4/6（＋政令市区 level5・支庁 level3）で leaf={4,6} に収まる。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS_2010)
        .filter(pl.col("cat04_code") == "000")
        .filter(pl.col("cat02_code") == "000"),
        occ_col="cat03_code",
        occ_map=_OCC_2010,
        sex_col="cat01_code",
        sex_map=SEX_MUNI_2010,
    )


def clean_2005(tidy: pl.DataFrame) -> pl.DataFrame:
    """2005（0003024287・職業新分類×男女別就業者数 市区町村）用。軽量2次元 marginal（2015 同型）。

    「職業（新分類）」は 12区分 A〜L で 2010 と同一コード体系（001=A管理的…299=L分類不能）＝マクロ major12
    と同ツリー（カタログの「1995-2005=major10」は旧大分類の参考表 0003410412 の話で、市区町村版 2005 は
    新分類＝major12）。職業=cat02（_OCC_2010 と同一マップ）・男女=cat01（3桁 SEX_MUNI_2010）・tab=1。
    旧市町村 level7 は持たず、平成大合併前ゆえ level6（町村）が多いが leaf={4,6} に収まる。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS),
        occ_col="cat02_code",
        occ_map=_OCC_2010,
        sex_col="cat01_code",
        sex_map=SEX_MUNI_2010,
    )
