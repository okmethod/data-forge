"""getStatsData レスポンスの外枠 strict 検証（構造崩れ＝即例外）。

`get(..., "")` の黙認をやめ、transform が依拠する骨格
（`GET_STATS_DATA` → `STATISTICAL_DATA` → `TABLE_INF` / `CLASS_INF` / `DATA_INF`）の
欠落・型崩れを取得時点で例外化する。検証の粒度は「外枠 strict / 内側 passthrough」:

- strict … 上記の骨格キーの存在と型。ページング用 `RESULT_INF.NEXT_KEY` は Optional で明示。
- passthrough … `VALUE[]` や `CLASS` の中身。軸名（@tab/@cat01/@area/@time 等）は
  statsDataId ごとに変動するため固定スキーマにしない。軸の実在確認は従来どおり
  transform 側の CLASS_INF 突合に委ねる。

STATUS≠0 の意味論エラー（ERROR_MSG 同梱）は呼び出し側の `_raise_for_api_error` が
先に扱う前提のため、ここでは STATUS の値までは縛らず純粋な構造検証に徹する。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

__all__ = ["StatsDataResponse", "ValidationError", "validate_stats_data"]


class _Passthrough(BaseModel):
    """未知キーを許す（内側の可変構造を素通しする）基底。"""

    model_config = ConfigDict(extra="allow")


class ResultBlock(_Passthrough):
    STATUS: int


class ResultInf(_Passthrough):
    # ページングの続き位置。最終ページでは欠落するため Optional。
    NEXT_KEY: int | None = None


class ClassInf(_Passthrough):
    # 軸ごとのコード↔名称辞書。中身（CLASS）は軸依存のため passthrough。
    CLASS_OBJ: Any


class DataInf(_Passthrough):
    # コードのみを持つファクト行。中身（@tab 等の軸キー）は passthrough。
    VALUE: Any


class StatisticalData(_Passthrough):
    TABLE_INF: dict[str, Any]
    CLASS_INF: ClassInf
    DATA_INF: DataInf
    RESULT_INF: ResultInf


class GetStatsData(_Passthrough):
    RESULT: ResultBlock
    STATISTICAL_DATA: StatisticalData


class StatsDataResponse(_Passthrough):
    GET_STATS_DATA: GetStatsData


def validate_stats_data(data: dict[str, Any]) -> None:
    """getStatsData レスポンス（1ページ分）の外枠を検証する。崩れていれば例外を送出。

    検証済みオブジェクトは使わず、崩れの検出（副作用）のみを目的とする。
    正規化（単一 dict → list）は transform 側の `_as_list` に委ねるため、ここでは行わない。
    """
    StatsDataResponse.model_validate(data)
