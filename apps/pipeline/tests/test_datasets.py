"""データセットレジストリの契約テスト。

派生（複数年結合）データセットの追加時に静かに壊れやすい2点を固定する:
  1. stem の一意性（別データセットが同じ出力ファイル名を上書きしない）。
  2. 県粒度派生ビューの正規化モード（default_join="prefecture"）と出力先分離。
"""

from data_forge.datasets import DATASETS, CompositeDataset, get_dataset

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
        assert isinstance(ds, CompositeDataset)
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
        assert isinstance(pref, CompositeDataset) and isinstance(muni, CompositeDataset)
        assert pref.upstreams == muni.upstreams
        assert pref.table_name == muni.table_name
