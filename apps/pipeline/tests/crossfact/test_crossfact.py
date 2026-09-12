"""クロスファクト検算（三角測量）のテスト。

別ソース由来の同一軸（総人口）を共有軸（conformed dimension）で相互照合し、
match / mismatch / scope_out / known_diff の status 分類が正しいことを回帰ガードする。
照合ロジックは reconcile.cross_fact、実データ照合は CLI `crossfact-check` が担う。
設計（C1-C5 の恒等式・許容カテゴリ）は docs/data-quality-assurance.md が正典。
"""

import polars as pl

from data_forge.area import reconcile
from data_forge.area.specs import _MAC_AGE5_TO_BAND, _MIC_AGE_TO_BAND


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


def _by_age_hub(rows: list[tuple[str, str, str, int, int]]) -> pl.DataFrame:
    """population_by_age 相当（area×sex×age_class×year の3区分人口）を手組みする。"""
    return pl.DataFrame(
        [{"area_code": a, "sex_code": s, "age_class_code": ac, "year": y, "population": p} for a, s, ac, y, p in rows]
    )


def test_cross_fact_c2_folds_age5_bands_into_three_categories():
    # C2: age5 の5歳階級(nat=0)を年齢3区分へ畳込し by_age の区分(1/2/3)と区分ごとに一致する。
    # 130(10-14)→年少1・150/240(15-64)→生産2・250(65+)→老年3。総数100/不詳999・日本人(nat=1)は除外。
    fold = {"130": "1", "150": "2", "240": "2", "250": "3"}
    hub = _by_age_hub(
        [
            ("01100", "0", "0", 2020, 1000),  # 総数（除外されるべき）
            ("01100", "0", "1", 2020, 100),  # 年少 0-14
            ("01100", "0", "2", 2020, 700),  # 生産 15-64
            ("01100", "0", "3", 2020, 200),  # 老年 65+
            ("01100", "0", "9", 2020, 0),  # 不詳（除外されるべき）
        ]
    )
    other = _age5_other(
        [
            ("01100", "0", "0", "100", 2020, 1000),  # 総数（除外されるべき）
            ("01100", "0", "0", "130", 2020, 100),  # 年少 → cat1
            ("01100", "0", "0", "150", 2020, 300),  # 生産 → cat2
            ("01100", "0", "0", "240", 2020, 400),  # 生産 → cat2（Σ=700）
            ("01100", "0", "0", "250", 2020, 200),  # 老年 → cat3
            ("01100", "0", "0", "999", 2020, 5),  # 不詳（バンド外＝除外）
            ("01100", "0", "1", "150", 2020, 280),  # 日本人（nat=1＝除外）
        ]
    )
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "age3_code", "year"],
        hub_slice=pl.col("age_class_code").is_in(["1", "2", "3"]),
        hub_with=[pl.col("age_class_code").alias("age3_code")],
        other_slice=(pl.col("nationality_code") == "0") & pl.col("age_class_code").is_in(list(fold)),
        other_with=[pl.col("age_class_code").replace_strict(fold, default=None).alias("age3_code")],
    ).sort("age3_code")
    assert rep["age3_code"].to_list() == ["1", "2", "3"]
    assert rep["diff"].to_list() == [0, 0, 0]
    assert rep["ok"].all()


def test_cross_fact_c2_flags_category_boundary_error():
    # 区分レベルの取り違え（総数は保存するが境界がズレる）を C2 は検出する（C1/C3 は総数のみで素通り）。
    fold = {"240": "2", "250": "3"}  # 240=60-64→生産・250=65-69→老年
    hub = _by_age_hub([("01100", "0", "2", 2020, 400), ("01100", "0", "3", 2020, 200)])
    other = _age5_other(
        [
            ("01100", "0", "0", "240", 2020, 300),  # 生産が100不足
            ("01100", "0", "0", "250", 2020, 300),  # 老年が100過剰（総和600は保存）
        ]
    )
    rep = reconcile.cross_fact(
        hub,
        other,
        keys=["area_code", "sex_code", "age3_code", "year"],
        hub_slice=pl.col("age_class_code").is_in(["1", "2", "3"]),
        hub_with=[pl.col("age_class_code").alias("age3_code")],
        other_slice=(pl.col("nationality_code") == "0") & pl.col("age_class_code").is_in(list(fold)),
        other_with=[pl.col("age_class_code").replace_strict(fold, default=None).alias("age3_code")],
    ).sort("age3_code")
    assert dict(zip(rep["age3_code"], rep["diff"], strict=True)) == {"2": 100, "3": -100}
    assert not rep["ok"].any()  # 両区分とも真の不一致


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


def _c4_report(hub: pl.DataFrame, other: pl.DataFrame) -> pl.DataFrame:
    """C4 の県 rollup＋5歳バンド写像を cli の band map で組み、cross_fact に掛けた結果を返す。"""
    return reconcile.cross_fact(
        hub,
        other,
        keys=["pref_code", "sex_code", "age_band", "year"],
        hub_with=[
            pl.col("area_code").str.slice(0, 2).alias("pref_code"),
            pl.col("age_class_code").replace_strict(_MAC_AGE5_TO_BAND, default=None).alias("age_band"),
        ],
        hub_slice=pl.col("age_band").is_not_null(),
        other_with=[
            pl.col("area_code").str.slice(0, 2).alias("pref_code"),
            pl.col("age_class_code").replace_strict(_MIC_AGE_TO_BAND, default=None).alias("age_band"),
        ],
        other_slice=(pl.col("nationality_code") == "0") & pl.col("age_band").is_not_null(),
        mode="conservation",
    ).sort("age_band")


def test_cross_fact_c4_folds_micro_85plus_and_rolls_up_to_prefecture():
    # C4: age5 ミクロ(市区町村・別コード体系)を県 rollup し 5歳バンドへ写像＝マクロ(県)と一致する。
    # マクロ 250=65-69・310=85歳以上／ミクロ 240=65-69・280-310=85-89…100歳以上（85+は畳んで合流）。
    # 県 rollup は area_code 先頭2桁（01100/01200→01）。総数100・不詳999・日本人(nat=1)は写像外＝除外。
    hub = pl.DataFrame(
        [
            {"area_code": "01000", "sex_code": "0", "age_class_code": ac, "year": 2020, "population": p}
            for ac, p in [("100", 999), ("250", 150), ("310", 70), ("999", 5)]  # 総数/不詳は band 外
        ]
    )
    other = pl.DataFrame(
        [
            {
                "area_code": a,
                "sex_code": "0",
                "nationality_code": n,
                "age_class_code": ac,
                "year": 2020,
                "population": p,
            }
            for a, n, ac, p in [
                ("01100", "0", "240", 100),  # 65-69（→band65）
                ("01200", "0", "240", 50),  # 別市区町村（rollup で合流＝150）
                ("01100", "0", "280", 30),  # 85-89 ┐
                ("01100", "0", "290", 25),  # 90-94 ├ 85+ 畳込＝70
                ("01100", "0", "300", 10),  # 95-99 │
                ("01100", "0", "310", 5),  # 100+ ┘
                ("01100", "1", "240", 88),  # 日本人（nat=1＝除外）
            ]
        ]
    )
    rep = _c4_report(hub, other)
    assert rep["age_band"].to_list() == [65, 85]
    assert rep["diff"].to_list() == [0, 0]  # 65-69=150 / 85+=70 が両側一致
    assert rep["ok"].all()


def test_cross_fact_c4_flags_per_band_misallocation_within_prefecture():
    # per-band ゆえ県総数が保存しても 5歳バンド間の誤配分（85+の畳み先違い等）は検出する（mode=conservation）。
    hub = pl.DataFrame(
        [
            {"area_code": "01000", "sex_code": "0", "age_class_code": ac, "year": 2020, "population": p}
            for ac, p in [("250", 150), ("310", 70)]
        ]
    )
    other = pl.DataFrame(  # 65-69 に+10・85+ に-10（県総数は保存するがバンドがズレる）
        [
            {
                "area_code": "01100",
                "sex_code": "0",
                "nationality_code": "0",
                "age_class_code": ac,
                "year": 2020,
                "population": p,
            }
            for ac, p in [("240", 160), ("280", 60)]
        ]
    )
    rep = _c4_report(hub, other)
    assert dict(zip(rep["age_band"], rep["diff"], strict=True)) == {65: -10, 85: 10}
    assert not rep["ok"].any()  # 両バンドとも真の不一致（既知年でなければ弾く）


def _geo(rows: list[tuple[str, int, int]]) -> pl.DataFrame:
    """地理保存の hub/other 相当（分類軸1本×year の測定量）を手組みする（keys に area_code を含めない）。"""
    return pl.DataFrame([{"code": c, "year": y, "population": v} for c, y, v in rows])


def test_cross_fact_conservation_accepts_known_diff_of_either_sign():
    # 地理保存（mode="conservation"）: 全国 hub == Σ県 other。known_diff_years は原資料の集計差を
    # **両符号**で受容する（equality の known_diff は diff>=0 のみ＝負符号を弾く点との対比）。
    hub = _geo([("100", 1985, 1000), ("100", 1950, 1000), ("100", 2020, 1000)])
    other = _geo([("100", 1985, 1006), ("100", 1950, 994), ("100", 2020, 1000)])
    common = {
        "keys": ["code", "year"],
        "known_diff_years": frozenset({1985, 1950}),
    }
    cons = reconcile.cross_fact(hub, other, mode="conservation", **common).sort("year")
    # 1985: diff=-6（負）／1950: diff=+6（正）／2020: match。全て ok。
    assert dict(zip(cons["year"], cons["diff"], strict=True)) == {1950: 6, 1985: -6, 2020: 0}
    assert dict(zip(cons["year"], cons["status"], strict=True)) == {
        1950: "known_diff",
        1985: "known_diff",
        2020: "match",
    }
    assert cons["ok"].all()
    # 対比: equality モードは同じ入力で負符号(1985)を弾く。
    eq = reconcile.cross_fact(hub, other, mode="equality", **common).sort("year")
    assert dict(zip(eq["year"], eq["ok"], strict=True)) == {1950: True, 1985: False, 2020: True}


def test_cross_fact_allowed_diffs_pins_magnitude_and_fails_on_drift():
    # allowed_diffs は既知差の**値**（年→Σ|diff|）を固定＝大きさが動けば known_diff 年でも失敗する
    # （area の KNOWN_DIFFS と同思想＝cleaner/transform の取り違えで既知差が変わる回帰を捕捉）。
    # 1985 は 2 セルが ±6（Σ|diff|=12）／1950 は +6（Σ|diff|=6）。
    hub = _geo([("100", 1985, 1000), ("200", 1985, 1000), ("100", 1950, 1000), ("100", 2020, 1000)])
    other = _geo([("100", 1985, 1006), ("200", 1985, 994), ("100", 1950, 994), ("100", 2020, 1000)])
    common = {"keys": ["code", "year"], "mode": "conservation"}
    # 値が一致する pin なら許容（両符号でも大きさが期待どおり）。
    ok = reconcile.cross_fact(hub, other, allowed_diffs={1985: 12, 1950: 6}, **common).sort("code", "year")
    assert dict(zip(ok["year"], ok["status"], strict=True))  # 1985/1950=known_diff・2020=match
    assert ok["ok"].all()
    # pin とズレる（1985 の期待を 12→99 に）なら、その年の全キーを弾く（他年は無傷）。
    bad = reconcile.cross_fact(hub, other, allowed_diffs={1985: 99, 1950: 6}, **common).sort("code", "year")
    verdict = {(c, y): o for c, y, o in zip(bad["code"], bad["year"], bad["ok"], strict=True)}
    assert verdict[("100", 1985)] is False and verdict[("200", 1985)] is False  # Σ|diff|≠99 で年ごと失敗
    assert verdict[("100", 1950)] is True and verdict[("100", 2020)] is True  # 他年は許容のまま
