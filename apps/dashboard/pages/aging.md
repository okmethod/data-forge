---
title: 年齢構成・高齢化率
sidebar_position: 2
---

データセット: **年齢3区分別人口（年少 0-14 / 生産年齢 15-64 / 老年 65+）×男女** - 1980〜2020年・全9回分

このページは **全国 → 都道府県の偏在 → ドリルダウン → サンプル市** の順に同じデータを見ていく。  
（印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

高齢化率は `老年人口 ÷ (年少＋生産年齢＋老年)`（年齢不詳を除く）で算出する。

---

## 全国：高齢化率の推移

高齢化率は **1980年の 9.1% から 2020年には 28.7%** へ、40年で約3倍に上昇した。

```sql aging_national
  select
    year,
    round(
      sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end)
    , 1) as aging_pct
  from census_age_prefecture.by_age
  where sex_code = '0'
  group by year
  order by year
```

<LineChart data={aging_national} x=year y=aging_pct title="全国 高齢化率（％）" yFmt="0.0" yMin=0 yMax=40 xType=category />

---

## 全国：年齢3区分別 人口構成の推移

老年人口が増える一方、**年少人口は一貫して縮小**し、生産年齢人口も1995年をピークに減少へ転じた。

```sql age_comp
  select
    year,
    age_class,
    sum(population) as population
  from census_age_prefecture.by_age
  where sex_code = '0' and age_class_code in ('1','2','3')
  group by year, age_class_code, age_class
  order by year, age_class_code
```

<AreaChart data={age_comp} x=year y=population series=age_class title="全国 年齢3区分別人口" yFmt="#,##0" xType=category />

---

## 全国：5歳階級で見る一世紀（1920〜2020）

**この節だけ**別のデータセットに切り替える（上までの年齢3区分とは出所が異なり、次の「都道府県の偏在」以降は再び3区分に戻る）。

データセット: **年齢5歳階級（0〜4／5〜9／…／85歳以上）×男女別人口** — 1920〜2020年・全21回分  
出所: e-Stat 国勢調査 時系列データ「年齢（5歳階級），男女別人口及び人口性比」（全国／都道府県の2表）

このデータセットは、同じ「年齢構成」でも上の3区分とは**粒度・年範囲・精製上の扱い**が異なる。デモとして、その差を明示しておく。

- **粒度は都道府県まで（市区町村なし）。** 市区町村の綺麗な5歳階級 長期時系列は e-Stat に存在しない（各回調査ごとに表の設計が違い、経年で接続できない）。市区町村まで下りるのは3区分だけ。→ 印西市の年齢構成は3区分で後述する。
- **その代わり1920年まで遡れる。** 3区分表は1980年からだが、この5歳階級表は**一世紀（21回）**をカバーする。
- **年齢の上限は「85歳以上」に統一。** 全国表はさらに細分（85〜89…110歳以上）を持つが、都道府県表は85歳以上止まり。両者を突き合わせられるよう85歳以上を終端に揃えた。
- **年齢不詳は「総数 −（5歳階級の合計）」で補って明示。** 元表に年齢不詳の欄が無い一方、近年は不詳が無視できない（2020年で全国 895 万人）。`5歳階級の合計 ＋ 不詳 ＝ 総数`が全年・全地域で閉じるよう、精製時に不詳を導出して行に足している。

### 高齢化率の超長期推移

1920年の **5.3%** から一貫して上昇し、戦後に急勾配となって2020年は 25.0%。

```sql aging_national_age5
  select
    year,
    round(
      sum(case when age_class_code in ('250','260','280','290','310') then population end) * 100.0
      / sum(case when age_class_code not in ('100','999') then population end)
    , 1) as aging_pct
  from census_age5.by_age5
  where area_code = '00000' and sex_code = '0'
  group by year
  order by year
```

<LineChart data={aging_national_age5} x=year y=aging_pct title="全国 高齢化率（％・5歳階級ベース 1920〜2020）" yFmt="0.0" yMin=0 yMax=40 xType=category />

> **注:** 同じ2020年でも高齢化率は本節（25.0%）と上の3区分ベース（28.7%）でズレる。5歳階級表のほうが
> 年齢不詳が多く（上記）、不詳を分母から除くと分子（65歳以上）が相対的に小さく出るため。
> **厳密な高齢化率は3区分ベースを正とし**、本節は一世紀の**形の変化**を見るためのもの。

### 年齢ピラミッド（男女×5歳階級）

**1920年の富士山型 → 2020年の壺型**という一世紀の人口転換が、5歳階級のピラミッドで形として分かる
（縦軸は同スケール＝±500万人で、総人口 5,596 万→1億2,615 万の拡大も同時に読める）。

```sql pyramid_1920_national
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5.by_age5
  where area_code = '00000' and sex_code in ('1','2')
    and age_class_code not in ('100','999') and year = 1920
  order by age_class_code desc
```

<BarChart data={pyramid_1920_national} title="全国 年齢5歳階級×男女（1920年）左=男 / 右=女" x=age_class y=pop series=sex swapXY=true type=stacked sort=false yMin=-5000000 yMax=5000000 />

```sql pyramid_2020_national
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5.by_age5
  where area_code = '00000' and sex_code in ('1','2')
    and age_class_code not in ('100','999') and year = 2020
  order by age_class_code desc
```

<BarChart data={pyramid_2020_national} title="全国 年齢5歳階級×男女（2020年）左=男 / 右=女" x=age_class y=pop series=sex swapXY=true type=stacked sort=false yMin=-5000000 yMax=5000000 />

---

## 都道府県の偏在：高齢化率ランキング（2020）

**秋田（37.6%）を筆頭に東北・山陰・四国が高く**、沖縄（22.6%）・東京（22.8%）・愛知など
若年流入や出生率の高い地域は低い。

```sql pref_aging
  select
    pref_name,
    round(
      sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end)
    , 1) as aging_pct
  from census_age_prefecture.by_age
  where sex_code = '0' and year = 2020
  group by pref_name
  order by aging_pct desc
```

<BarChart
    data={pref_aging}
    title="都道府県別 高齢化率（％・2020年）"
    x=pref_name
    y=aging_pct
    swapXY=true
    sort=false
    yFmt="0.0"
/>

---

## ドリルダウン：都道府県別 高齢化率の推移

<Dropdown data={pref_list} name=pref value=pref_name defaultValue="秋田県" title="都道府県" />

```sql pref_list
  select distinct pref_name, pref_code
  from census_age_prefecture.by_age
  order by pref_code
```

```sql pref_aging_trend
  select
    year,
    round(
      sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end)
    , 1) as aging_pct
  from census_age_prefecture.by_age
  where sex_code = '0' and pref_name = '${inputs.pref.value}'
  group by year
  order by year
```

<LineChart data={pref_aging_trend} x=year y=aging_pct title="{inputs.pref.value} の高齢化率推移（％）" yFmt="0.0" yMin=0 yMax=40 xType=category />

## サンプル市：千葉県印西市

市区町村粒度でしか描けないミクロの一例。  
印西市の高齢化率は **農村 → 若返り → 再び高齢化** というU字を描く。  
1980年は 12.5%と全国（9.1%）を上回る農村だったが、千葉ニュータウンの宅地開発で若い世代が流入し **1995年の 10.7% を底に全国を下回る若い街**へ。
その後は全国と同様に再上昇し、2020年は 23.2%（全国 28.7%）。

```sql inzai_aging
  select '印西市' as region, year,
    round(sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end), 1) as aging_pct
  from census_age_city.by_age where sex_code = '0' group by year
  union all
  select '全国' as region, year,
    round(sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end), 1) as aging_pct
  from census_age_prefecture.by_age where sex_code = '0' group by year
  order by region, year
```

<LineChart data={inzai_aging} x=year y=aging_pct series=region title="高齢化率（％）印西市 vs 全国" yFmt="0.0" yMin=0 yMax=35 xType=category />

年齢3区分×男女の構成（簡易人口ピラミッド）を1980年と2020年で比べると、街の規模が約3倍に膨らみ、生産年齢層を厚く保ちつつ **老年層（上段）が男女とも大きく膨らんだ**ことが読みとれる。

```sql pyramid_1980
  select age_class, sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age_city.by_age
  where sex_code in ('1','2') and age_class_code in ('1','2','3') and year = 1980
  order by age_class_code desc
```

<BarChart data={pyramid_1980} title="印西市 年齢3区分×男女（1980年）左=男 / 右=女" x=age_class y=pop series=sex swapXY=true type=stacked sort=false yMin=-35000 yMax=35000 />

```sql pyramid_2020
  select age_class, sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age_city.by_age
  where sex_code in ('1','2') and age_class_code in ('1','2','3') and year = 2020
  order by age_class_code desc
```

<BarChart data={pyramid_2020} title="印西市 年齢3区分×男女（2020年）左=男 / 右=女" x=age_class y=pop series=sex swapXY=true type=stacked sort=false yMin=-35000 yMax=35000 />
