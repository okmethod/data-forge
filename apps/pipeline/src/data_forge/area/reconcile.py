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
    other_slice: pl.Expr | None = None,
    value: str = "population",
    scope_years: frozenset[int] = frozenset(),
    known_diff_years: frozenset[int] = frozenset(),
) -> pl.DataFrame:
    """別ソース由来の 2 ファクトを共有軸 `keys` で突合し diff 表を返す（クロスファクト検算）。

    方針A「重複軸はハブと一致検証して捨てる」の実体化。`hub`（総人口の正典＝population）と
    `other`（照合相手。`other_slice` で総数スライスへ潰してから keys へ集約）を full-join し、
    共有軸ごとに `value` の差を出す。**full-join ゆえ片側だけに在るキー（カバレッジ差）も
    diff!=0 として検出する**（level7 差を見落とさない）。

    引数:
        hub / other … 畳込後（`derive.load(..., join="aggregate_to_base")`）の配布用 DF。
        keys        … 共有軸（例 `["area_code", "sex_code", "year"]`）。
        other_slice … other を総数スライスへ絞る述語（例 age5＝`nationality_code=="0"` かつ
                      `age_class_code=="100"`／by_age＝`age_class_code=="0"`）。hub 側は
                      呼び出し前に総数構成であること（population は sex 別の総人口）。
        scope_years … other が未収録の年（例 age5＝2025 速報）。この年は other==0 が期待で
                      status="scope_out"・ok=(other==0)＝スコープ外として許容する。
        known_diff_years … 定義差で diff!=0 が期待される年（例 age5＝2005 各歳表は「年齢不詳を
                      除く」ゆえ other = hub − 年齢不詳 ≤ hub）。status="known_diff"・
                      ok=(diff>=0)＝定義差の向き（other ≤ hub）が保たれる限り許容する。

    列: *keys / hub / other / diff / status / ok。
        status … match（diff==0）／scope_out／known_diff／mismatch。
        ok     … match、または scope_out(other==0)、または known_diff(diff>=0)。
    """
    h = hub.group_by(keys).agg(pl.col(value).fill_null(0).sum().alias("hub"))
    o = other.filter(other_slice) if other_slice is not None else other
    o = o.group_by(keys).agg(pl.col(value).fill_null(0).sum().alias("other"))
    rep = (
        h.join(o, on=keys, how="full", coalesce=True)
        .with_columns(pl.col("hub").fill_null(0), pl.col("other").fill_null(0))
        .with_columns((pl.col("hub") - pl.col("other")).alias("diff"))
    )
    if "year" in keys:
        status = (
            pl.when(pl.col("year").is_in(list(scope_years)))
            .then(pl.lit("scope_out"))
            .when(pl.col("year").is_in(list(known_diff_years)))
            .then(pl.lit("known_diff"))
            .when(pl.col("diff") == 0)
            .then(pl.lit("match"))
            .otherwise(pl.lit("mismatch"))
        )
    else:
        status = pl.when(pl.col("diff") == 0).then(pl.lit("match")).otherwise(pl.lit("mismatch"))
    return rep.with_columns(status.alias("status")).with_columns(
        (
            (pl.col("status") == "match")
            | ((pl.col("status") == "scope_out") & (pl.col("other") == 0))
            | ((pl.col("status") == "known_diff") & (pl.col("diff") >= 0))
        ).alias("ok")
    ).sort(keys)


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
    universe = set(atom_fact.get_column("area_code").unique().to_list()) | set(
        events.get_column("old_code").to_list()
    )
    return events.filter(
        pl.col("successor_code").is_not_null()
        & (pl.col("successor_code").str.len_chars() > 0)
        & ~pl.col("successor_code").is_in(list(universe))
    )
