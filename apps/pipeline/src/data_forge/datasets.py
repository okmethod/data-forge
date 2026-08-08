"""データセット定義レジストリ。

新しいデータセット（統計表）の追加は、原則このファイルにエントリを
1つ足すだけで済むようにする。ソース固有の取得・整形処理は
sources/ 以下の関数を参照する。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from data_forge.sources.estat import population


@dataclass(frozen=True)
class Dataset:
    """1データセットの定義。

    ソース固有の取得パラメータは `source_params` に閉じ込め、レジストリ自体は
    データソースに依存しない語彙で保つ（例: e-Stat の statsDataId は
    `source_params={"stats_data_id": ...}`）。
    """

    key: str
    source: str  # ソース識別子（"estat" など）
    source_params: dict[str, Any]  # ソース固有の取得パラメータ
    cleaner: Callable[[pl.DataFrame], pl.DataFrame]  # tidy DF → 配布用 DF
    stem: str  # 出力ファイル名の語幹
    table_name: str  # SQLite テーブル名
    index_columns: list[str] = field(default_factory=list)


DATASETS: dict[str, Dataset] = {
    "population": Dataset(
        key="population",
        source="estat",
        source_params={"stats_data_id": "0003445078"},
        cleaner=population.clean,
        stem="census_population_2020",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
}


def get_dataset(key: str) -> Dataset:
    try:
        return DATASETS[key]
    except KeyError:
        available = ", ".join(sorted(DATASETS))
        raise KeyError(f"未知のデータセット: {key!r}（利用可能: {available}）") from None
