"""rollup: アトム→基準年自治体 の前方マッピング（合併イベントの推移閉包）。

各アトム（各年の finest 分割ユニット）を、施行年 ≤ base_year の合併イベントだけを
たどって「基準年時点で属する自治体」へ写像する。多段合併（A→C→E）は 1 段ずつの
イベントを推移閉包でたどる。base_year を境界に外出しするので、配布物は 2025 投入後も
過去の基準年ビューを据え置ける（新年は現 partition ＋ 新イベント追記のみ）。
"""

import polars as pl


def _resolve(code: str, succ: dict[str, str]) -> str:
    """後継チェーンを終端までたどる（循環はその場で打ち切り）。"""
    seen = {code}
    cur = code
    while cur in succ:
        nxt = succ[cur]
        if nxt in seen:  # 循環防止（reconcile 側で別途警告）
            break
        seen.add(nxt)
        cur = nxt
    return cur


def rollup(events: pl.DataFrame, *, base_year: int) -> pl.DataFrame:
    """base_year 時点の後継対応表 code→base_code を返す（動くコードのみ）。

    施行年 ≤ base_year のイベントだけ適用。同一 old_code に複数イベントがある場合は
    施行年が新しい方（ただし ≤ base_year）を採用する。
    """
    applicable = events.filter(pl.col("year") <= base_year)
    if applicable.height == 0:
        return pl.DataFrame(schema={"code": pl.Utf8, "base_code": pl.Utf8})

    # old_code ごとに最新の施行年のイベントを1件に集約
    latest = applicable.sort("year").group_by("old_code").agg(pl.col("successor_code").last())
    succ = dict(
        zip(
            latest.get_column("old_code").to_list(),
            latest.get_column("successor_code").to_list(),
            strict=True,
        )
    )
    rows = [{"code": c, "base_code": _resolve(c, succ)} for c in succ]
    return pl.DataFrame(rows, schema={"code": pl.Utf8, "base_code": pl.Utf8})
