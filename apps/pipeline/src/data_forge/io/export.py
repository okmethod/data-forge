"""精製済み DataFrame を Parquet / CSV / SQLite / DuckDB の4形式で出力する共通層。

ソースに依存しない。出典メタ（`SourceMeta`）は各ソースが組み立て済みの状態で
受け取り、各成果物へ出典表記（citation）を必ず同梱する:

- Parquet … フッターの key-value メタデータに埋め込み（ファイル単体で出典が残る）
- SQLite  … `_source_meta` テーブル
- DuckDB  … `_source_meta` テーブル
- CSV     … 形式上メタを持てないため、併設の `<stem>.meta.json` サイドカーで担保
- meta.json … Parquet/CSV 併設のサイドカー

出力の最後に `_verify_attribution` で全成果物に citation が入ったか検証し、
欠けていれば例外にする。これにより「出典未記載の成果物は出荷できない」を保証する。
"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import duckdb
import polars as pl

from data_forge.config import PROCESSED_DIR
from data_forge.meta import SourceMeta


def export_all(
    df: pl.DataFrame,
    meta: SourceMeta,
    *,
    stem: str,
    table_name: str,
    index_columns: list[str] | None = None,
) -> list[Path]:
    """3形式＋メタサイドカーを data/processed/ に出力し、生成パスを返す。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    parquet_path = PROCESSED_DIR / f"{stem}.parquet"
    # 出典メタをフッターの key-value に埋め込む（ファイル単体で出典が残る）。
    df.write_parquet(parquet_path, metadata=meta.flat())
    outputs.append(parquet_path)

    csv_path = PROCESSED_DIR / f"{stem}.csv"
    df.write_csv(csv_path)
    outputs.append(csv_path)

    sqlite_path = PROCESSED_DIR / f"{stem}.sqlite"
    _write_sqlite(df, meta, sqlite_path, table_name=table_name, index_columns=index_columns or [])
    outputs.append(sqlite_path)

    duckdb_path = PROCESSED_DIR / f"{stem}.duckdb"
    _write_duckdb(
        meta,
        duckdb_path,
        parquet_path=parquet_path,
        table_name=table_name,
        index_columns=index_columns or [],
    )
    outputs.append(duckdb_path)

    meta_path = PROCESSED_DIR / f"{stem}.meta.json"
    meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")
    outputs.append(meta_path)

    _verify_attribution(
        parquet_path=parquet_path,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        meta_path=meta_path,
    )

    return outputs


def _write_sqlite(
    df: pl.DataFrame,
    meta: SourceMeta,
    path: Path,
    *,
    table_name: str,
    index_columns: list[str],
) -> None:
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        _create_data_table(conn, df, table_name)
        for col in index_columns:
            conn.execute(f"CREATE INDEX idx_{table_name}_{col} ON {table_name}({col})")
        _create_meta_table(conn, meta)
        conn.commit()
    finally:
        conn.close()


def _write_duckdb(
    meta: SourceMeta,
    path: Path,
    *,
    parquet_path: Path,
    table_name: str,
    index_columns: list[str],
) -> None:
    if path.exists():
        path.unlink()

    conn = duckdb.connect(str(path))
    try:
        # 併設 Parquet を直接読み込む（型をそのまま保持でき、pyarrow 依存も不要）。
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet(?)", [str(parquet_path)]
        )
        for col in index_columns:
            conn.execute(f'CREATE INDEX idx_{table_name}_{col} ON {table_name}("{col}")')
        conn.execute("CREATE TABLE _source_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
        conn.executemany("INSERT INTO _source_meta VALUES (?, ?)", list(meta.flat().items()))
    finally:
        conn.close()


_PL_TO_SQLITE = {
    pl.Int8: "INTEGER",
    pl.Int16: "INTEGER",
    pl.Int32: "INTEGER",
    pl.Int64: "INTEGER",
    pl.Float32: "REAL",
    pl.Float64: "REAL",
    pl.Boolean: "INTEGER",
}


def _create_data_table(conn: sqlite3.Connection, df: pl.DataFrame, table_name: str) -> None:
    cols_ddl = ", ".join(
        f'"{name}" {_PL_TO_SQLITE.get(dtype, "TEXT")}' for name, dtype in zip(df.columns, df.dtypes)
    )
    conn.execute(f"CREATE TABLE {table_name} ({cols_ddl})")
    placeholders = ", ".join("?" for _ in df.columns)
    conn.executemany(
        f"INSERT INTO {table_name} VALUES ({placeholders})",
        df.iter_rows(),
    )


def _create_meta_table(conn: sqlite3.Connection, meta: SourceMeta) -> None:
    conn.execute("CREATE TABLE _source_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO _source_meta VALUES (?, ?)",
        list(meta.flat().items()),
    )


def _verify_attribution(
    *,
    parquet_path: Path,
    sqlite_path: Path,
    duckdb_path: Path,
    meta_path: Path,
) -> None:
    """全成果物に出典表記（citation）が同梱されたか検証し、欠けていれば例外にする。

    出荷物から出典が失われることを防ぐ最終ゲート。CSV は形式上メタを持てないため、
    併設の meta.json サイドカーが citation を持つことで担保する。
    """
    problems: list[str] = []

    parquet_meta = pl.read_parquet_metadata(parquet_path)
    if not parquet_meta.get("citation"):
        problems.append(f"{parquet_path.name}: フッターメタに citation が無い")

    conn = sqlite3.connect(sqlite_path)
    try:
        row = conn.execute("SELECT value FROM _source_meta WHERE key = 'citation'").fetchone()
    finally:
        conn.close()
    if not (row and row[0]):
        problems.append(f"{sqlite_path.name}: _source_meta に citation が無い")

    duck = duckdb.connect(str(duckdb_path))
    try:
        row = duck.execute("SELECT value FROM _source_meta WHERE key = 'citation'").fetchone()
    finally:
        duck.close()
    if not (row and row[0]):
        problems.append(f"{duckdb_path.name}: _source_meta に citation が無い")

    meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta_json.get("citation"):
        problems.append(f"{meta_path.name}: citation が無い（CSV の出典担保も兼ねる）")

    if problems:
        raise RuntimeError("出典表記（citation）の担保に失敗:\n  - " + "\n  - ".join(problems))
