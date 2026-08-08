"""コマンドラインエントリポイント。

疎結合な独立ステップをサブコマンドとして提供する:
    fetch  … 生データを取得しキャッシュ（data/raw/）
    clean  … 取得→名称解決→クレンジングし先頭を表示（書き出しなし）
    export … クレンジング結果を3形式で出力（data/processed/）
    run    … fetch→clean→export の一気通し（export と同義）

使用例:
    uv run poe run population_2020        # poe タスク経由
    uv run data-forge run population_2020 # コンソールスクリプト直接
"""

import argparse
import sys

import polars as pl

from data_forge.combine import combine_years
from data_forge.datasets import CompositeDataset, Dataset, get_dataset
from data_forge.io.export import export_all
from data_forge.meta import SourceMeta, combine_meta
from data_forge.sources.estat import fetch as estat_fetch
from data_forge.sources.estat import transform

# NOTE: 現状ソースは e-Stat 固定。
# 複数ソース対応（Source プロトコル + dispatch）はPhase 2 で導入する。
# ここではソース固有パラメータの読み出しだけ抽象化しておく。


def _load_base(ds: Dataset, *, refresh: bool = False) -> tuple[pl.DataFrame, SourceMeta]:
    """基底データセットを fetch→clean し、配布用 DF と出典メタを返す。"""
    raw = estat_fetch.fetch(ds.source_params["stats_data_id"], refresh=refresh)
    df = ds.cleaner(transform.to_tidy(raw))
    return df, transform.extract_meta(raw)


def _load_composite(
    ds: CompositeDataset, *, refresh: bool, join: str
) -> tuple[pl.DataFrame, SourceMeta]:
    """派生（複数年結合）データセットを upstream 合成して返す。"""
    frames: list[pl.DataFrame] = []
    metas: list[SourceMeta] = []
    for key in ds.upstreams:
        up = get_dataset(key)
        if not isinstance(up, Dataset):
            raise TypeError(f"upstream {key!r} は基底データセットである必要があります")
        df, meta = _load_base(up, refresh=refresh)
        frames.append(df)
        metas.append(meta)
    df = combine_years(frames, mode=join)  # type: ignore[arg-type]
    return df, combine_meta(metas, title=ds.title)


def _load(
    ds: Dataset | CompositeDataset, args: argparse.Namespace
) -> tuple[pl.DataFrame, SourceMeta]:
    """基底/派生を判別して配布用 DF と出典メタを返す。"""
    if isinstance(ds, CompositeDataset):
        return _load_composite(ds, refresh=args.refresh, join=args.join or ds.default_join)
    return _load_base(ds, refresh=args.refresh)


def _cmd_fetch(ds: Dataset | CompositeDataset, args: argparse.Namespace) -> None:
    if isinstance(ds, CompositeDataset):
        for key in ds.upstreams:
            _cmd_fetch(get_dataset(key), args)
        return
    stats_data_id = ds.source_params["stats_data_id"]
    raw = estat_fetch.fetch(stats_data_id, refresh=args.refresh)
    n = len(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"])
    print(f"[fetch] {ds.key}: statsDataId={stats_data_id} → {n:,} 行をキャッシュ")


def _cmd_clean(ds: Dataset | CompositeDataset, args: argparse.Namespace) -> None:
    df, _ = _load(ds, args)
    print(f"[clean] {ds.key}: {df.height:,} 行 / {df.width} 列")
    print(df.head(10))


def _cmd_export(ds: Dataset | CompositeDataset, args: argparse.Namespace) -> None:
    df, src_meta = _load(ds, args)
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
        p.add_argument("dataset", help="データセットキー（例: population_2020）")
        p.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
        p.add_argument(
            "--join",
            choices=["union", "intersection", "grid"],
            default=None,
            help="派生（時系列）データセットの正規化モード。既定はデータセット定義に従う",
        )
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
