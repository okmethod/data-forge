"""来歴（provenance）語彙: 各行の値がどの確からしさで得られたかを表す `data_status` 列。

出力契約の一部だが、特定の処理層（combine=縦結合 / aggregate=合併集約）に属さない
横断的な語彙なので中立モジュールに置く。
将来 `estimated` / `interpolated` 等を足す付与者が combine とは限らないため（例: 補間ステップ）、
ここを単一の真実源にする。

- `confirmed`   … 確定値（既定。過去の確定集計）。
- `preliminary` … 速報値（後で確定へ置換される暫定）。

値は `enum.Enum` でなく `Literal` で持つ（既存 `combine.Mode` の流儀に合わせる）。
許容集合 `VALUES` は型 `DataStatus` から `get_args` で導出し、値の二重記述を避ける。
軸は「値の出自」というカテゴリカルな次元なので `is_preliminary`(bool) は採らない。
（`estimated` / `interpolated` 等の 3 値目が出た瞬間 bool は破壊的変更になり、組合せも曖昧になる）
"""

from collections.abc import Sequence
from typing import Literal, get_args

import polars as pl

COLUMN = "data_status"

# 来歴の値集合。拡張時はこの Literal に 1 語足すだけ（他は無改修）。
DataStatus = Literal["confirmed", "preliminary"]
VALUES: frozenset[str] = frozenset(get_args(DataStatus))


def assert_status(df: pl.DataFrame) -> None:
    """`data_status` 列が許容集合内であることを保証する（静かに通さない＝ `_assert_grain` 流儀）。"""
    if COLUMN not in df.columns:
        raise ValueError(f"{COLUMN!r} 列が無い（来歴列は splice_preliminary で付与する）")
    bad = set(df.get_column(COLUMN).unique().to_list()) - VALUES
    if bad:
        raise ValueError(f"未知の {COLUMN}: {sorted(bad)}（許容: {sorted(VALUES)}）")


def splice_preliminary(
    confirmed: pl.DataFrame,
    preliminary: pl.DataFrame,
    *,
    grain: Sequence[str],
) -> pl.DataFrame:
    """確定ビューに速報行を継ぎ足し、`data_status` 来歴列で両者を明示する。

    確定側（合併集約などの機械を通り終えた最終ビュー）に `confirmed`、
    速報側に `preliminary` を付与して縦結合する。
    速報は最新境界＝合併 rollup 不要なので、集約の**後段**で
    ここに合流させることで area 集約（共有ハブ）を無改修に保つ。
    後段に置くのが要点＝`aggregate.py` は列を「値=sum」「code↔label ペア」の 2 種しかモデル化せず、aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    来歴列は第 3 種で `.select(atom_fact.columns)` に落とされ共有ハブも汚す。
    よって集約の機械には通さず、畳み終えた最終ビューにだけ足す。

    `grain`（fact 依存＝area×sex×year 等）で確定と速報が同一セルを重複させないことを
    保証する（速報年が既に確定で存在する等の取り違えを静かに通さない）。
    """
    if set(confirmed.columns) != set(preliminary.columns):
        raise ValueError(
            f"confirmed と preliminary の列が不一致: "
            f"{sorted(set(confirmed.columns) ^ set(preliminary.columns))}"
        )
    tagged_confirmed = confirmed.with_columns(pl.lit("confirmed").alias(COLUMN))
    tagged_preliminary = preliminary.select(confirmed.columns).with_columns(
        pl.lit("preliminary").alias(COLUMN)
    )
    out = pl.concat([tagged_confirmed, tagged_preliminary], how="vertical")

    grain = list(grain)
    dup = out.group_by(grain).len().filter(pl.col("len") > 1)
    if dup.height:
        sample = dup.head(3).to_dicts()
        raise ValueError(
            f"来歴 splice の粒度違反: {tuple(grain)} が重複 {dup.height} 件（例: {sample}）。"
            "速報年が確定側に既に存在していないか確認すること。"
        )

    assert_status(out)
    sort_keys = ["area_code", "year", *(c for c in grain if c not in ("area_code", "year"))]
    return out.sort(sort_keys)
