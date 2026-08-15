"""派生データセットの合成（オーケストレーション）層。

基底データセット（各回帳票）を fetch→clean し、2つの処理フローで時系列へ合成する:

    縫合（StitchedDataset）… 各回帳票を year 軸で結合し時系列化。合併畳込
        (aggregate_to_base)・空間集約（prefecture/region）・速報 splice を持つ。
    射影（ProjectedDataset）… e-Stat 既製の時系列帳票を area 軸で union するだけ。
        年の縫合も area master も持たない。

CLI から argparse を切り離すため、公開関数は明示キーワード（refresh/join/base_year）を
受け取る（cli.py はコマンド引数をここへ橋渡しするだけ）。純粋な DF 変換は combine.py が担い、
本モジュールは fetch→clean→合成の配線と area 集約の呼び出しに徹する。
"""

import polars as pl

from data_forge.area import aggregate as area_aggregate
from data_forge.area import atoms as area_atoms
from data_forge.area import events as area_events
from data_forge.area import spatial_rollup as area_spatial
from data_forge.datasets import Dataset, ProjectedDataset, StitchedDataset, get_dataset
from data_forge.derive.combine import combine_years, union_areas
from data_forge.meta import SourceMeta, combine_meta
from data_forge.provenance import splice_preliminary
from data_forge.sources.estat import fetch as estat_fetch
from data_forge.sources.estat import transform

# --join の正規化モード。3系統に分かれる（combine 系 / 時間軸=合併集約 / 空間軸=行政集約）。
# argparse の choices（cli.build_parser）と _load_stitched の分岐でこの定義を共有する。
_COMBINE_JOINS = ("union", "intersection", "grid")  # combine のみ（アトム抽出なし）
_TIME_ROLLUP_JOINS = ("aggregate_to_base", "crosswalk")  # 合併集約（events 依存）
_SPACE_ROLLUP_JOINS = ("prefecture", "region")  # 行政集約（events 非依存）
JOIN_CHOICES = [*_COMBINE_JOINS, *_TIME_ROLLUP_JOINS, *_SPACE_ROLLUP_JOINS]


def _load_base(ds: Dataset, *, refresh: bool = False) -> tuple[pl.DataFrame, SourceMeta]:
    """基底データセットを fetch→clean し、配布用 DF と出典メタを返す。"""
    raw = estat_fetch.fetch(ds.source_params["stats_data_id"], refresh=refresh)
    df = ds.cleaner(transform.to_tidy(raw))
    return df, transform.extract_meta(raw)


def _upstream_frames(
    ds: StitchedDataset | ProjectedDataset, *, refresh: bool
) -> tuple[list[pl.DataFrame], list[SourceMeta]]:
    """派生データセットの各 upstream を fetch→clean し、フレーム群とメタ群を返す。

    縫合（combine 系 else 節）・射影の両フローが共通で使う fetch→clean の前段。
    """
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
    ds: StitchedDataset, *, refresh: bool
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
        # 全国行はそのまま渡す（reconcile が分類軸コードで総数スライスを絞るため列を落とさない）。
        nationals.append(fact.filter(pl.col("area_code") == "00000"))
        metas.append(transform.extract_meta(raw))
    return atom_frames, metas, pl.concat(nationals)


def _combine_atoms(ds: StitchedDataset, *, refresh: bool) -> tuple[pl.DataFrame, list[SourceMeta]]:
    """rollup 系パスの共通前段: clean→atoms(年ごと)→combine(union) でアトム時系列を組む。

    集約は combine に埋め込まず、この後段で aggregate（時間軸）/ spatial_rollup（空間軸）が行う。
    """
    atom_frames, metas, _ = _atom_upstreams(ds, refresh=refresh)
    return combine_years(atom_frames, mode="union", grain=ds.grain), metas


def _load_stitched(
    ds: StitchedDataset, *, refresh: bool, join: str, base_year: int | None
) -> tuple[pl.DataFrame, SourceMeta]:
    """縫合（複数年を year 軸で結合）データセットを upstream 合成して返す（3系統に分岐）。"""
    if join in _TIME_ROLLUP_JOINS:
        # 時間軸＝合併集約（events 依存）。crosswalk=畳まず後継コード列同梱 / base=畳んで確定。
        atom_fact, metas = _combine_atoms(ds, refresh=refresh)
        events = area_events.load_events()
        if join == "crosswalk":
            df = area_aggregate.attach_crosswalk(atom_fact, events, base_year=base_year)
        else:
            df = area_aggregate.aggregate_to_base(atom_fact, events, base_year=base_year)
    elif join in _SPACE_ROLLUP_JOINS:
        # 空間軸＝行政集約（events 非依存・合併 rollup と直交）。県プレフィックスで束ねる。
        atom_fact, metas = _combine_atoms(ds, refresh=refresh)
        df = area_spatial.aggregate_to_admin(atom_fact, level=join)
    else:
        # combine のみ（union/intersection/grid）。アトム抽出なしで各年 fact を直接結合。
        frames, metas = _upstream_frames(ds, refresh=refresh)
        df = combine_years(frames, mode=join, grain=ds.grain)  # type: ignore[arg-type]
    if ds.preliminary_upstreams:
        # 確定ビュー確定後の後段で速報を継ぎ足す（area 集約=共有ハブは無改修）。
        df, metas = _splice_preliminary(ds, df, metas, refresh=refresh)
    return df, combine_meta(metas, title=ds.title)


def _load_projected(ds: ProjectedDataset, *, refresh: bool) -> tuple[pl.DataFrame, SourceMeta]:
    """射影（既製時系列を area 軸で union）データセットを合成して返す。

    upstream は各々全年を持つ disjoint な area パーティション。年の縫合・合併集約・速報 splice は
    無く、union_areas で縦積みするだけ（combine_years の重機構も area master も通さない）。
    """
    frames, metas = _upstream_frames(ds, refresh=refresh)
    df = union_areas(frames, grain=ds.grain)
    return df, combine_meta(metas, title=ds.title)


def _splice_preliminary(
    ds: StitchedDataset, confirmed: pl.DataFrame, metas: list[SourceMeta], *, refresh: bool
) -> tuple[pl.DataFrame, list[SourceMeta]]:
    """確定ビューに速報 upstream を継ぎ足し、data_status 来歴列で明示する（集約の後段）。

    速報は最新境界＝合併 rollup 不要なので集約機械を通さず、ここで合流させる。
    速報表は全国/県/市区町村が混在するため、確定ビューに既に在る area_code だけへ
    intersection scoping してから継ぎ足す。
    レベル混在・二重計上を防ぎ、view の粒度に自動追従。
    2025 新設合併など確定側に無いコードは coverage gap として落ちるだけ。
    出典メタは速報ソース分を確定分に足して束ねる（配布物に速報の出典も残す）。
    """
    frames: list[pl.DataFrame] = []
    prelim_metas: list[SourceMeta] = []
    for key in ds.preliminary_upstreams:
        up = get_dataset(key)
        if not isinstance(up, Dataset):
            raise TypeError(f"preliminary upstream {key!r} は基底データセットである必要があります")
        frame, meta = _load_base(up, refresh=refresh)
        frames.append(frame)
        prelim_metas.append(meta)
    confirmed_areas = confirmed.get_column("area_code").unique().to_list()
    prelim = pl.concat(frames, how="vertical").filter(pl.col("area_code").is_in(confirmed_areas))
    spliced = splice_preliminary(confirmed, prelim, grain=ds.grain)
    return spliced, [*metas, *prelim_metas]


def load(
    ds: Dataset | StitchedDataset | ProjectedDataset,
    *,
    refresh: bool = False,
    join: str | None = None,
    base_year: int | None = None,
) -> tuple[pl.DataFrame, SourceMeta]:
    """基底/縫合/射影を判別して配布用 DF と出典メタを返す（CLI 各コマンドの入口）。"""
    if isinstance(ds, StitchedDataset):
        return _load_stitched(
            ds, refresh=refresh, join=join or ds.default_join, base_year=base_year
        )
    if isinstance(ds, ProjectedDataset):
        # 射影フローは正規化モードを持たない（join / base_year は無視）。
        return _load_projected(ds, refresh=refresh)
    return _load_base(ds, refresh=refresh)


def build_atoms(
    ds: Dataset | StitchedDataset | ProjectedDataset, *, refresh: bool = False
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """area 支援ツール用に、アトム時系列・全国行・実効イベントを構築して返す。

    合併集約（area master）を持つ縫合フロー専用。射影フローや基底は対象外として弾く。
    """
    if isinstance(ds, ProjectedDataset):
        # 射影フローは area master 非依存（合併集約を持たない）＝area 検査の対象外。
        raise SystemExit(
            f"{ds.key!r} は射影（area master 非依存）データセットで、area 検査の対象外です"
        )
    if not isinstance(ds, StitchedDataset):
        raise SystemExit(f"{ds.key!r} は派生（時系列）データセットではありません")
    # national 行だけ別途要る（人口保存検査用）ので _atom_upstreams を直接呼ぶ。
    atom_frames, _, national = _atom_upstreams(ds, refresh=refresh)
    atom_fact = combine_years(atom_frames, mode="union", grain=ds.grain)
    return atom_fact, national, area_events.load_events()
