"""国勢調査 産業大分類×男女別就業者数 市区町村版（industry のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「産業（大分類）」表。同じ table_name "industry" に
同居する全国／都道府県の回次跨マクロ（単一 ID・industry.py）と対をなし、市区町村まで下りる。
着手＝2015（0003175084・唯一「男女×産業大分類×市区町村」の軽量2次元 marginal が揃う年）。
2020（0003450542）は軽量表が廃止されたため産業×職業クロスの職業総数スライスで marginal を復元する。
2010（0003052127）は産業×従業上の地位クロスの地位総数スライスで復元し、旧市町村 level7 を持つ。

**帳票の事実は docs/sources/estat-census-catalog.md「産業（大分類）」節が正典**
（ここには再掲しない＝ドリフト防止）＝年別 statsDataId・軸割当/コード体系・分類区分数の断層・muni_levels。

Note（実装判断のみ）:
- **産業分類コードが年で違う**: 市区町村版（2015=cat05・0000/0010/0080…）はマクロの産業コード
  （100〜330＝industry.INDUSTRY の鍵）と別体系。
  年別マップでマクロコードへ写像して縫合する（family_type ミクロと同型。コードは getStatsData の実コードで確定する）。
- **分類は3体系**: 15区分(1995/2000) → 19区分A-S(2005) → 20区分A-T(2010-2020)。
  2010/2015/2020 は 20区分A-T でマクロ（現行20区分）と同ツリー＝写像は1:1。ただし軸コードが年で違い、
  産業=2015 cat05（4桁 0000/0010）／2020 cat02（英字 A〜T）／2010 cat02（数字 000/001/007…）、
  男女=2015 SEX_MUNI（4桁）／2020 SEX_MUNI_2020（1桁）／2010 SEX_MUNI_2010（3桁 000系）で年別マップ。
  旧体系年（〜2005）は着手時に別マップ／別セグメント判断。
- **多次元クロスからの marginal 復元（2010/2020）**: 純カウントの「男女×産業×市区町村」軽量2次元表は
  2010/2020 に無く、多次元クロス表の総数スライスで産業marginalを復元する。
  2020＝産業×職業クロス（0003450542）の職業総数（cat03='0'）スライス（filters cdCat03='0'）。
  2010＝産業×従業上の地位クロス（0003052127・旧市町村 level7 あり）の地位総数（cat03='000'）スライス
  ＋DID 軸を全域(cat01='00710')で潰す（filters cdCat01='00710'・cdCat03='000'）。
  2020 表は産業総数スライスで occupation 2020 にも使える。
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
# 2010 表は全域(00710)／人口集中地区(00711) の DID 軸を持つ＝全域で潰す（households 2010 と同型）。
_DID_WHOLE_2010 = "00710"

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


# 産業分類_2020（cat02・大分類 lv1）→ マクロ industry.INDUSTRY の鍵（100〜330）。
# 2020 市区町村版は令和型で 2015（cat05・4桁）と別体系＝大分類が A〜T の英字直接。
# マクロコードの割当はアルファ順で _IND_2015 の value 列と 1:1（同じ 20区分 A-T ツリー）。
# 中間集計「うち農業」(01)・再掲第1/2/3次(R1/R2/R3)はマップ非収載＝自動除外。
_IND_2020 = {
    "0": "100",  # 総数
    "A": "120",  # 農業，林業
    "B": "130",  # 漁業
    "C": "150",  # 鉱業，採石業，砂利採取業
    "D": "160",  # 建設業
    "E": "170",  # 製造業
    "F": "190",  # 電気・ガス・熱供給・水道業
    "G": "200",  # 情報通信業
    "H": "210",  # 運輸業，郵便業
    "I": "220",  # 卸売業，小売業
    "J": "230",  # 金融業，保険業
    "K": "240",  # 不動産業，物品賃貸業
    "L": "250",  # 学術研究，専門・技術サービス業
    "M": "260",  # 宿泊業，飲食サービス業
    "N": "270",  # 生活関連サービス業，娯楽業
    "O": "280",  # 教育，学習支援業
    "P": "290",  # 医療，福祉
    "Q": "300",  # 複合サービス事業
    "R": "310",  # サービス業（他に分類されないもの）
    "S": "320",  # 公務（他に分類されるものを除く）
    "T": "330",  # 分類不能の産業
}


def _finalize(
    df: pl.DataFrame,
    *,
    ind_col: str,
    ind_map: dict[str, str],
    sex_col: str,
    sex_map: dict[str, tuple[str, str]] = SEX_MUNI,
) -> pl.DataFrame:
    """産業分類コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。

    男女コードは年で体系が違う（2015=4桁 SEX_MUNI／2020=1桁 SEX_MUNI_2020）ため sex_map で差し替える。
    """
    return (
        df.filter(pl.col(ind_col).is_in(list(ind_map)))
        .filter(pl.col(sex_col).is_in(list(sex_map)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, sex_map, "sex"),
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


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003450542・産業×職業クロス）用。職業総数(cat03='0')で絞り産業marginalを復元。

    純カウントの軽量2次元表が令和2年で廃止されたため、産業×職業クロスの職業総数スライスを採る。
    産業=cat02（令和型 A〜T）・男女=cat01（1桁 SEX_MUNI_2020）・tab=2020_05（就業者数）・area=level4/6。
    取得は filters cdCat03='0' で職業総数に絞り込む（source_params 側）。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS_2020).filter(pl.col("cat03_code") == "0"),
        ind_col="cat02_code",
        ind_map=_IND_2020,
        sex_col="cat01_code",
        sex_map=SEX_MUNI_2020,
    )


# 産業分類_2010（cat02・大分類 lv1）→ マクロ industry.INDUSTRY の鍵（100〜330）。
# 2010 は数字コード体系で 2015（4桁 cat05）・2020（英字 cat02）と別。A〜T の並びはマクロと同じ 20区分ツリー。
# 中間集計「うち農業」(002・lv2)・再掲第1/2/3次(400/401/402)はマップ非収載＝自動除外。
_IND_2010 = {
    "000": "100",  # 総数
    "001": "120",  # A 農業，林業
    "007": "130",  # B 漁業
    "012": "150",  # C 鉱業，採石業，砂利採取業
    "015": "160",  # D 建設業
    "018": "170",  # E 製造業
    "135": "190",  # F 電気・ガス・熱供給・水道業
    "141": "200",  # G 情報通信業
    "158": "210",  # H 運輸業，郵便業
    "175": "220",  # I 卸売業，小売業
    "224": "230",  # J 金融業，保険業
    "231": "240",  # K 不動産業，物品賃貸業
    "239": "250",  # L 学術研究，専門・技術サービス業
    "260": "260",  # M 宿泊業，飲食サービス業
    "271": "270",  # N 生活関連サービス業，娯楽業
    "290": "280",  # O 教育，学習支援業
    "301": "290",  # P 医療，福祉
    "318": "300",  # Q 複合サービス事業
    "323": "310",  # R サービス業（他に分類されないもの）
    "347": "320",  # S 公務（他に分類されるものを除く）
    "353": "330",  # T 分類不能の産業
}


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003052127・産業×従業上の地位）用。地位総数(cat03='000')で絞り産業marginalを復元。

    軽量2次元表が無く産業×従業上の地位クロスしか市区町村（＋旧市町村 level7）まで下りない。従業上の地位総数
    スライスを採る。産業=cat02（数字コード）・男女=cat04（3桁 SEX_MUNI_2010）・tab=340・DID 軸(cat01)は
    全域(00710)で潰す。旧市町村 level7 を含む＝合併畳込（aggregate_to_base）の材料。
    取得は filters cdCat01='00710'・cdCat03='000' で絞る（source_params 側）。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_WORKERS_2010)
        .filter(pl.col("cat01_code") == _DID_WHOLE_2010)
        .filter(pl.col("cat03_code") == "000"),
        ind_col="cat02_code",
        ind_map=_IND_2010,
        sex_col="cat04_code",
        sex_map=SEX_MUNI_2010,
    )
