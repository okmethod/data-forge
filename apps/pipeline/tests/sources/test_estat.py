"""e-Stat 取得層（client / fetch）の単体テスト（ネットワーク不要）。

実 API を叩かず、モックで以下を検証する。「未カバー領域: 実 API 取得（fetch.py）」の消化。
- client.get_stats_data: NEXT_KEY ページング追従と VALUE マージ・単一 dict の正規化
- client の RESULT 検査: HTTP 200 でも STATUS≠0 は例外／getStatsList の 0 件は空リスト
- fetch.fetch: ローカルキャッシュのヒット／ミス／refresh 強制再取得・絞り込みごとの別キャッシュ
設計の正典は docs/data-quality-assurance.md、コマンドは `uv run data-forge --help`。
"""

import pytest

from data_forge.sources.estat import client, fetch, schema


def _data_page(values, *, next_key=None, status=0):
    """getStatsData の1ページ相当のレスポンス dict を組む（外枠 strict 検証を通る最小構造）。"""
    stat_data = {
        "TABLE_INF": {"@id": "X"},
        "CLASS_INF": {"CLASS_OBJ": []},
        "DATA_INF": {"VALUE": values},
        "RESULT_INF": {} if next_key is None else {"NEXT_KEY": next_key},
    }
    return {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": status, "ERROR_MSG": "boom"},
            "STATISTICAL_DATA": stat_data,
        }
    }


# --- client: getStatsData のページング / 正規化 / エラー検査 ---


def test_get_stats_data_follows_next_key_and_merges(monkeypatch):
    pages = {
        None: _data_page([{"$": "1"}, {"$": "2"}], next_key=101),
        101: _data_page([{"$": "3"}], next_key=202),
        202: _data_page([{"$": "4"}]),
    }
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: pages[params.get("startPosition")])

    data = client.get_stats_data("0003448237")

    values = data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
    assert [v["$"] for v in values] == ["1", "2", "3", "4"]


def test_get_stats_data_normalizes_single_value_dict(monkeypatch):
    # e-Stat は VALUE が1件だと配列でなく単一 dict を返す → リスト化される。
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: _data_page({"$": "42"}))

    data = client.get_stats_data("x")

    assert data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"] == [{"$": "42"}]


def test_get_stats_data_raises_on_api_error(monkeypatch):
    # HTTP 200 でも RESULT.STATUS≠0 は RuntimeError（ERROR_MSG 同梱）。
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: _data_page([], status=1))

    with pytest.raises(RuntimeError, match="STATUS=1"):
        client.get_stats_data("x")


# --- schema: 外枠 strict 検証（構造崩れ＝即例外 / 内側 passthrough）---


def test_validate_accepts_well_formed_page():
    # 正常な骨格＋未知の軸キー（@tab 等）は passthrough で通る。
    schema.validate_stats_data(_data_page([{"@tab": "001", "$": "1"}]))


def test_validate_normalizes_nothing_but_raises_on_missing_statistical_data():
    data = {"GET_STATS_DATA": {"RESULT": {"STATUS": 0}}}  # STATISTICAL_DATA 欠落
    with pytest.raises(schema.ValidationError):
        schema.validate_stats_data(data)


@pytest.mark.parametrize("drop", ["TABLE_INF", "CLASS_INF", "DATA_INF"])
def test_validate_raises_on_missing_skeleton_key(drop):
    data = _data_page([{"$": "1"}])
    del data["GET_STATS_DATA"]["STATISTICAL_DATA"][drop]
    with pytest.raises(schema.ValidationError):
        schema.validate_stats_data(data)


def test_validate_raises_on_missing_value():
    data = _data_page([{"$": "1"}])
    del data["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
    with pytest.raises(schema.ValidationError):
        schema.validate_stats_data(data)


def test_get_stats_data_raises_on_broken_structure(monkeypatch):
    # 取得経路（_fetch_data_page）で構造崩れが例外化される（STATUS=0 でも骨格欠落は弾く）。
    broken = {"GET_STATS_DATA": {"RESULT": {"STATUS": 0}, "STATISTICAL_DATA": {}}}
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: broken)

    with pytest.raises(schema.ValidationError):
        client.get_stats_data("x")


# --- client: getStatsList の 0 件許容 / 単一 dict ラップ ---


def test_get_stats_list_returns_empty_on_no_hit(monkeypatch):
    resp = {"GET_STATS_LIST": {"RESULT": {"STATUS": 1}}}  # 該当なしは例外にせず空
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: resp)

    assert client.get_stats_list(search_word="存在しない表") == []


def test_get_stats_list_wraps_single_table(monkeypatch):
    resp = {
        "GET_STATS_LIST": {
            "RESULT": {"STATUS": 0},
            "DATALIST_INF": {"TABLE_INF": {"@id": "X"}},  # 1件だと単一 dict
        }
    }
    monkeypatch.setattr(client, "get_estat_app_id", lambda: "APPID")
    monkeypatch.setattr(client, "_get_json", lambda c, url, params: resp)

    assert client.get_stats_list(stats_code="00200521") == [{"@id": "X"}]


# --- fetch: ローカルキャッシュの挙動 ---


def test_fetch_caches_and_reuses(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get(stats_data_id, *, filters=None):
        calls.append(stats_data_id)
        return {"hello": "world"}

    monkeypatch.setattr(fetch, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch, "get_stats_data", fake_get)

    first = fetch.fetch("0003448237")
    assert first == {"hello": "world"}
    assert (tmp_path / "estat" / "0003448237.json").exists()

    # 2回目はキャッシュ再利用＝API を叩かない。
    second = fetch.fetch("0003448237")
    assert second == {"hello": "world"}
    assert calls == ["0003448237"]


def test_fetch_refresh_bypasses_cache(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get(stats_data_id, *, filters=None):
        calls.append(stats_data_id)
        return {"n": len(calls)}

    monkeypatch.setattr(fetch, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch, "get_stats_data", fake_get)

    fetch.fetch("x")
    refreshed = fetch.fetch("x", refresh=True)  # 強制再取得

    assert len(calls) == 2
    assert refreshed == {"n": 2}


def test_fetch_filters_use_separate_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch, "get_stats_data", lambda sid, *, filters=None: {"f": filters})

    fetch.fetch("x", filters={"cdCat01": "00700"})
    fetch.fetch("x", filters={"cdCat01": "00800"})

    # 同じ statsDataId でも絞り込みが違えば中身が違う → 別ファイルに保存される。
    files = sorted(p.name for p in (tmp_path / "estat").glob("*.json"))
    assert len(files) == 2
