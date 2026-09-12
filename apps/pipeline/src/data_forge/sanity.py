"""値サニティ: 配布ファクトの測定量が壊れていないか（非負）を検査する。

保存則（area-check）・クロスファクト検算（crossfact-check）は「総数どうしの一致」を見るため、
導出注入した不詳（不詳 = 総数 − Σ内訳）が負に振れても総数側は一致したままで**自明化して
捕まらない**（例 family_type / labor_force の `_inject_unknown`）。
ここは測定量そのものの値域（≥ 0）を実データで直接突き、この穴を塞ぐ。

area-check が市区町村ミクロ系列（合併畳込を持つ縫合フロー）専用なのに対し、
本検査は area master 非依存で全ファクト（射影フロー含む）に効く。
両者は守る不変条件が別で相補的。
"""

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class KnownNegative:
    """原資料由来で受容する負値セル1件（値サニティの既知例外）。

    `match`（キー列→値の全一致）で対象セルを1点特定し、`value`（負の値）を **pin** する。
    保存則の `KNOWN_DIFFS` と同じく値を明記して固定＝**ずれたら失敗**
    （cleaner/transform の取り違えで残差が動けば未知の負値として exit 1 に落ちる）。
    """

    match: dict[str, object]
    measure: str
    value: int
    reason: str

    def mask(self) -> pl.Expr:
        expr = pl.col(self.measure) == self.value
        for col, val in self.match.items():
            expr = expr & (pl.col(col) == val)
        return expr


# 受容する負値の pin 値（KNOWN_NEGATIVES）は、
# 差分値を一元管理するため他の既知差分（KNOWN_DIFFS / CROSSFACT）と同じ known_pins.py に集約する。
# 型（本 KnownNegative）とエンジンは本モジュールに残す。
# cli が known_pins から注入し、下記エンジンは spec を引数で受ける。


def measure_columns(df: pl.DataFrame) -> list[str]:
    """測定量列（数値かつ非キー）を返す。

    キーは次元コード（`*_code`＝Utf8）・年（`year`）・階層レベル（`*_level`＝整数だが次元属性）で、
    これらを除いた数値列が測定量（population / households / household_members / workers 等）。
    列名をハードコードせず dtype と命名から判定するので、新ファクトの測定量にも自動追従する。
    """
    return [
        name
        for name, dtype in df.schema.items()
        if dtype.is_numeric() and name != "year" and not name.endswith("_level")
    ]


def negative_values(df: pl.DataFrame) -> pl.DataFrame:
    """いずれかの測定量が負の行を返す（値サニティ違反）。測定量が無ければ空表。"""
    cols = measure_columns(df)
    if not cols:
        return df.clear()
    return df.filter(pl.any_horizontal(pl.col(c) < 0 for c in cols))


def unknown_negatives(df: pl.DataFrame, known: list[KnownNegative] | None = None) -> pl.DataFrame:
    """負の測定量行のうち既知例外（`known`）に該当しない＝未知の破綻行を返す（ゲート判定用）。"""
    neg = negative_values(df)
    if neg.height == 0 or not known:
        return neg
    accepted = known[0].mask()
    for spec in known[1:]:
        accepted = accepted | spec.mask()
    return neg.filter(~accepted)


def known_negative_hits(df: pl.DataFrame, known: list[KnownNegative] | None = None) -> list[tuple[KnownNegative, int]]:
    """各既知例外が実データで該当した行数を返す（受容の可視化＋レジストリ陳腐化=0件の検出用）。"""
    return [(spec, int(df.filter(spec.mask()).height)) for spec in (known or [])]


def null_measure_count(df: pl.DataFrame) -> int:
    """測定量に null を含む行数（advisory）。未収録セルの null 混入を可視化する。"""
    cols = measure_columns(df)
    if not cols:
        return 0
    return int(df.filter(pl.any_horizontal(pl.col(c).is_null() for c in cols)).height)
