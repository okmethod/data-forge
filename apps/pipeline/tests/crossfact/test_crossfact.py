"""クロスファクト検算（三角測量）のテスト。

別ソース由来の同一軸（総人口）を共有軸（conformed dimension）で相互照合し、
match / mismatch / scope_out / known_diff の status 分類が正しいことを回帰ガードする。
照合ロジックは reconcile.cross_fact、実データ照合は CLI `crossfact-check` が担う。
設計（C1-C5 の恒等式・許容カテゴリ）は docs/data-quality-assurance.md が正典。
"""

import polars as pl

from data_forge.area import reconcile


def _pop_hub(rows: list[tuple[str, str, int, int]]) -> pl.DataFrame:
    """population 相当（area×sex×year の総人口）を手組みする。"""
    return pl.DataFrame([{"area_code": a, "sex_code": s, "year": y, "population": p} for a, s, y, p in rows])


def _age5_other(rows: list[tuple[str, str, str, str, int, int]]) -> pl.DataFrame:
    """age5 相当（area×sex×nationality×age_class×year）を手組みする。"""
    return pl.DataFrame(
        [
            {"area_code": a, "sex_code": s, "nationality_code": n, "age_class_code": ac, "year": y, "population": p}
            for a, s, n, ac, y, p in rows
        ]
    )


def test_cross_fact_matches_hub_and_slices_total():
    # age5 の nat=0×age_class=100 スライスが population ハブと一致し、内訳(age=110)・日本人(nat=1)は
    # other_slice で除外され二重計上しない。
    hub = _pop_hub([("01100", "0", 2020, 1000), ("01100", "1", 2020, 480), ("01100", "2", 2020, 520)])
    other = _age5_other(
        [
            ("01100", "0", "0", "100", 2020, 1000),  # 総数×総数（拾う）
            ("01100", "1", "0", "100", 2020, 480),
            ("01100", "2", "0", "100", 2020, 520),
            ("01100", "0", "0", "110", 2020, 60),  # 0〜4歳の内訳（除外されるべき）
            ("01100", "0", "1", "100", 2020, 950),  # 日本人（除外されるべき）
        ]
    )
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "100"),
    )
    assert rep["ok"].all()
    assert rep["diff"].to_list() == [0, 0, 0]
    assert sorted(rep["sex_code"].to_list()) == ["0", "1", "2"]


def test_cross_fact_flags_coverage_gap():
    # 片側だけに在るキー（level7 カバレッジ差の相当）は full-join で diff!=0 として検出する。
    hub = _pop_hub([("01100", "0", 2020, 1000), ("09999", "0", 2020, 300)])  # 09999 は hub のみ
    other = _age5_other([("01100", "0", "0", "100", 2020, 1000)])
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "100"),
    ).sort("area_code")
    assert dict(zip(rep["area_code"], rep["ok"], strict=True)) == {"01100": True, "09999": False}
    assert dict(zip(rep["area_code"], rep["diff"], strict=True)) == {"01100": 0, "09999": 300}
    assert dict(zip(rep["area_code"], rep["status"], strict=True)) == {"01100": "match", "09999": "mismatch"}


def test_cross_fact_scope_out_year_accepts_absent_other():
    # scope_years の年は other 未収録（=0）が期待＝スコープ外として許容（ok=True・status=scope_out）。
    # ただし other が実在すれば（想定破れ）不一致として弾く。
    hub = _pop_hub([("01100", "0", 2025, 1000), ("01100", "0", 2020, 900)])
    other = _age5_other([("01100", "0", "0", "100", 2020, 900)])  # 2025 は age5 に無い
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "100"),
        scope_years=frozenset({2025}),
    ).sort("year")
    assert dict(zip(rep["year"], rep["status"], strict=True)) == {2020: "match", 2025: "scope_out"}
    assert rep["ok"].all()  # 2025 は diff=1000 でもスコープ外ゆえ許容


def test_cross_fact_known_diff_year_accepts_directional_gap():
    # known_diff_years の年は定義差で diff!=0 が期待＝other<=hub（diff>=0）なら許容。
    # 逆向き（other>hub＝あり得ない）は真の不一致として弾く。
    hub = _pop_hub([("01100", "0", 2005, 1000), ("09999", "0", 2005, 500)])
    other = _age5_other(
        [
            ("01100", "0", "0", "100", 2005, 990),  # 年齢不詳10を欠く（diff=+10・許容）
            ("09999", "0", "0", "100", 2005, 520),  # other>hub（diff=-20・許容しない）
        ]
    )
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "100"),
        known_diff_years=frozenset({2005}),
    ).sort("area_code")
    assert dict(zip(rep["area_code"], rep["status"], strict=True)) == {"01100": "known_diff", "09999": "known_diff"}
    assert dict(zip(rep["area_code"], rep["ok"], strict=True)) == {"01100": True, "09999": False}
