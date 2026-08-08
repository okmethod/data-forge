"""コマンドラインエントリポイント。

疎結合な独立ステップをサブコマンドとして提供する:
    fetch  … 生データを取得しキャッシュ（data/raw/）
    clean  … 取得→名称解決→クレンジングし先頭を表示（書き出しなし）
    export … クレンジング結果を3形式で出力（data/processed/）
    run    … fetch→clean→export の一気通し（export と同義）

使用例:
    uv run poe run population        # poe タスク経由
    uv run data-forge run population # コンソールスクリプト直接
"""

import argparse
import sys

import polars as pl

from data_forge.datasets import Dataset, get_dataset
from data_forge.io.export import export_all
from data_forge.meta import SourceMeta
from data_forge.sources.estat import fetch as estat_fetch
from data_forge.sources.estat import transform

# NOTE: 現状ソースは e-Stat 固定。
# 複数ソース対応（Source プロトコル + dispatch）はPhase 2 で導入する。
# ここではソース固有パラメータの読み出しだけ抽象化しておく。


def _load_tidy(ds: Dataset, *, refresh: bool = False) -> tuple[pl.DataFrame, SourceMeta]:
    raw = estat_fetch.fetch(ds.source_params["stats_data_id"], refresh=refresh)
    return transform.to_tidy(raw), transform.extract_meta(raw)


def _cmd_fetch(ds: Dataset, args: argparse.Namespace) -> None:
    stats_data_id = ds.source_params["stats_data_id"]
    raw = estat_fetch.fetch(stats_data_id, refresh=args.refresh)
    n = len(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"])
    print(f"[fetch] {ds.key}: statsDataId={stats_data_id} → {n:,} 行をキャッシュ")


def _cmd_clean(ds: Dataset, args: argparse.Namespace) -> None:
    tidy, _ = _load_tidy(ds, refresh=args.refresh)
    df = ds.cleaner(tidy)
    print(f"[clean] {ds.key}: {df.height:,} 行 / {df.width} 列")
    print(df.head(10))


def _cmd_export(ds: Dataset, args: argparse.Namespace) -> None:
    tidy, src_meta = _load_tidy(ds, refresh=args.refresh)
    df = ds.cleaner(tidy)
    outputs = export_all(
        df,
        src_meta,
        stem=ds.stem,
        table_name=ds.table_name,
        index_columns=ds.index_columns,
    )
    print(f"[export] {ds.key}: {df.height:,} 行を出力")
    for path in outputs:
        print(f"  - {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-forge", description="公的データ精製パイプライン")
    sub = parser.add_subparsers(dest="command", required=True)

    handlers = {
        "fetch": _cmd_fetch,
        "clean": _cmd_clean,
        "export": _cmd_export,
        "run": _cmd_export,  # run は export と同義（fetch はキャッシュ経由で内包）
    }
    for name, handler in handlers.items():
        p = sub.add_parser(name, help=f"{name} ステップを実行")
        p.add_argument("dataset", help="データセットキー（例: population）")
        p.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
        p.set_defaults(handler=handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ds = get_dataset(args.dataset)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1
    args.handler(ds, args)
    return 0
