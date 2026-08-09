"""地域参照層（アトム軸スタースキーマ）のテスト。

アトム抽出（政令市=市1・東京特別区=各1・旧内訳/集計行の除外）、合併イベントの
rollup（推移閉包・基準年カットオフ）、基準年集約（人口保存）、reconcile（孤児検出）を
手組みの階層・fact・イベントで検証する。
"""

import polars as pl

from data_forge.area import aggregate, atoms, events, mapping, reconcile

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
    agg = aggregate.aggregate_to_base(fact, ev, base_year=2010).select(
        "area_code", "year", "sex_code", "population"
    )
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
    #（さもないと 年少+生産+老年+不詳 の二重計上で atom_sum が総数の2倍になる）。
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

    national = pl.DataFrame(
        {"year": [2005, 2020], "sex_code": ["0", "0"], "population": [140, 150]}
    )
    cons = reconcile.national_conservation(fact, national)
    assert cons["ok"].to_list() == [True, True]


def test_conservation_known_diff_is_accepted():
    # 1980 は既知差分 37（区未定分）を受容＝ok。他年の diff=0 も ok。値は KNOWN_DIFFS で固定。
    assert reconcile.KNOWN_DIFFS[1980] == 37
    fact = _fact([("01201", "A市", 1980, 100 - 37), ("01201", "A市", 2020, 150)])
    national = pl.DataFrame(
        {"year": [1980, 2020], "sex_code": ["0", "0"], "population": [100, 150]}
    )
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
