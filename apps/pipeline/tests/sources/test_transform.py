"""e-Stat 変換層（transform.py）の単体テスト。

大半のヘルパ（int_value_expr / exclude_imputed_version_expr / area_axis_cols 等）は
消費側の cleaner テストが実データで担保するため、ここでは cleaner を通らない関数と防御分岐だけを直接固める。
- extract_area_hierarchy: area 軸の parent_code 抽出・level キャスト・軸欠如の ValueError
  （area マスタの「標準市区町村」判定に効くが cleaner を経由しないため間接カバレッジが無い）
- scope_area / code_name_cols: 未知入力での例外分岐（正常系は cleaner テストが担保）

設計の正典は transform.py の docstring、地域マスタは docs/pipeline-architecture.md。
"""

import polars as pl
import pytest

from data_forge.sources.estat import transform


def _raw_with_area(class_items: list[dict] | dict) -> dict:
    """area 軸 CLASS_OBJ を1つ持つ最小 raw を組む。"""
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {"@id": "tab", "CLASS": {"@code": "020", "@name": "人口"}},
                        {"@id": "area", "CLASS": class_items},
                    ]
                }
            }
        }
    }


# --- extract_area_hierarchy ---


def test_extract_area_hierarchy_extracts_parent_and_casts_level():
    raw = _raw_with_area(
        [
            {"@code": "00000", "@name": "全国", "@level": "1"},  # 親なし
            {"@code": "01000", "@name": "北海道", "@level": "2", "@parentCode": "00000"},
            {"@code": "01100", "@name": "札幌市", "@level": "3", "@parentCode": "01000"},
        ]
    )

    hier = transform.extract_area_hierarchy(raw)

    assert hier.columns == ["code", "name", "level", "parent_code"]
    assert hier.schema["level"] == pl.Int8  # 文字列 "@level" を Int8 へ
    assert hier.schema["parent_code"] == pl.Utf8
    rows = {r["code"]: r for r in hier.to_dicts()}
    assert rows["00000"]["parent_code"] is None  # @parentCode 欠如 → null
    assert rows["00000"]["level"] == 1
    assert rows["01100"]["parent_code"] == "01000"  # 親コードを別立てに取り出す


def test_extract_area_hierarchy_defaults_missing_name_and_level():
    # @name / @level 欠如は "" / 0 に寄せる（int("0") 経由）。
    raw = _raw_with_area([{"@code": "09999"}])

    row = transform.extract_area_hierarchy(raw).to_dicts()[0]

    assert row == {"code": "09999", "name": "", "level": 0, "parent_code": None}


def test_extract_area_hierarchy_accepts_single_class_dict():
    # e-Stat は CLASS が1件だと配列でなく単一 dict → _as_list でラップされる。
    raw = _raw_with_area({"@code": "00000", "@name": "全国", "@level": "1"})

    assert transform.extract_area_hierarchy(raw).height == 1


def test_extract_area_hierarchy_raises_without_area_axis():
    raw = {"GET_STATS_DATA": {"STATISTICAL_DATA": {"CLASS_INF": {"CLASS_OBJ": [{"@id": "cat01", "CLASS": []}]}}}}

    with pytest.raises(ValueError, match="area 軸"):
        transform.extract_area_hierarchy(raw)


# --- scope_area: 未知 scope の防御分岐（正常系は cleaner テストが担保） ---


def test_scope_area_rejects_unknown_scope():
    fact = pl.DataFrame({"area_code": ["00000"]})

    with pytest.raises(ValueError, match="未知の scope"):
        transform.scope_area(fact, "bogus")


# --- code_name_cols: 未知値は replace_strict で例外（未知値の握り潰し防止） ---


def test_code_name_cols_raises_on_unmapped_value():
    fact = pl.DataFrame({"cat01_code": ["999"]})  # mapping に無いコード

    with pytest.raises(pl.exceptions.InvalidOperationError):
        fact.select(*transform.code_name_cols("cat01_code", {"100": ("0", "総数")}, "sex"))
