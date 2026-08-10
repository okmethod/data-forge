"""crosswalk / aggregate_to_base: 各年アトム × rollup(base_year) の2ビュー。

Design A（実データで人口保存を実証済み）:
    1. fact = 各年のアトム（現行境界の最finest分割。atoms.extract_atoms）。
    2. rollup = 施行年 ≤ base_year の合併イベントで code→base_code（mapping.rollup）。

この rollup を「畳んで確定するか／畳まず後継コードを付けるだけか」で2ビューに分ける:
    attach_crosswalk:
        各アトムを畳まず、後継コード列 base_code（＋ base_name）を同梱して返す。
        利用者が `GROUP BY base_code` すれば前方 rollup 相当、area_code のままなら原境界。
        畳む/畳まないを配布時に固定しない。
    aggregate_to_base:
        crosswalk を base_code で実際に合算した確定ビュー。
        （= attach_crosswalk + GROUP BY base_code）
        name/level は base_year 時点のアトム値で統一する。

各年のアトムは国土を過不足なく1回覆い、rollup は各アトム→単一 base_code の関数なので、二重計上は起きない。
イベント未整備で消滅アトムが自分自身に留まる場合は「幽霊 base ユニット」として残る。
（reconcile が検出＝クッション候補）
base_year は集約パラメータに外出しするので、2025 投入後も過去の基準年ビューを据え置ける。
combine と相互非依存で、cli.py が clean→atoms→combine→(crosswalk|aggregate) と配線する。
"""

import polars as pl

from data_forge.area.mapping import rollup

_OBSOLETE_AREA_LEVEL = 7  # 旧市区町村（現存でない）
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


def _cat_code_cols(df: pl.DataFrame) -> list[str]:
    """分類軸のコード列（area_code / base_code 以外の `*_code`）を返す。

    例: population → `["sex_code"]` ／ population_by_age → `["sex_code", "age_class_code"]`。
    集約の group キー・ソートキーはこの軸で構成し、名称列（`sex` / `age_class`）は畳み込み時に
    `.first()` で運ぶ（各群内で一定）。出力スキーマは固定表を持たず入力 `atom_fact` の列構成を
    そのまま踏襲するので、population(8列) と population_by_age(10列) を同じコードで畳める。
    """
    return [c for c in df.columns if c.endswith("_code") and c not in ("area_code", "base_code")]


def _base_year(atom_fact: pl.DataFrame, base_year: int | None) -> int:
    return base_year if base_year is not None else max(atom_fact.get_column("year").to_list())


def attach_crosswalk(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
    """各年アトムを畳まず、後継コード列 base_code・base_name を同梱して返す（入力列＋2列）。

    畳む/畳まないを配布時に固定しない「非固定」ビュー。利用者は area_code のまま使えば
    原境界（合併前の実態保持）、`GROUP BY base_code` すれば前方 rollup 相当（連続時系列）。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（入力スキーマは fact 依存）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 後継先の基準年（既定=atom_fact の最新年）。

    返り値の列 = 入力列 ＋ base_code（後継先コード。未合併/未整備は area_code と同値）
    ＋ base_name（base_year 時点の後継先名称。幽霊 base ユニットでは null）。
    """
    base = _base_year(atom_fact, base_year)
    roll = rollup(events, base_year=base)
    base_names = (
        atom_fact.filter(pl.col("year") == base)
        .select(pl.col("area_code").alias("base_code"), pl.col("area_name").alias("base_name"))
        .unique(subset="base_code")
    )
    sort_keys = ["area_code", "year", *_cat_code_cols(atom_fact)]
    return (
        atom_fact.join(roll, left_on="area_code", right_on="code", how="left")
        .with_columns(pl.coalesce("base_code", "area_code").alias("base_code"))
        .join(base_names, on="base_code", how="left")
        .select(*atom_fact.columns, "base_code", "base_name")
        .sort(sort_keys)
    )


def aggregate_to_base(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
    """アトム時系列を base_year 境界の自治体時系列へ畳む（入力と同じスキーマで返す）。

    = attach_crosswalk を base_code で実際に合算した確定ビュー。

    引数:
        atom_fact … 各年アトムを union 結合した時系列 DF（入力スキーマは fact 依存）。
        events    … 実効合併イベント（area.events.load_events の出力）。
        base_year … 集約の基準年（既定=atom_fact の最新年）。
    """
    base = _base_year(atom_fact, base_year)
    cw = attach_crosswalk(atom_fact, events, base_year=base)

    cat_codes = _cat_code_cols(atom_fact)
    cat_labels = [
        c.removesuffix("_code") for c in cat_codes
    ]  # sex_code→sex / age_class_code→age_class
    agg = cw.group_by(["base_code", "year", *cat_codes]).agg(
        pl.col("population").sum().alias("population"),
        *(pl.col(lbl).first().alias(lbl) for lbl in cat_labels),
    )

    # name/level は base_year 時点のアトム（＝基準年に現存する自治体）から与える
    base_attrs = (
        atom_fact.filter(pl.col("year") == base)
        .select(
            pl.col("area_code").alias("base_code"),
            pl.col("area_name"),
            pl.col("area_level"),
        )
        .unique(subset="base_code")
    )

    return (
        agg.join(base_attrs, on="base_code", how="left")
        .rename({"base_code": "area_code"})
        .with_columns((pl.col("area_level") != _OBSOLETE_AREA_LEVEL).alias("is_current"))
        .select(atom_fact.columns)
        .sort(["area_code", "year", *cat_codes])
    )


def aggregate_to_admin(atom_fact: pl.DataFrame, *, level: str) -> pl.DataFrame:
    """アトム時系列を行政階層（都道府県 / 地方ブロック）へ上位集約する（events 非依存）。

    合併 rollup（`aggregate_to_base`）とは**直交する軸**。市区町村は都道府県を跨がないため、
    各年アトムを area_code の県プレフィックスで group して合算するだけで県/地方合計になる
    （合併を畳もうが畳むまいが県内合計は不変＝`national_conservation` が保証する不変量）。
    よって events は不要で、`aggregate_to_base` の前後どちらに適用しても結果は同じ。

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
