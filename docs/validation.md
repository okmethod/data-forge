# 精製データの検証計画

各データセット doc に散在する検証記述を横断で束ねた、確からしさの管理ドキュメント。  
「何を検証済みか（**結果・実証値**）」は各データセット doc・CLI 実走・`poe test` を正典とし、本書は「**何をどう検証するか（方針・恒等式の設計）／未カバー領域**」に集約する。

> **ドリフト防止方針**: 件数・年リスト・diff の実測値などの揮発する数値は本書に埋め込まず、取得コマンド（§6）か正典 doc を指し示す。本書に残すのは「設計」と「バックログ」、および `reconcile.py` をミラーする既知差分レジストリ（§7）に限る。

> **配置は暫定**（`docs/` 直下）。再検討予定。

## 1. 方針

精製データの確からしさは、次の**機械検証**で担保する。  
人手確認に頼る箇所は「未カバー領域」（§9）に明示し、放置しない。

実装のマッピング（検証関数・コードパス）は各詳細節（§2〜§4）を正典とし、本表は重複させない。

| 系統                   | 何を守るか                             | 詳細 |
| ---------------------- | -------------------------------------- | ---- |
| **保存則（恒等式）**   | 数値の正しさ（合計の一致）             | §2   |
| **クロスファクト検算** | 別ソース由来の同一軸(総人口)の相互整合 | §2   |
| **粒度ガード**         | 二重計上の防止                         | §3   |
| **出典ゲート**         | 全成果物への citation 同梱             | §4   |

## 2. 保存則（恒等式）による検証

数値の確からしさの中核。「部分の合計 == 総数」が全年で成立することを検査する（期待は全て **diff=0**、総数スライスのみビット一致）。  
以下は検証する**恒等式（設計）→ 検証関数 / テスト**の対応。実測結果（何年が一致したか）は各検証関数・テスト・CLI 実走を正典とする。

- **人口保存** … 各年「アトム合計（総数）== 全国 total」 → `national_conservation`（`area/reconcile.py`）
- **空間集約の保存** … 「県／地方合計 == 全国 total」（`aggregate_to_base` 前後で同値）→ 同上
- **年齢保存** … 年少 + 生産 + 老年 + 不詳 == 総数 → `test_clean_population_by_age_conservation`
- **男女保存** … 男 + 女 == 総数 → 同上
- **総数スライス一致** … `age_class_code=0` / `daynight=夜間` スライスが現行 `population` とビット一致 → 各データセット doc で実証（§5）

### クロスファクト検算（conformed dimension の三角測量）

3ファクト（population / population_by_age / population_by_age5）は市区町村×year×sex で、**総人口を共有軸（conformed dimension）として冗長に持つ**。  
別ソース・別系統から同じ総人口へ到達することを相互照合し、方針A「重複軸はハブと一致検証して捨てる」をテストで実体化する。  
ハブ（正典）は総人口を level7 まで完全に持つ **population**。系統は A＝各回基本集計 / B＝派生表。期待は全て **diff=0**（C2 のみ未実装＝§9）。

| #   | 恒等式                                         | 粒度              | 系統 |
| --- | ---------------------------------------------- | ----------------- | ---- |
| C1  | age5(nat=0・年齢総数) == population            | 市区町村×year×sex | A×A  |
| C2  | age5(nat=0)を3区分へ畳込 == population_by_age  | 市区町村×year×sex | A×B  |
| C3  | population_by_age(年齢総数) == population      | 市区町村×year×sex | B×A  |
| C4  | age5→県rollup == population_by_age5_prefecture | 県×year           | A×B  |
| C5  | daynight(夜間) == population                   | 全国              | −×A  |

- **C1 が最も堅い**: population も age5 も同じ各回基本集計（系統A・同一調査母集団）ゆえ厳密 diff=0 が期待できる。実測ステータスは `crossfact-check population_by_age5_timeseries`（§6）で得る。
  - **muni_levels の設計上の注意**（C1 が顕在化させた知見）: 一部の各歳表は令和型 level4/6 で市区町村を持つが、旗艦 age5 の Dataset が muni_levels override を欠くとグローバル `_MUNI_LEVELS`（人口時系列製品向け）が適用され、level3=郡/支庁の中間集計を葉に拾って粒度非対称になる。該当年は `Dataset.muni_levels` を明示上書きして市区町村フルへ揃える。
- **年別の許容カテゴリ**（`cross_fact` の `scope_years` / `known_diff_years`）: 全年が diff=0 とは限らないため CLI は年別に status を分類し、**真の不一致のみ**を失敗（exit 1）とする。
  - **scope_out**: 照合相手が未収録の年（population 速報のみ等）。`other==0` を期待＝スコープ外として許容。
  - **known_diff**: 定義差が既知の年。例＝各歳表が「年齢不詳を除く」ゆえ age5 総数 = population − 年齢不詳（`other ≤ hub`）。差の向き（diff≥0）が保たれる限り許容。※C3 の by_age は不詳を含むソースゆえ同年でも diff=0。
- **C4/C5** は既存の実装・実証を本枠へ収めたもの（`population_by_age5_prefecture` / `daynight_population` の各 doc が正典）。
- **C2 は未実装**（§9 バックログ）。
- **実装方式**: 実データ照合が本質（手組みでは自明化する）ため、実データは CLI 検証（`crossfact-check`・`area-check` と同系統）で回し、照合ロジック（スライス→突合→diff→status 分類）は fixture テストで回帰ガードする（§8）。

## 3. 粒度ガード

grain 列の組で重複がないことを保証し、静かに通さず reject する。

- `combine.py` `_assert_grain` … union / intersection / grid の各合成モードで grain 重複を拒否。
- `provenance.py` `splice_preliminary` … confirmed と preliminary で同一セルの重複を禁止。

## 4. 出典ゲート

全成果物（Parquet / SQLite / DuckDB / meta.json）に citation が入ったかを検証し、欠ければ `RuntimeError` で**出荷をブロック**する（`io/export.py` `_verify_attribution`）。

- Parquet … フッター key-value メタ
- SQLite / DuckDB … `_source_meta` テーブル
- CSV … 併設 `<stem>.meta.json` サイドカー

## 5. データセット別の検証状況（索引）

各データセット doc の検証セクションへのリンク。**実証値・diff の具体値はそちらを正典**とし、本表は検証観点の有無のみを示す。

| データセット             | 主な検証観点                                                    | doc                                                         |
| ------------------------ | --------------------------------------------------------------- | ----------------------------------------------------------- |
| **地域マスタ（area）**   | 人口保存・孤児検出・既知差分（1980）                            | [area_master.md](datasets/area_master.md)                   |
| **population**           | 総数スライスで総人口再現・area マスタ依存                       | [population.md](datasets/population.md)                     |
| **population_by_age**    | 国民保存＋年齢/男女保存・クロスファクト検算 C3                  | [population_by_age.md](datasets/population_by_age.md)       |
| **population_by_age5**   | 年齢保存・全国＝47県合計・クロスファクト検算 C1 / C4            | [population_by_age5.md](datasets/population_by_age5.md)     |
| **daynight_population**  | 夜間人口保存・孤児・クロスファクト検算 C5                       | [daynight_population.md](datasets/daynight_population.md)   |
| **labor_force**          | 3区分保存・労働力率＝公表値一致                                 | [labor_force.md](datasets/labor_force.md)                   |
| **family_type**          | ツリー保存則・47県合計＝全国・不詳(999)の導出注入               | [family_type.md](datasets/family_type.md)                   |
| **industry**             | 産業内訳保存（県版）・47県合計＝全国                            | [industry.md](datasets/industry.md)                         |
| **occupation (major12)** | 職業内訳保存（県版）・47県合計＝全国                            | [occupation.md](datasets/occupation.md)                     |
| **occupation (major10)** | 職業内訳保存（県版）・総数保存（内訳は分類境界差を doc に明記） | [occupation.md](datasets/occupation.md)                     |
| **census ソース表**      | 統一案の全年突合せ（値一致・部分集合の発見）                    | [census_source_tables.md](datasets/census_source_tables.md) |

## 6. CLI による検証コマンド

数値の最新実測は各 doc に埋め込まず、以下で取得する。

```bash
uv run data-forge area-check      <dataset>   # 人口保存＋孤児件数
uv run data-forge area-orphans    <dataset>   # 未整備の消滅アトムを人口降順で全件一覧（堀を駆動）
uv run data-forge crossfact-check <dataset>   # 総人口スライスを population ハブと突合（§2 三角測量）
```

- `area-check` … `national_conservation`（保存則）と孤児件数を出力。
- `area-orphans` … 合併イベント未整備で base_year に届かないアトムを列挙し、`data/area/events_overrides.csv` への追記候補を示す。
- `crossfact-check` … `cross_fact` で総人口スライスを `population_timeseries` と full-join 突合し、年別 status（match / known_diff / scope_out / mismatch）を集計。真の mismatch が 1 件でもあれば exit 1。対応キー＝`population_by_age5_timeseries`（C1）/ `population_by_age_timeseries`（C3）。

## 7. 既知差分レジストリ

原資料の真実であり override では解消しない差分は `KNOWN_DIFFS` として受容しテストで固定する。  
**正典はコード**（`area/reconcile.py` の `KNOWN_DIFFS`）。本節はその要点をミラーするものであり、乖離時はコードを信じる。

現在の登録（詳細・全件は `KNOWN_DIFFS` を参照）:

- **1980（+37 人）** … 東京都特別区部の集計値(8,351,893) が 23 区合計(8,351,856) より 37 人多い＝区に按分されない「区未定分」。市区町村グレインに受け皿が無く、捏造せず保持する。

> 新統計投入時に新規差分が混入した場合、`diff != 既知` として保存則検証が失敗する（見落とし防止）。増えた差分は原資料を確認のうえ本レジストリ（と `KNOWN_DIFFS`）へ追記する。

## 8. 自動テスト（pytest）

`uv run poe test`（`poe check` は lint＋test）。  
取得（fixture）→クレンジング→合成→地域参照→出力の全層をカバーする。ファイル数・ケース数は実行結果を正典とする。

- **取得（transform）** … メタ抽出・tidy 化（fixture JSON 使用）
- **クレンジング** … 年別スキーマ変種・level7・欠損 null 化・保存則
- **合成（combine）** … union / intersection / grid・粒度ガード
- **地域参照（area）** … アトム抽出・推移閉包・基準年集約・孤児検出・廃置分合 CSV
- **クロスファクト検算** … スライス→突合→diff→status 分類の回帰ガード（fixture）
- **出力（export）** … citation 同梱・欠損検知
- **来歴（provenance）** … data_status 付与・splice

## 9. 未カバー領域（確からしさの穴）

機械検証が及ばず、人手 or 将来対応に頼っている箇所。ここを埋めることが検証計画の本丸。

| 領域                        | 現状                                                      | 対応方針                                                                                                 |
| --------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **実 API 取得（fetch.py）** | テスト無し（fixture 前提）。ネットワーク/ページング未検証 | モック化した単体テスト追加                                                                               |
| **e-Stat raw JSON 構造**    | `get(..., "")` で黙認。構造崩れを例外化しない             | Pydantic による strict スキーマ検証（README ロードマップ Phase 2）                                       |
| **合併 overrides の妥当性** | 後継先の指定ミスに気づけない                              | 後継コード実在チェック等の自動検証                                                                       |
| **孤児アトム**              | 機械検出のみ・修正は人手（件数は `area-orphans` で確認）  | overrides 追記運用（`area-orphans` で駆動）                                                              |
| **既知差分の網羅性**        | 1980 のみ登録                                             | 新統計投入時に全年洗い出し                                                                               |
| **新年度スキーマ**          | 確定版投入時は手動で cleaner 追加＝一時的にテスト空白     | スキーマ差分の自動検出                                                                                   |
| **CI 不在**                 | ローカル `poe check` 頼み                                 | GitHub Actions で `poe check` 自動化                                                                     |
| **クロスファクト検算 C2**   | age5→3区分畳込 vs population_by_age は未実装              | by_age(系統B)の年齢不詳の帰属を `getStatsData` 実測→照合式・畳込後アトムで比較・diff は KNOWN_DIFFS 登録 |
| **日本人スライスの検算**    | C1〜C5 は総人口(nationality=0)のみ照合＝日本人(=1)は検証網の外。旗艦 age5 の 1990/1995 日本人が支庁 level3 混入で壊れていた事故を C1 は検知できず（`muni_levels` 設定の契約テストで別途ガード） | 日本人版の照合オラクル（例: 県 rollup vs 系統B の日本人表・年齢/男女保存）を crossfact に追加 |

## 10. 関連

- パイプライン全体像・ロードマップ … [apps/pipeline/README.md](../apps/pipeline/README.md)
- 地域マスタ（保存則・孤児・堀運用の正典）… [area_master.md](datasets/area_master.md)
