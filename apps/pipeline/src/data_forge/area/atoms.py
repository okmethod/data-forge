"""アトム抽出＝各年の「標準的な市区町村」による最finest分割を取り出す。

地域マスタ（アトム軸スタースキーマ）の fact 層。各国勢調査年について、
**国土をちょうど1回だけ覆う標準的な市区町村ユニット**を抽出する。

設計（Design A / 実データで人口保存を実証済み。全4年で 葉合計 == 全国total, diff=0）:
    - 対象グレインは「市区町村別」とし、政令市は 1 ユニット（市）として扱う。
      行政区（政令市の区）には分割しない。＝政令市移行が「区集合への 1→多 分裂」でなく
      「市コードの 1→1 変更」で表せ、合併集約(rollup)が破綻しない。
      東京23特別区はそれぞれ独立自治体なのでアトムとして残す（特別区部の集計行は除外）。
    - 合併済み自治体の「旧内訳（name に "旧"）」は現自治体と二重計上になるため除外。
    - 合併の後継対応は fact でなく events（廃置分合）側に持たせ、集約時に各年ユニットを
      base_year の自治体へ前方 rollup する（aggregate.py）。

葉集合の選択規則:
    候補 = 市区町村レベル（年で異なる）かつ name に "旧" を含まない。
    非葉 = 別の候補の parent_code に現れるコード（＝集計行/上位コンテナ。
           例: 特別区部・市部・郡部・政令市本体が区を子に持つ場合）。
    葉   = 候補 − 非葉。

依存境界（重要）:
    area 層はデータセット非依存だが**ソース非依存ではない**。
    このファイルは e-Stat の area 階層（level の意味・"00000" 全国・"13100" 特別区部）に依存する唯一の層で、
    第2ソース（例: 国土数値情報）を足す場合の主な改修点は `_MUNI_LEVELS`（市区町村 level の解釈）と特別区ハードコード。
    events/mapping/combine は JIS コード軸だけに依存するソース非依存の核なので流用できる。
    （詳細は docs/datasets/population.md）
"""

import polars as pl

# 年ごとの「標準的な市区町村レベル」。level の意味が年（テーブル世代）で異なるため明示する。
# 1980/1985/1990/1995/2000/2005: level3=市区町村。2010/2015/2020(令和型): level4=市/特別区・level6=町村
# （level5=政令市の行政区は対象グレイン外なので採らない＝市に含める）。
_MUNI_LEVELS: dict[int, frozenset[int]] = {
    1980: frozenset({3}),
    1985: frozenset({3}),
    1990: frozenset({3}),
    1995: frozenset({3}),
    2000: frozenset({3}),
    2005: frozenset({3}),
    2010: frozenset({4, 6}),
    2015: frozenset({4, 6}),
    2020: frozenset({4, 6}),
}
# 未知年（2025 以降）は令和型を既定に。破れたら reconcile の人口保存チェックが検知する。
_DEFAULT_MUNI_LEVELS = frozenset({4, 6})

# 東京都特別区部の集計コード。その 23 区（子）は「行政区」でなく独立自治体なので、
# 年によらずアトムとして扱う（2005 は特別区が muni_level の下＝level4 にあるため明示追加が要る）。
_SPECIAL_WARD_PARENT = "13100"


def _muni_levels(year: int) -> frozenset[int]:
    return _MUNI_LEVELS.get(year, _DEFAULT_MUNI_LEVELS)


def leaf_codes(hierarchy: pl.DataFrame, *, year: int, muni_levels: frozenset[int] | None = None) -> pl.Series:
    """その年の area 階層から finest 分割の葉コード集合を返す。

    引数:
        hierarchy   … transform.extract_area_hierarchy の出力
                      （code / name / level / parent_code）。
        year        … 国勢調査年（市区町村レベルの解釈に使う）。
        muni_levels … 市区町村レベルの明示上書き（None なら年から `_muni_levels` で決める）。
                      同じ年でも e-Stat 製品ごとに level の意味が違うことがある
                      （例: 2000 の人口時系列製品は level3=市区町村だが、
                      同年の人口等基本集計・市規模別2表は令和型 level4/6＝旗艦 age5 の 2000）。

    グレインは全年で「標準的な市区町村（政令市=1・東京23特別区=各1）」に統一する。
    2005 は特別区部・政令市がともに level3、23区・行政区がともに level4 で level では
    区別できないため、東京23区（parent=特別区部）を明示的に候補へ加え、集計ノード
    （特別区部・市部・郡部・政令市本体で区を子に持つ場合）は「候補の親」として除外する。
    """
    levels = muni_levels if muni_levels is not None else _muni_levels(year)
    cand = hierarchy.filter(
        (
            pl.col("level").is_in(list(levels))
            | (pl.col("parent_code") == _SPECIAL_WARD_PARENT)  # 東京23特別区（独立自治体）
        )
        & ~pl.col("name").str.contains("旧", literal=True)
    )
    codes = set(cand.get_column("code").to_list())
    # 非葉: 候補の誰かの親になっているコード（特別区部・市部/郡部などの集計ノード）
    used = {p for p in cand.get_column("parent_code").to_list() if p in codes}
    return pl.Series("code", sorted(codes - used))


def extract_atoms(
    fact_year: pl.DataFrame, hierarchy: pl.DataFrame, *, year: int, muni_levels: frozenset[int] | None = None
) -> pl.DataFrame:
    """1 年分の配布用 fact から、その年のアトム（finest 分割）行だけを残す。

    fact のスキーマはそのまま。旧内訳・政令市の区・集計行などの非葉行を落とすだけ。
    `muni_levels` は市区町村レベルの明示上書き（`leaf_codes` へそのまま渡す）。
    """
    leaves = leaf_codes(hierarchy, year=year, muni_levels=muni_levels)
    return fact_year.filter(pl.col("area_code").is_in(leaves))
