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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from data_forge import config, derive
from data_forge.area import reconcile as area_reconcile
from data_forge.area.history import ingest as area_ingest
from data_forge.datasets import Dataset, ProjectedDataset, StitchedDataset, get_dataset
from data_forge.output import export_all
from data_forge.public_scope import PublicScopePolicy, find_violations
from data_forge.sources.estat import age5year_municipality as estat_age5year_municipality
from data_forge.sources.estat import fetch as estat_fetch
from data_forge.sources.estat import schema_drift as estat_schema_drift
from data_forge.sources.estat.client import get_stats_list

# NOTE: 現状ソースは e-Stat 固定。
# 複数ソース対応（Source プロトコル + dispatch）はPhase 2 で導入する。


def _cmd_fetch(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    if isinstance(ds, StitchedDataset | ProjectedDataset):
        for key in ds.upstreams:
            _cmd_fetch(get_dataset(key), args)
        return
    stats_data_id = ds.source_params["stats_data_id"]
    raw = estat_fetch.fetch(stats_data_id, refresh=args.refresh, filters=ds.source_params.get("filters"))
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


def _cmd_area_orphans(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    """base_year に届かない消滅アトム（＝合併イベント未整備）を一覧＝次に埋める候補。"""
    atom_fact, _, events = derive.build_atoms(ds, refresh=args.refresh)
    rep = area_reconcile.orphans(atom_fact, events, base_year=args.base_year)
    base = args.base_year or "最新"
    print(f"[area-orphans] {ds.key}: 未整備の消滅アトム {rep.height} 件（base_year={base}）")
    with pl.Config(tbl_rows=50):
        print(rep)


def _cmd_area_check(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    """人口保存と孤児アトムを検証するブロッキングゲート（違反時 exit 1）。

    crossfact-check / public-scope-check と同格のリリースゲート。次のいずれかで exit 1：
    保存則の未知差分（既知差分は受容）、保存則の空振り（総数スライス不一致＝未検証）、
    未整備の孤児アトム。これにより「孤児=0／保存則一致」を新統計投入でも素通りさせない
    不変条件として固定する。dangling_successors は良性の false-positive を含むため advisory
    （警告のみ・exit には影響しない）。
    """
    atom_fact, national, events = derive.build_atoms(ds, refresh=args.refresh)
    failed = False
    cons = area_reconcile.national_conservation(atom_fact, national)
    n_bad = int(cons.filter(~pl.col("ok")).height)
    if cons.height == 0:
        # 総数スライス（全分類軸コード=="0"）が1行もマッチしないと空表になる。
        # このとき n_bad==0 だが「全年一致」ではなく検査ゼロ＝空振りなので ✅ を出さない。
        status = "⚠️ 検査対象0年（総数スライス不一致＝空振り。保存則が未検証）"
        failed = True
    elif n_bad == 0:
        status = "✅ 全年一致"
    else:
        status = f"⚠️ {n_bad} 年で不一致"
        failed = True
    print(f"[area-check] {ds.key}: 人口保存 {status}")
    for row in cons.filter(pl.col("known")).iter_rows(named=True):
        reason = area_reconcile.KNOWN_DIFF_REASONS.get(row["year"], "")
        print(f"  ⚠️ {row['year']} は既知差分 {row['diff']} 人を受容: {reason}")
    print(cons)
    orph = area_reconcile.orphans(atom_fact, events, base_year=args.base_year)
    if orph.height:
        top = orph.head(5).get_column("area_name").to_list()
        print(f"⚠️ 未整備の消滅アトム {orph.height} 件（例: {top}）→ area-orphans で全件確認")
        failed = True
    else:
        print("✅ 孤児アトムなし（全消滅アトムが base_year へ到達）")
    dangling = area_reconcile.dangling_successors(events, atom_fact)
    if dangling.height:
        print(f"⚠️ 後継先が実在しないイベント {dangling.height} 件（後継コードの指定ミス疑い）:")
        print(dangling)
    else:
        print("✅ 全イベントの後継先が実在コードへ着地")
    if failed:
        raise SystemExit(1)


# クロスファクト検算（§data-quality-assurance.md 三角測量）＋日本人スライスの保存則検算。
# 照合相手 ds.key → 検算スペックのリスト（1 データセットに複数検算を束ねる）。
# ハブ（総人口の正典）の既定は population_municipality_timeseries。within-fact 検算は hub_key に自 ds を指す。
_CROSSFACT_HUB = "population_municipality_timeseries"


@dataclass(frozen=True)
class _CrossFactSpec:
    """検算1件の仕様。年別の許容カテゴリ（スコープ外・定義差）とハブ/スライス/モードを同梱する。"""

    name: str  # 検算名（C1・日本人上界 等。実走ログの見出しに使う）
    keys: list[str]
    other_slice: pl.Expr | None = None  # other を絞る述語（地理保存は絞らず None）
    hub_key: str = _CROSSFACT_HUB  # ハブのデータセットキー（within-fact は自 ds を指す）
    hub_slice: pl.Expr | None = None  # within-fact でハブ側を総数スライスへ絞る述語
    hub_with: list[pl.Expr] | None = None  # 集約前に足す派生列（折り畳み検算の粒度写像）
    other_with: list[pl.Expr] | None = None  # 同上（other 側）
    value: str = "population"  # 突合する測定量列（就業系=workers・世帯系=households）
    mode: str = "equality"  # "equality"（diff=0）／"bound"（上界）／"conservation"（全国==Σ県・両符号 known_diff）
    scope_years: frozenset[int] = frozenset()  # other 未収録の年（other==0 を許容）
    known_diff_years: frozenset[int] = frozenset()  # 定義差で diff!=0 が期待される年（diff>=0 を許容）
    known_diffs: dict[int, int] = field(default_factory=dict)  # 既知差の値 pin＝年→期待 Σ|diff|（ずれたら失敗）
    reasons: dict[int, str] = field(default_factory=dict)  # 年 → 許容理由（表示用）


# 日本人スライスの再利用述語（age5 のミクロ系列のみ nationality 軸を持つ）。
_JP_TOTAL = (pl.col("nationality_code") == "1") & (pl.col("age_class_code") == "100")  # 日本人×年齢総数

# C2: age5（市区町村ミクロ系列）の 5歳階級コード → 年齢3区分コード（by_age の age_class_code 1/2/3 に対応）。
# コード体系は市区町村版 age5year_municipality.AGE_CLASS が正典
# （回次跨の県版 age5.AGE5 とは別体系＝140=15〜19歳・240=65〜69歳）。
# 境界は 15歳（130→140）と 65歳（230→240）でコード昇順にクリーンに割れる。
# バンド集合は正典から採り（総数 100・不詳 999 を除く＝3区分は不詳を含まない）drift を防ぐ。
_AGE5_BANDS = [c for c in estat_age5year_municipality.AGE_CLASS if c not in ("100", "999")]  # 110〜310（5歳階級のみ）
_AGE5_TO_AGE3 = {c: ("1" if c < "140" else "2" if c < "240" else "3") for c in _AGE5_BANDS}

# C4: age5 ミクロ(回次別)を県 rollup し マクロ(回次跨) age5year_prefecture と 5歳階級ごとに突合する。
# 2 product は age_class コード体系が別（マクロ=age5year.AGE5／ミクロ=age5year_municipality.AGE_CLASS）で
# 終端も非対称（マクロ 310＝85歳以上 で打ち切り／ミクロ 280-310＝85-89…100歳以上 で細分）。
# 両者を意味（5歳バンド下限年齢）で共通 band へ写像し、マクロ 310 へ ミクロ 85+ 細分(280-310)を畳んで揃える。
# 総数(100)・不詳(999)は map に含めず fold から除く（default=None→スライスで落とす）。
# 正典＝両 source の code 辞書。
_MAC_AGE5_TO_BAND = {  # age5year.AGE5 のコード → 5歳バンド下限年齢（85=85歳以上で打ち切り）
    "110": 0,
    "120": 5,
    "130": 10,
    "150": 15,
    "160": 20,
    "170": 25,
    "180": 30,
    "190": 35,
    "200": 40,
    "210": 45,
    "220": 50,
    "230": 55,
    "240": 60,
    "250": 65,
    "260": 70,
    "280": 75,
    "290": 80,
    "310": 85,
}
_MIC_AGE_TO_BAND = {  # age5year_municipality.AGE_CLASS のコード → 同上（280-310=85+細分は 85 へ畳む）
    "110": 0,
    "120": 5,
    "130": 10,
    "140": 15,
    "150": 20,
    "160": 25,
    "170": 30,
    "180": 35,
    "190": 40,
    "200": 45,
    "210": 50,
    "220": 55,
    "230": 60,
    "240": 65,
    "250": 70,
    "260": 75,
    "270": 80,
    "280": 85,
    "290": 85,
    "300": 85,
    "310": 85,
}
_C4_PRE1980 = frozenset(range(1920, 1980, 5))  # ミクロ(回次別)未収録＝回次跨マクロのみ（scope_out）

_CROSSFACT: dict[str, list[_CrossFactSpec]] = {
    "age5year_municipality_timeseries": [
        # C1: age5 の 国籍総数(nat=0)×年齢総数(age_class=100) スライス == population。
        _CrossFactSpec(
            name="C1 総数×年齢総数 == population",
            keys=["area_code", "sex_code", "year"],
            other_slice=(pl.col("nationality_code") == "0") & (pl.col("age_class_code") == "100"),
            scope_years=frozenset({2025}),
            known_diff_years=frozenset({2005}),
            reasons={
                2025: "age5 未収録（population 速報のみ）＝スコープ外",
                2005: "各歳表が「年齢不詳を除く」ゆえ age5 総数 = population − 年齢不詳（other ≤ hub）",
            },
        ),
        # C2: age5(nat=0・市区町村) を年齢3区分へ畳込 == population_by_age（別ソース＝独立検算）。
        # 5歳階級を age3_code へ写像し keys に含め、by_age の区分(1/2/3)と区分ごとに突合する。
        # 2005 は各歳表の「埋め込み不詳」（Σ5歳 ≤ 総数＝5歳バンドに未分類残差が残る）で
        # 老年 fold が by_age より僅少（by_age ≥ age5・向き diff≥0）＝known_diff。
        _CrossFactSpec(
            name="C2 age5→3区分 == population_by_age",
            keys=["area_code", "sex_code", "age3_code", "year"],
            hub_key="age3class_municipality_timeseries",
            hub_slice=pl.col("age_class_code").is_in(["1", "2", "3"]),  # by_age の3区分（総数0/不詳9を除く）
            hub_with=[pl.col("age_class_code").alias("age3_code")],
            other_slice=(pl.col("nationality_code") == "0") & pl.col("age_class_code").is_in(_AGE5_BANDS),
            other_with=[pl.col("age_class_code").replace_strict(_AGE5_TO_AGE3, default=None).alias("age3_code")],
            scope_years=frozenset({2025}),
            known_diff_years=frozenset({2005}),
            reasons={
                2025: "age5 未収録（population 速報のみ）＝スコープ外",
                2005: "各歳表の埋め込み不詳で 5歳バンドΣ≤総数＝老年 fold が by_age より僅少（other≤hub）",
            },
        ),
        # J1（上界）: 日本人(nat=1)×年齢総数 ≤ population。diff = 総人口 − 日本人 = 外国人 ≥ 0。
        # 外国人コードが無く等値にならないため部分集合関係のみ保証（日本人スライスの実在も要求）。
        _CrossFactSpec(
            name="J1 日本人 ≤ population（上界）",
            keys=["area_code", "sex_code", "year"],
            other_slice=_JP_TOTAL,
            mode="bound",
            scope_years=frozenset({1980, 1985, 2025}),  # 日本人 age5 未収録（総人口のみ）＝other==0 を許容
            reasons={
                1980: "日本人 age5 未収録（総人口のみ・国籍軸なし）＝スコープ外",
                1985: "日本人 age5 未収録（総人口のみ・国籍軸なし）＝スコープ外",
                2025: "age5 未収録（population 速報のみ）＝スコープ外",
            },
        ),
        # J2（年齢保存・within-fact）: 日本人 Σ(age_class≠100) == 日本人 年齢総数(age_class=100)。
        # age5 の age_class は 100=総数／5歳階級／999=不詳 のみ（中間集計なし）＝Σ内訳で二重計上しない。
        _CrossFactSpec(
            name="J2 日本人 年齢保存（within-fact）",
            keys=["area_code", "sex_code", "year"],
            hub_key="age5year_municipality_timeseries",
            hub_slice=_JP_TOTAL,
            other_slice=(pl.col("nationality_code") == "1") & (pl.col("age_class_code") != "100"),
            known_diff_years=frozenset({2005}),  # 2005 各歳表は 5歳階級再掲が不詳を含まず総数 T01 は含む
            reasons={
                2005: "2005 各歳表は 5歳階級再掲に年齢不詳が無い一方 総数(T01) は含む"
                "＝総数 ≥ Σ5歳（不詳分・不詳行は非materialize）",
            },
        ),
        # J3（男女保存・within-fact）: 日本人 男(sex=1)+女(sex=2) == 日本人 男女計(sex=0)。
        _CrossFactSpec(
            name="J3 日本人 男女保存（within-fact）",
            keys=["area_code", "year"],
            hub_key="age5year_municipality_timeseries",
            hub_slice=_JP_TOTAL & (pl.col("sex_code") == "0"),
            other_slice=_JP_TOTAL & pl.col("sex_code").is_in(["1", "2"]),
        ),
        # C4: age5 ミクロ→県 rollup == age5year_prefecture（回次跨マクロ）。別 product 間を県×sex×5歳階級で照合。
        # 県 rollup は area_code 先頭2桁（pref_code）で束ね、age は共通 band へ写像して突合する。
        # mode=conservation: 1980-2000 は 2 product の県レベル集計差（秘匿/境界振替）が両符号で ±相殺し、
        # 2005 はミクロ各歳表が年齢不詳を除く一方向差＝ともに known_diff（両符号受容）。2010-2020 は厳密 diff=0。
        _CrossFactSpec(
            name="C4 age5→県rollup == age5year_prefecture",
            keys=["pref_code", "sex_code", "age_band", "year"],
            hub_key="age5year_prefecture_timeseries",
            hub_with=[
                pl.col("area_code").str.slice(0, 2).alias("pref_code"),
                pl.col("age_class_code").replace_strict(_MAC_AGE5_TO_BAND, default=None).alias("age_band"),
            ],
            hub_slice=pl.col("age_band").is_not_null(),
            other_with=[
                pl.col("area_code").str.slice(0, 2).alias("pref_code"),
                pl.col("age_class_code").replace_strict(_MIC_AGE_TO_BAND, default=None).alias("age_band"),
            ],
            other_slice=(pl.col("nationality_code") == "0") & pl.col("age_band").is_not_null(),
            mode="conservation",
            scope_years=_C4_PRE1980,
            # 既知差の値 pin（年→Σ|diff|）。cleaner/transform の取り違えで既知年の差が動けば失敗する。
            known_diffs={1980: 8666, 1985: 8600, 1990: 8648, 1995: 8508, 2000: 8160, 2005: 28574},
            reasons={
                1980: "2 product(回次別ミクロ vs 回次跨マクロ)の県レベル集計差（秘匿/境界振替・両符号・年内±相殺）",
                1985: "2 product の県レベル集計差（秘匿/境界振替・両符号・年内±相殺）",
                1990: "2 product の県レベル集計差（秘匿/境界振替・両符号・年内±相殺）",
                1995: "2 product の県レベル集計差（秘匿/境界振替・両符号・年内±相殺）",
                2000: "2 product の県レベル集計差（秘匿/境界振替・両符号・年内±相殺）",
                2005: "ミクロ各歳表が年齢不詳を除く＝マクロ ≥ ミクロ fold（C1/C2 の2005と同因・diff≥0）",
            },
        ),
    ],
    # C5: daynight 夜間(常住地・daynight_code=0) == population（全国＝keys=["year"] で市区町村を合算）。
    # 2010-2020 は厳密 diff=0。1990-2005 は従業地・通学地集計の常住地人口ベースが基本集計人口と相違し
    # pop>night（〜0.1-0.4%・一方向 diff≥0）＝known_diff。1980/1985/2025 は daynight 未収録＝scope_out。
    "daynight_municipality_timeseries": [
        _CrossFactSpec(
            name="C5 夜間(常住地) == population（全国）",
            keys=["year"],
            hub_slice=pl.col("sex_code") == "0",
            other_slice=pl.col("daynight_code") == "0",
            scope_years=frozenset({1980, 1985, 2025}),
            # 既知差の値 pin（年→diff＝pop−night）。全国1セル/年ゆえ diff がそのまま Σ|diff|。ずれたら失敗。
            known_diffs={1990: 326357, 1995: 130973, 2000: 228561, 2005: 482341},
            reasons={
                1990: "従業地・通学地集計の常住地(夜間)人口ベースが基本集計人口と相違（pop≥night・2010〜で解消）",
                1995: "従業地・通学地集計 vs 基本集計 のベース差（pop≥night）",
                2000: "従業地・通学地集計 vs 基本集計 のベース差（pop≥night）",
                2005: "従業地・通学地集計 vs 基本集計 のベース差（pop≥night）",
            },
        ),
    ],
    # C3: by_age の 年齢総数(age_class=0) スライス == population（既存「総数スライス一致」の明文化）。
    "age3class_municipality_timeseries": [
        _CrossFactSpec(
            name="C3 年齢総数 == population",
            keys=["area_code", "sex_code", "year"],
            other_slice=pl.col("age_class_code") == "0",
            scope_years=frozenset({2025}),  # by_age も 1980-2020＝2025 速報は未収録
            reasons={2025: "by_age 未収録（population 速報のみ）＝スコープ外"},
        ),
    ],
}


# 地理保存則（G）: 全国/県を別配布に分けた各 family で、全国(_national_timeseries) == Σ都道府県
# (_prefecture_timeseries) を分類軸×year で検算する（split が値を落とさない/二重化しない保証）。
# hub=全国・other=県 を area_code を含めない keys で突合＝other 側は自動で47県合算される。
# scope_years＝県が未収録の旧回（全国のみ・other==0 を許容）。known_diff_years＝原資料の集計差
# （区未定分/按分・沖縄扱い等）で全国とΣ県が僅かにズレる旧回（両符号を文書化して受容）。
def _geo_conservation_spec(
    family: str,
    axes: list[str],
    value: str,
    *,
    scope_years: frozenset[int] = frozenset(),
    known_diff_years: frozenset[int] = frozenset(),
    reasons: dict[int, str] | None = None,
) -> _CrossFactSpec:
    return _CrossFactSpec(
        name=f"G 全国 == Σ都道府県（{value}）",
        keys=[*axes, "year"],
        hub_key=f"{family}_national_timeseries",
        value=value,
        mode="conservation",
        scope_years=scope_years,
        known_diff_years=known_diff_years,
        reasons=reasons or {},
    )


_CROSSFACT.update(
    {
        f"{family}_prefecture_timeseries": [spec]
        for family, spec in {
            "labor_force": _geo_conservation_spec(
                "labor_force",
                ["sex_code", "labor_status_code"],
                "population",
                known_diff_years=frozenset({1950, 1960, 1965, 1985}),
                reasons={
                    1950: "旧回の原資料集計差（区未定分/按分）で 全国 と Σ県 が僅少ズレ（両符号）",
                    1960: "旧回の原資料集計差（区未定分/按分）で 全国 と Σ県 が僅少ズレ（両符号）",
                    1965: "旧回の原資料集計差（区未定分/按分）で 全国 と Σ県 が僅少ズレ（両符号）",
                    1985: "旧回の原資料集計差で Σ県 が 全国 を僅少上回る（負符号）",
                },
            ),
            "industry": _geo_conservation_spec(
                "industry",
                ["sex_code", "industry_code"],
                "workers",
                scope_years=frozenset({1995, 2000}),
                reasons={
                    1995: "都道府県 産業表は 2005〜＝旧回は全国のみ（other==0）＝スコープ外",
                    2000: "都道府県 産業表は 2005〜＝旧回は全国のみ（other==0）＝スコープ外",
                },
            ),
            "occupation_major12": _geo_conservation_spec(
                "occupation_major12",
                ["sex_code", "occupation_code"],
                "workers",
                scope_years=frozenset({1995, 2000}),
                reasons={
                    1995: "都道府県 職業(12区分)表は 2005〜＝旧回は全国のみ（other==0）＝スコープ外",
                    2000: "都道府県 職業(12区分)表は 2005〜＝旧回は全国のみ（other==0）＝スコープ外",
                },
            ),
            "occupation_major10": _geo_conservation_spec(
                "occupation_major10",
                ["sex_code", "occupation_code"],
                "workers",
                scope_years=frozenset({1950, 1955, 1960, 1965, 1970, 1975}),
                known_diff_years=frozenset({1980, 1985, 1990, 1995}),
                reasons={
                    **{
                        y: "都道府県 職業(10区分)表は 1980〜＝旧回は全国のみ（other==0）＝スコープ外"
                        for y in (1950, 1955, 1960, 1965, 1970, 1975)
                    },
                    1980: "全国表と県表で職業大分類の境界振り分けが相違（コード対で±相殺・総数は一致）",
                    1985: "全国表と県表で職業大分類の境界振り分けが相違（コード対で±相殺・総数は一致）",
                    1990: "全国表と県表で職業大分類の境界振り分けが相違（コード対で±相殺・総数は一致）",
                    1995: "全国表と県表で職業大分類の境界振り分けが相違（コード対で±相殺・総数は一致）",
                },
            ),
            # age5 は per-age（5歳階級ごと）で保存検算する。全国表が近年 85+ を細分(320-370)で持つ回は
            # clean_national が 320-370 を 85歳以上(310) へ畳んで共通粒度へ揃える（総数スライスでは総数が
            # 保存し不詳が 85+ を吸収するため band 誤配分を見逃す＝per-age だけが捕捉する）。
            # 残差は pre-1960 の回次跨（全国表 vs 県表）の史料集計差のみ＝両符号 known_diff で受容。
            "age5year": _geo_conservation_spec(
                "age5year",
                ["sex_code", "age_class_code"],
                "population",
                known_diff_years=frozenset({1920, 1925, 1930, 1935, 1945, 1950, 1955}),
                reasons={
                    y: "回次跨の全国表と県表で史料の集計が相違する旧回（両符号・pre-1960）"
                    for y in (1920, 1925, 1930, 1935, 1945, 1950, 1955)
                },
            ),
            "households": _geo_conservation_spec(
                "households",
                ["household_type_code"],
                "households",
                known_diff_years=frozenset({1960}),
                reasons={1960: "1960年は原資料の集計差で 全国 と Σ県 が僅少ズレ（32世帯）"},
            ),
            "family_type": _geo_conservation_spec(
                "family_type",
                ["family_type_code"],
                "households",
            ),
        }.items()
    }
)


def _run_crossfact_spec(spec: _CrossFactSpec, other: pl.DataFrame, hub: pl.DataFrame) -> int:
    """検算1件を走らせ結果を表示し、真の不一致キー数を返す。"""
    rep = area_reconcile.cross_fact(
        hub,
        other,
        keys=spec.keys,
        hub_slice=spec.hub_slice,
        other_slice=spec.other_slice,
        hub_with=spec.hub_with,
        other_with=spec.other_with,
        value=spec.value,
        scope_years=spec.scope_years,
        known_diff_years=spec.known_diff_years,
        known_diffs=spec.known_diffs,
        mode=spec.mode,
    )
    n_bad = int(rep.filter(~pl.col("ok")).height)
    head = f"  [{spec.name}] vs {spec.hub_key}"
    if "year" not in spec.keys:  # 年軸を持たない検算は総キーだけ突合
        print(f"{head}: {'✅ 全キー一致' if n_bad == 0 else f'⚠️ {n_bad} キーで不一致'}")
    else:
        summary = (
            rep.with_columns(bad=~pl.col("ok"), adiff=pl.col("diff").abs())
            .group_by("year", "status")
            .agg(keys=pl.len(), bad=pl.col("bad").sum(), max_adiff=pl.col("adiff").max())
            .sort("year")
        )
        verdict = "✅ 全キー整合" if n_bad == 0 else f"⚠️ 真の不一致 {n_bad} キー"
        print(f"{head}: {verdict}")
        with pl.Config(tbl_rows=40):
            print(summary)
        for year in sorted(spec.reasons):
            print(f"    ・{year}: {spec.reasons[year]}")
    if n_bad:  # 許容カテゴリに収まらない真の不一致だけを詳細表示
        with pl.Config(tbl_rows=30):
            print(rep.filter(~pl.col("ok")).sort(pl.col("diff").abs(), descending=True))
    return n_bad


def _cmd_crossfact_check(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    """クロスファクト検算＋日本人スライスの保存則検算を実データで走らせる。

    別ソース・別系統から到達した同一の総人口（conformed dimension）を照合し、加えて日本人スライスの
    上界（≤ 総人口）と保存則（年齢・男女）を検算する。全ファクトを同じ base_year で aggregate_to_base
    畳込してから突合するので、level7 カバレッジ差を吸収する。
    """
    specs = _CROSSFACT.get(ds.key)
    if specs is None:
        raise SystemExit(f"{ds.key!r} はクロスファクト検算の対象外（対応: {sorted(_CROSSFACT)}）")
    other, _ = derive.load(ds, refresh=args.refresh, join="aggregate_to_base", base_year=args.base_year)
    hub_cache: dict[str, pl.DataFrame] = {ds.key: other}  # within-fact は other（自 ds）を再利用

    def load_hub(key: str) -> pl.DataFrame:
        if key not in hub_cache:
            hub_cache[key], _ = derive.load(
                get_dataset(key), refresh=args.refresh, join="aggregate_to_base", base_year=args.base_year
            )
        return hub_cache[key]

    print(f"[crossfact-check] {ds.key}: {len(specs)} 検算（match=diff0／bound=上界／known_diff/scope_out=許容）")
    total_bad = sum(_run_crossfact_spec(spec, other, load_hub(spec.hub_key)) for spec in specs)
    if total_bad:
        raise SystemExit(1)


def _cmd_public_scope_check(args: argparse.Namespace) -> None:
    """公開範囲の流出ゲート: build/data に公開範囲外の市区町村コードが無いか検査する。

    検査対象は SQL 絞り込み後の公開物（build/data）に限る。pipeline の生成物は全部入りが
    正常なので流出は build にしか発生しない。許可値の正典は public_scope.yaml（SSoT）。
    """
    policy = PublicScopePolicy.load(args.policy)
    build_data = Path(args.build_data)
    if not any(build_data.glob("**/*.parquet")):
        raise SystemExit(f"[public-scope-check] 検査対象の parquet が無い（{build_data}）。先にビルドが必要。")
    allow = sorted(policy.allow_municipalities)
    violations = find_violations(build_data, policy)
    if violations:
        print(f"[public-scope-check] ✗ 公開範囲外の市区町村コードを検出（policy allow={allow}）")
        for code, sample in sorted(violations.items()):
            print(f"  - {code}  (例: {sample})")
        print("  → SQL の絞り込みかポリシーのどちらかが不整合。修正するまでデプロイ不可。")
        raise SystemExit(1)
    print(f"[public-scope-check] ✓ 市区町村粒度コードは許可分のみ {allow}")


def _underlying_fetches(ds: Dataset | StitchedDataset | ProjectedDataset) -> list[tuple[str, dict[str, str] | None]]:
    """データセットが取得する e-Stat 表を (stats_data_id, filters) の一意リストで返す。

    Stitched/Projected は upstream を再帰展開する。同一 statsDataId が複数 upstream から
    参照されても cache_key で畳んで重複取得・重複検査を避ける。
    """
    seen: dict[str, tuple[str, dict[str, str] | None]] = {}
    stack: list[Dataset | StitchedDataset | ProjectedDataset] = [ds]
    while stack:
        cur = stack.pop()
        if isinstance(cur, StitchedDataset | ProjectedDataset):
            upstreams = list(cur.upstreams)
            if isinstance(cur, StitchedDataset):
                upstreams += cur.preliminary_upstreams
            stack.extend(get_dataset(k) for k in upstreams)
            continue
        stats_data_id = cur.source_params["stats_data_id"]
        filters = cur.source_params.get("filters")
        seen.setdefault(estat_fetch.cache_key(stats_data_id, filters), (stats_data_id, filters))
    return list(seen.values())


def _print_signature_diff(diff: estat_schema_drift.SignatureDiff) -> None:
    if diff.axes_added:
        print(f"    + 軸追加: {diff.axes_added}")
    if diff.axes_removed:
        print(f"    - 軸削除: {diff.axes_removed}")
    for axis_id, (old, new) in sorted(diff.name_changed.items()):
        print(f"    ~ 軸名変更 {axis_id}: {old!r} → {new!r}")
    for axis_id, codes in sorted(diff.codes_added.items()):
        print(f"    + コード追加 {axis_id}: {codes}")
    for axis_id, codes in sorted(diff.codes_removed.items()):
        print(f"    - コード削除 {axis_id}: {codes}")


def _cmd_schema_check(ds: Dataset | StitchedDataset | ProjectedDataset, args: argparse.Namespace) -> None:
    """新年度スキーマ・ドリフトの検出ゲート（入口ガードの軸構成版・違反時 exit 1）。

    取得済みレスポンスの軸シグネチャ（軸ID＋名称＋分類コード）をコミット済みスナップショット
    （schema_snapshots.json）と突合し、軸の増減・意味の入れ替わり・分類コードの増減を検出する。
    `--update` でスナップショットを（初回=シード／以降=更新）書き込む。未スナップショットの表は
    exit 1 で止め、`--update` による意図的なシードを促す（＝新年度投入を素通りさせない）。
    """
    registry = estat_schema_drift.load_registry()
    updated = False
    failed = False
    print(f"[schema-check] {ds.key}: {'スナップショット更新' if args.update else '軸ドリフト検査'}")
    for stats_data_id, filters in _underlying_fetches(ds):
        key = estat_fetch.cache_key(stats_data_id, filters)
        raw = estat_fetch.fetch(stats_data_id, refresh=args.refresh, filters=filters)
        actual = estat_schema_drift.axis_signature(raw)
        if args.update:
            registry[key] = actual
            updated = True
            print(f"  ✅ {key}: 軸 {sorted(actual)} をスナップショット")
            continue
        expected = registry.get(key)
        if expected is None:
            print(f"  ⚠️ {key}: 未スナップショット（--update でシード）")
            failed = True
            continue
        diff = estat_schema_drift.diff_signature(expected, actual)
        if diff.has_drift:
            print(f"  ⚠️ {key}: 軸ドリフト検出")
            _print_signature_diff(diff)
            failed = True
        else:
            print(f"  ✅ {key}: 軸構成一致")
    if updated:
        estat_schema_drift.save_registry(registry)
        print("→ schema_snapshots.json を更新（差分をレビューしてコミット）")
    if failed:
        raise SystemExit(1)


def _cmd_area_ingest(args: argparse.Namespace) -> None:
    """廃置分合の生CSV を正規化イベント（events_parsed.csv）へ変換して保存する。"""
    src = args.path
    if src is None:
        csvs = sorted(config.AREA_HISTORY_RAW.glob("*.csv"))
        if len(csvs) != 1:
            raise SystemExit(f"{config.AREA_HISTORY_RAW} にCSVが {len(csvs)} 件。パスを引数で指定してください。")
        src = csvs[0]
    ev = area_ingest.parse_history_csv(src, encoding=args.encoding)
    config.AREA_EVENTS_PARSED.parent.mkdir(parents=True, exist_ok=True)
    ev.write_csv(config.AREA_EVENTS_PARSED)
    print(f"[area-ingest] {src} → {ev.height:,} イベント → {config.AREA_EVENTS_PARSED}")
    print(ev.group_by("kind").len().sort("len", descending=True))


def _estat_field(value: Any) -> str:
    """e-Stat のフィールドは {"$": 値} の dict にも素の値にもなり得るため吸収する。"""
    if isinstance(value, dict):
        return str(value.get("$", ""))
    return "" if value is None else str(value)


def _cmd_estat_search(args: argparse.Namespace) -> None:
    """帳票リスト（getStatsList）を検索し、statsDataId と表題を端末へ一覧表示する。

    探索専用の使い捨てツール。目当ての statsDataId を突き止めたら docs へ手で記録する。
    キャッシュや docs 生成はしない（正典は docs/distributions/ 側）。
    """
    tables = get_stats_list(
        stats_code=args.stats_code,
        search_word=args.word,
        survey_years=args.survey_years,
        search_kind=args.search_kind,
        limit=args.limit,
    )
    cond = ", ".join(
        f"{k}={v}"
        for k, v in (
            ("statsCode", args.stats_code),
            ("word", args.word),
            ("surveyYears", args.survey_years),
        )
        if v is not None
    )
    # e-Stat は表題の部分一致で同一 statsDataId を複数回返すため id 単位で畳む
    seen: set[str] = set()
    lines: list[str] = []
    for t in tables:
        stats_data_id = _estat_field(t.get("@id"))
        if stats_data_id in seen:
            continue
        seen.add(stats_data_id)
        title = _estat_field(t.get("TITLE")) or _estat_field(t.get("STATISTICS_NAME"))
        survey = _estat_field(t.get("SURVEY_DATE"))
        rows = _estat_field(t.get("OVERALL_TOTAL_NUMBER"))
        lines.append(f"  {stats_data_id}  {survey:>8}  {title}（行数: {rows}）")

    print(f"[estat-search] {len(lines)} 件" + (f"（{cond}）" if cond else ""))
    for line in lines:
        print(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-forge", description="公的データ精製パイプライン")
    sub = parser.add_subparsers(dest="command", required=True)

    # 廃置分合CSV → 正規化イベント（データセット非依存の単発コマンド）
    pi = sub.add_parser("area-ingest", help="廃置分合の生CSVを events_parsed.csv へ正規化")
    pi.add_argument("path", nargs="?", default=None, help="生CSVパス（省略時は data/raw/history/ の単一CSV）")
    pi.add_argument(
        "--encoding",
        default="utf8",
        help="生CSVのエンコーディング（既定 utf8。Shift-JIS 版なら shift-jis）",
    )
    pi.set_defaults(handler=lambda ds, args: _cmd_area_ingest(args))

    # 公開範囲の流出ゲート（ダッシュボード公開ビルドを SSoT ポリシーと照合。データセット非依存）
    pp = sub.add_parser("public-scope-check", help="公開範囲の流出ゲート: build/data を public_scope.yaml と照合")
    pp.add_argument("--policy", required=True, help="公開範囲ポリシー public_scope.yaml のパス")
    pp.add_argument("--build-data", required=True, help="検査対象ディレクトリ（例: build/data）")
    pp.set_defaults(handler=lambda ds, args: _cmd_public_scope_check(args))

    # 帳票リスト検索（getStatsList）＝目当ての statsDataId を探す探索ツール
    ps = sub.add_parser("estat-search", help="帳票リストを検索し statsDataId を一覧表示")
    ps.add_argument("--stats-code", default=None, help="政府統計コード（例: 00200521=国勢調査）")
    ps.add_argument("--word", default=None, help="検索キーワード（searchWord。AND/OR 可）")
    ps.add_argument("--survey-years", default=None, help="調査年（yyyy / yyyymm / yyyymm-yyyymm 範囲）")
    ps.add_argument(
        "--search-kind",
        type=int,
        default=None,
        help="検索種別（1=統計情報 既定, 2=小地域/メッシュ）",
    )
    ps.add_argument("--limit", type=int, default=None, help="取得件数の上限")
    ps.set_defaults(handler=lambda ds, args: _cmd_estat_search(args))

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
        p.add_argument("dataset", help="派生データセットキー（例: population_municipality_timeseries）")
        p.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
        p.add_argument("--base-year", type=int, default=None, help="基準年（既定=最新年）")
        p.set_defaults(handler=handler)

    # 新年度スキーマ・ドリフト検出（軸シグネチャをコミット済みスナップショットと突合）
    pd_ = sub.add_parser("schema-check", help="新年度スキーマ・ドリフト検出: 軸構成をスナップショットと突合")
    pd_.add_argument("dataset", help="データセットキー（Stitched/Projected は upstream を再帰展開）")
    pd_.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
    pd_.add_argument("--update", action="store_true", help="スナップショットを書き込む（初回シード／更新）")
    pd_.set_defaults(handler=_cmd_schema_check)

    # クロスファクト検算（総人口スライスを population ハブと突合＝§data-quality-assurance.md 三角測量）
    pc = sub.add_parser("crossfact-check", help="クロスファクト検算: 総人口スライスを population ハブと突合")
    pc.add_argument("dataset", help="照合相手データセットキー（例: age5year_municipality_timeseries）")
    pc.add_argument("--refresh", action="store_true", help="キャッシュを無視して再取得")
    pc.add_argument("--base-year", type=int, default=None, help="両ファクトの畳込基準年（既定=最新年）")
    pc.set_defaults(handler=_cmd_crossfact_check)

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
