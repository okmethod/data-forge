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
