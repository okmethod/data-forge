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

_PREFECTURE_KEYS = ("daynight_prefecture_timeseries",)


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
        "daynight_prefecture_timeseries": "daynight_municipality_timeseries",
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

    既製の時系列帳票（回次跨・県のみ＝案Aで全国は _national_timeseries へ分離）を area 射影するだけなので、
    default_join（正規化モード）も preliminary_upstreams（速報 splice）も持たないことを固定する。
    市区町村ミクロ（age5year_municipality_timeseries）は逆に合併畳込 Stitched（aggregate_to_base）である。
    """
    ds = get_dataset("age5year_prefecture_timeseries")
    assert isinstance(ds, ProjectedDataset)
    assert not hasattr(ds, "default_join")
    assert not hasattr(ds, "preliminary_upstreams")

    micro = get_dataset("age5year_municipality_timeseries")
    assert isinstance(micro, StitchedDataset)
    assert micro.default_join == "aggregate_to_base"
    # 2系列は同じ table_name（bare）を共有する＝1 family・N:1 ハブ。
    assert ds.table_name == micro.table_name == "age5year"


def test_population_prefecture_timeseries_is_longterm_macro() -> None:
    """総人口の県時系列は回次跨世紀マクロ（union＋2025速報 splice・1920〜2020＋速報）。

    戦略B: 旧・空間rollup 版から回次跨 raw 長期へ張り替え。2025速報を持つため ProjectedDataset
    ではなく StitchedDataset(default_join="union") で組み、preliminary_upstreams で速報を継ぐ。
    """
    ds = get_dataset("population_prefecture_timeseries")
    assert isinstance(ds, StitchedDataset)
    assert ds.default_join == "union"
    assert ds.upstreams == ["population_prefecture"]
    assert ds.preliminary_upstreams == ["population_municipality_2025_preliminary"]

    base = get_dataset("population_prefecture")
    assert isinstance(base, Dataset)
    assert base.source_params["stats_data_id"] == "0003410379"
    assert ds.table_name == base.table_name == "population"


def test_by_age_prefecture_timeseries_is_projected_macro() -> None:
    """3区分の県時系列は回次跨世紀マクロ＝射影フロー（ProjectedDataset・1920〜2020）。

    戦略B: 旧・空間rollup 版（市区町村ミクロ→県・1980〜）から回次跨 raw 長期へ張り替えた。
    ミクロ（age3class_municipality_timeseries）は逆に合併畳込 Stitched のまま。table_name は共有。
    """
    ds = get_dataset("age3class_prefecture_timeseries")
    assert isinstance(ds, ProjectedDataset)
    assert ds.upstreams == ["age3class_prefecture"]

    base = get_dataset("age3class_prefecture")
    assert isinstance(base, Dataset)
    assert base.source_params["stats_data_id"] == "0003410383"

    micro = get_dataset("age3class_municipality_timeseries")
    assert isinstance(micro, StitchedDataset)
    assert micro.default_join == "aggregate_to_base"
    assert ds.table_name == micro.table_name == base.table_name == "age3class"


def test_age5_municipality_reiwa_tables_override_muni_levels() -> None:
    """令和型 level4/6 の各回 age5 表（1980-2005）は muni_levels={4,6} を必ず明示上書きする。

    これらの年はグローバル _MUNI_LEVELS が {3}（人口時系列製品向け）だが、各回基本集計の
    5歳/各歳表は市/区=level4・町村=level6・level3=支庁の中間集計、という令和型グレイン。
    override を欠くと extract_atoms が level3 の支庁だけを葉に拾い市区町村フル（level4/6）を全て
    落とす（＝日本人カバレッジが壊れた 1990/1995 のバグ）。この不変条件を設定レベルで固定する。
    2010/2015/2020 はグローバル既定が {4,6} ゆえ override 不要（muni_levels=None 可）。
    """
    keys = [f"age5year_municipality_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005)]
    keys += ["age5year_municipality_1990_total", "age5year_municipality_1995_total"]
    for key in keys:
        ds = get_dataset(key)
        assert ds.muni_levels == frozenset({4, 6}), f"{key}: 令和型表は muni_levels={{4,6}} 必須"


# 案A（地理粒度排他）: 全国と県を別配布に分ける family（射影＝別 ID の national/prefecture パーティション）。
_GEO_SPLIT_PROJECTED = ("age5year", "labor_force", "industry", "occupation_major12", "occupation_major10")
# 案A: 全国と県を別配布に分ける family（single-ID を cleaner の scope で分離）。
_GEO_SPLIT_SINGLE_ID = ("households", "family_type")


def test_projected_geo_split_is_disjoint() -> None:
    """案A: 射影系の _prefecture_timeseries は県のみ・_national_timeseries は全国のみ（同居させない）。

    以前は _prefecture_timeseries が全国＋県を union していたが、地理粒度排他（案A）で全国を剥離し
    _national_timeseries を新設した。両者は disjoint な単一パーティション upstream を射影するだけ。
    """
    for fam in _GEO_SPLIT_PROJECTED:
        pref = get_dataset(f"{fam}_prefecture_timeseries")
        nat = get_dataset(f"{fam}_national_timeseries")
        assert isinstance(pref, ProjectedDataset), f"{fam}_prefecture_timeseries は射影"
        assert isinstance(nat, ProjectedDataset), f"{fam}_national_timeseries は射影"
        assert pref.upstreams == [f"{fam}_prefecture"], f"{fam}: 県ビューは県 upstream のみ"
        assert nat.upstreams == [f"{fam}_national"], f"{fam}: 全国ビューは全国 upstream のみ"
        assert pref.table_name == nat.table_name == fam


def test_single_id_geo_split_shares_source_and_family() -> None:
    """案A: single-ID fact の全国/県分離は同一 statsDataId を scope 違いで2配布にする（fetch 共有）。"""
    for fam in _GEO_SPLIT_SINGLE_ID:
        pref = get_dataset(f"{fam}_prefecture_timeseries")
        nat = get_dataset(f"{fam}_national_timeseries")
        assert isinstance(pref, Dataset) and isinstance(nat, Dataset)
        assert pref.source_params["stats_data_id"] == nat.source_params["stats_data_id"]
        assert pref.table_name == nat.table_name == fam


def test_projected_datasets_reference_existing_base_upstreams() -> None:
    """射影データセットの upstream は実在する基底 Dataset（既製時系列の area パーティション）。"""
    for ds in DATASETS.values():
        if not isinstance(ds, ProjectedDataset):
            continue
        for key in ds.upstreams:
            up = get_dataset(key)
            assert isinstance(up, Dataset), f"{ds.key}: upstream {key!r} は基底 Dataset 必須"
