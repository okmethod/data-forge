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


@dataclass(frozen=True)
class CompositeDataset:
    """複数の基底データセットを合成した派生データセット（例: 複数年結合）。

    `upstreams` は基底 Dataset のキー。各 upstream を fetch→clean した結果
    （同一スキーマ）を `combine.combine_years` で結合する。汎用の依存グラフは
    まだ作らず、具体1件のみを表す最小の型（実例が2つ揃ったら再検討）。
    """

    key: str
    upstreams: list[str]  # 基底 Dataset のキー
    title: str  # 結合表の出典メタ用タイトル
    stem: str
    table_name: str
    index_columns: list[str] = field(default_factory=list)
    default_join: str = "union"  # 既定の正規化モード（CLI --join で上書き可）


DATASETS: dict[str, Dataset | CompositeDataset] = {
    "population_2020": Dataset(
        key="population_2020",
        source="estat",
        source_params={"stats_data_id": "0003445078"},
        cleaner=population.clean_2020,
        stem="census_population_2020",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 別年（2015年, 0003149040）。2015表は2020表と軸設計が全く異なる
    # （tab軸なし・cat01=全域/DID・cat02に表章事項＋男女が統合）ため、
    # 2015専用の clean_2015 で 2020 と同一の8列スキーマへ写像する。
    "population_2015": Dataset(
        key="population_2015",
        source="estat",
        source_params={"stats_data_id": "0003149040"},
        cleaner=population.clean_2015,
        stem="census_population_2015",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 別年（2005年, 0003408216）。第3の構造: cat01に測定項目＋男女が融合・DID軸なし。
    "population_2005": Dataset(
        key="population_2005",
        source="estat",
        source_params={"stats_data_id": "0003408216"},
        cleaner=population.clean_2005,
        stem="census_population_2005",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 別年（2010年, 0003038587）。2015と同じ平成型エンコードだが cat02 コード体系が異なる。
    "population_2010": Dataset(
        key="population_2010",
        source="estat",
        source_params={"stats_data_id": "0003038587"},
        cleaner=population.clean_2010,
        stem="census_population_2010",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 派生: 2005〜2020 を結合した男女別人口の時系列テーブル。
    "population_timeseries": CompositeDataset(
        key="population_timeseries",
        upstreams=[
            "population_2005",
            "population_2010",
            "population_2015",
            "population_2020",
        ],
        title="国勢調査 男女別人口 時系列（2005年・2010年・2015年・2020年）",
        stem="census_population_timeseries",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
    ),
}


def get_dataset(key: str) -> Dataset | CompositeDataset:
    try:
        return DATASETS[key]
    except KeyError:
        available = ", ".join(sorted(DATASETS))
        raise KeyError(f"未知のデータセット: {key!r}（利用可能: {available}）") from None
