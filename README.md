# okmethod data-forge

日本の公的データ（e-Stat・国土数値情報等）を取得・クレンジングし、再利用性の高いデータセット（Parquet / CSV / SQLite）へ精製するデータパイプライン。

政府や自治体が提供するオープンデータ・公的データは、信頼性や網羅性に優れている一方で、「形式の揺れ」「セル結合」「レスポンスの重さ」「複雑なデータ構造」といった利用上の不便さが存在する。

`okmethod/data-forge` は、これらの公的データを再現性のあるコードによってクレンジング・構造化し、分析者やエンジニアが即座に活用できる「精製済みデータ」へと変換することを目的としたプロジェクト。

---

## 主な特徴

### コンセプト

- **自動クレンジング:** 日本語特有の文字コード（CP932/Shift_JIS/BOM）、不要なヘッダー・フッター、セル結合の自動補正
- **結合を前提とした設計:** 都道府県コード・市区町村コード・地域メッシュコードを基準としたデータ接合性の担保
- **2つの粒度層（マクロ／ミクロ）:** 全国・都道府県の長期系列（マクロ＝多くは1920〜）と、市区町村を合併畳込で接続した近年系列（ミクロ＝多くは1980〜）を、同一スキーマで接合
- **多様な出力フォーマット:** Parquet（高速・省メモリ）/ CSV / SQLite（APIバックエンド向け）
- **疎結合なパイプライン:** 取得（Fetch）→ 精製（Clean）→ 出力（Export）を独立したステップとして分離

### 対応データソース

商用利用可否を含むデータソース詳細は [docs/sources/data_catalog.md](docs/sources/data_catalog.md) を参照。

### 出力と活用方法

| フォーマット | 用途                                                                 |
| ------------ | -------------------------------------------------------------------- |
| Parquet      | データ分析・機械学習・ローカルでの高速クエリ（Polars / DuckDB）      |
| CSV          | 汎用的なデータ共有・表計算ソフトとの連携                             |
| SQLite       | Cloudflare D1 へデプロイし省コストの REST API バックエンドとして運用 |

---

## ディレクトリ構成

```text
data-forge/
├── apps/
│   ├── pipeline/    # データ精製パイプライン
│   ├── dashboard/   # データ可視化ダッシュボード
│   └── server/      # データ配信サーバー（将来）
├── data/            # .gitignore 対象
│   ├── raw/         # 取得した生データ
│   └── processed/   # 精製済みデータ
└── docs/            # ドキュメント（索引 = docs/README.md）
```

---

## 起動（Docker Compose）

### ダッシュボード（Evidence・ホットリロード）

```bash
docker compose up dashboard  # → http://localhost:3000
```

- ソースは bind mount で被せているため、`apps/dashboard/` の編集が即反映される。
- 初回はデータ未生成のため、ソース（parquet）を生成する:

  ```bash
  docker compose run --rm dashboard npm run sources
  ```

### パイプライン（バッチ実行）

```bash
docker compose run --rm pipeline data-forge run  # 取得→精製→出力
docker compose run --rm pipeline poe check       # lint + test
```

- 出力先の `data/` はホストにマウントしており、コンテナで生成した精製データがそのまま残る。
- e-Stat の appId は `apps/pipeline/.env`（`ESTAT_APP_ID`）に設定する。

### 停止・後片付け

```bash
docker compose down     # コンテナ停止・削除
docker compose down -v  # 依存キャッシュ（named volume）も削除
```

> コンテナを使わないローカル開発（uv セットアップ等）は [apps/pipeline/README.md](apps/pipeline/README.md) を参照。
