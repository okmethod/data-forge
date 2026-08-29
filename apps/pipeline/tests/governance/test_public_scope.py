"""公開範囲ゲート（data_forge.public_scope）のユニットテスト。"""

from pathlib import Path

import polars as pl
import pytest

from data_forge.public_scope import PublicScopePolicy, find_violations, is_municipality_grain


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("12231", True),  # 印西市＝市区町村粒度
        ("13101", True),  # 千代田区＝市区町村粒度
        ("13000", False),  # 東京都＝県コード XX000
        ("00000", False),  # 全国
        ("1", False),  # sex_code など短いコード
        ("100", False),  # age_class_code など
    ],
)
def test_is_municipality_grain(code: str, expected: bool) -> None:
    assert is_municipality_grain(code) is expected


def _policy() -> PublicScopePolicy:
    return PublicScopePolicy(
        area_code_columns=["area_code", "pref_code"],
        allow_municipalities=frozenset({"12231"}),
    )


def _write(dir_: Path, **columns: list) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(columns).write_parquet(dir_ / "t.parquet")


def test_find_violations_clean(tmp_path: Path) -> None:
    _write(tmp_path / "data" / "x", area_code=["00000", "13000", "12231"], population=[1, 2, 3])
    assert find_violations(tmp_path / "data", _policy()) == {}


def test_find_violations_detects_leak(tmp_path: Path) -> None:
    _write(tmp_path / "data" / "x", area_code=["12231", "13101"])
    assert set(find_violations(tmp_path / "data", _policy())) == {"13101"}


def test_find_violations_ignores_non_code_columns(tmp_path: Path) -> None:
    # population に 5桁・末尾≠000 の値があっても、対象列でないので誤検知しない。
    _write(tmp_path / "data" / "x", area_code=["12231"], population=[12345])
    assert find_violations(tmp_path / "data", _policy()) == {}


def test_load_policy(tmp_path: Path) -> None:
    p = tmp_path / "public_scope.yaml"
    p.write_text(
        'area_code_columns:\n  - area_code\nallow_municipalities:\n  - "12231"\n',
        encoding="utf-8",
    )
    pol = PublicScopePolicy.load(p)
    assert pol.area_code_columns == ["area_code"]
    assert pol.allow_municipalities == frozenset({"12231"})
