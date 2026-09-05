# households — 国勢調査 世帯の種類別 世帯数・世帯人員

国勢調査（e-Stat）の **世帯の種類別世帯数及び世帯人員 － 全国，都道府県**（時系列データ製品`0003410420`、その1＝一般世帯及び施設等の世帯）を、**全国・47都道府県 × 1960〜2020** に精製した**データセットの正典**。  
世帯数・世帯人員という**人口(person)とは別の基幹軸**を提供し、平均世帯人員（＝世帯人員÷世帯数、世帯規模の縮小＝核家族化・単身化）を分析できる。

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
