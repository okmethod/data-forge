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
