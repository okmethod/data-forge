"""来歴列 data_status（provenance）の検証と、速報 splice のテスト。

確定ビューへ速報行を継ぎ足す splice_preliminary が、来歴列の付与・列一致・
粒度（同一セル重複の禁止）・許容値を担保することを確認する。
"""

import polars as pl
import pytest

from data_forge import provenance

_GRAIN = ["area_code", "sex_code", "year"]


def _pop(area: str, year: int, pop: int) -> pl.DataFrame:
    """population fact の最小フレーム（総数 sex=0）。"""
    return pl.DataFrame(
        {
            "area_code": [area],
            "area_name": [area],
            "area_level": [2],
            "sex_code": ["0"],
            "sex": ["総数"],
            "year": [year],
            "population": [pop],
            "is_current": [True],
        }
    )


def test_values_derived_from_literal():
    # 許容集合は Literal 型から導出＝二重記述しない
    assert provenance.VALUES == {"confirmed", "preliminary"}


def test_splice_tags_both_sides():
    confirmed = pl.concat([_pop("A", 2015, 100), _pop("A", 2020, 110)])
    preliminary = _pop("A", 2025, 120)
    out = provenance.splice_preliminary(confirmed, preliminary, grain=_GRAIN)

    assert provenance.COLUMN in out.columns
    assert out.height == 3
    status = dict(zip(out["year"], out[provenance.COLUMN]))
    assert status == {2015: "confirmed", 2020: "confirmed", 2025: "preliminary"}


def test_splice_rejects_overlapping_cell():
    # 速報年が確定側に既に存在する＝取り違え → 粒度違反で弾く
    confirmed = _pop("A", 2020, 110)
    preliminary = _pop("A", 2020, 999)
    with pytest.raises(ValueError, match="粒度違反"):
        provenance.splice_preliminary(confirmed, preliminary, grain=_GRAIN)


def test_splice_rejects_column_mismatch():
    confirmed = _pop("A", 2020, 110)
    preliminary = _pop("A", 2025, 120).drop("is_current")
    with pytest.raises(ValueError, match="列が不一致"):
        provenance.splice_preliminary(confirmed, preliminary, grain=_GRAIN)


def test_assert_status_rejects_unknown_value():
    df = _pop("A", 2025, 120).with_columns(pl.lit("bogus").alias(provenance.COLUMN))
    with pytest.raises(ValueError, match="未知の data_status"):
        provenance.assert_status(df)


def test_assert_status_requires_column():
    with pytest.raises(ValueError, match="列が無い"):
        provenance.assert_status(_pop("A", 2020, 110))
