# tests — パイプラインテストスイート

外部依存なしのユニット／回帰テスト。fixture・合成データで完結し、実 API は叩かない。

**何をどう検証するかの設計（保存則の恒等式・クロスファクト検算）は [docs/data-quality-assurance.md](../../../docs/data-quality-assurance.md) が正典。**  
本書はそれを実装した pytest スイートの地図であり、数値の最新実測・確からしさの設計判断は埋め込まない。  
（CLI 検証コマンド `area-check` / `crossfact-check` と上記 doc を参照）

---

## ディレクトリ構成

パイプライン層で分ける（1テスト＝1層ディレクトリ）。  
ファイル名が対象データセット／コンポーネントを表し、個別仕様は [docs/distributions](../../../docs/distributions/) が正典なので、ここでは層の粒度でのみ説明する。

```text
tests/
├── fixtures/     # テスト入力（e-Stat 生レスポンス等・tidy 化の起点）
├── sources/      # 取得層：client ページング・fetch キャッシュ・軸ドリフト検出
├── cleaners/     # クレンジング：スキーマ変種・欠損 null 化・保存則
├── combine/      # 合成：union / intersection / grid＋粒度ガード
├── area/         # 地域参照：rollup・基準年集約・孤児検出・既知差分
├── crossfact/    # クロスファクト検算（三角測量）：層横断ゆえ独立
├── output/       # 出力：citation 同梱・欠損検知（出荷ブロック）
└── governance/   # 契約・ゲート系：レジストリ・来歴・公開スコープ
```

### ゲート↔層の対応（軸の相関）

5ゲートは層とほぼ1対1に対応する（＝層で切ればゲート区別も付いてくる）。  
空セルの多くは構造的に必然だが、クロスファクトだけは横断ゲートゆえ独立させ、拡張（C2・日本人版）に備える。

| 層 \ ゲート   | 入口ガード | 保存則 | クロスファクト | 粒度ガード | 出典同梱 |
| ------------- | :--------: | :----: | :------------: | :--------: | :------: |
| sources       |     ●      |        |                |            |          |
| cleaners      |            |   ●    |                |            |          |
| area          |            |   ●    |                |            |          |
| combine       |            |        |                |     ●      |          |
| provenance    |            |        |                |     ●      |          |
| output        |            |        |                |            |    ●     |
| **crossfact** |            |        |       ●        |            |          |

---

## 実行

全体は `uv run poe check`（lint + test）／`uv run poe test`。  
基本コマンドは [pipeline/README.md](../README.md) の「使い方」が正典。  
テストスイート固有の狙い撃ち実行のみ、下記に補う（対象は次節「ディレクトリ構成」の層に対応）。

```bash
# 層ディレクトリ単位で回す（例: クレンジング層のみ）
uv run poe test tests/cleaners

# クロスファクト検算だけ回す
uv run poe test tests/crossfact

# 名前で絞る（例: 保存則テスト）
uv run poe test -k conservation
```
