"""地域参照層（アトム軸スタースキーマ）のテスト。

アトム抽出（政令市=市1・東京特別区=各1・旧内訳/集計行の除外）、合併イベントの
rollup（推移閉包・基準年カットオフ）、基準年集約（人口保存）、reconcile（孤児検出）を
手組みの階層・fact・イベントで検証する。
"""

import polars as pl

from data_forge import known_pins
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
    # 同じ 2000 でも muni_levels={4,6} を明示上書きすると 2020 と同じアトム集合になる（age5 ミクロの 2000＝32965）。
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


def test_aggregate_multi_measure_folds_each_and_preserves_null_year():
    # households（2測度＝households/household_members）でも合併集約が測度ごとに独立に合算される。
    # 世帯人員は 2015/2020 のみ実在（他年 null）＝全 null の fold 群は 0 でなく null を保つ
    # （sum_measure_expr の null 保持。素の sum なら「未計測」を「値0」に潰す回帰を捕捉）。
    fact = pl.DataFrame(
        [
            # 2000: 旧A・旧B（後に合併）。世帯人員は当時ミクロ表に無く null。
            {"area_code": "01201", "area_name": "A市", "area_level": 4, "household_type_code": "100",
             "household_type": "総数", "year": 2000, "households": 100, "household_members": None, "is_current": True},
            {"area_code": "01202", "area_name": "B市", "area_level": 4, "household_type_code": "100",
             "household_type": "総数", "year": 2000, "households": 40, "household_members": None, "is_current": True},
            # 2020: 合併後の A（世帯人員あり）。
            {"area_code": "01201", "area_name": "A市", "area_level": 4, "household_type_code": "100",
             "household_type": "総数", "year": 2020, "households": 150, "household_members": 320, "is_current": True},
        ]
    )  # fmt: skip
    ev = pl.DataFrame(
        {"old_code": ["01202"], "successor_code": ["01201"], "year": [2008], "kind": [None]},
        schema=events.EVENTS_SCHEMA,
    )
    out = aggregate.aggregate_to_base(fact, ev, base_year=2020)
    assert out.columns == fact.columns  # 2測度とも踏襲
    a2000 = out.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2000)).row(0, named=True)
    assert a2000["households"] == 140  # 旧A+旧B を合算
    assert a2000["household_members"] is None  # 全 null 群は 0 でなく null（未計測を保つ）
    a2020 = out.filter((pl.col("area_code") == "01201") & (pl.col("year") == 2020)).row(0, named=True)
    assert a2020["household_members"] == 320  # 実在年はそのまま


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


def test_dangling_successors_flags_nonexistent_target():
    # 01202→01201 は実在(01201 はアトム)、01202→99999 は着地先が宇宙に無い＝指定ミス。
    fact = _fact([("01201", "A市", 2020, 150), ("01202", "B市", 2005, 40)])
    ev = pl.DataFrame(
        {
            "old_code": ["01202", "01203"],
            "successor_code": ["01201", "99999"],
            "year": [2008, 2008],
            "kind": [None, None],
        },
        schema=events.EVENTS_SCHEMA,
    )
    bad = reconcile.dangling_successors(ev, fact)
    assert bad["old_code"].to_list() == ["01203"]  # 後継 99999 は実在せず


def test_dangling_successors_accepts_intermediate_chain():
    # A→B→C の多段。中間後継 B はアトムに登場しなくても old_code なので実在扱い＝dangling でない。
    fact = _fact([("C", "C市", 2020, 100)])
    ev = pl.DataFrame(
        {"old_code": ["A", "B"], "successor_code": ["B", "C"], "year": [2005, 2008], "kind": [None, None]},
        schema=events.EVENTS_SCHEMA,
    )
    assert reconcile.dangling_successors(ev, fact).height == 0


def test_stale_successors_flags_anachronistic_target():
    # 01202→01201 は 01201 が施行年(2008)後の2020に生存＝OK。
    # 01203→01900 は 01900 が施行年(2015)より前の2005にしか登場しない＝時制の取り違え。
    fact = _fact(
        [
            ("01201", "A市", 2020, 150),
            ("01900", "旧市", 2005, 30),  # 2005 にしか居ない＝以後 消滅
        ]
    )
    ev = pl.DataFrame(
        {
            "old_code": ["01202", "01203"],
            "successor_code": ["01201", "01900"],
            "year": [2008, 2015],
            "kind": [None, None],
        },
        schema=events.EVENTS_SCHEMA,
    )
    stale = reconcile.stale_successors(ev, fact)
    assert stale["old_code"].to_list() == ["01203"]


def test_stale_successors_resolves_chain_to_terminal():
    # A→B→C の多段。B は atom に居ないが終端 C は 2020 に生存＝時制OK（連鎖を吸収）。
    fact = _fact([("C", "C市", 2020, 100)])
    ev = pl.DataFrame(
        {"old_code": ["A", "B"], "successor_code": ["B", "C"], "year": [2005, 2008], "kind": [None, None]},
        schema=events.EVENTS_SCHEMA,
    )
    assert reconcile.stale_successors(ev, fact).height == 0


def test_conservation_known_diff_is_accepted():
    # 1980 は既知差分 37（区未定分）を許容＝ok。他年の diff=0 も ok。値は known_pins.CONSERVATION_DIFFS で固定。
    pins = reconcile.year_pins(known_pins.CONSERVATION_DIFFS)
    assert pins[1980] == 37
    fact = _fact([("01201", "A市", 1980, 100 - 37), ("01201", "A市", 2020, 150)])
    national = pl.DataFrame({"year": [1980, 2020], "sex_code": ["0", "0"], "population": [100, 150]})
    cons = reconcile.national_conservation(fact, national, allowed_diffs=pins).sort("year")
    assert cons["diff"].to_list() == [37, 0]
    assert cons["ok"].to_list() == [True, True]  # 既知差分は許容
    assert cons["allowed"].to_list() == [True, False]  # 1980 のみ「許容した既知差分」


def test_conservation_unknown_diff_still_fails():
    # 既知差分と違う値（40≠37）は依然 NG＝新規混入を検知できる。
    fact = _fact([("01201", "A市", 1980, 60)])
    national = pl.DataFrame({"year": [1980], "sex_code": ["0"], "population": [100]})
    pins = reconcile.year_pins(known_pins.CONSERVATION_DIFFS)
    cons = reconcile.national_conservation(fact, national, allowed_diffs=pins)
    assert cons["diff"].to_list() == [40]
    assert cons["ok"].to_list() == [False]
    assert cons["allowed"].to_list() == [False]
