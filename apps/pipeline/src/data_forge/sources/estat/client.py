"""e-Stat REST API の薄いクライアント（getStatsData / getStatsList）。

appId の注入と `NEXT_KEY` ページングの吸収のみを担う汎用層。
特定の統計表に依存しないため、他の statsDataId でも再利用できる。
"""

from typing import Any

import httpx

from data_forge.config import get_estat_app_id

_API_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"  # ホスト＋APIバージョン（共通）
_DATA_URL = f"{_API_BASE}/getStatsData"
_LIST_URL = f"{_API_BASE}/getStatsList"
_LIMIT = 100_000  # 1リクエストの最大取得件数（e-Stat 既定値）


def _raise_for_api_error(data: dict[str, Any], root_key: str) -> None:
    """e-Stat はHTTP 200でもRESULTブロックにエラーを返すため明示チェック。"""
    result = data.get(root_key, {}).get("RESULT", {})
    status = result.get("STATUS")
    if status not in (0, None):
        raise RuntimeError(f"e-Stat API エラー (STATUS={status}): {result.get('ERROR_MSG')}")


def _get_json(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET して JSON を返す共通 transport。e-Stat の RESULT 検査は呼び出し側の責務。"""
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def _fetch_data_page(
    client: httpx.Client,
    app_id: str,
    stats_data_id: str,
    *,
    start_position: int | None,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """getStatsData の1ページ分を取得する（NEXT_KEY ページングの1単位）。

    `filters` はサーバ側の絞り込みパラメータ（例: `{"cdCat03": "T01,200,201"}`）。
    巨大表を必要なコードだけに絞って取得件数を抑えるのに使う。
    """
    params: dict[str, Any] = {
        "appId": app_id,
        "statsDataId": stats_data_id,
        "limit": _LIMIT,
    }
    if filters:
        params.update(filters)
    if start_position is not None:
        params["startPosition"] = start_position

    data = _get_json(client, _DATA_URL, params)
    _raise_for_api_error(data, "GET_STATS_DATA")
    return data


def _as_list(value: Any) -> list[Any]:
    """e-Stat は要素1件だと配列でなく単一 dict を返すため常にリスト化する。"""
    if isinstance(value, list):
        return value
    return [value]


def get_stats_list(
    *,
    stats_code: str | None = None,
    search_word: str | None = None,
    survey_years: str | None = None,
    search_kind: int | None = None,
    limit: int | None = None,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """帳票リスト（統計表の一覧）を検索し、各表のメタ情報 dict のリストを返す。

    getStatsData の対になる getStatsList を叩く探索用の薄い層。データ本体ではなく
    statsDataId・表題・調査年などのメタデータだけを返すため、目当ての statsDataId を
    素早く突き止めるのに使う。渡された絞り込み条件のみをそのままクエリに載せる。

    該当なし（STATUS=1）は例外にせず空リストを返す（探索では「0件」も正常な結果）。
    """
    app_id = get_estat_app_id()
    params: dict[str, Any] = {"appId": app_id}
    if stats_code is not None:
        params["statsCode"] = stats_code
    if search_word is not None:
        params["searchWord"] = search_word
    if survey_years is not None:
        params["surveyYears"] = survey_years
    if search_kind is not None:
        params["searchKind"] = search_kind
    if limit is not None:
        params["limit"] = limit

    with httpx.Client(timeout=timeout) as client:
        data = _get_json(client, _LIST_URL, params)

    result = data.get("GET_STATS_LIST", {}).get("RESULT", {})
    if result.get("STATUS") == 1:  # 該当データなし
        return []
    _raise_for_api_error(data, "GET_STATS_LIST")

    datalist = data["GET_STATS_LIST"]["DATALIST_INF"]
    tables = datalist.get("TABLE_INF")
    return _as_list(tables) if tables else []


def get_stats_data(
    stats_data_id: str, *, timeout: float = 60.0, filters: dict[str, str] | None = None
) -> dict[str, Any]:
    """statsDataId を指定して統計データを全件取得し、生レスポンス dict を返す。

    総件数が1リクエスト上限を超える場合は `NEXT_KEY` で追従し、
    追加ページの VALUE を1つ目のレスポンスにマージして返す。
    `filters` はサーバ側の絞り込みパラメータ（`_fetch_data_page` 参照）。
    """
    app_id = get_estat_app_id()

    with httpx.Client(timeout=timeout) as client:
        first = _fetch_data_page(client, app_id, stats_data_id, start_position=None, filters=filters)
        stat_data = first["GET_STATS_DATA"]["STATISTICAL_DATA"]
        values = _as_list(stat_data["DATA_INF"]["VALUE"])

        next_key = stat_data["RESULT_INF"].get("NEXT_KEY")
        while next_key:
            page = _fetch_data_page(client, app_id, stats_data_id, start_position=next_key, filters=filters)
            page_stat = page["GET_STATS_DATA"]["STATISTICAL_DATA"]
            values.extend(_as_list(page_stat["DATA_INF"]["VALUE"]))
            next_key = page_stat["RESULT_INF"].get("NEXT_KEY")

    # マージした全 VALUE で差し替え
    stat_data["DATA_INF"]["VALUE"] = values
    return first
