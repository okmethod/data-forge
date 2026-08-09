"""合併イベント（旧→後継）の読み込みと合成。

実効イベント = **parsed（廃置分合CSVを ingest で正規化）⊕ overrides（人手クッション）**。
overrides が同じ old_code を持てば置換（＝堀の作り込みが parsed を上書き）。
両ファイルとも data 側（.gitignore）で、未配置なら空イベント＝畳み込み無しの安全側。

イベントスキーマ（正規化後）:
    old_code(str)       … 消滅/被合併側の JIS コード（アトム）
    successor_code(str) … 直接の後継コード（1 段。多段は複数行で表現）
    year(int)           … 施行年（国勢調査 5 年刻みで近似可）
    kind(str|null)      … 種別（合体/新設・編入・境界変更・分割・改称 等。任意）

overrides での「無効化（ignore）」は successor_code を空にした行で表す
（parsed の該当 old_code を打ち消す）。
"""

import polars as pl

from data_forge.config import AREA_EVENTS_OVERRIDES, AREA_EVENTS_PARSED

EVENTS_SCHEMA = {
    "old_code": pl.Utf8,
    "successor_code": pl.Utf8,
    "year": pl.Int16,
    "kind": pl.Utf8,
}


def _read_csv(path) -> pl.DataFrame:
    if path is None or not path.exists():
        return pl.DataFrame(schema=EVENTS_SCHEMA)
    df = pl.read_csv(path, comment_prefix="#", schema_overrides=EVENTS_SCHEMA)
    # kind 列が無くても許容
    if "kind" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("kind"))
    return df.select(*EVENTS_SCHEMA.keys())


def load_events(parsed_path=None, overrides_path=None) -> pl.DataFrame:
    """実効イベント（parsed ⊕ overrides）を返す。

    overrides が優先（同一 old_code は置換）。successor_code が空の override 行は
    その old_code を無効化する（parsed 側も落とす）。両者未配置なら空。
    """
    parsed = _read_csv(parsed_path or AREA_EVENTS_PARSED)
    overrides = _read_csv(overrides_path or AREA_EVENTS_OVERRIDES)

    overridden = set(overrides.get_column("old_code").to_list())
    merged = pl.concat(
        [parsed.filter(~pl.col("old_code").is_in(list(overridden))), overrides],
        how="vertical",
    )
    # 無効化（successor_code 空/null）行を除去
    return merged.filter(
        pl.col("successor_code").is_not_null() & (pl.col("successor_code").str.len_chars() > 0)
    )
