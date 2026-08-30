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
- **ライセンス・商用可否・利用規約**: [docs/sources/data-provider-catalog.md](docs/sources/data-provider-catalog.md)
- **e-Stat 国勢調査の帳票カタログ（採用/不採用・statsDataId・年別軸クセ・ソース選定根拠）**: [docs/sources/estat-census-catalog.md](docs/sources/estat-census-catalog.md)
- **本パイプラインが精製・配布するデータセットごとの仕様（出力スキーマ・カバレッジ・検証結果）**: [docs/distributions/forged-dataset-catalog.md](docs/distributions/forged-dataset-catalog.md)
- **データ品質保証（保存則・クロスファクト検算・粒度ガード・出典同梱）**: [docs/data-quality-assurance.md](docs/data-quality-assurance.md)
- **各段の内部設計**: 当該パッケージの `__init__.py` docstring が正典
