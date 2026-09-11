"""値サニティ検算（測定量の非負）のテスト。

保存則・クロスファクトが「総数一致」で自明化して見逃す値の破綻（例 導出注入した不詳が
負に振れる）を、測定量の値域で直接捕まえられるかを検証する。
"""

import polars as pl

from data_forge import sanity


def _fact(populations: list[int], households: list[int] | None = None) -> pl.DataFrame:
    """測定量（population・任意で households）とキー各種を持つ最小 fact。"""
    n = len(populations)
    cols = {
        "area_code": [f"0{i:04d}" for i in range(n)],
        "area_level": [pl.Series([4] * n, dtype=pl.Int8)][0],
        "sex_code": ["0"] * n,
        "year": [2020] * n,
        "population": populations,
    }
    if households is not None:
        cols["households"] = households
    return pl.DataFrame(cols)


def test_measure_columns_excludes_keys_and_levels():
    df = _fact([100, 200], households=[40, 80])
    # year(数値)・area_level(*_level)・*_code(Utf8) はキーゆえ測定量から除外。
    assert sanity.measure_columns(df) == ["population", "households"]


def test_negative_values_flags_broken_measure():
    # 3行目 population=-5（不詳導出のはみ出しを模す）。保存則では総数一致で自明化して見逃す穴。
    df = _fact([100, 0, -5])
    bad = sanity.negative_values(df)
    assert bad.height == 1
    assert bad["population"].to_list() == [-5]


def test_negative_values_catches_any_measure():
    # population は非負でも households が負なら検出（any_horizontal）。
    df = _fact([100, 200], households=[40, -1])
    assert sanity.negative_values(df)["households"].to_list() == [-1]


def test_negative_values_all_nonnegative_is_empty():
    assert sanity.negative_values(_fact([0, 100, 200], households=[0, 40, 80])).height == 0


def test_null_measure_count_is_advisory_signal():
    df = _fact([100, None, 200])  # 未収録セル由来の null 混入を模す
    assert sanity.null_measure_count(df) == 1
    # null は負ではないので負値ゲートには乗らない（advisory 扱い）。
    assert sanity.negative_values(df).height == 0


def _neg_fact(codes_years_vals: list[tuple[str, int, int]]) -> pl.DataFrame:
    """(labor_status_code, year, population) から labor_force 型の最小 fact を作る。"""
    n = len(codes_years_vals)
    return pl.DataFrame(
        {
            "area_code": ["47000"] * n,
            "sex_code": ["1"] * n,
            "labor_status_code": [c for c, _, _ in codes_years_vals],
            "year": [y for _, y, _ in codes_years_vals],
            "population": [v for _, _, v in codes_years_vals],
        }
    )


_SPEC = sanity.KnownNegative(
    match={"area_code": "47000", "year": 1955, "sex_code": "1", "labor_status_code": "999"},
    measure="population",
    value=-100,
    reason="テスト用",
)


def test_unknown_negatives_excludes_pinned_cell():
    # pin した (-100) セルは受容、別の負値(-5)は未知として残る。
    df = _neg_fact([("999", 1955, -100), ("999", 1985, -5)])
    out = sanity.unknown_negatives(df, [_SPEC])
    assert out["year"].to_list() == [1985]


def test_unknown_negatives_flags_value_drift():
    # pin は -100。残差が -101 に動けば（回帰）一致せず未知の負値として検出される。
    df = _neg_fact([("999", 1955, -101)])
    assert sanity.unknown_negatives(df, [_SPEC]).height == 1


def test_known_negative_hits_counts_matches():
    df = _neg_fact([("999", 1955, -100)])
    assert sanity.known_negative_hits(df, [_SPEC]) == [(_SPEC, 1)]
    # 該当0件（データ側から消失）はレジストリ陳腐化の signal。
    assert sanity.known_negative_hits(_neg_fact([("110", 1955, 500)]), [_SPEC]) == [(_SPEC, 0)]
