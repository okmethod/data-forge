"""和解（reconcile）: 人口保存チェックと「孤児アトム」検出。

堀（moat）の駆動役。parsed イベントだけでは埋まらない箇所を機械的にフラグし、
人手 overrides（クッション）で埋める運用を支える。

3 つの検査:
    - national_conservation … 各年、アトム合計 == 全国total か（アトム抽出の健全性）。
    - orphans … base_year までに消滅したのに rollup 先が base_year に無いアトム
                （＝合併イベント未整備）。人口降順で「次に埋める候補」を返す。
    - dangling_successors … 後継先が実在コードへ着地しないイベント行（後継コードの指定ミス）。
"""

import polars as pl

from data_forge.area.mapping import rollup

# 既知の人口保存差分（原資料特性で受容する年 → 期待差分）。
# 孤児やロジック不整合とは別物で、override では解消しない「原資料の真実」。
# 値が動いたら回帰＝別問題としてテストで固定する。
KNOWN_DIFFS: dict[int, int] = {1980: 37}
KNOWN_DIFF_REASONS: dict[int, str] = {
    1980: "東京都特別区部の区未定分（23区に按分されない集計差）",
}


def _total_mask(df: pl.DataFrame) -> pl.Expr:
    """全分類軸が「総数」（コード=="0"）の行だけを選ぶ述語。

    population は sex_code=="0" だけだが、population_by_age は sex_code=="0" かつ
    age_class_code=="0"（総数×総数）で grand total 1 行に絞る（さもないと年少+生産+老年+不詳の
    重複で二重計上になる）。`*_code` 列の増減に追従するので fact 非依存。

    ただし age5year は年齢総数コードが "0" でなく "100" のため、
    本 mask は 0 行マッチ＝保存則が空振りになる（area-check は空表をガードで検知）。
    age5year の保存則は crossfact C1（age5 の国籍総数×年齢総数 == population）が hub 経由で担保するため、
    ここでの直接検査は委譲する。
    """
    codes = [c for c in df.columns if c.endswith("_code") and c not in ("area_code", "base_code")]
    return pl.all_horizontal([pl.col(c) == "0" for c in codes])


def national_conservation(atom_fact: pl.DataFrame, national: pl.DataFrame) -> pl.DataFrame:
    """各年で「アトム合計（総数）== 全国total」を検査した表を返す。

    引数:
        atom_fact … 各年アトムの時系列（fact 依存スキーマ）。
        national  … 全国行のみ（area_code=='00000'）を含む DF。総数スライスを絞るため
                    分類軸コード列（sex_code・あれば age_class_code）を保持していること。

    列: year / national / atom_sum / diff / known_diff / known / ok。
    `known_diff` は既知差分の期待値（KNOWN_DIFFS、既定 0）。`ok` は diff が期待値に一致するか
    （0 一致だけでなく既知差分も許容）。`known` は「0 でない既知差分を受容した」行のフラグ。
    """
    atom_sum = (
        atom_fact.filter(_total_mask(atom_fact))
        .group_by("year")
        .agg(pl.col("population").fill_null(0).sum().alias("atom_sum"))
    )
    nat = national.filter(_total_mask(national)).select("year", pl.col("population").alias("national"))
    return (
        nat.join(atom_sum, on="year", how="left")
        .with_columns((pl.col("national") - pl.col("atom_sum")).alias("diff"))
        .with_columns(pl.col("year").replace_strict(KNOWN_DIFFS, default=0, return_dtype=pl.Int64).alias("known_diff"))
        .with_columns(
            (pl.col("diff") == pl.col("known_diff")).alias("ok"),
            ((pl.col("diff") != 0) & (pl.col("diff") == pl.col("known_diff"))).alias("known"),
        )
        .sort("year")
    )


def cross_fact(
    hub: pl.DataFrame,
    other: pl.DataFrame,
    *,
    keys: list[str],
    hub_slice: pl.Expr | None = None,
    other_slice: pl.Expr | None = None,
    hub_with: list[pl.Expr] | None = None,
    other_with: list[pl.Expr] | None = None,
    value: str = "population",
    scope_years: frozenset[int] = frozenset(),
    known_diff_years: frozenset[int] = frozenset(),
    mode: str = "equality",
) -> pl.DataFrame:
    """2 スライスを共有軸 `keys` で突合し diff 表を返す（クロスファクト検算／保存則検算）。

    方針A「重複軸はハブと一致検証して捨てる」の実体化。`hub` と `other` を各々のスライス述語で
    絞り keys へ集約して full-join し、共有軸ごとに `value` の差を出す。**full-join ゆえ片側だけに
    在るキー（カバレッジ差）も diff!=0 として検出する**（level7 差を見落とさない）。

    用途は2系統:
      - クロスファクト（別ファクト間）: hub=population・other=age5 など。既定 mode="equality"。
      - within-fact 保存則（同一ファクト内の別スライス）: hub_slice/other_slice で同じ DF を
        総数側/内訳側に切り、Σ内訳==総数 を検算（例 日本人の年齢保存・男女保存）。

    引数:
        hub / other … 畳込後（`derive.load(..., join="aggregate_to_base")`）の配布用 DF。
                      within-fact では同一 DF を両方に渡し hub_slice/other_slice で切り分ける。
        keys        … 共有軸（例 `["area_code", "sex_code", "year"]`）。
        hub_slice   … hub を絞る述語（within-fact で総数スライスへ絞る用。既定 None＝絞らない）。
        other_slice … other を絞る述語（例 age5 総数＝`nationality_code=="0"` かつ
                      `age_class_code=="100"`／by_age＝`age_class_code=="0"`）。
        hub_with / other_with … filter/集約の前に with_columns で足す派生列（既定 None＝足さない）。
                      粒度をまたぐ折り畳み検算で使う。例 C2＝age5 の 5歳階級コードを 3区分コード
                      （`age3_code`）へ写像し、それを keys に含めて by_age の区分と突合する。
        scope_years … other（や hub 側の対象国籍）が未収録の年。この年は other==0 が期待で
                      status="scope_out"・ok=(other==0)＝スコープ外として許容する。
        known_diff_years … 定義差で diff!=0 が期待される年（例 age5＝2005 各歳表は「年齢不詳を
                      除く」ゆえ other = hub − 年齢不詳 ≤ hub）。status="known_diff"・
                      ok=(diff>=0)＝定義差の向き（other ≤ hub）が保たれる限り許容する。
        mode        … "equality"（既定・diff==0 を期待）／"bound"（上界検算＝other ≤ hub の
                      部分集合関係のみ保証。status="bound"・ok=(diff>=0 かつ other>0)。
                      hub>0 なのに other==0（スライス欠落）を見逃さないため実在も要求するが、
                      hub==0 の空セル（そもそも住民がいない自治体）は other==0 でも許容する）／
                      "conservation"（地理保存＝全国 hub と Σ県 other の一致。equality と同じく diff==0 を
                      期待するが、known_diff_years は**両符号**の集計差を許容する＝旧回の 区未定分/按分/
                      沖縄扱い 等の原資料集計差を年ごとに文書化して受容する。equality の known_diff は
                      other≤hub 前提で diff>=0 のみ許容だったのに対し、地理保存は符号が定まらないため緩める）。

    列: *keys / hub / other / diff / status / ok。
        status … match（diff==0）／bound／scope_out／known_diff／mismatch。
        ok     … match、scope_out(other==0)、known_diff(diff>=0／conservation は両符号)、
                 bound(diff>=0 かつ (other>0 または hub==0))。
    """
    h = hub.with_columns(*hub_with) if hub_with else hub
    h = h.filter(hub_slice) if hub_slice is not None else h
    h = h.group_by(keys).agg(pl.col(value).fill_null(0).sum().alias("hub"))
    o = other.with_columns(*other_with) if other_with else other
    o = o.filter(other_slice) if other_slice is not None else o
    o = o.group_by(keys).agg(pl.col(value).fill_null(0).sum().alias("other"))
    rep = (
        h.join(o, on=keys, how="full", coalesce=True)
        .with_columns(pl.col("hub").fill_null(0), pl.col("other").fill_null(0))
        .with_columns((pl.col("hub") - pl.col("other")).alias("diff"))
    )
    if "year" in keys:
        scoped = pl.when(pl.col("year").is_in(list(scope_years))).then(pl.lit("scope_out"))
        if mode == "bound":
            status = scoped.otherwise(pl.lit("bound"))
        else:  # equality / conservation は status 割り当てが同一（差は known_diff の符号許容のみ）
            status = (
                scoped.when(pl.col("year").is_in(list(known_diff_years)))
                .then(pl.lit("known_diff"))
                .when(pl.col("diff") == 0)
                .then(pl.lit("match"))
                .otherwise(pl.lit("mismatch"))
            )
    elif mode == "bound":
        status = pl.lit("bound")
    else:
        status = pl.when(pl.col("diff") == 0).then(pl.lit("match")).otherwise(pl.lit("mismatch"))
    # 地理保存（conservation）は known_diff を両符号で受容。それ以外は other≤hub 前提で diff>=0 のみ。
    known_ok = pl.col("status") == "known_diff"
    if mode != "conservation":
        known_ok = known_ok & (pl.col("diff") >= 0)
    return (
        rep.with_columns(status.alias("status"))
        .with_columns(
            (
                (pl.col("status") == "match")
                | ((pl.col("status") == "scope_out") & (pl.col("other") == 0))
                | known_ok
                | (
                    (pl.col("status") == "bound")
                    & (pl.col("diff") >= 0)
                    & ((pl.col("other") > 0) | (pl.col("hub") == 0))
                )
            ).alias("ok")
        )
        .sort(keys)
    )


def orphans(atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None) -> pl.DataFrame:
    """rollup 後も base_year に存在しないアトム（＝イベント未整備）を人口降順で返す。

    列: area_code / area_name / last_year / last_population / base_code。
    base_code は現状の（未整備な）rollup 先。ここを overrides で正しい後継へ向ける。
    """
    years = atom_fact.get_column("year").unique().to_list()
    base = base_year if base_year is not None else max(years)

    base_codes = set(atom_fact.filter(pl.col("year") == base).get_column("area_code").to_list())
    roll = rollup(events, base_year=base)

    # 各アトムの最終出現年・その年の総数人口・名称
    last = (
        atom_fact.filter(_total_mask(atom_fact))
        .sort("year")
        .group_by("area_code")
        .agg(
            pl.col("year").max().alias("last_year"),
            pl.col("population").last().alias("last_population"),
            pl.col("area_name").last().alias("area_name"),
        )
    )
    mapped = last.join(roll, left_on="area_code", right_on="code", how="left").with_columns(
        pl.coalesce("base_code", "area_code").alias("base_code")
    )
    return (
        mapped.filter(~pl.col("base_code").is_in(list(base_codes)))
        .select("area_code", "area_name", "last_year", "last_population", "base_code")
        .sort("last_population", descending=True, nulls_last=True)
    )


def dangling_successors(events: pl.DataFrame, atom_fact: pl.DataFrame) -> pl.DataFrame:
    """後継先が実在コードへ着地しないイベント行を返す（後継コードの指定ミス検出）。

    orphans が「消滅アトム側」から未整備を炙り出すのに対し、本検査は overrides/parsed の
    `successor_code` そのものを突く。合併先を打ち間違えても rollup は黙って通し、孤児として
    表に出ないことがある（例: 消滅アトムの人口が 0／その年に非登場）。ここで後継先の実在を
    直接確かめ、指定ミスを取りこぼさない。

    実在コードの宇宙 = 全年に登場するアトム area_code ∪ イベントの old_code。後者を含めるのは、
    中間後継（さらに合併される側）が国勢調査の葉として登場しないまま連鎖解決されるため。
    この宇宙のどこにも無い successor_code は着地先の無い dangling 参照＝ほぼ指定ミスなので、
    人手確認用に該当行を返す（rollup は無効化しないので配布は止めず、警告に留める）。
    """
    universe = set(atom_fact.get_column("area_code").unique().to_list()) | set(events.get_column("old_code").to_list())
    return events.filter(
        pl.col("successor_code").is_not_null()
        & (pl.col("successor_code").str.len_chars() > 0)
        & ~pl.col("successor_code").is_in(list(universe))
    )
