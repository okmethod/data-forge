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


def test_cross_fact_bound_accepts_subset_and_flags_overflow():
    # 上界検算（mode="bound"）: 日本人(nat=1)<=population。diff>=0 かつ other>0 なら許容（bound）。
    # 日本人>総人口（diff<0＝支庁二重計上など）は真の不一致として弾く。
    hub = _pop_hub([("01100", "0", 2020, 1000), ("09999", "0", 2020, 500)])
    other = _age5_other(
        [
            ("01100", "0", "1", "100", 2020, 950),  # 日本人950<=総1000（外国人50・許容）
            ("09999", "0", "1", "100", 2020, 520),  # 日本人520>総500（diff=-20・許容しない）
        ]
    )
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "1") & (pl.col("age_class_code") == "100"),
        mode="bound",
    ).sort("area_code")
    assert dict(zip(rep["area_code"], rep["status"], strict=True)) == {"01100": "bound", "09999": "bound"}
    assert dict(zip(rep["area_code"], rep["ok"], strict=True)) == {"01100": True, "09999": False}


def test_cross_fact_bound_flags_missing_japanese_slice_but_allows_empty_cell():
    # bound の other>0 要件は「hub>0 なのに日本人スライス欠落」を弾く一方、hub==0 の空セル
    # （住民のいない自治体＝07543 避難区域 等）は other==0 でも許容する。
    hub = _pop_hub(
        [
            ("01100", "0", 2020, 1000),  # 日本人あり → 許容
            ("09999", "0", 2020, 500),  # hub>0 なのに日本人欠落 → 弾く
            ("07543", "0", 2020, 0),  # hub==0 の空セル → other==0 でも許容
            ("01100", "0", 1980, 900),  # 1980 は国籍軸なし → scope_out
        ]
    )
    other = _age5_other([("01100", "0", "1", "100", 2020, 950)])
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "year"],
        other_slice=(pl.col("nationality_code") == "1") & (pl.col("age_class_code") == "100"),
        mode="bound",
        scope_years=frozenset({1980}),  # 1980 は日本人未収録＝スコープ外として許容
    )
    ok = {(a, y): o for a, y, o in zip(rep["area_code"], rep["year"], rep["ok"], strict=True)}
    assert ok == {
        ("01100", 2020): True,  # diff50 & other>0
        ("09999", 2020): False,  # hub>0 & other==0 ＝欠落
        ("07543", 2020): True,  # hub==0 の空セル
        ("01100", 1980): True,  # scope_out
    }


def test_cross_fact_within_fact_conservation_via_hub_slice():
    # within-fact 保存則: hub_slice/other_slice で同一 DF を総数側/内訳側へ切り、Σ内訳==総数 を検算。
    # 日本人 年齢保存: 日本人 Σ(age_class!=100) == 日本人 年齢総数(age_class=100)。
    fact = _age5_other(
        [
            ("01100", "1", "1", "100", 2020, 100),  # 日本人 年齢総数（ハブ側）
            ("01100", "1", "1", "110", 2020, 60),  # 0〜4歳
            ("01100", "1", "1", "120", 2020, 40),  # 5〜9歳（Σ=100 で保存成立）
            ("01100", "1", "0", "100", 2020, 130),  # 総数(nat=0) はスライスで除外されるべき
        ]
    )
    rep = reconcile.cross_fact(
        fact,
        fact,
        keys=["area_code", "sex_code", "year"],
        hub_slice=(pl.col("nationality_code") == "1") & (pl.col("age_class_code") == "100"),
        other_slice=(pl.col("nationality_code") == "1") & (pl.col("age_class_code") != "100"),
    )
    assert rep["status"].to_list() == ["match"]
    assert rep["ok"].all()
    assert rep["diff"].to_list() == [0]


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
