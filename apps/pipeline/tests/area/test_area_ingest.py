"""廃置分合 生CSV パーサ（area.history.ingest）のテスト。

e-Stat の改正事由は自由文でコードを括弧に埋め込む。主要パターン
（編入・新設合併(コード明示/略記)・政令指定都市施行/移行の表記揺れ・改称・区域変更）を
合成事由で検証する。消滅コードも行に出るため、後継はテキスト文法から取る。
"""

import polars as pl

from data_forge.area.history import ingest


def _raw(pairs: list[tuple[str, str]]) -> pl.DataFrame:
    """(施行年月日, 改正事由) の列を持つ最小 raw を作る。"""
    return pl.DataFrame(
        {
            "廃置分合等施行年月日": [d for d, _ in pairs],
            "改正事由": [r for _, r in pairs],
        }
    )


def _map(ev: pl.DataFrame) -> dict[str, str]:
    return dict(zip(ev["old_code"].to_list(), ev["successor_code"].to_list(), strict=True))


def test_parse_absorption_and_merger_with_explicit_code():
    raw = _raw(
        [
            ("2005-01-01", "石下町(08523)が水海道市(08211)に編入"),
            ("2006-01-01", "伊達町(07302)、梁川町(07304)が合併し、伊達市(07213)を新設"),
        ]
    )
    m = _map(ingest.normalize(raw))
    assert m["08523"] == "08211"  # 編入
    assert m["07302"] == "07213" and m["07304"] == "07213"  # 新設（コード明示）


def test_parse_merger_with_omitted_code_via_name_match():
    # 「津市を新設」＝後継コード略記 → 名前マッチで津市(24201)へ解決
    raw = _raw([("2006-01-01", "津市(24201)、久居市(24213)が合併し、津市を新設")])
    m = _map(ingest.normalize(raw))
    assert m == {"24213": "24201"}  # 24201→24201 は自己ループなので出ない


def test_parse_designated_city_both_wordings():
    # 施行（旧表記）と 移行（2009以降）の両方を拾う
    raw = _raw(
        [
            ("2006-04-01", "堺市(27201)の堺市(27140)への政令指定都市施行\n堺区(27141)の新設"),
            ("2009-04-01", "岡山市(33201)の岡山市(33100)への政令指定都市移行"),
        ]
    )
    m = _map(ingest.normalize(raw))
    assert m["27201"] == "27140" and m["33201"] == "33100"


def test_parse_rename_and_subprefecture_recode():
    raw = _raw(
        [
            ("2006-01-01", "大宮町(08344)が常陸大宮町に名称変更し、常陸大宮市(08225)に市制施行"),
            ("2010-04-01", "留萌支庁幌延町(01488)が宗谷支庁幌延町(01520)に区域変更"),
            ("2006-01-01", "水海道市(08211)が常総市(08211)に名称変更"),  # 同一コード→出ない
        ]
    )
    m = _map(ingest.normalize(raw))
    assert m["08344"] == "08225"  # 名称変更＋市制施行の合わせ技
    assert m["01488"] == "01520"  # 支庁区域変更＝改称扱い
    assert "08211" not in m  # 同一コードの名称変更はイベント化しない


def test_ignore_ward_and_gun_lines():
    raw = _raw([("2005-01-01", "中郡(26480)の廃止\n○○区(11101)、△△区(11102)の新設")])
    ev = ingest.normalize(raw)
    assert ev.height == 0  # 郡廃止・区新設のみ＝イベント無し
