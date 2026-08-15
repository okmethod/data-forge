"""コマンドラインエントリポイント。

疎結合な独立ステップをサブコマンドとして提供する:
    fetch  … 生データを取得しキャッシュ（data/raw/）
    clean  … 取得→名称解決→クレンジングし先頭を表示（書き出しなし）
    export … クレンジング結果を3形式で出力（data/processed/）
    run    … fetch→clean→export の一気通し（export と同義）

派生データセットの合成（縫合/射影）ロジックは data_forge.derive に分離してあり、
本モジュールは引数解析とコマンド dispatch に徹する。

使用例:
    uv run poe run population_2020        # poe タスク経由
    uv run data-forge run population_2020 # コンソールスクリプト直接
"""

import argparse
import sys

import polars as pl

from data_forge import config, derive
from data_forge.area import reconcile as area_reconcile
from data_forge.area.history import ingest as area_ingest
from data_forge.datasets import Dataset, ProjectedDataset, StitchedDataset, get_dataset
from data_forge.output import export_all
from data_forge.sources.estat import fetch as estat_fetch

# NOTE: 現状ソースは e-Stat 固定。
# 複数ソース対応（Source プロトコル + dispatch）はPhase 2 で導入する。


def _cmd_fetch(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    if isinstance(ds, StitchedDataset | ProjectedDataset):
        for key in ds.upstreams:
            _cmd_fetch(get_dataset(key), args)
        return
    stats_data_id = ds.source_params["stats_data_id"]
    raw = estat_fetch.fetch(stats_data_id, refresh=args.refresh)
    n = len(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"])
    print(f"[fetch] {ds.key}: statsDataId={stats_data_id} → {n:,} 行をキャッシュ")


def _cmd_clean(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    df, _ = derive.load(ds, refresh=args.refresh, join=args.join, base_year=args.base_year)
    print(f"[clean] {ds.key}: {df.height:,} 行 / {df.width} 列")
    print(df.head(10))


def _cmd_export(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    df, src_meta = derive.load(ds, refresh=args.refresh, join=args.join, base_year=args.base_year)
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


def _cmd_area_orphans(
    ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace
) -> None:
    """base_year に届かない消滅アトム（＝合併イベント未整備）を一覧＝次に埋める候補。"""
    atom_fact, _, events = derive.build_atoms(ds, refresh=args.refresh)
    rep = area_reconcile.orphans(atom_fact, events, base_year=args.base_year)
    base = args.base_year or "最新"
    print(f"[area-orphans] {ds.key}: 未整備の消滅アトム {rep.height} 件（base_year={base}）")
    with pl.Config(tbl_rows=50):
        print(rep)


def _cmd_area_check(
    ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace
) -> None:
    """人口保存（各年 アトム合計==全国total）と孤児アトム件数を検証。"""
    atom_fact, national, events = derive.build_atoms(ds, refresh=args.refresh)
    cons = area_reconcile.national_conservation(atom_fact, national)
    n_bad = int(cons.filter(~pl.col("ok")).height)
    print(
        f"[area-check] {ds.key}: 人口保存 {'✅ 全年一致' if n_bad == 0 else f'⚠️ {n_bad} 年で不一致'}"
    )
    for row in cons.filter(pl.col("known")).iter_rows(named=True):
        reason = area_reconcile.KNOWN_DIFF_REASONS.get(row["year"], "")
        print(f"  ⚠️ {row['year']} は既知差分 {row['diff']} 人を受容: {reason}")
    print(cons)
    orph = area_reconcile.orphans(atom_fact, events, base_year=args.base_year)
    if orph.height:
        top = orph.head(5).get_column("area_name").to_list()
        print(f"⚠️ 未整備の消滅アトム {orph.height} 件（例: {top}）→ area-orphans で全件確認")
    else:
        print("✅ 孤児アトムなし（全消滅アトムが base_year へ到達）")


def _cmd_area_ingest(args: argparse.Namespace) -> None:
    """廃置分合の生CSV を正規化イベント（events_parsed.csv）へ変換して保存する。"""
    src = args.path
    if src is None:
        csvs = sorted(config.AREA_HISTORY_RAW.glob("*.csv"))
        if len(csvs) != 1:
            raise SystemExit(
                f"{config.AREA_HISTORY_RAW} にCSVが {len(csvs)} 件。パスを引数で指定してください。"
            )
        src = csvs[0]
    ev = area_ingest.parse_history_csv(src, encoding=args.encoding)
    config.AREA_EVENTS_PARSED.parent.mkdir(parents=True, exist_ok=True)
    ev.write_csv(config.AREA_EVENTS_PARSED)
    print(f"[area-ingest] {src} → {ev.height:,} イベント → {config.AREA_EVENTS_PARSED}")
    print(ev.group_by("kind").len().sort("len", descending=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-forge", description="公的データ精製パイプライン")
    sub = parser.add_subparsers(dest="command", required=True)

    # 廃置分合CSV → 正規化イベント（データセット非依存の単発コマンド）
    pi = sub.add_parser("area-ingest", help="廃置分合の生CSVを events_parsed.csv へ正規化")
    pi.add_argument(
        "path", nargs="?", default=None, help="生CSVパス（省略時は data/raw/history/ の単一CSV）"
    )
    pi.add_argument(
        "--encoding",
        default="utf8",
        help="生CSVのエンコーディング（既定 utf8。Shift-JIS 版なら shift-jis）",
    )
    pi.set_defaults(handler=lambda ds, args: _cmd_area_ingest(args))

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
            choices=derive.JOIN_CHOICES,
            default=None,
            help="派生（時系列）データセットの正規化モード。既定はデータセット定義に従う"
            "（prefecture/region は都道府県/地方ブロックへの上位集約）",
        )
        p.add_argument(
            "--base-year",
            type=int,
            default=None,
            help="aggregate_to_base の基準年（既定=最新年）。この年の地域区分へ合併集約する",
        )
        p.set_defaults(handler=handler)

    # area overrides（クッション）整備の支援ツール（派生データセットに対して実行）
    area_handlers = {
        "area-orphans": _cmd_area_orphans,  # 未整備の消滅アトム一覧
        "area-check": _cmd_area_check,  # 人口保存＋孤児件数の検証
    }
    for name, handler in area_handlers.items():
        p = sub.add_parser(name, help=f"area overrides 整備支援: {name}")
        p.add_argument("dataset", help="派生データセットキー（例: population_timeseries）")
        p.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
        p.add_argument("--base-year", type=int, default=None, help="基準年（既定=最新年）")
        p.set_defaults(handler=handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset_key = getattr(args, "dataset", None)
    if dataset_key is None:  # データセット非依存コマンド（area-ingest 等）
        args.handler(None, args)
        return 0
    try:
        ds = get_dataset(dataset_key)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 1
    args.handler(ds, args)
    return 0
