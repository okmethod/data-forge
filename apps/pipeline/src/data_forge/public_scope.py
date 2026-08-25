"""公開範囲ポリシーの検査（流出ゲート）。

ダッシュボードの公開ビルド（build/data/**/*.parquet）に、公開範囲ポリシー
（public_scope.yaml＝SSoT）で許可していない市区町村粒度コードが混入していないかを
検査する純ロジック。CLI（`data-forge public-scope-check`）から呼ばれる。

判定ルール:
    市区町村粒度コード = 5桁 かつ 末尾3桁 ≠ 000
      （県コード XX000・全国 00000 は市区町村粒度でない＝常に許可）
    市区町村粒度コードは allow_municipalities 以外を「流出」とみなす。

検査対象は build/data 側（＝SQL 絞り込み後の公開物）に限る。pipeline の生成物は
全部入り（全市区町村）が正常なので、流出は原理的に build にしか発生しない。
このモジュールは検査対象ディレクトリ・ポリシーパスを引数で受ける汎用ツールで、
ダッシュボード固有のパスは知らない（呼び出し側＝dashboard の npm script が与える）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import yaml


@dataclass(frozen=True)
class PublicScopePolicy:
    """公開範囲ポリシー（public_scope.yaml の内容）。"""

    area_code_columns: list[str]
    allow_municipalities: frozenset[str]

    @classmethod
    def load(cls, path: str | Path) -> PublicScopePolicy:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            area_code_columns=list(raw["area_code_columns"]),
            allow_municipalities=frozenset(str(c) for c in raw["allow_municipalities"]),
        )


def is_municipality_grain(code: str) -> bool:
    """市区町村粒度コードか（5桁かつ末尾3桁≠000）。県 XX000・全国 00000 は False。"""
    return len(code) == 5 and code[2:] != "000"


def find_violations(build_data_dir: str | Path, policy: PublicScopePolicy) -> dict[str, str]:
    """build_data_dir 配下の parquet を走査し、公開範囲外の市区町村コード→検出パス例 を返す。

    policy.area_code_columns で指定した列だけを見る（人口・年など数値列の誤検知を防ぐ）。
    違反が無ければ空 dict。
    """
    root = Path(build_data_dir)
    violations: dict[str, str] = {}
    for f in sorted(root.glob("**/*.parquet")):
        names = pl.scan_parquet(f).collect_schema().names()
        for col in policy.area_code_columns:
            if col not in names:
                continue
            vals = pl.scan_parquet(f).select(pl.col(col).cast(pl.Utf8)).unique().collect().to_series().to_list()
            for v in vals:
                if v is None:
                    continue
                if is_municipality_grain(v) and v not in policy.allow_municipalities:
                    violations.setdefault(v, str(f.relative_to(root)))
    return violations
