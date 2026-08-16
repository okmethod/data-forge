"""設定とパス解決。

`.env` から e-Stat の appId を読み込み、data/ 配下（raw・processed）の
ディレクトリを一元管理する。data/ はリポジトリルート直下（.gitignore 対象）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# apps/pipeline/src/data_forge/config.py → リポジトリルートは 5 つ上
REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
# --- 地域マスタ（アトム軸スタースキーマ）---
# 合併イベント = parsed（廃置分合CSVを ingest で正規化）⊕ overrides（人手クッション）。
# raw 履歴CSVは再取得可・overrides は堀本体。いずれも data 側（.gitignore）。
AREA_HISTORY_RAW = RAW_DIR / "history"  # 総務省/e-Stat 廃置分合 の生CSV置き場
AREA_EVENTS_PARSED = DATA_DIR / "area" / "events_parsed.csv"  # ingest 出力（正規化イベント）
AREA_EVENTS_OVERRIDES = DATA_DIR / "area" / "events_overrides.csv"  # 人手クッション


def get_estat_app_id() -> str:
    """e-Stat の appId を返す。未設定なら明示的にエラー。"""
    app_id = os.getenv("ESTAT_APP_ID")
    if not app_id or app_id == "your_app_id_here":
        raise RuntimeError(
            "ESTAT_APP_ID が未設定です。apps/pipeline/.env に設定してください （取得: https://www.e-stat.go.jp/api/）。"
        )
    return app_id
