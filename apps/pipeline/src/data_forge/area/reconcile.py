"""和解（reconcile）: 人口保存チェックと「孤児アトム」検出。

堀（moat）の駆動役。parsed イベントだけでは埋まらない箇所を機械的にフラグし、
人手 overrides（クッション）で埋める運用を支える。

2 つの検査:
    - national_conservation … 各年、アトム合計 == 全国total か（アトム抽出の健全性）。
    - orphans … base_year までに消滅したのに rollup 先が base_year に無いアトム
                （＝合併イベント未整備）。人口降順で「次に埋める候補」を返す。
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
    nat = national.filter(_total_mask(national)).select(
        "year", pl.col("population").alias("national")
    )
    return (
        nat.join(atom_sum, on="year", how="left")
        .with_columns((pl.col("national") - pl.col("atom_sum")).alias("diff"))
        .with_columns(
            pl.col("year")
            .replace_strict(KNOWN_DIFFS, default=0, return_dtype=pl.Int64)
            .alias("known_diff")
        )
        .with_columns(
            (pl.col("diff") == pl.col("known_diff")).alias("ok"),
            ((pl.col("diff") != 0) & (pl.col("diff") == pl.col("known_diff"))).alias("known"),
        )
        .sort("year")
    )


def orphans(
    atom_fact: pl.DataFrame, events: pl.DataFrame, *, base_year: int | None = None
) -> pl.DataFrame:
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
