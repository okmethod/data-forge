---
title: 高齢化率
sidebar_position: 3
---

データセット: **合併畳み込み済みの市区町村別 年齢3区分（年少 0-14 / 生産年齢 15-64 / 老年 65+）×男女別人口** - 1980〜2020年・全9回分

このページは **全国 → 都道府県の偏在 → ドリルダウン → サンプル市** の順に同じデータを見ていく。  
（年齢構造そのものの形＝人口ピラミッドの一世紀は [人口ピラミッド](/pyramid) を、印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

高齢化率は `老年人口 ÷ (年少＋生産年齢＋老年)`（年齢不詳を除く）で算出する。

---

## 全国：高齢化率と年齢3区分構成の推移

高齢化率は **1980年の 9.1% から 2020年には 28.7%** へ、40年で約3倍に上昇した。  
老年人口が増える一方、**年少人口は一貫して縮小**し、生産年齢人口も1995年をピークに減少へ転じた。

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

<LineChart
  data={aging_national}
  x=year
  y=aging_pct
  title="全国 高齢化率（％）"
  yFmt="0.0"
  yMin=0
  yMax=40
  xType=category
/>

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

<AreaChart
  data={age_comp}
  x=year
  y=population
  series=age_class
  title="全国 年齢3区分別人口"
  yFmt="#,##0"
  xType=category
/>

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
  x=pref_name
  y=aging_pct
  title="都道府県別 高齢化率（％・2020年）"
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

<LineChart
  data={pref_aging_trend}
  x=year
  y=aging_pct
  title="{inputs.pref.value} の高齢化率推移（％）"
  yFmt="0.0"
  yMin=0
  yMax=40
  xType=category
/>

---

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

<LineChart
  data={inzai_aging}
  x=year
  y=aging_pct
  series=region
  title="高齢化率（％）印西市 vs 全国"
  yFmt="0.0"
  yMin=0
  yMax=35
  xType=category
/>

年齢3区分×男女の構成（簡易人口ピラミッド）を1980年と2020年で比べると、街の規模が約3倍に膨らみ、生産年齢層を厚く保ちつつ **老年層（上段）が男女とも大きく膨らんだ**ことが読みとれる。

```sql pyramid_1980
  select age_class, sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age_city.by_age
  where sex_code in ('1','2') and age_class_code in ('1','2','3') and year = 1980
  order by age_class_code desc
```

<!-- prettier-ignore -->
<BarChart
  data={pyramid_1980}
  x=age_class
  y=pop
  series=sex
  title="印西市 年齢3区分×男女（1980年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
  yMin=-35000
  yMax=35000
/>

```sql pyramid_2020
  select age_class, sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age_city.by_age
  where sex_code in ('1','2') and age_class_code in ('1','2','3') and year = 2020
  order by age_class_code desc
```

<!-- prettier-ignore -->
<BarChart
  data={pyramid_2020}
  x=age_class
  y=pop
  series=sex
  title="印西市 年齢3区分×男女（2020年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
  yMin=-35000
  yMax=35000
/>
