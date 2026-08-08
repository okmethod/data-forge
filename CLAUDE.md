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
