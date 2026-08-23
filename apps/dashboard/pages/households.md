---
title: 世帯
sidebar_position: 5
---

データセット: **世帯の種類別 世帯数・世帯人員** - 1960〜2020年（12回）・全国＋都道府県

このページでは、人口とは別の基幹軸である**世帯**を、全国 → 都道府県のスケールで見ていく。  
主役は **平均世帯人員（＝世帯人員 ÷ 世帯数）**で、その縮小が**核家族化・単身化**を表す。  
世帯の大きさではなく**中身（家族構成）**は、[家族類型](/family_type)ページで扱う。  
（市区町村粒度は持たないため、印西市を軸にした横断は扱わない）

---

## 全国：世帯数は増え、世帯人員（総人口）は頭打ち

初回調査年（1960 年）を 100 とすると、**世帯数の指数は伸び続ける一方、世帯人員は 2010 年前後で頭打ち**になる。
両者の指数差が開くほど、1 世帯あたりの人数（＝平均世帯人員）は小さくなる。

```sql hh_national
  select
    year,
    round(households * 100.0 / first_value(households) over (order by year), 1) as households,
    round(household_members * 100.0 / first_value(household_members) over (order by year), 1) as household_members
  from census_households.households
  where area_code = '00000' and household_type_code = '110'
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={hh_national}
  x=year
  y={['households','household_members']}
  title="全国 一般世帯の世帯数・世帯人員（初回調査年=100）"
  yFmt="0.0"
  xType=category
/>

_※ 世帯数（単位: 世帯）と世帯人員（単位: 人）は単位が異なるため、それぞれの初回調査年（1960 年）を 100 とした指数で比較している。_

---

## 全国：平均世帯人員の縮小（核家族化・単身化）

世帯人員を世帯数で割ると、**1960 年の約 4 人 → 2020 年の約 2 人**へと、
半世紀で世帯規模がおよそ半分に縮んだことが分かる。核家族化・単身化の帰結といえる。

```sql hh_avg_national
  select
    year,
    round(household_members * 1.0 / households, 2) as avg_members
  from census_households.households
  where area_code = '00000' and household_type_code = '110'
  order by year
```

<LineChart
  data={hh_avg_national}
  x=year
  y=avg_members
  title="全国 一般世帯の平均世帯人員（世帯あたり人数）"
  yFmt="0.00"
  yMin=0
  xType=category
/>

_※ 平均世帯人員は施設等の世帯を除いた**一般世帯**で算出（施設は大人数で歪むため）。_

---

## 都道府県の偏在：平均世帯人員ランキング（2020）

同じ 2020 年でも県によって世帯規模は異なる。  
三世代同居が残る**山形・福井**などは大きく、単身世帯の多い**東京**は最も小さい。

```sql hh_pref_ranking
  select
    area_name,
    round(household_members * 1.0 / households, 2) as avg_members
  from census_households.households
  where area_code != '00000' and household_type_code = '110' and year = 2020
  order by avg_members desc
```

<BarChart
  data={hh_pref_ranking}
  x=area_name
  y=avg_members
  title="都道府県別 平均世帯人員（一般世帯・2020年）"
  swapXY=true
  sort=false
  yFmt="0.00"
  yMin=1.5
/>

---

## 都道府県ドリルダウン：都道府県別 世帯数・世帯人員の推移

<Dropdown
  data={hh_pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql hh_pref_list
  select distinct area_name, area_code
  from census_households.households
  where area_code != '00000'
  order by area_code
```

```sql hh_pref_trend
  select
    year,
    round(households * 100.0 / first_value(households) over (order by year), 1) as households,
    round(household_members * 100.0 / first_value(household_members) over (order by year), 1) as household_members
  from census_households.households
  where area_name = '${inputs.pref.value}' and household_type_code = '110'
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={hh_pref_trend}
  x=year
  y={['households','household_members']}
  title="{inputs.pref.value} 一般世帯の世帯数・世帯人員（初回調査年=100）"
  yFmt="0.0"
  xType=category
/>

```sql hh_pref_avg
  select
    year,
    round(household_members * 1.0 / households, 2) as avg_members
  from census_households.households
  where area_name = '${inputs.pref.value}' and household_type_code = '110'
  order by year
```

<LineChart
  data={hh_pref_avg}
  x=year
  y=avg_members
  title="{inputs.pref.value} 一般世帯の平均世帯人員（世帯あたり人数）"
  yFmt="0.00"
  yMin=0
  xType=category
/>
