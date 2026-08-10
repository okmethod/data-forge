"""出力共通層（io/export）の出典表記（citation）担保テスト。

全成果物に citation が同梱されること、および欠けた場合に
_verify_attribution が例外で出荷を止めることを検証する。
"""

import json
import sqlite3

import duckdb
import polars as pl
import pytest

from data_forge.io import export
from data_forge.meta import SourceMeta

_META = SourceMeta(
    source="estat",
    dataset_id="0000000000",
    title="テスト表",
    provider="総務省",
    citation="出典：政府統計の総合窓口(e-Stat) 「テスト表」を加工して作成",
    attributes={"stat_name": "テスト調査"},
)


def _df() -> pl.DataFrame:
    return pl.DataFrame({"area_code": ["00000"], "population": [123]})


def test_export_embeds_citation_in_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "PROCESSED_DIR", tmp_path)

    outputs = export.export_all(_df(), _META, stem="t", table_name="t")
    by_suffix = {p.suffix: p for p in outputs}

    # Parquet: フッターの key-value メタに citation
    assert export.pl.read_parquet_metadata(by_suffix[".parquet"])["citation"] == _META.citation

    # SQLite: _source_meta テーブル
    conn = sqlite3.connect(by_suffix[".sqlite"])
    try:
        row = conn.execute("SELECT value FROM _source_meta WHERE key = 'citation'").fetchone()
    finally:
        conn.close()
    assert row[0] == _META.citation

    # DuckDB: _source_meta テーブル
    duck = duckdb.connect(str(by_suffix[".duckdb"]))
    try:
        row = duck.execute("SELECT value FROM _source_meta WHERE key = 'citation'").fetchone()
    finally:
        duck.close()
    assert row[0] == _META.citation

    # meta.json サイドカー（CSV の出典担保を兼ねる）
    meta_json = json.loads(by_suffix[".json"].read_text(encoding="utf-8"))
    assert meta_json["citation"] == _META.citation


def test_verify_attribution_raises_when_citation_missing(tmp_path):
    # citation 空の meta.json を用意し、ゲートが検知することを確認
    parquet = tmp_path / "t.parquet"
    sqlite_path = tmp_path / "t.sqlite"
    duckdb_path = tmp_path / "t.duckdb"
    meta_path = tmp_path / "t.meta.json"

    _df().write_parquet(parquet, metadata={"citation": "x"})
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE _source_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO _source_meta VALUES ('citation', 'x')")
    conn.commit()
    conn.close()
    duck = duckdb.connect(str(duckdb_path))
    duck.execute("CREATE TABLE _source_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    duck.execute("INSERT INTO _source_meta VALUES ('citation', 'x')")
    duck.close()
    meta_path.write_text(json.dumps({"citation": ""}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="citation"):
        export._verify_attribution(
            parquet_path=parquet,
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            meta_path=meta_path,
        )
