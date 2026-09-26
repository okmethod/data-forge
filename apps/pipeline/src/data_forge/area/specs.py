"""検算スペック（政策レジストリ）: reconcile エンジンが消費する既知差分と検算登録簿。

reconcile.py は検算の「機構（エンジン）」に徹し、本モジュールは検算の「スペック定義」を持つ:
    - CrossFactSpec / CROSSFACT … クロスファクト検算・保存則検算・地理保存の登録簿
      （データセットキー → 検算スペック。年別の許容カテゴリ・スライス・モードを同梱）。

spec が参照する **pin 値**（C4/C5 の Σ|diff|＝`known_pins.CROSSFACT_C4`/`CROSSFACT_C5`）は
差分値の一元管理のため `known_pins.py` に分離している（＝定義は specs・値は known_pins）。
検算の意味論・許容カテゴリの why は docs/data-quality-assurance.md が正典。
"""

from dataclasses import dataclass, field

import polars as pl

from data_forge import known_pins
from data_forge.sources.estat import age5year_municipality as estat_age5year_municipality

# クロスファクト検算（§data-quality-assurance.md 三角測量）＋日本人スライスの保存則検算。
# 照合相手 ds.key → 検算スペックのリスト（1 データセットに複数検算を束ねる）。
# ハブ（総人口の正典）の既定は population_municipality_timeseries。within-fact 検算は hub_key に自 ds を指す。
_CROSSFACT_HUB = "population_municipality_timeseries"


@dataclass(frozen=True)
class CrossFactSpec:
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
    # 年→許容理由。scope_out / known_diff_year も含む「年ステータス」の説明で、
    # pin 値とは別粒度（値を持たず理由だけの年が大半）ゆえ spec 側が正典＝known_pins には移さない。
    reasons: dict[int, str] = field(default_factory=dict)


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

# H: households ミクロは 1985 始まり（1980 以前は各回の「一般/施設」別 世帯数表が無い）。
# マクロ households_prefecture は 1960/1970/1975/1980 も持つ＝これらはミクロ側 scope_out。
_HOUSEHOLDS_MACRO_ONLY = frozenset({1960, 1970, 1975, 1980})
# 世帯人員(household_members)はミクロ各回表が 2015/2020 のみ収録＝それ以外の年は scope_out。
_HH_MEMBERS_MICRO_ONLY_GAP = frozenset({1985, 1990, 1995, 2000, 2005, 2010})
_HH_MEMBERS_SCOPE = _HOUSEHOLDS_MACRO_ONLY | _HH_MEMBERS_MICRO_ONLY_GAP

# F: family_type ミクロは 2005-2020（1995/2000 は市区町村版が旧分類しか無く新分類マクロと非互換ゆえ不採用）。
# マクロ family_type_prefecture は 1995-2020 を持つ＝1995/2000 はミクロ側 scope_out。
_FAMILY_TYPE_MACRO_ONLY = frozenset({1995, 2000})
_FT_OLDCLASS_REASON = "回次跨マクロのみ（市区町村版は旧分類＝新分類マクロと非互換で不採用）"
_FT_MEMBERS_GAP_REASON = "世帯人員はミクロ軽量表（2015=0003148560/2020=0003445080）が一般世帯数のみ収録＝スコープ外"

# I/O/L: 就業系ミクロ(産業/職業/労働力)は 2015 のみ着手（唯一「男女×大分類×市区町村」の軽量2次元 marginal が
# 揃う年）。県跨マクロ(_prefecture_timeseries)が持つ他年はミクロ未収録＝scope_out
# （着手順 2020→2010→1995-2005 で順次外す）。悉皆カウントゆえ 2015 は県レベルで一致（F1/H1 と同型）。
_EMPLOYED_MUNI_YEARS = frozenset({2015})
_INDUSTRY_PREF_YEARS = frozenset({2005, 2010, 2015, 2020})  # industry_prefecture_timeseries の収録年
_OCCUPATION_PREF_YEARS = frozenset({2005, 2010, 2015, 2020})  # occupation_major12_prefecture_timeseries の収録年
_LABOR_FORCE_PREF_YEARS = frozenset(range(1950, 2021, 5))  # labor_force_prefecture_timeseries の収録年（5年間隔）
_EMPLOYED_MUNI_ONLY_REASON = "就業系ミクロは2015のみ着手＝他年は未収録（着手順 2020→2010→1995-2005 で順次追加）"

CROSSFACT: dict[str, list[CrossFactSpec]] = {
    "age5year_municipality_timeseries": [
        # C1: age5 の 国籍総数(nat=0)×年齢総数(age_class=100) スライス == population。
        CrossFactSpec(
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
        CrossFactSpec(
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
        CrossFactSpec(
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
        CrossFactSpec(
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
        CrossFactSpec(
            name="J3 日本人 男女保存（within-fact）",
            keys=["area_code", "year"],
            hub_key="age5year_municipality_timeseries",
            hub_slice=_JP_TOTAL & (pl.col("sex_code") == "0"),
            other_slice=_JP_TOTAL & pl.col("sex_code").is_in(["1", "2"]),
        ),
        # C4: age5 ミクロ→県 rollup == age5year_prefecture（回次跨マクロ）。別 product 間を県×sex×5歳階級で照合。
        # 県 rollup は area_code 先頭2桁（pref_code）で束ね、age は共通 band へ写像して突合する。
        # mode=conservation: 1980-2000 は 2 product の県レベル集計差（秘匿/境界振替）が両符号で ±相殺し、
        # 2005 はミクロ各歳表が年齢不詳を除く一方向差＝ともに known_diff（両符号許容）。2010-2020 は厳密 diff=0。
        CrossFactSpec(
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
            # 既知差の値 pin（年→Σ|diff|）は known_pins.py が正典。取り違えで既知年の差が動けば失敗する。
            known_diffs=known_pins.CROSSFACT_C4,
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
    # H: households ミクロ(回次別)→県 rollup == households_prefecture（回次跨マクロ）。別 product 間の検算オラクル。
    # 世帯は悉皆カウント（標本でない）ゆえ、回次別と回次跨が県レベルで一致。
    # 世帯数・世帯人員の2測度を別 spec で照合。
    # ミクロは aggregate_to_base（2020境界へ合併畳込）後に県 rollup するため、
    # 県跨ぎ合併（山口村: 長野→岐阜 2005 等）が旧年（1985-2000）で県間を移動
    # ＝マクロ（各年境界）と両符号 ±相殺（net=0）＝C4 と同型の境界振替。
    # → H1 は mode=conservation＋Σ|diff| 値 pin（2005 以降は境界一致で diff=0）。
    # 県 rollup は area_code 先頭2桁で束ねる。
    "households_municipality_timeseries": [
        CrossFactSpec(
            name="H1 世帯数 ミクロ→県rollup == households_prefecture",
            keys=["pref_code", "household_type_code", "year"],
            hub_key="households_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="households",
            mode="conservation",
            scope_years=_HOUSEHOLDS_MACRO_ONLY,
            known_diffs=known_pins.CROSSFACT_H1,
            reasons={
                **{
                    y: "回次跨マクロのみ（ミクロは1985始まり＝各回の一般/施設別 世帯数表が無い旧回）"
                    for y in _HOUSEHOLDS_MACRO_ONLY
                },
                **{
                    y: "県跨ぎ合併の境界振替（山口村 長野→岐阜 2005 等）＝ミクロ2020境界 vs マクロ各年境界・両符号±相殺"
                    for y in (1985, 1990, 1995, 2000)
                },
            },
        ),
        CrossFactSpec(
            name="H2 世帯人員 ミクロ→県rollup == households_prefecture",
            keys=["pref_code", "household_type_code", "year"],
            hub_key="households_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="household_members",
            scope_years=_HH_MEMBERS_SCOPE,
            reasons={
                **{y: "回次跨マクロのみ（ミクロは1985始まり）" for y in _HOUSEHOLDS_MACRO_ONLY},
                **{y: "世帯人員はミクロ各回表が 2015/2020 のみ収録＝スコープ外" for y in _HH_MEMBERS_MICRO_ONLY_GAP},
            },
        ),
    ],
    # F: family_type ミクロ(回次別)→県 rollup == family_type_prefecture（回次跨マクロ）。別 product 間の検算オラクル。
    # 世帯は悉皆カウント（標本でない）ゆえ、回次別と回次跨が県レベルで一致（H1 と同型）。
    # ミクロは 2005-2020（すべて新分類）＝各年 diff=0（2020境界どうしで合併振替も無く known_diff pin 不要）。
    # 1995/2000 は市区町村版が旧分類しか無く新分類マクロと非互換ゆえミクロ不採用＝scope_out。
    # 県 rollup は area_code 先頭2桁で束ねる。世帯数(F1)・世帯人員(F2)を別 spec で照合。
    "family_type_municipality_timeseries": [
        CrossFactSpec(
            name="F1 世帯数 ミクロ→県rollup == family_type_prefecture",
            keys=["pref_code", "family_type_code", "year"],
            hub_key="family_type_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="households",
            mode="conservation",
            scope_years=_FAMILY_TYPE_MACRO_ONLY,
            reasons={y: _FT_OLDCLASS_REASON for y in _FAMILY_TYPE_MACRO_ONLY},
        ),
        CrossFactSpec(
            name="F2 世帯人員 ミクロ→県rollup == family_type_prefecture",
            keys=["pref_code", "family_type_code", "year"],
            hub_key="family_type_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="household_members",
            mode="conservation",
            scope_years=_FAMILY_TYPE_MACRO_ONLY | frozenset({2015, 2020}),
            reasons={
                **{y: _FT_OLDCLASS_REASON for y in _FAMILY_TYPE_MACRO_ONLY},
                **{y: _FT_MEMBERS_GAP_REASON for y in (2015, 2020)},
            },
        ),
    ],
    # I/O/L: 就業系ミクロ(回次別)→県 rollup == _prefecture_timeseries（回次跨マクロ）。別 product 間の検算オラクル。
    # 就業状態等基本集計の大分類は悉皆カウント（標本でない）ゆえ、回次別と回次跨が県レベルで一致（F1/H1 と同型）。
    # 県 rollup は area_code 先頭2桁で束ねる。ミクロは 2015 のみ＝他の県収録年は scope_out。
    "industry_municipality_timeseries": [
        CrossFactSpec(
            name="I1 就業者数 ミクロ→県rollup == industry_prefecture",
            keys=["pref_code", "industry_code", "year"],
            hub_key="industry_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="workers",
            mode="conservation",
            scope_years=_INDUSTRY_PREF_YEARS - _EMPLOYED_MUNI_YEARS,
            reasons={y: _EMPLOYED_MUNI_ONLY_REASON for y in _INDUSTRY_PREF_YEARS - _EMPLOYED_MUNI_YEARS},
        ),
    ],
    "occupation_major12_municipality_timeseries": [
        CrossFactSpec(
            name="O1 就業者数 ミクロ→県rollup == occupation_major12_prefecture",
            keys=["pref_code", "occupation_code", "year"],
            hub_key="occupation_major12_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="workers",
            mode="conservation",
            scope_years=_OCCUPATION_PREF_YEARS - _EMPLOYED_MUNI_YEARS,
            reasons={y: _EMPLOYED_MUNI_ONLY_REASON for y in _OCCUPATION_PREF_YEARS - _EMPLOYED_MUNI_YEARS},
        ),
    ],
    "labor_force_municipality_timeseries": [
        CrossFactSpec(
            name="L1 15歳以上人口 ミクロ→県rollup == labor_force_prefecture",
            keys=["pref_code", "labor_status_code", "year"],
            hub_key="labor_force_prefecture_timeseries",
            hub_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            other_with=[pl.col("area_code").str.slice(0, 2).alias("pref_code")],
            value="population",
            mode="conservation",
            scope_years=_LABOR_FORCE_PREF_YEARS - _EMPLOYED_MUNI_YEARS,
            reasons={y: _EMPLOYED_MUNI_ONLY_REASON for y in _LABOR_FORCE_PREF_YEARS - _EMPLOYED_MUNI_YEARS},
        ),
    ],
    # C5: daynight 夜間(常住地・daynight_code=0) == population（全国＝keys=["year"] で市区町村を合算）。
    # 2010-2020 は厳密 diff=0。1990-2005 は従業地・通学地集計（人口等基本集計とは別系統の集計）の常住地人口が
    # 確定人口を僅かに下回り pop≥night（〜0.1-0.4%・一方向 diff≥0）＝known_diff。
    # 1980/1985/2025 は未収録＝scope_out。
    # 差は集計系統/母集団定義の違いで 2010 全数集計化により消滅＝別系統の集計差（精製バグではない）。
    # 正典＝docs/data-quality-assurance.md §既知の逸脱値レジストリ②。
    "daynight_municipality_timeseries": [
        CrossFactSpec(
            name="C5 夜間(常住地) == population（全国）",
            keys=["year"],
            hub_slice=pl.col("sex_code") == "0",
            other_slice=pl.col("daynight_code") == "0",
            scope_years=frozenset({1980, 1985, 2025}),
            # 既知差の値 pin（年→diff＝pop−night）は known_pins.py が正典。全国1セル/年ゆえ diff がそのまま Σ|diff|。
            known_diffs=known_pins.CROSSFACT_C5,
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
        CrossFactSpec(
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
# scope_years＝県が未収録の旧回（全国のみ・other==0 を許容）。
# known_diff_years＝原資料の集計差（区未定分/按分・沖縄扱い等）で
# 全国とΣ県が僅かにズレる旧回（両符号を文書化して許容）。
def _geo_conservation_spec(
    family: str,
    axes: list[str],
    value: str,
    *,
    scope_years: frozenset[int] = frozenset(),
    known_diff_years: frozenset[int] = frozenset(),
    reasons: dict[int, str] | None = None,
) -> CrossFactSpec:
    return CrossFactSpec(
        name=f"G 全国 == Σ都道府県（{value}）",
        keys=[*axes, "year"],
        hub_key=f"{family}_national_timeseries",
        value=value,
        mode="conservation",
        scope_years=scope_years,
        known_diff_years=known_diff_years,
        reasons=reasons or {},
    )


CROSSFACT.update(
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
            # 残差は pre-1960 の回次跨（全国表 vs 県表）の史料集計差のみ＝両符号 known_diff で許容。
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
