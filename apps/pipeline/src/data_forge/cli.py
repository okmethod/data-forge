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

from data_forge import config
from data_forge.area import aggregate as area_aggregate
from data_forge.area import atoms as area_atoms
from data_forge.area import events as area_events
from data_forge.area import reconcile as area_reconcile
from data_forge.area.history import ingest as area_ingest
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


def _upstream_frames(
    ds: CompositeDataset, *, refresh: bool
) -> tuple[list[pl.DataFrame], list[SourceMeta]]:
    """派生データセットの各 upstream を fetch→clean し、フレーム群とメタ群を返す。"""
    frames: list[pl.DataFrame] = []
    metas: list[SourceMeta] = []
    for key in ds.upstreams:
        up = get_dataset(key)
        if not isinstance(up, Dataset):
            raise TypeError(f"upstream {key!r} は基底データセットである必要があります")
        df, meta = _load_base(up, refresh=refresh)
        frames.append(df)
        metas.append(meta)
    return frames, metas


def _atom_upstreams(
    ds: CompositeDataset, *, refresh: bool
) -> tuple[list[pl.DataFrame], list[SourceMeta], pl.DataFrame]:
    """各 upstream（単年）を fetch→clean→アトム抽出し、アトムフレーム群・メタ群・全国行を返す。

    アトム抽出には area 階層（parentCode）が要るため raw から直接取り出す
    （combine 前に年ごとに finest 分割へ絞る）。全国行は reconcile の人口保存検査用。
    """
    atom_frames: list[pl.DataFrame] = []
    metas: list[SourceMeta] = []
    nationals: list[pl.DataFrame] = []
    for key in ds.upstreams:
        up = get_dataset(key)
        if not isinstance(up, Dataset):
            raise TypeError(f"upstream {key!r} は基底データセットである必要があります")
        raw = estat_fetch.fetch(up.source_params["stats_data_id"], refresh=refresh)
        fact = up.cleaner(transform.to_tidy(raw))
        hierarchy = transform.extract_area_hierarchy(raw)
        year = int(fact.get_column("year").unique().item())
        atom_frames.append(area_atoms.extract_atoms(fact, hierarchy, year=year))
        nationals.append(
            fact.filter(pl.col("area_code") == "00000").select("year", "sex_code", "population")
        )
        metas.append(transform.extract_meta(raw))
    return atom_frames, metas, pl.concat(nationals)


def _load_composite(
    ds: CompositeDataset, *, refresh: bool, join: str, base_year: int | None
) -> tuple[pl.DataFrame, SourceMeta]:
    """派生（複数年結合）データセットを upstream 合成して返す。"""
    if join == "aggregate_to_base":
        # clean→atoms(年ごと)→combine(union)→area.aggregate と配線（集約は combine に埋め込まない）
        atom_frames, metas, _ = _atom_upstreams(ds, refresh=refresh)
        atom_fact = combine_years(atom_frames, mode="union")
        events = area_events.load_events()
        df = area_aggregate.aggregate_to_base(atom_fact, events, base_year=base_year)
    else:
        frames, metas = _upstream_frames(ds, refresh=refresh)
        df = combine_years(frames, mode=join)  # type: ignore[arg-type]
    return df, combine_meta(metas, title=ds.title)


def _load(
    ds: Dataset | CompositeDataset, args: argparse.Namespace
) -> tuple[pl.DataFrame, SourceMeta]:
    """基底/派生を判別して配布用 DF と出典メタを返す。"""
    if isinstance(ds, CompositeDataset):
        return _load_composite(
            ds,
            refresh=args.refresh,
            join=args.join or ds.default_join,
            base_year=args.base_year,
        )
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


def _composite_atoms(
    ds: Dataset | CompositeDataset, args: argparse.Namespace
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """area 支援ツール用に、アトム時系列・全国行・実効イベントを構築して返す。"""
    if not isinstance(ds, CompositeDataset):
        raise SystemExit(f"{ds.key!r} は派生（時系列）データセットではありません")
    atom_frames, _, national = _atom_upstreams(ds, refresh=args.refresh)
    atom_fact = combine_years(atom_frames, mode="union")
    return atom_fact, national, area_events.load_events()


def _cmd_area_orphans(ds: Dataset | CompositeDataset, args: argparse.Namespace) -> None:
    """base_year に届かない消滅アトム（＝合併イベント未整備）を一覧＝次に埋める候補。"""
    atom_fact, _, events = _composite_atoms(ds, args)
    rep = area_reconcile.orphans(atom_fact, events, base_year=args.base_year)
    base = args.base_year or "最新"
    print(f"[area-orphans] {ds.key}: 未整備の消滅アトム {rep.height} 件（base_year={base}）")
    with pl.Config(tbl_rows=50):
        print(rep)


def _cmd_area_check(ds: Dataset | CompositeDataset, args: argparse.Namespace) -> None:
    """人口保存（各年 アトム合計==全国total）と孤児アトム件数を検証。"""
    atom_fact, national, events = _composite_atoms(ds, args)
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
            choices=["union", "intersection", "grid", "aggregate_to_base"],
            default=None,
            help="派生（時系列）データセットの正規化モード。既定はデータセット定義に従う",
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
