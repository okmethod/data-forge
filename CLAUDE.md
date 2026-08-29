# CLAUDE.md

## 行動原則

- **回答は日本語で簡潔に行う**
- **サブエージェントを積極活用しトークン節約する**

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
└── docs/           # ドキュメント（索引の正典 = docs/README.md）
```

## 参照先（正典はここを見る／CLAUDE.md には再掲しない＝ドリフト防止）

- **コマンド・使い方**: [apps/pipeline/README.md](apps/pipeline/README.md) の「使い方」（poe タスク一覧は `apps/pipeline/pyproject.toml` の `[tool.poe.tasks]`）
  - lint + test（最頻・CI 相当）: `cd apps/pipeline && uv run poe check`
- **ドキュメント索引**: [docs/README.md](docs/README.md) が正典（下記の各正典もここから辿れる）
- **パイプライン全体設計（段構成・派生フロー・依存の向き・seam）**: [docs/pipeline-architecture.md](docs/pipeline-architecture.md)
- **データ品質保証（保存則・クロスファクト検算・粒度ガード・出典同梱）**: [docs/data-quality-assurance.md](docs/data-quality-assurance.md)
- **データセット仕様・一覧**: [docs/README.md](docs/README.md) の索引 → 各 `docs/datasets/<name>.md` が個別の正典
- **ライセンス・商用可否・利用規約**: [docs/sources/data_catalog.md](docs/sources/data_catalog.md)
- **各段の内部設計**: 当該パッケージの `__init__.py` docstring が正典
