"""aggregate_to_admin: アトム時系列を行政階層（都道府県 / 地方ブロック）へ上位集約する。

合併 rollup（[aggregate.py] の `aggregate_to_base`＝時間軸）とは**直交する空間軸**の集約。
市区町村は都道府県を跨がないため events 非依存で、`aggregate_to_base` の前後どちらに適用しても
結果は同じ（＝県内合計は合併を畳もうが不変。`reconcile.national_conservation` が保証する不変量）。

分類軸（sex / age / daynight）の自動判別は `aggregate._cat_code_cols` を共用する
（時間軸・空間軸で同じ「fact のスキーマから分類軸を読む」ユーティリティ）。
"""

import polars as pl

from data_forge.area.aggregate import _cat_code_cols

_PREFECTURE_LEVEL = 2  # 都道府県（全国=1 の直下）
_REGION_LEVEL = 0  # 地方ブロック（全国=1 と都道府県=2 の間の合成集約層）

# 都道府県コード（area_code 先頭2桁）→ 名称。conformed dimension の上位階層（正典）。
# 従来 dashboard 側に埋め込んでいた県名マスタをパイプへ昇格し、集約と一元化する。
_PREFECTURES: dict[str, str] = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県",
}  # fmt: skip

# 標準8地方区分（統計局の一般的な区分）: 三重(24)=近畿 / 沖縄(47)=九州 に含める。
_REGION_SPEC: list[tuple[str, str, tuple[str, ...]]] = [
    ("R1", "北海道地方", ("01",)),
    ("R2", "東北地方", ("02", "03", "04", "05", "06", "07")),
    ("R3", "関東地方", ("08", "09", "10", "11", "12", "13", "14")),
    ("R4", "中部地方", ("15", "16", "17", "18", "19", "20", "21", "22", "23")),
    ("R5", "近畿地方", ("24", "25", "26", "27", "28", "29", "30")),
    ("R6", "中国地方", ("31", "32", "33", "34", "35")),
    ("R7", "四国地方", ("36", "37", "38", "39")),
    ("R8", "九州地方", ("40", "41", "42", "43", "44", "45", "46", "47")),
]
# 都道府県コード → (region_code, region_name)。
_REGIONS: dict[str, tuple[str, str]] = {
    pref: (code, name) for code, name, prefs in _REGION_SPEC for pref in prefs
}


def aggregate_to_admin(atom_fact: pl.DataFrame, *, level: str) -> pl.DataFrame:
    """アトム時系列を行政階層（都道府県 / 地方ブロック）へ上位集約する（events 非依存）。

    各年アトムを area_code の県プレフィックスで group して合算するだけで県/地方合計になる。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（入力スキーマは fact 依存）。
        level     … "prefecture"（`area_code[:2]+"000"` の実 JIS コード・`area_level`=2）
                    / "region"（標準8地方区分 `R1`〜`R8`・`area_level`=0）。

    出力スキーマは入力 `atom_fact` の列構成をそのまま踏襲（fact 非依存＝population /
    population_by_age / daynight_population 共用）。分類軸（sex/age/daynight）は
    `_cat_code_cols` で自動判別して保持する。
    """
    cat_codes = _cat_code_cols(atom_fact)
    cat_labels = [c.removesuffix("_code") for c in cat_codes]
    pref2 = pl.col("area_code").str.slice(0, 2)

    if level == "prefecture":
        area_code = pl.concat_str([pref2, pl.lit("000")])
        area_name = pref2.replace_strict(_PREFECTURES)
        area_level = _PREFECTURE_LEVEL
    elif level == "region":
        area_code = pref2.replace_strict({k: v[0] for k, v in _REGIONS.items()})
        area_name = pref2.replace_strict({k: v[1] for k, v in _REGIONS.items()})
        area_level = _REGION_LEVEL
    else:
        raise ValueError(f"level は 'prefecture' か 'region'（受領: {level!r}）")

    level_dtype = atom_fact.schema["area_level"]
    return (
        atom_fact.with_columns(area_code.alias("area_code"), area_name.alias("area_name"))
        .group_by(["area_code", "year", *cat_codes])
        .agg(
            pl.col("population").sum().alias("population"),
            pl.col("area_name").first().alias("area_name"),
            *(pl.col(lbl).first().alias(lbl) for lbl in cat_labels),
        )
        .with_columns(
            pl.lit(area_level).cast(level_dtype).alias("area_level"),
            pl.lit(True).alias("is_current"),  # 都道府県/地方は現存（level7 消滅の概念なし）
        )
        .select(atom_fact.columns)
        .sort(["area_code", "year", *cat_codes])
    )
