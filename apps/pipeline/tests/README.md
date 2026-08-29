# tests — パイプラインテストスイート

外部依存なしのユニット／回帰テスト。fixture・合成データで完結し、実 API は叩かない。

> `fetch.py` のモック化は未着手＝[docs/data-quality-assurance.md](../../../docs/data-quality-assurance.md) §未カバー領域 バックログ）

**何をどう検証するかの設計（保存則の恒等式・クロスファクト検算）は [docs/data-quality-assurance.md](../../../docs/data-quality-assurance.md) が正典。**  
本書はそれを実装した pytest スイートの地図であり、数値の最新実測・確からしさの設計判断は埋め込まない。  
（CLI 検証コマンド `area-check` / `crossfact-check` と上記 doc を参照）

---

## ディレクトリ構成

取得（transform / tidy）→ クレンジング → 合成 → 地域参照 → 出力の全層をカバーする。

```text
tests/
├── fixtures/                   # e-Stat 生レスポンス等のテスト入力（tidy 化の起点）
│   └── estat_population_sample.json
│
│   # クレンジング（cleaner）＝年別スキーマ変種・level7・欠損 null 化・保存則（年齢／男女・内訳）
├── test_population.py          # 男女別人口（年別4変種・全国復元）
├── test_age5.py                # 5歳階級（全国・都道府県 companion）
├── test_age5_municipality.py   # 5歳階級 市区町村（旗艦）
├── test_daynight.py            # 昼夜間人口
├── test_households.py          # 世帯の種類別
├── test_family_type.py         # 家族類型16区分
├── test_labor_force.py         # 労働力状態3区分
├── test_industry.py            # 産業大分類
├── test_occupation.py          # 職業大分類
│                               # ※ 取得・整形（transform: メタ抽出・CLASS_INF+DATA_INF の tidy 化）は
│                               #    上記 cleaner テストが fixture 経由で併せて検証する
│
├── test_combine.py             # 合成：union / intersection / grid・粒度ガード（grain 重複の reject）
├── test_area.py                # 地域参照：アトム抽出・推移閉包・基準年集約・孤児検出・クロスファクト検算の回帰
├── test_area_ingest.py         # 地域参照：廃置分合 CSV パーサ
├── test_datasets.py            # レジストリ契約：family / table_name 一意性
├── test_provenance.py          # 来歴：data_status 付与・速報 splice
├── test_export.py              # 出力：citation 同梱・欠損検知（出荷ブロック）
└── test_public_scope.py        # 公開スコープゲート：流出防止
```

TODO: グルーピングしてディレクトリ分けする。
