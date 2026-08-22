"""データセットレジストリの契約テスト。

派生（複数年結合）データセットの追加時に静かに壊れやすい2点を固定する:
  1. stem の一意性（別データセットが同じ出力ファイル名を上書きしない）。
  2. 県粒度派生ビューの正規化モード（default_join="prefecture"）と出力先分離。
"""

from data_forge.datasets import (
    DATASETS,
    FAMILIES,
    Dataset,
    ProjectedDataset,
    StitchedDataset,
    get_dataset,
)

_PREFECTURE_KEYS = (
    "population_prefecture_timeseries",
    "population_by_age_prefecture_timeseries",
    "daynight_population_prefecture_timeseries",
)


def test_all_stems_unique() -> None:
    """全データセットの stem が一意（＝出力ファイルの相互上書きが起きない）。"""
    stems = [ds.stem for ds in DATASETS.values()]
    dup = {s for s in stems if stems.count(s) > 1}
    assert not dup, f"stem が重複: {dup}"


def test_prefecture_datasets_default_to_prefecture_join() -> None:
    """県粒度派生ビューは既定で空間軸集約（prefecture）＝市区町村 upstream を県へ束ねる。"""
    for key in _PREFECTURE_KEYS:
        ds = get_dataset(key)
        assert isinstance(ds, StitchedDataset)
        assert ds.default_join == "prefecture"


def test_prefecture_datasets_share_upstreams_with_municipality_view() -> None:
    """県粒度ビューは市区町村時系列と同一 upstream（同じ素材を粒度違いで出すだけ）。"""
    pairs = {
        "population_prefecture_timeseries": "population_timeseries",
        "population_by_age_prefecture_timeseries": "population_by_age_timeseries",
        "daynight_population_prefecture_timeseries": "daynight_population_timeseries",
    }
    for pref_key, muni_key in pairs.items():
        pref, muni = get_dataset(pref_key), get_dataset(muni_key)
        assert isinstance(pref, StitchedDataset) and isinstance(muni, StitchedDataset)
        assert pref.upstreams == muni.upstreams
        assert pref.table_name == muni.table_name


def test_preliminary_upstreams_reference_existing_base_datasets() -> None:
    """preliminary_upstreams のキーは実在する基底 Dataset を指す（配線ずれ・タイポの早期検知）。"""
    for ds in DATASETS.values():
        if not isinstance(ds, StitchedDataset):
            continue
        for key in ds.preliminary_upstreams:
            up = get_dataset(key)  # 未知キーなら KeyError
            assert isinstance(up, Dataset), f"{ds.key}: 速報 upstream {key!r} は基底 Dataset 必須"


def test_all_table_names_are_registered_families() -> None:
    """全 table_name はファミリー台帳 FAMILIES の要素（＝閉じた語彙・幽霊テーブル/タイポ検知）。"""
    unknown = {ds.table_name for ds in DATASETS.values()} - FAMILIES
    assert not unknown, f"FAMILIES 未登録の table_name: {unknown}"


def test_age5_prefecture_timeseries_is_projected_flow() -> None:
    """5歳階級の県世紀時系列は射影フロー（ProjectedDataset）＝縫合専用の機構を持たない。

    既製の時系列帳票（系統B・全国＋県）を area union するだけなので、default_join（正規化モード）も
    preliminary_upstreams（速報 splice）も持たないことを固定する。
    市区町村旗艦（population_by_age5_timeseries）は逆に合併畳込 Stitched（aggregate_to_base）である。
    """
    ds = get_dataset("population_by_age5_prefecture_timeseries")
    assert isinstance(ds, ProjectedDataset)
    assert not hasattr(ds, "default_join")
    assert not hasattr(ds, "preliminary_upstreams")

    flagship = get_dataset("population_by_age5_timeseries")
    assert isinstance(flagship, StitchedDataset)
    assert flagship.default_join == "aggregate_to_base"
    # 2系列は同じ table_name（bare）を共有する＝1 family・N:1 ハブ。
    assert ds.table_name == flagship.table_name == "population_by_age5"


def test_age5_municipality_reiwa_tables_override_muni_levels() -> None:
    """令和型 level4/6 の各回 age5 表（1980-2005）は muni_levels={4,6} を必ず明示上書きする。

    これらの年はグローバル _MUNI_LEVELS が {3}（人口時系列製品向け）だが、各回基本集計の
    5歳/各歳表は市/区=level4・町村=level6・level3=支庁の中間集計、という令和型グレイン。
    override を欠くと extract_atoms が level3 の支庁だけを葉に拾い市区町村フル（level4/6）を全て
    落とす（＝日本人カバレッジが壊れた 1990/1995 のバグ）。この不変条件を設定レベルで固定する。
    2010/2015/2020 はグローバル既定が {4,6} ゆえ override 不要（muni_levels=None 可）。
    """
    keys = [f"population_by_age5_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005)]
    keys += ["population_by_age5_1990_total", "population_by_age5_1995_total"]
    for key in keys:
        ds = get_dataset(key)
        assert ds.muni_levels == frozenset({4, 6}), f"{key}: 令和型表は muni_levels={{4,6}} 必須"


def test_projected_datasets_reference_existing_base_upstreams() -> None:
    """射影データセットの upstream は実在する基底 Dataset（既製時系列の area パーティション）。"""
    for ds in DATASETS.values():
        if not isinstance(ds, ProjectedDataset):
            continue
        for key in ds.upstreams:
            up = get_dataset(key)
            assert isinstance(up, Dataset), f"{ds.key}: upstream {key!r} は基底 Dataset 必須"
