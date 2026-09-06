"""データセット定義の共通型。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl


@dataclass(frozen=True)
class Dataset:
    """1データセットの定義。

    ソース固有の取得パラメータは `source_params` に閉じ込め、
    レジストリ自体はデータソースに依存しない語彙で保つ。
    （例: e-Stat の statsDataId は `source_params={"stats_data_id": ...}`）
    """

    key: str
    source: str  # ソース識別子（"estat" など）
    source_params: dict[str, Any]  # ソース固有の取得パラメータ
    cleaner: Callable[[pl.DataFrame], pl.DataFrame]  # tidy DF → 配布用 DF
    stem: str  # 出力ファイル名の語幹
    table_name: str  # SQLite テーブル名
    universe: str  # 母集団メタ（population/households/employed）
    index_columns: list[str] = field(default_factory=list)
    # アトム抽出時の市区町村レベルの明示上書き（None なら年から自動判定）。同じ年でも
    # e-Stat 製品ごとに level の意味が違う表（例: age5 ミクロの 2000＝令和型 level4/6）で使う。
    muni_levels: frozenset[int] | None = None


@dataclass(frozen=True)
class StitchedDataset:
    """複数の基底データセットを縫合した派生データセット（複数年を year 軸で結合）。

    各 upstream を fetch→clean した結果（同一スキーマ）を `combine.combine_years` で結合する。
    依存グラフは持たず、具体を表す最小の型。

    default_join は既定の正規化モード（CLI --join で上書き可）:
    - "union" … 各年当時の境界のまま縦積み（生）
    - "aggregate_to_base" … 合併で消えた旧コードを後継自治体へ畳み連続時系列にする（配布正典）
    - "prefecture" … 市区町村アトムを県プレフィックスで束ねる空間集約ビュー
    grain は combine_years の一意性ガードの粒度（既定＝area×sex×year。分類軸が増える fact だけ上書き）。
    preliminary_upstreams は確定集約の**後段**で継ぎ足す速報 upstream で
    `data_status=preliminary` を付与する（provenance.splice_preliminary）。
    空なら来歴列は付かない。
    """

    key: str
    upstreams: list[str]  # 基底 Dataset のキー
    title: str  # 結合表の出典メタ用タイトル
    stem: str
    table_name: str
    universe: str  # 母集団メタ（population/households/employed）
    index_columns: list[str] = field(default_factory=list)
    default_join: str = "union"
    grain: list[str] = field(default_factory=lambda: ["area_code", "sex_code", "year"])
    preliminary_upstreams: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectedDataset:
    """既製の時系列帳票（e-Stat 時系列データ製品）を area 軸で union するだけの派生。

    StitchedDataset（縫合）と対になる「射影」フロー。
    各 upstream は既に全年を持つ時系列で、disjoint な area パーティションを単純に縦積みする。
    （例: 全国 00000 ＋ 47 都道府県）
    年の縫合・合併畳み込み（area master）・速報 splice は持たない。
    つまり、combine.combine_years の重機構ではなく combine.union_areas を通る。
    分類軸が増える fact（例: 年齢区分）は grain を上書きして disjoint 検証の粒度を明示する。
    """

    key: str
    upstreams: list[str]  # 既製時系列の disjoint な area パーティション（基底 Dataset キー）
    title: str
    stem: str
    table_name: str
    universe: str  # 母集団メタ（population/households/employed）
    index_columns: list[str] = field(default_factory=list)
    grain: list[str] = field(default_factory=lambda: ["area_code", "sex_code", "year"])


# 各サブ辞書・DATASETS・get_dataset で共有するエントリ型。
DatasetEntry = Dataset | StitchedDataset | ProjectedDataset
