# docs

okmethod/data-forge のドキュメント群。

---

## 構成

- [pipeline-architecture.md](pipeline-architecture.md): パイプライン全体設計（段構成・派生フロー・依存の向き・seam）
- **収集データカタログ** `sources/` — 精製の取得元（ソース側）の一覧
  - [sources/data-provider-catalog.md](sources/data-provider-catalog.md): データ提供者の利用規約・商用可否（e-Stat 等）
  - [sources/estat-census-catalog.md](sources/estat-census-catalog.md): e-Stat 国勢調査の帳票カタログ（採用/不採用・statsDataId・年別軸クセ・ソース選定根拠）
- **精製データカタログ** `distributions/` — 本パイプラインが精製・配布するデータセットごとの仕様（出力スキーマ・使い方・検証結果）
  - 後述の「精製データ一覧」参照
- [data-quality-assurance.md](data-quality-assurance.md): データ品質保証（保存則・クロスファクト検算・粒度ガード・出典同梱）

---

## 精製データの2つの粒度層（マクロ／ミクロ）

各データセットは、粒度と時間カバレッジの異なる2層で構成される。

- **マクロ（都道府県粒度・長期）**: 全国・都道府県スケール。多くが一世紀（1920〜）の長期系列。合併の影響を受けない固定コードで単一帳票から安価に得られる。
- **ミクロ（市区町村粒度・近年）**: 市区町村スケール。各回調査の別々の帳票を合併畳込で接続した近年（多くは1980〜）の時系列。年ごとに形の違う帳票を縫い合わせる泥臭い経路を要する。

---

## 精製データ一覧

| データセット群                                              | 内容                                                                                               |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [population](distributions/population.md)                   | 国勢調査 男女別人口（市区町村 1980〜2020＋2025速報／都道府県 1920〜2020）                          |
| [population_by_age](distributions/population_by_age.md)     | 国勢調査 年齢3区分×男女別人口（市区町村 1980〜2020／都道府県 1920〜2020・総数）                    |
| [population_by_age5](distributions/population_by_age5.md)   | 国勢調査 年齢5歳階級×男女別人口（市区町村 2010〜2020／全国・都道府県 1920〜2020）                  |
| [daynight_population](distributions/daynight_population.md) | 国勢調査 昼夜間人口（従業地・通学地, 1990〜2020, 7年時系列）                                       |
| [households](distributions/households.md)                   | 国勢調査 世帯の種類別 世帯数・世帯人員（全国・都道府県, 1960〜2020）                               |
| [family_type](distributions/family_type.md)                 | 国勢調査 世帯の家族類型16区分別 世帯数・世帯人員（全国・都道府県, 1995〜2020, 単独世帯割合）       |
| [labor_force](distributions/labor_force.md)                 | 国勢調査 労働力状態3区分×男女別人口（全国・都道府県, 1950〜2020）                                  |
| [industry](distributions/industry.md)                       | 国勢調査 産業大分類×男女別就業者数（全国1995〜/都道府県2005〜2020）                                |
| [occupation](distributions/occupation.md)                   | 国勢調査 職業大分類×男女別就業者数（major12=12区分1995〜/major10=10区分・全国1950〜/県1980〜2005） |
| [area_master](distributions/area_master.md)                 | 地域マスタ（アトム軸スタースキーマ）＝合併集約の共有ハブ                                           |
