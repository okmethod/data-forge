"""e-Stat のスタースキーマ（CLASS_INF + DATA_INF）を tidy な Polars DataFrame へ。

e-Stat のレスポンスは「軸ごとのコード↔名称辞書（CLASS_INF）」と
「コードだけを持つファクト行（DATA_INF.VALUE）」に分離している。
ここではコードを名称解決し、1軸につき `<axis>_code` / `<axis>_name` /
`<axis>_level` の3列＋`value`（文字列）を持つロング形式へ変換する。

特定の統計表に依存しない汎用処理。人口固有の整形は population.py が担う。
"""

from typing import Any

import polars as pl

from data_forge.meta import SourceMeta

# e-Stat 共通の出典表記ベース（政府統計利用規約）
_CITATION_BASE = "出典：政府統計の総合窓口(e-Stat)（https://www.e-stat.go.jp/）"

# 単一 ID に同居する 全国(level1) を表す area code / name。配布時に地理粒度で分離する。
NATIONAL_AREA_CODE = "00000"
NATIONAL_AREA_NAME = "全国"

# census「男女_時系列」軸 {軸コード → (sex_code, sex名称)}。100/110/120＝総数/男/女。
# age5year / industry / occupation / labor_force が共用（同コードだが cat01/cat02 は表ごと）。
# population は年別に軸コードが変わるため population.SEX_YYYY を独自に持つ。
SEX = {"100": ("0", "総数"), "110": ("1", "男"), "120": ("2", "女")}


def scope_area(fact: pl.DataFrame, scope: str) -> pl.DataFrame:
    """配布スキーマの地理粒度を排他選択する: national=全国のみ / prefecture=47都道府県のみ / all=両方。

    単一 ID に全国(level1) と 47都道府県(level2) が同居する fact（households / family_type 等）で、
    配布時に地理粒度を分離するための共通フィルタ。
    """
    if scope == "all":
        return fact
    if scope == "national":
        return fact.filter(pl.col("area_code") == NATIONAL_AREA_CODE)
    if scope == "prefecture":
        return fact.filter(pl.col("area_code") != NATIONAL_AREA_CODE)
    raise ValueError(f"未知の scope: {scope!r}（all/national/prefecture のいずれか）")


def int_value() -> pl.Expr:
    """tidy な value（文字列）を Int64 へ。数字以外（"-" 等の欠損記号）は null に落とす。"""
    return pl.col("value").str.replace_all(r"[^0-9-]", "").cast(pl.Int64, strict=False)


def year_from_time_code() -> pl.Expr:
    """time_code の先頭4桁を調査年 year(Int16) へ（例: "2020000000" → 2020）。"""
    return pl.col("time_code").str.slice(0, 4).cast(pl.Int16).alias("year")


def area_passthrough_cols() -> list[pl.Expr]:
    """原 area 列（code/name）をそのまま採り、area_level だけ Int8 に整える3列。

    ソースの area 行をそのまま配布する表（households / family_type / daynight / population 等）が共用。
    area_level は年で dtype が揺れるため strict=False で寄せる（未変換は null）。
    """
    return [
        pl.col("area_code"),
        pl.col("area_name"),
        pl.col("area_level").cast(pl.Int8, strict=False).alias("area_level"),
    ]


def code_name_cols(src: str, mapping: dict[str, tuple[str, str]], name: str) -> list[pl.Expr]:
    """コード→(出力コード, 名称) の辞書で src 列を <name>_code / <name> の2列へ写像する。

    e-Stat の軸コード（SEX / AGE_* / DAYNIGHT 等）を配布スキーマの code/name ペアへ一括変換する。
    src の値は mapping のキーを網羅している前提（replace_strict＝未知値は例外）。
    """
    return [
        pl.col(src).replace_strict({k: v[0] for k, v in mapping.items()}).alias(f"{name}_code"),
        pl.col(src).replace_strict({k: v[1] for k, v in mapping.items()}).alias(name),
    ]


def area_axis_cols(national: bool) -> list[pl.Expr]:
    """全国表と都道府県表が別 ID に分かれる census 表の area 3列（code/name/level）を選ぶ。

    national=True … area 軸を持たない全国集計表：00000/全国/level1 を合成する。
    national=False … 都道府県表（47県, level2）：原 area 列をそのまま採る（area_passthrough_cols）。
    industry / occupation / age5year が共用（単一 ID 内で全国↔県が同居する households 系は scope_area を使う）。
    """
    if national:
        return [
            pl.lit(NATIONAL_AREA_CODE).alias("area_code"),
            pl.lit(NATIONAL_AREA_NAME).alias("area_name"),
            pl.lit(1).cast(pl.Int8).alias("area_level"),
        ]
    return area_passthrough_cols()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def extract_meta(raw: dict[str, Any]) -> SourceMeta:
    """TABLE_INF から共通の出典メタ（出典表記込み）を組み立てる。"""
    table = raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["TABLE_INF"]
    dataset_id = str(table.get("@id", ""))
    stat_name = str(table.get("STAT_NAME", {}).get("$", ""))
    title = str(table.get("TITLE", {}).get("$", ""))
    survey_date = str(table.get("SURVEY_DATE", ""))
    provider = str(table.get("GOV_ORG", {}).get("$", ""))

    return SourceMeta(
        source="estat",
        dataset_id=dataset_id,
        title=title,
        provider=provider,
        citation=f"{_CITATION_BASE} 「{stat_name} {title}」を加工して作成",
        attributes={"stat_name": stat_name, "survey_date": survey_date},
    )


def _build_lookups(raw: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    """軸ID → コード → {name, level} の辞書を構築する。"""
    class_objs = _as_list(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"])
    lookups: dict[str, dict[str, dict[str, str]]] = {}
    for obj in class_objs:
        axis_id = obj["@id"]
        table: dict[str, dict[str, str]] = {}
        for item in _as_list(obj["CLASS"]):
            table[item["@code"]] = {
                "name": item.get("@name", ""),
                "level": item.get("@level", ""),
            }
        lookups[axis_id] = table
    return lookups


def extract_area_hierarchy(raw: dict[str, Any]) -> pl.DataFrame:
    """area 軸の階層（code/name/level/parent_code）を取り出す。

    地域マスタ（アトム抽出）で「その年の標準的な市区町村」を判定するのに使う。
    to_tidy は name/level しか運ばないため、集計行/上位コンテナの判定に要る
    `@parentCode`（親コード）をここで別立てに取り出す（fact スキーマは 8 列のまま）。
    """
    class_objs = _as_list(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"])
    area = next((o for o in class_objs if o["@id"] == "area"), None)
    if area is None:
        raise ValueError("area 軸が CLASS_INF に見つかりません")
    rows = [
        {
            "code": it["@code"],
            "name": it.get("@name", ""),
            "level": int(it.get("@level", "0")),
            "parent_code": it.get("@parentCode"),
        }
        for it in _as_list(area["CLASS"])
    ]
    return pl.DataFrame(
        rows,
        schema={
            "code": pl.Utf8,
            "name": pl.Utf8,
            "level": pl.Int8,
            "parent_code": pl.Utf8,
        },
    )


def to_tidy(raw: dict[str, Any]) -> pl.DataFrame:
    """スタースキーマを名称解決済みのロング形式 DataFrame に変換する。"""
    lookups = _build_lookups(raw)
    values = _as_list(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"])

    records: list[dict[str, Any]] = []
    for v in values:
        row: dict[str, Any] = {}
        for axis_id, table in lookups.items():
            code = v.get(f"@{axis_id}")
            entry = table.get(code, {})
            row[f"{axis_id}_code"] = code
            row[f"{axis_id}_name"] = entry.get("name")
            row[f"{axis_id}_level"] = entry.get("level")
        row["unit"] = v.get("@unit")
        row["value"] = v.get("$")
        records.append(row)

    return pl.DataFrame(records)
