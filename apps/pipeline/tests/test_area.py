"""地域参照層（アトム軸スタースキーマ）のテスト。

アトム抽出（政令市=市1・東京特別区=各1・旧内訳/集計行の除外）、合併イベントの
rollup（推移閉包・基準年カットオフ）、基準年集約（人口保存）、reconcile（孤児検出）を
手組みの階層・fact・イベントで検証する。
"""

import polars as pl

from data_forge.area import aggregate, atoms, events, mapping, reconcile, spatial_rollup

# --- 合成 area 階層（令和型 level を模す）---
# 通常市 A(01201)・B(01202)、政令市 P(27100)+行政区(level5)、東京特別区部(13100)+2区(level4)
_HIER = pl.DataFrame(
    {
        "code": ["01201", "01202", "27100", "27101", "27102", "13100", "13101", "13102", "01999"],
        "name": ["A市", "B市", "P市", "P区1", "P区2", "特別区部", "W区", "X区", "旧B町"],
        "level": [4, 4, 4, 5, 5, 4, 4, 4, 7],
        "parent_code": [
            "01000",
            "01000",
            "27000",
            "27100",
            "27100",
            "13000",
            "13100",
            "13100",
            "01202",
        ],
    },
    schema={"code": pl.Utf8, "name": pl.Utf8, "level": pl.Int8, "parent_code": pl.Utf8},
)


def _fact(rows: list[tuple[str, str, int, int]]) -> pl.DataFrame:
    """(area_code, area_name, year, population) の総数行から最小 fact を作る。"""
    return pl.DataFrame(
        {
            "area_code": [r[0] for r in rows],
            "area_name": [r[1] for r in rows],
            "area_level": [4 for _ in rows],
            "sex_code": ["0" for _ in rows],
            "sex": ["総数" for _ in rows],
            "year": [r[2] for r in rows],
            "population": [r[3] for r in rows],
            "is_current": [True for _ in rows],
        }
    )


def _age_fact(rows: list[tuple[str, str, int, dict[str, int]]]) -> pl.DataFrame:
    """(area_code, area_name, year, {age_class_code: population}) から年齢3区分 fact を作る。

    総数(age=0)は 年少(1)+生産(2)+老年(3)+不詳(9) を自動合算して補う。sex は総数のみ。
    population_by_age（10列）の grain を area 集約でも通せるか検証するための最小 fact。
    """
    _AGE_NAME = {"0": "総数", "1": "年少", "2": "生産", "3": "老年", "9": "不詳"}
    recs: list[dict] = []
    for area_code, area_name, year, parts in rows:
        full = {**parts, "0": sum(parts.values())}
        for age_code in ("0", "1", "2", "3", "9"):
            recs.append(
                {
                    "area_code": area_code,
                    "area_name": area_name,
                    "area_level": 4,
                    "sex_code": "0",
                    "sex": "総数",
                    "age_class_code": age_code,
                    "age_class": _AGE_NAME[age_code],
                    "year": year,
                    "population": full[age_code],
                    "is_current": True,
                }
            )
    return pl.DataFrame(recs)


def test_leaf_codes_grain():
    leaves = set(atoms.leaf_codes(_HIER, year=2020).to_list())
    # 通常市・政令市本体・東京23区は残る。行政区・特別区部・旧内訳は落ちる。
    assert leaves == {"01201", "01202", "27100", "13101", "13102"}


def test_leaf_codes_muni_levels_override():
    # 2000 の既定は level3=市区町村（人口時系列製品）。令和型 level4/6 の _HIER では level3 が無く、
    # 東京特別区（parent=13100）だけが葉に残る（level4 の通常市/政令市は拾われない）。
    assert set(atoms.leaf_codes(_HIER, year=2000).to_list()) == {"13101", "13102"}
    # 同じ 2000 でも muni_levels={4,6} を明示上書きすると 2020 と同じアトム集合になる（age5 旗艦の 2000＝32965）。
    over = set(atoms.leaf_codes(_HIER, year=2000, muni_levels=frozenset({4, 6})).to_list())
    assert over == {"01201", "01202", "27100", "13101", "13102"}


def test_rollup_transitive_and_cutoff():
    ev = pl.DataFrame(
        {
            "old_code": ["B", "C"],
            "successor_code": ["C", "E"],
            "year": [2008, 2013],
            "kind": [None, None],
        },
        schema=events.EVENTS_SCHEMA,
    )
    # base 2020: B→C→E を推移閉包で E まで畳む
    roll = mapping.rollup(ev, base_year=2020)
    m = dict(zip(roll["code"].to_list(), roll["base_code"].to_list(), strict=True))
    assert m["B"] == "E" and m["C"] == "E"
    # base 2010: 2013 の C→E は未適用。B→C まで
    roll2 = mapping.rollup(ev, base_year=2010)
    m2 = dict(zip(roll2["code"].to_list(), roll2["base_code"].to_list(), strict=True))
    assert m2["B"] == "C" and "C" not in m2


def test_aggregate_folds_predecessor_and_conserves():
    # 2005: A,B 別々 / 2010: B が A へ合併済み（Bは消滅、Aに人口集約済み）
    fact = _fact(
        [
            ("01201", "A市", 2005, 100),
            ("01202", "B市", 2005, 40),
            ("01201", "A市", 2010, 150),
        ]
    )
    ev = pl.DataFrame(
        {"old_code": ["01202"], "successor_code": ["01201"], "year": [2008], "kind": [None]},
        schema=events.EVENTS_SCHEMA,
    )
    out = aggregate.aggregate_to_base(fact, ev, base_year=2020)
    # 2005 の A 境界（2020基準）= 旧A 100 + 旧B 40 = 140
    a2005 = out.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2005))
    assert a2005["population"][0] == 140
    # B は base_year に存在しないので独立行として残らない（A へ畳まれた）
    assert out.filter(pl.col("area_code") == "01202").height == 0
    # 総人口は各年で保存（2005: 140, 2010: 150）
    tot = out.group_by("year").agg(pl.col("population").sum()).sort("year")
    assert tot["population"].to_list() == [140, 150]


def test_crosswalk_keeps_atoms_and_groupby_equals_aggregate():
    # 2005: A,B 別々 / 2010: B が A へ合併済み
    fact = _fact(
        [
            ("01201", "A市", 2005, 100),
            ("01202", "B市", 2005, 40),
            ("01201", "A市", 2010, 150),
        ]
    )
    ev = pl.DataFrame(
        {"old_code": ["01202"], "successor_code": ["01201"], "year": [2008], "kind": [None]},
        schema=events.EVENTS_SCHEMA,
    )
    cw = aggregate.attach_crosswalk(fact, ev, base_year=2010)
    # 畳まない: 行数は原アトムと同じ（B も原境界で残る）
    assert cw.height == fact.height
    # base_code: B は後継 A、A は自分自身。base_name は base_year(=2010)の名称
    b = cw.filter(pl.col("area_code") == "01202").row(0, named=True)
    assert b["base_code"] == "01201" and b["base_name"] == "A市"
    a = cw.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2005)).row(0, named=True)
    assert a["base_code"] == "01201"
    # GROUP BY base_code は aggregate_to_base と一致（畳む/畳まないは同じ rollup の2ビュー）
    grouped = (
        cw.group_by(["base_code", "year", "sex_code"])
        .agg(pl.col("population").sum())
        .rename({"base_code": "area_code"})
        .sort("area_code", "year", "sex_code")
    )
    agg = aggregate.aggregate_to_base(fact, ev, base_year=2010).select("area_code", "year", "sex_code", "population")
    assert grouped.sort("area_code", "year", "sex_code").to_dicts() == agg.to_dicts()


def test_aggregate_by_age_folds_and_conserves_age():
    # Phase 2: 年齢3区分 fact でも合併集約が通り、集約後も年齢保存が成立する。
    fact = _age_fact(
        [
            ("01201", "A市", 2005, {"1": 30, "2": 50, "3": 15, "9": 5}),  # 総数100
            ("01202", "B市", 2005, {"1": 10, "2": 20, "3": 8, "9": 2}),  # 総数40
            ("01201", "A市", 2010, {"1": 40, "2": 70, "3": 35, "9": 5}),  # 総数150
        ]
    )
    ev = pl.DataFrame(
        {"old_code": ["01202"], "successor_code": ["01201"], "year": [2008], "kind": [None]},
        schema=events.EVENTS_SCHEMA,
    )
    out = aggregate.aggregate_to_base(fact, ev, base_year=2020)
    # 出力スキーマは入力(10列)を踏襲＝age_class 軸が畳まれず各区分が残る
    assert out.columns == fact.columns
    # A の 2005 境界（2020基準）= 旧A + 旧B を age_class ごとに合算
    a2005 = out.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2005))
    by_age = dict(zip(a2005["age_class_code"].to_list(), a2005["population"].to_list(), strict=True))
    assert by_age == {"0": 140, "1": 40, "2": 70, "3": 23, "9": 7}
    # 年齢保存: 年少+生産+老年+不詳 == 総数（集約後も恒等成立）
    assert by_age["1"] + by_age["2"] + by_age["3"] + by_age["9"] == by_age["0"]
    # B は base_year に存在せず A へ畳まれる
    assert out.filter(pl.col("area_code") == "01202").height == 0


def test_national_conservation_by_age_uses_total_slice():
    # Phase 2: 全国行が age_class 別でも、総数×総数スライスだけで人口保存を検査する
    # （さもないと 年少+生産+老年+不詳 の二重計上で atom_sum が総数の2倍になる）。
    fact = _age_fact(
        [
            ("01201", "A市", 2020, {"1": 40, "2": 70, "3": 35, "9": 5}),  # 総数150
        ]
    )
    national = _age_fact([("00000", "全国", 2020, {"1": 40, "2": 70, "3": 35, "9": 5})])
    cons = reconcile.national_conservation(fact, national)
    assert cons["national"].to_list() == [150]  # 総数のみ拾う
    assert cons["atom_sum"].to_list() == [150]
    assert cons["ok"].to_list() == [True]


def test_orphans_by_age_dedups_to_total():
    # Phase 2: 年齢別行があってもアトム毎に総数1行へ絞って孤児判定する。
    fact = _age_fact(
        [
            ("01201", "A市", 2005, {"1": 30, "2": 50, "3": 15, "9": 5}),
            ("01202", "B市", 2005, {"1": 10, "2": 20, "3": 8, "9": 2}),  # 2020に無く孤児
            ("01201", "A市", 2020, {"1": 40, "2": 70, "3": 35, "9": 5}),
        ]
    )
    empty = pl.DataFrame(schema=events.EVENTS_SCHEMA)
    orph = reconcile.orphans(fact, empty, base_year=2020)
    assert orph["area_code"].to_list() == ["01202"]
    assert orph["last_population"].to_list() == [40]  # 総数（年齢別の重複でなく）


def _daynight_fact(rows: list[tuple[str, str, int, int, int]]) -> pl.DataFrame:
    """(area_code, area_name, year, night, day) から昼夜間人口 fact を作る（8列・sex 軸なし）。

    daynight_code="0"=夜間(常住地)/"1"=昼間(従業地通学地)。sex/age のような入れ子でなく、
    "1" は "0" へ合算されない並列母集団＝一般化（`*_code` 自動判別）の3例目検証用。
    """
    recs: list[dict] = []
    for area_code, area_name, year, night, day in rows:
        for code, name, val in (
            ("0", "夜間人口（常住地）", night),
            ("1", "昼間人口（従業地・通学地）", day),
        ):
            recs.append(
                {
                    "area_code": area_code,
                    "area_name": area_name,
                    "area_level": 4,
                    "daynight_code": code,
                    "daynight": name,
                    "year": year,
                    "population": val,
                    "is_current": True,
                }
            )
    return pl.DataFrame(recs)


def test_aggregate_daynight_parallel_axis_folds_independently():
    # 3例目: 昼夜間人口（sex なし・"1" は "0" の内訳でない並列母集団）でも
    # 合併集約が daynight_code ごとに独立に畳まれ、総数スライスは夜間(0)のみを拾う。
    fact = _daynight_fact(
        [
            ("01201", "A市", 2005, 100, 120),  # 夜間100/昼間120（流入超）
            ("01202", "B市", 2005, 40, 30),  # 夜間40/昼間30（流出超）
            ("01201", "A市", 2010, 150, 170),
        ]
    )
    ev = pl.DataFrame(
        {"old_code": ["01202"], "successor_code": ["01201"], "year": [2008], "kind": [None]},
        schema=events.EVENTS_SCHEMA,
    )
    out = aggregate.aggregate_to_base(fact, ev, base_year=2020)
    assert out.columns == fact.columns  # 入力8列を踏襲（daynight 軸が残る）
    a2005 = out.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2005))
    by = dict(zip(a2005["daynight_code"].to_list(), a2005["population"].to_list(), strict=True))
    # 夜間・昼間それぞれ 旧A+旧B を独立に合算（夜間140 / 昼間150）
    assert by == {"0": 140, "1": 150}
    assert out.filter(pl.col("area_code") == "01202").height == 0  # B は A へ畳まれる

    # 総数スライス（全 *_code=="0"）＝夜間のみ。国民保存は夜間人口で成立する。
    national = _daynight_fact([("00000", "全国", 2005, 140, 150)])
    cons = reconcile.national_conservation(fact, national)
    assert cons["national"].to_list() == [140]  # 昼間(150)を拾わず夜間総数のみ
    assert cons["atom_sum"].to_list() == [140]
    assert cons["ok"].to_list() == [True]


def test_aggregate_to_admin_prefecture_sums_and_names():
    # 市区町村を県コード先頭2桁で束ね、実 JIS コード XX000・県名・level2・現存 になる。
    fact = _fact(
        [
            ("13101", "千代田区", 2020, 60),
            ("13102", "中央区", 2020, 40),
            ("14100", "横浜市", 2020, 370),
        ]
    )
    out = spatial_rollup.aggregate_to_admin(fact, level="prefecture")
    assert out.columns == fact.columns  # 入力スキーマを踏襲
    tokyo = out.filter(pl.col("area_code") == "13000").row(0, named=True)
    assert tokyo["area_name"] == "東京都"
    assert tokyo["population"] == 100  # 60+40
    assert tokyo["area_level"] == 2 and tokyo["is_current"] is True
    assert out.filter(pl.col("area_code") == "14000")["population"][0] == 370


def test_aggregate_to_admin_region_folds_prefectures():
    # 東京(13)・神奈川(14)は共に関東(R3)へ、北海道(01)は北海道地方(R1)へ束ねる（標準8区分）。
    fact = _fact(
        [
            ("13101", "千代田区", 2020, 100),
            ("14100", "横浜市", 2020, 370),
            ("01100", "札幌市", 2020, 200),
        ]
    )
    out = spatial_rollup.aggregate_to_admin(fact, level="region")
    kanto = out.filter(pl.col("area_code") == "R3").row(0, named=True)
    assert kanto["area_name"] == "関東地方"
    assert kanto["population"] == 470  # 東京+神奈川
    assert kanto["area_level"] == 0
    assert out.filter(pl.col("area_code") == "R1")["population"][0] == 200  # 北海道地方


def test_aggregate_to_admin_conserves_national_and_keeps_axis():
    # 県合計 == 全国 を national_conservation で確認（by_age の総数×総数スライスでも成立）。
    fact = _age_fact(
        [
            ("13101", "千代田区", 2020, {"1": 10, "2": 40, "3": 8, "9": 2}),  # 総数60
            ("14100", "横浜市", 2020, {"1": 60, "2": 250, "3": 55, "9": 5}),  # 総数370
        ]
    )
    pref = spatial_rollup.aggregate_to_admin(fact, level="prefecture")
    assert pref.columns == fact.columns  # age_class 軸は畳まれず保持
    # 東京の年齢別も県内で合算されている（千代田のみ→総数60・年少10…）
    tokyo_age = dict(
        zip(
            pref.filter(pl.col("area_code") == "13000")["age_class_code"].to_list(),
            pref.filter(pl.col("area_code") == "13000")["population"].to_list(),
            strict=True,
        )
    )
    assert tokyo_age == {"0": 60, "1": 10, "2": 40, "3": 8, "9": 2}
    national = _age_fact([("00000", "全国", 2020, {"1": 70, "2": 290, "3": 63, "9": 7})])  # 430
    cons = reconcile.national_conservation(pref, national)
    assert cons["national"].to_list() == [430]
    assert cons["atom_sum"].to_list() == [430]  # 県合計＝全国
    assert cons["ok"].to_list() == [True]


def test_events_override_wins_and_ignore(tmp_path):
    parsed = tmp_path / "p.csv"
    over = tmp_path / "o.csv"
    parsed.write_text("old_code,successor_code,year,kind\nB,WRONG,2008,編入\nD,E,2008,編入\n")
    # B は正しい後継へ置換、D は空後継で無効化
    over.write_text("old_code,successor_code,year,kind\nB,C,2008,編入\nD,,2008,\n")
    ev = events.load_events(parsed_path=parsed, overrides_path=over)
    m = dict(zip(ev["old_code"].to_list(), ev["successor_code"].to_list(), strict=True))
    assert m == {"B": "C"}  # D は無効化、B は override 優先


def test_reconcile_orphans_flags_unmapped():
    fact = _fact(
        [
            ("01201", "A市", 2005, 100),
            ("01202", "B市", 2005, 40),  # 2020 に存在せず・イベント無し＝孤児
            ("01201", "A市", 2020, 150),
        ]
    )
    empty = pl.DataFrame(schema=events.EVENTS_SCHEMA)
    orph = reconcile.orphans(fact, empty, base_year=2020)
    assert orph["area_code"].to_list() == ["01202"]

    national = pl.DataFrame({"year": [2005, 2020], "sex_code": ["0", "0"], "population": [140, 150]})
    cons = reconcile.national_conservation(fact, national)
    assert cons["ok"].to_list() == [True, True]


def test_conservation_known_diff_is_accepted():
    # 1980 は既知差分 37（区未定分）を受容＝ok。他年の diff=0 も ok。値は KNOWN_DIFFS で固定。
    assert reconcile.KNOWN_DIFFS[1980] == 37
    fact = _fact([("01201", "A市", 1980, 100 - 37), ("01201", "A市", 2020, 150)])
    national = pl.DataFrame({"year": [1980, 2020], "sex_code": ["0", "0"], "population": [100, 150]})
    cons = reconcile.national_conservation(fact, national).sort("year")
    assert cons["diff"].to_list() == [37, 0]
    assert cons["ok"].to_list() == [True, True]  # 既知差分は許容
    assert cons["known"].to_list() == [True, False]  # 1980 のみ「受容した既知差分」


def test_conservation_unknown_diff_still_fails():
    # 既知差分と違う値（40≠37）は依然 NG＝新規混入を検知できる。
    fact = _fact([("01201", "A市", 1980, 60)])
    national = pl.DataFrame({"year": [1980], "sex_code": ["0"], "population": [100]})
    cons = reconcile.national_conservation(fact, national)
    assert cons["diff"].to_list() == [40]
    assert cons["ok"].to_list() == [False]
    assert cons["known"].to_list() == [False]


# --- クロスファクト検算（cross_fact）: 別ソース由来の総人口を共有軸で三角測量 ---


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
