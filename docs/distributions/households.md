# households — 国勢調査 世帯の種類別 世帯数・世帯人員

国勢調査（e-Stat）の **世帯の種類別 世帯数・世帯人員** を精製した**データセットの正典**。  
世帯数・世帯人員という**人口(person)とは別の基幹軸**を提供し、平均世帯人員（＝世帯人員÷世帯数、世帯規模の縮小＝核家族化・単身化）を分析できる。  
**1 つの table_name `households` に 3 系列が同居する**（粒度は key suffix で表し family 名には持たせない）:

| 系列                   | 粒度・カバレッジ                                                      | 帳票の性質                        | 配布 key                             | cleaner                   |
| ---------------------- | --------------------------------------------------------------------- | --------------------------------- | ------------------------------------ | ------------------------- |
| **市区町村（ミクロ）** | 市区町村（level4/6/7）・1985-2020（5年間隔）・世帯人員は2015/2020のみ | 回次別帳票を縫合                  | `households_municipality_timeseries` | `households_municipality` |
| **全国（マクロ）**     | 全国（00000）・1960〜2020                                             | 回次跨帳票（単一 ID・scope 分岐） | `households_national_timeseries`     | `households`              |
| **都道府県（マクロ）** | 47都道府県・1960〜2020                                                | 回次跨帳票（単一 ID・scope 分岐） | `households_prefecture_timeseries`   | `households`              |

> 2010-2020 では市区町村↑県値が重なるため物理2重保存せず、市区町村→県 rollup==県マクロ を**検算オラクル**（H1/H2・test）で照合する（定義は [data-quality-assurance.md](../data-quality-assurance.md)）。

> 共通の位置づけ・関連ドキュメントは [forged-dataset-catalog.md](forged-dataset-catalog.md)。
> 全国（`households_national_timeseries`）と都道府県（`households_prefecture_timeseries`）は**地理粒度排他**で別配布に分ける（原則・検証は [forged-dataset-catalog.md](forged-dataset-catalog.md#全国と都道府県の分離地理粒度排他)）。全国＋県が同一 ID(0003410420) に同居するため、実現は別 ID の射影ではなく **cleaner の scope 分岐**（`area_code=="00000"` で全国/県へ2出力・fetch はキャッシュ共有）。

---

## データソース

| statsDataId | 帳票名                                                    | 粒度・期間                    |
| ----------- | --------------------------------------------------------- | ----------------------------- |
| 0003410420  | 世帯の種類別世帯数及び世帯人員 － 全国，都道府県（その1） | 全国＋47都道府県 / 1960〜2020 |

- **area master 不要**の低コスト fact：area 軸は全国(level1)＋47都道府県(level2)固定で旧市区町村(level7)を持たず、合併の影響を受けない（[age5year.md](age5year.md)と同性格）。全国も都道府県も同一 ID に含むため、全国/県の分離は別 ID の射影ではなく cleaner の scope 分岐で行う（上記の位置づけ注記）。
- **不詳処理は不要**：世帯は悉皆カウントで cat01（世帯の種類）に不詳区分が無い。配偶関係表（0003410382）で問題になった大量の「不詳」は本表には存在しない。
- 1965 年は本帳票に無く、**実在する 12 時点**（1960/1970/1975/1980/…/2020）のみ運ぶ。

### 軸の採否

| 軸               | コード               | 採否                                                     |
| ---------------- | -------------------- | -------------------------------------------------------- |
| tab 040          | 世帯数（単位: 世帯） | ✅ `households`                                          |
| tab 050          | 世帯人員（単位: 人） | ✅ `household_members`                                   |
| tab 1390         | 1世帯当たり人員      | ❌ `household_members / households` で導出可能ゆえ捨てる |
| cat01 100        | 世帯の種類＝総数     | ✅ `household_type_code=100`（総数=一般+施設）           |
| cat01 110        | 一般世帯             | ✅ `household_type_code=110`                             |
| cat01 120        | 施設等の世帯         | ✅ `household_type_code=120`                             |
| area 00100/00200 | 人口集中地区 / 以外  | ❌ 都道府県と同 level2 だが地理単位でないため除外        |

---

## 出力スキーマ

grain = **area × household_type × year**。
population 系の8列を土台に、sex→household_type、単一 `population`→2測定量（`households` / `household_members`）へ差し替えた形。

| 列                    | 型   | 説明                                            |
| --------------------- | ---- | ----------------------------------------------- |
| `area_code`           | str  | 地域コード（00000=全国 / 47都道府県）           |
| `area_name`           | str  | 地域名                                          |
| `area_level`          | int  | 階層（1=全国 / 2=都道府県）                     |
| `household_type_code` | str  | 100=総数 / 110=一般世帯 / 120=施設等の世帯      |
| `household_type`      | str  | 名称                                            |
| `year`                | int  | 調査年                                          |
| `households`          | int  | 世帯数（欠損は null）                           |
| `household_members`   | int  | 世帯人員（欠損は null）                         |
| `is_current`          | bool | 現存自治体か（本表は level7 を持たず常に true） |

**保存則:** 各 area×year で `household_type=総数 == 一般世帯 + 施設等の世帯`（世帯数・世帯人員とも）。
**地理保存（G）:** `households_prefecture_timeseries の 47都道府県合計 == households_national_timeseries の全国`（全国/県の scope 分割が値を落とさない/二重化しない保証・世帯数/世帯人員とも）。

**派生指標:** 平均世帯人員は配布側で `household_members / households`（世帯規模の縮小＝核家族化・単身化の指標）として算出する。

---

## 市区町村ミクロ系列（`households_municipality_timeseries`）

回次跨マクロ（`0003410420`）は都道府県止まりなので、市区町村は各回の「世帯の種類別」表を **year 軸で縫合し合併畳込（`aggregate_to_base`）** したミクロ系列にする（age5year の市区町村版と同じ Stitched フロー）。**入力側の帳票事実（年別 statsDataId・軸コード・カバレッジ非対称）は [estat-census-catalog.md](../sources/estat-census-catalog.md)「世帯の種類・人員」節が正典**。

- **grain** = `area × household_type × year`（マクロと同一 9 列。世帯の種類 100=総数/110=一般世帯/120=施設等の世帯）。**カバレッジ = 市区町村 × 1985〜2020**（世帯人員は 2015/2020 のみ・旧市区町村は 2010-2020 のみ）＝非対称の理由（1980欠・年別軸差）は上記 catalog が正典。
- **世帯人員の非対称同居**: 世帯人員が取れない年（1985-2010）も `household_members` 列を保持し null を埋める（age5year の国籍軸と同思想）。合併畳込では全 null の年を 0 でなく null に保つ（未計測と値0を混同しない）。
- **保存則:** 世帯の種類不詳を導出注入しないので `総数 ≥ 一般世帯 + 施設等の世帯`（差＝世帯の種類不詳。不詳が原表に無い年は等号）。

**検算オラクル（H1/H2）:** ミクロを県 rollup してマクロ `0003410420` の県と照合する（別プロダクト間クロスファクト検算）。悉皆ゆえ近年は diff=0・遡及年は県跨ぎ合併の境界振替を受容する。意味論・許容年・pin 値は [data-quality-assurance.md](../data-quality-assurance.md) が正典。
