# area_master — 地域マスタ（アトム軸スタースキーマ）

星座型アーキテクチャの**共有ディメンション（conformed dimension）**。  
特定のファクトに属さず、合併をまたぐ市区町村の連続時系列を成立させる**共有ハブ**として、全ファクト（[population](population.md) / [population_by_age](population_by_age.md) / 将来の兄弟ファクト）から参照される。

**関連ドキュメント**:

- **正座型アーキテクチャについて**: [docs/pipeline-architecture.md](../pipeline-architecture.md)
- **実装詳細**: [src/data_forge/area/](../../apps/pipeline/src/data_forge/area/) の docstring

> 本 doc は `distributions/`（精製データカタログ）に同居するが、それ自体が配布データセットなのではなく、各データセットが依存する**内部の共有ハブ**の設計を記す。

> **なぜファクトから独立させるか:** 地域集合が年で変わる問題（合併・政令市移行・DID等）はどのファクト（総人口・年齢別・世帯…）にも共通で、grain に依存しない。  
> 1 ファクトの doc に埋めるとハブが二重化するため、conformed dimension として 1 箇所に正典を置く。

---

## 多年化の知見（地域マスタが必要な理由）

生テーブルの地域表現は年で不統一で、set 演算だけでは時系列として成立しない。具体的には:

1. **area 属性が年で非互換:** `area_level` の意味が違い（2005: level3=市区町村/4=区、2020: level4=市/6=市区町村）、`area_name` の表記も違う（2005「北海道札幌市」/2020「札幌市」）。年またぎで信頼できるのは `area_code` のみ。
2. **旧市区町村の埋め込み方が違う:** 合併前自治体を 2005 は letter付コード（例 `0120A (旧 函館市)`）で、2020 は level7 で特掲。set 演算では旧コードの人口を**後継自治体へ集約できない**。
3. 平成大合併は 2005 の調査時点(2005/10)で大半が完了済みのため、2005 起点では合併が捉えにくい（2005にあり2020に無いコードは93件）。**遡及するほど合併前の自治体が増え、畳み込み（連続時系列）の価値が本領を発揮する**（1980=3278・1985=3276・1990=3268・1995=3255・2000=3252 アトム → 2020=1741 へ集約） → 地域マスタで 1980〜2020 を接続済み（人口保存 孤児0・diff=0 を検証。ただし 1980 のみ 37 人差＝下記の特別区部「区未定分」）。

→ 実用グレードの連続時系列には **地域マスタ（アトム軸スタースキーマ）** が必要。fact=各年の「標準的な市区町村」による最finest分割（アトム）、dim 相当=合併イベントによる rollup。
「生」の簡易オプション（union/intersection/grid、[population.md の正規化モード節](population.md#派生データセット複数年結合の正規化モード)）はそのまま残す。以下の設計は
**実装済み**（`src/data_forge/area/`）。

---

## 設計

**核となる考え方:** 年ごとに変わる地域集合を、履歴型 dim（有効期間・後継）で持つのではなく、**fact 側を「国土をちょうど1回だけ覆う標準的な市区町村ユニット（アトム）」に固定**し、合併の後継対応は **events（廃置分合イベント）** に切り出す。
各年アトムを基準年へ前方 rollup することで、合併をまたいで正しく畳んだ連続時系列が得られる。

### アトム（fact 層）の grain

各国勢調査年について、`area` 階層（`parentCode`）から finest 分割の葉集合を抽出する（`area/atoms.py`）。
grain は全年で「標準的な市区町村」に統一する。

- **政令市は市レベル1ユニット**（行政区 level5 は採らない＝市に含める）。政令市移行が「区集合への 1→多 分裂」でなく「市コードの 1→1 変更」で表せ、合併集約(rollup)が破綻しないため。
- **東京23特別区は各1**（それぞれ独立自治体。特別区部 `13100` の集計行は除外）。
- **合併済み自治体の「旧内訳（name に "旧"）」は除外**（現自治体と二重計上になるため）。

葉集合の選択規則は「市区町村レベル（年で異なる）かつ name に "旧" を含まない候補」から、「別の候補の親に現れるコード（集計行/上位コンテナ）」を除いたもの。

> **人口保存の実証:** 全9統計（1980〜2020）で「アトム合計 == 全国total」を確認済み（1980=3278自治体, 1985=3276, 1990=3268, 1995=3255, 2005=2239, 2020=1741=1718市町村+23特別区）。diff=0 は 8 年で成立。**1980 のみ 37 人差**が残るが、これは東京都特別区部の集計値(8,351,893)が23 区合計(8,351,856)より 37 人多い＝**区に按分されない「区未定分」**という 1980 国勢調査の原資料特性で、市区町村グレインに受け皿が無いため（捏造せず原資料の真実を保持）。

### events（合併イベント）— dim 相当

合併の後継は fact でなく events 側に持つ。**実効イベント = parsed ⊕ overrides**（`area/events.py`）。

- **parsed:** e-Stat「廃置分合等情報」の生CSVを `area/history/ingest.py` の `normalize` で正規化したもの。
- **overrides:** 人手クッション（＝堀本体）。同一 `old_code` を持てば parsed を**置換**、`successor_code` を空にした行で**無効化**（ignore）する。

events スキーマ（正規化後）:

| 列               | 型  | 説明                                             |
| ---------------- | --- | ------------------------------------------------ |
| `old_code`       | str | 消滅/被合併側の JIS コード（アトム）             |
| `successor_code` | str | 直接の後継コード（1段。多段は複数行で表現）      |
| `year`           | int | 施行年（国勢調査 5 年刻みで近似可）              |
| `kind`           | str | 種別（合体/新設・編入・境界変更・分割・改称 等） |

> **廃置分合CSVの実物で列確定する運用:** `ingest.py` の生CSV列マッピング（`_RAW_COLS`）と種別フィルタ（`_MERGER_KINDS`）は実物CSV未取得のため**現状は想定値（TODO）**。実サンプル入手後に実列名へ合わせる。境界変更・分割・改称は人口保存を崩す/別扱いのため overrides 側で個別対応する。

### 集約モード `aggregate_to_base`（第4の正規化）

`aggregate_to_base(atom_fact, events, base_year=最新)` は、各年アトムを施行年 ≤ base_year の events で `base_code` へ**前方 rollup**（推移閉包で多段 A→C→E に対応）し、`(base_code, year, sex)` で**合算**する（`area/mapping.py` ＋ `area/aggregate.py`）。`name`/`level` は base_year 時点のアトム値で統一する。出力は単年 fact と同じ8列スキーマ。

```bash
uv run data-forge run population_timeseries --join aggregate_to_base                 # 既定=最新年へ畳む
uv run data-forge run population_timeseries --join aggregate_to_base --base-year 2020 # 基準年を固定
```

> **二重計上が原理的に起きない理由:** 各年アトムが国土を過不足なく1回覆い、rollup は各アトム→単一 `base_code` の関数だから。イベント未整備で消滅アトムが自分自身に留まる場合は「幽霊 base ユニット」として残る（reconcile が検出＝クッション候補）。

### 非固定モード `crosswalk`（畳む/畳まないを配布時に決めない）

`aggregate_to_base` は「畳んで確定した1ビュー」にすぎない。
合併前の実態（原境界）を保持したい利用者もいるため、**畳まず後継コード列を同梱**する `attach_crosswalk(atom_fact, events, base_year=最新)` を用意する。
出力は単年 fact の8列 ＋ `base_code`（後継先コード）＋ `base_name`（base_year 時点の後継先名称）の10列。
**同じ rollup の2ビュー**であり、`aggregate_to_base` は「`attach_crosswalk` を `base_code` で `GROUP BY` したもの」に等しい。

```bash
uv run data-forge run population_timeseries --join crosswalk                 # 畳まず base_code 列を同梱
uv run data-forge run population_timeseries --join crosswalk --base-year 2020 # 後継先の基準年を固定
```

- `area_code` のまま使う → **原境界**（合併前の自治体を各年そのまま。実態保持だが連続性なし）。
- `GROUP BY base_code` → **前方 rollup 相当**（現行自治体で連続時系列＝`aggregate_to_base` と一致）。

畳む/畳まないの選択を**配布時に固定せず利用者の集約クエリへ委譲**できるのが利点。

**2025 投入時の耐性:** `base_year` は**集約パラメータに外出し**しているため、次の調査年（2025）投入時は現 partition に新年 fact を union し、新イベントを events に追記するだけで済む。過去に配布した時系列の基準年ビューは据え置ける（配布物の安定性を `base_year` で守る）。

### 上位集約 `prefecture` / `region`（行政階層 roll-up）

合併 rollup（`aggregate_to_base`）が**時間方向**（合併後継で畳む）なのに対し、都道府県・地方ブロックへの集約は**空間方向の行政階層**を上る別軸。両者は直交するので、モジュールも分離する（時間軸＝`area/aggregate.py`、空間軸＝`area/spatial_rollup.py` の `aggregate_to_admin`。分類軸判別 `_cat_code_cols` のみ共用）。

- **events 非依存:** 市区町村は都道府県を跨がないため、各年アトムを `area_code` の県プレフィックス（先頭2桁）で group して合算するだけで県/地方合計になる。合併を畳もうが畳むまいが県内合計は不変（＝`national_conservation` が保証する不変量）なので、`aggregate_to_base` の前後どちらに適用しても同値。
- `prefecture` … `area_code[:2]+"000"`（実 JIS コード）へ集約。`area_level`=2、名称は 47 都道府県マスタ（`_PREFECTURES`）。**従来 dashboard 側に埋め込んでいた県名マスタ＋集約 SQL をパイプへ昇格し一元化**。
- `region` … 標準8地方区分（`_REGIONS`：三重=近畿・沖縄=九州）で `R1`〜`R8` へ集約。`area_level`=0（全国=1 と都道府県=2 の間の合成集約層）。地方名は「北海道地方」〜「九州地方」。
- 出力スキーマは入力 fact を踏襲し、分類軸（sex/age/daynight）は `_cat_code_cols` で保持（population / population_by_age / daynight_population 共用の無改修一般化）。

```bash
uv run data-forge run population_timeseries --join prefecture  # 47 都道府県へ集約
uv run data-forge run population_timeseries --join region      # 8 地方ブロックへ集約
```

**登録済みの県粒度データセット（配布物）:** 3ファクトとも県粒度を `default_join="prefecture"` で固定した専用データセットを持つ（市区町村時系列と upstream 共通・stem だけ分離した派生ビュー）。
dashboard はこれを素の射影で consume する（従来ダッシュ側に3重で埋めていた県集約 SQL＋47行 VALUES 県マスタを撤廃し、県名の正典を `_PREFECTURES` に一元化）。`region` は現状 dashboard 未使用のため未登録。

```bash
uv run data-forge run population_prefecture_timeseries          # 男女別人口・県粒度
uv run data-forge run population_by_age_prefecture_timeseries   # 年齢3区分×男女別・県粒度
uv run data-forge run daynight_population_prefecture_timeseries # 昼夜間人口・県粒度
```

> **検証（実データ・全3ファクト）:** 「県/地方合計 == 全国total」を `national_conservation` で全年 diff=0 確認（1980 の 37 人差＝区未定分も `KNOWN_DIFFS` で受容）。スポット: 東京都 2020=14,047,594・大阪府 2020=8,837,685・北海道地方 2020=5,224,614（いずれも公表値一致）。

### reconcile（堀の駆動）

parsed だけでは埋まらない箇所を機械的にフラグし、人手 overrides（クッション）で埋める運用を支える（`area/reconcile.py`）。2つの検査:

- **national_conservation** … 各年「アトム合計 == 全国total」を検査（アトム抽出の健全性）。
- **orphans** … base_year までに消滅したのに rollup 先が base_year に無いアトム（＝合併イベント未整備）を人口降順で列挙＝次に埋める候補。events 未整備の現状は **orphans=615件**（2006の大量合併＋政令市移行）。

```bash
uv run data-forge area-check population_timeseries    # 人口保存＋孤児件数の検証
uv run data-forge area-orphans population_timeseries  # 未整備の消滅アトムを人口降順で全件一覧
```

遡及で追加した overrides は 2 類型のみ（各行の根拠は [events_overrides.csv](../../data/area/events_overrides.csv) のインラインコメントに記す）:

- ① **行政区への編入 → 政令市補正**: 政令市アトムは「市 1 ユニット」なので、区への編入を市へ寄せる（例 `34108→34100`）。
- ② **郡区域変更に伴うコード変更**: ingest が「郡区域変更」を無視するため 1 段だけ補うと、後段の合併/現存は parsed 側で連鎖解決する（例 `09381→09410` 塩原町）。

各年の遡及結果（人口保存＝アトム合計 vs 公表全国total、孤児＝rollup 未到達アトム）:

| 年   | 追加 overrides | 孤児 | 人口保存 diff |
| ---- | -------------- | ---- | ------------- |
| 2000 | 6              | 0    | 0             |
| 1995 | 0              | 0    | 0             |
| 1990 | 1（古殿町）    | 0    | 0             |
| 1985 | 0              | 0    | 0             |
| 1980 | 1（塩原町）    | 0    | **37**        |

> **1980 の 37 人差＝原資料の真実（override では解消しない）:** 東京都特別区部の集計値(8,351,893)が 23 区合計(8,351,856)より 37 人多い＝**区に按分されない「区未定分」**。市区町村グレインに受け皿が無く、捏造せず保持する。reconcile は `KNOWN_DIFFS={1980:37}` として受容し（`area/reconcile.py`）、テストで固定する。

### 配置

| ファイル                                     | 場所                                      | 扱い                 |
| -------------------------------------------- | ----------------------------------------- | -------------------- |
| 生履歴CSV（廃置分合）                        | `data/raw/history/`                       | .gitignore・再取得可 |
| `events_parsed.csv`（ingest 出力）           | `data/area/`                              | .gitignore           |
| `events_overrides.csv`（人手クッション＝堀） | `data/area/`                              | .gitignore           |
| ひな形                                       | `area/seeds/events_overrides.example.csv` | コミット対象         |

> **運用上の注意:** data 側は Git 履歴に残らないため、堀そのものである `events_overrides.csv` は別途バックアップ/私的バージョン管理を推奨（喪失＝堀の喪失）。両ファイルが未配置/空でも `aggregate_to_base` は畳み込みを行わず union と同じ結果になる（データ欠落は起こさない安全側の挙動）。

### レイヤー

area 層は combine と同格の**データセット非依存**の参照層（population 固有でない）。`combine`（縦結合）と `area.aggregate`（基準年集約）は相互に依存させず、`cli.py` が clean→atoms→combine(union)→aggregate と配線する（集約を combine に埋め込まない＝合成層を特定の参照データに縛らない）。詳細は [docs/pipeline-architecture.md](../pipeline-architecture.md) の「依存の向きの原則」を参照。

> **再利用の範囲（重要）:** area 層は「ソース非依存」ではない。アトム抽出は各ソースの area 表現に依存する（今は e-Stat の area 階層前提）。ソースをまたいで再利用できるのはコード軸が JIS（全国地方公共団体コード）で揃う範囲で、とくに **events（合併の後継）は JIS コードの事実なので**他ソースでも使い回せる核。メッシュ・小地域・都市雇用圏など別のコード体系を使う統計とは噛み合わない。現状 consumer は population(e-Stat) の1例のみのため、非依存は主張せず e-Stat 前提で作り2例目で検証する。
