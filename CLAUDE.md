# CLAUDE.md

## 行動原則

- **回答は日本語で簡潔に行う**
- **サブエージェントを積極活用しトークン節約する**:

## プロジェクト概要

日本の公的データ（e-Stat・国土数値情報等）を取得・クレンジングし、Parquet / CSV / SQLite へ精製するデータパイプライン。
コードは公開、データはコミットしない方針。商用利用可能なデータソースに限定する。

### アーキテクチャ（モノレポ）

- `apps/pipeline/` — Python（uv + Polars）：取得 → クレンジング → 出力
- `apps/server/` — TypeScript（Cloudflare Workers + Hono）：SQLite を REST API として公開（将来）

### ディレクトリ構成

```
data-forge/
├── apps/
│   ├── pipeline/   # Python パイプライン
│   ├── dashboard/  # Evidence ダッシュボード
│   └── server/     # Cloudflare Workers（将来）
├── data/           # .gitignore 対象（raw/ / processed/）
└── docs/
    └── sources/    # データソースカタログ（商用可否・利用規約）
```

## 参照先（正典はここを見る／CLAUDE.md には再掲しない＝ドリフト防止）

- **コマンド・使い方**: [apps/pipeline/README.md](apps/pipeline/README.md) の「使い方」（poe タスク一覧は `apps/pipeline/pyproject.toml` の `[tool.poe.tasks]`）
  - lint + test（最頻・CI 相当）: `cd apps/pipeline && uv run poe check`
- **データセット仕様・一覧**: [docs/README.md](docs/README.md) を索引の正典とし、各 `docs/datasets/<name>.md` が個別の正典
- **各段の内部設計**: 当該パッケージの `__init__.py` docstring が正典
