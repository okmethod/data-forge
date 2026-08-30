# docs

okmethod/data-forge のドキュメント群。

- [pipeline-architecture.md](pipeline-architecture.md): パイプライン全体設計（段構成・派生フロー・依存の向き・seam）
- **収集データカタログ** `sources/` — 精製の取得元（ソース側）の一覧
  - [sources/data-provider-catalog.md](sources/data-provider-catalog.md): データ提供者の利用規約・商用可否（e-Stat 等）
  - [sources/estat-census-catalog.md](sources/estat-census-catalog.md): e-Stat 国勢調査の帳票カタログ（採用/不採用・statsDataId・年別軸クセ・ソース選定根拠）
- **精製データカタログ** `distributions/` — 本パイプラインが精製・配布するデータセットごとの仕様（出力スキーマ・カバレッジ・検証結果）
  - [distributions/forged-dataset-catalog.md](distributions/forged-dataset-catalog.md): 精製データセットの索引（一覧・2つの粒度層＝マクロ／ミクロ）。個別仕様は各 `distributions/<name>.md`
- [data-quality-assurance.md](data-quality-assurance.md): データ品質保証（保存則・クロスファクト検算・粒度ガード・出典同梱）
