"""精製済み DataFrame を Parquet / CSV / SQLite の3形式で出力する共通層。

ソースに依存しない。出典メタ（`SourceMeta`）は各ソースが組み立て済みの状態で
受け取り、SQLite の `_source_meta` テーブルと、Parquet/CSV 併設の
`<stem>.meta.json` サイドカーの両方へ書き出す。
"""

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

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
    df.write_parquet(parquet_path)
    outputs.append(parquet_path)

    csv_path = PROCESSED_DIR / f"{stem}.csv"
    df.write_csv(csv_path)
    outputs.append(csv_path)

    sqlite_path = PROCESSED_DIR / f"{stem}.sqlite"
    _write_sqlite(df, meta, sqlite_path, table_name=table_name, index_columns=index_columns or [])
    outputs.append(sqlite_path)

    meta_path = PROCESSED_DIR / f"{stem}.meta.json"
    meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")
    outputs.append(meta_path)

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
