"""area_level セマンティクス（e-Stat area 階層）: 現存境界フラグ is_current の正典。

area_level の意味そのもの（どの level がアトムか）は [atoms.py] が持つ。
本モジュールはそのうち「旧市区町村 level7＝合併で消滅・現存でない」判定だけを切り出し、
fact 各行に付与する `is_current` 列を単一の式に集約する（source 各表 / spatial_rollup が共用）。

level7（旧市区町村）は 2020(令和型) の一部表にのみ現れ、
都道府県/地方ブロックなど上位集約後の層には概念が存在しない（＝常に現存）。
"""

import polars as pl

OBSOLETE_AREA_LEVEL = 7  # 旧市区町村（合併で消滅・現存でない）。2020 令和型の一部表のみ。


def is_current_expr() -> pl.Expr:
    """area_level が旧市区町村（level7）でない＝現存境界かを示す is_current 列式。"""
    return (pl.col("area_level") != OBSOLETE_AREA_LEVEL).alias("is_current")


def always_current_expr() -> pl.Expr:
    """level7（旧市区町村）の概念がない層（都道府県/地方）向けの is_current=True 列式。"""
    return pl.lit(True).alias("is_current")
