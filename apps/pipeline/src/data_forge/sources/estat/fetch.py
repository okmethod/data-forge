"""生レスポンスの取得とローカルキャッシュ。

取得した JSON を data/raw/estat/<statsDataId>.json に保存し、
再実行時はキャッシュを再利用して不要なAPIアクセスを避ける。
"""

import json
from pathlib import Path
from typing import Any

from data_forge.config import RAW_DIR
from data_forge.sources.estat.client import get_stats_data


def _raw_path(stats_data_id: str) -> Path:
    return RAW_DIR / "estat" / f"{stats_data_id}.json"


def fetch(stats_data_id: str, *, refresh: bool = False) -> dict[str, Any]:
    """統計データを取得して返す。キャッシュがあれば再利用（refresh=Trueで強制再取得）。"""
    path = _raw_path(stats_data_id)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    data = get_stats_data(stats_data_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
