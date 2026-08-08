"""e-Stat REST API の薄いクライアント（getStatsData）。

appId の注入と `NEXT_KEY` ページングの吸収のみを担う汎用層。
特定の統計表に依存しないため、他の statsDataId でも再利用できる。
"""

from typing import Any

import httpx

from data_forge.config import get_estat_app_id

_BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
_LIMIT = 100_000  # 1リクエストの最大取得件数（e-Stat 既定値）


def get_stats_data(stats_data_id: str, *, timeout: float = 60.0) -> dict[str, Any]:
    """statsDataId を指定して統計データを全件取得し、生レスポンス dict を返す。

    総件数が1リクエスト上限を超える場合は `NEXT_KEY` で追従し、
    追加ページの VALUE を1つ目のレスポンスにマージして返す。
    """
    app_id = get_estat_app_id()

    with httpx.Client(timeout=timeout) as client:
        first = _request(client, app_id, stats_data_id, start_position=None)
        stat_data = first["GET_STATS_DATA"]["STATISTICAL_DATA"]
        values = _as_list(stat_data["DATA_INF"]["VALUE"])

        next_key = stat_data["RESULT_INF"].get("NEXT_KEY")
        while next_key:
            page = _request(client, app_id, stats_data_id, start_position=next_key)
            page_stat = page["GET_STATS_DATA"]["STATISTICAL_DATA"]
            values.extend(_as_list(page_stat["DATA_INF"]["VALUE"]))
            next_key = page_stat["RESULT_INF"].get("NEXT_KEY")

    # マージした全 VALUE で差し替え
    stat_data["DATA_INF"]["VALUE"] = values
    return first


def _request(
    client: httpx.Client,
    app_id: str,
    stats_data_id: str,
    *,
    start_position: int | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "appId": app_id,
        "statsDataId": stats_data_id,
        "limit": _LIMIT,
    }
    if start_position is not None:
        params["startPosition"] = start_position

    resp = client.get(_BASE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    _raise_for_api_error(data)
    return data


def _raise_for_api_error(data: dict[str, Any]) -> None:
    """e-Stat はHTTP 200でもRESULTブロックにエラーを返すため明示チェック。"""
    result = data.get("GET_STATS_DATA", {}).get("RESULT", {})
    status = result.get("STATUS")
    if status not in (0, None):
        raise RuntimeError(f"e-Stat API エラー (STATUS={status}): {result.get('ERROR_MSG')}")


def _as_list(value: Any) -> list[Any]:
    """e-Stat は要素1件だと配列でなく単一 dict を返すため常にリスト化する。"""
    if isinstance(value, list):
        return value
    return [value]
