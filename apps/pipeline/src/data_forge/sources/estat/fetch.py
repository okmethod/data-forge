"""生レスポンスの取得とローカルキャッシュ。

取得した JSON を data/raw/estat/<statsDataId>.json に保存し、
再実行時はキャッシュを再利用して不要なAPIアクセスを避ける。
サーバ側絞り込み（filters）を使う表は絞り込み内容ごとに別キャッシュにする
（同じ statsDataId でも絞り込みが違えば中身が違うため）。
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from data_forge.config import RAW_DIR
from data_forge.sources.estat.client import get_stats_data


def _raw_path(stats_data_id: str, filters: dict[str, str] | None) -> Path:
    name = stats_data_id
    if filters:
        # 絞り込み内容を安定ハッシュ化してファイル名に付す（キー順に依存しない）。
        digest = hashlib.sha1(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:8]
        name = f"{stats_data_id}_{digest}"
    return RAW_DIR / "estat" / f"{name}.json"


def fetch(stats_data_id: str, *, refresh: bool = False, filters: dict[str, str] | None = None) -> dict[str, Any]:
    """統計データを取得して返す。キャッシュがあれば再利用（refresh=Trueで強制再取得）。

    `filters` はサーバ側絞り込み（例: `{"cdCat01": "00700", "cdCat03": "T01,200,..."}`）。
    巨大表を必要なコードだけに絞り取得件数を抑える。絞り込みごとに別キャッシュに保存する。
    """
    path = _raw_path(stats_data_id, filters)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    data = get_stats_data(stats_data_id, filters=filters)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
