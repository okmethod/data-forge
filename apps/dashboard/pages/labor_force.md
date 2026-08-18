---
title: 労働力
sidebar_position: 7
---

データセット: **労働力状態（3区分）別 人口・労働力率** - 1950〜2020年（15回）・全国＋都道府県。

このページでは、人口・世帯に続く基幹軸である**就業構造**を、全国 → 都道府県のスケールで見ていく。  
主役は **労働力率（＝労働力人口 ÷ 労働力状態が判明した15歳以上人口）**で、高齢化（[人口ピラミッド](/pyramid)）と対にすると「**働き手の比率の変化**」が読める。  
（市区町村粒度は持たないため、印西市を軸にした横断は扱わない）

_※ 労働力率の分母は `労働力人口 + 非労働力人口`（＝労働力状態が判明した人）とし、労働力状態不詳は除外している。_

---

## 全国：男性は低下・女性は上昇（労働力率）

労働力率を男女別に見ると、**男性は 1955 年の約 85% をピークに低下**（高齢化で引退世代＝非労働力人口が増えるため）、**女性は 1975 年の約 46% を底に上昇**（社会進出）し、2020 年に 53.5% へ達している。

```sql lf_national_sex
  select
    year,
    round(
      max(case when sex_code = '1' and labor_status_code = '110' then population end) * 100.0
      / (max(case when sex_code = '1' and labor_status_code = '110' then population end)
         + max(case when sex_code = '1' and labor_status_code = '140' then population end)), 1) as "男",
    round(
      max(case when sex_code = '2' and labor_status_code = '110' then population end) * 100.0
      / (max(case when sex_code = '2' and labor_status_code = '110' then population end)
         + max(case when sex_code = '2' and labor_status_code = '140' then population end)), 1) as "女"
  from census_labor_force.labor_force
  where area_code = '00000'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={lf_national_sex}
  x=year
  y={['男','女']}
  seriesOrder={['男','女']}
  title="全国 男女別の労働力率（%）"
  yFmt="0.0"
  xType=category
/>

---

## 全国：完全失業率の推移（景気の鏡）

完全失業率（＝完全失業者 ÷ 労働力人口）は、**バブル崩壊後に上昇し 2010 年の 6.4% でピーク**（リーマンショック後）、その後の景気回復で 2020 年は 3.9% まで下がっている。

```sql lf_unemployment
  select
    year,
    round(
      max(case when labor_status_code = '130' then population end) * 100.0
      / max(case when labor_status_code = '110' then population end), 2) as unemployment_rate
  from census_labor_force.labor_force
  where area_code = '00000' and sex_code = '0'
  group by year
  order by year
```

<LineChart
  data={lf_unemployment}
  x=year
  y=unemployment_rate
  title="全国 完全失業率（%）"
  yFmt="0.0"
  yMin=0
  xType=category
/>

_※ 完全失業率は総数（男女計）で算出。就業者・完全失業者は労働力人口の再掲。_

---

## 都道府県：労働力率ランキング（2020）

同じ 2020 年でも県によって労働力率は異なる。  
共働き・若年層の集中する**東京・愛知**や、女性就業率の高い**福井・長野**が上位に来る。

```sql lf_pref_ranking
  select
    area_name,
    round(
      max(case when labor_status_code = '110' then population end) * 100.0
      / (max(case when labor_status_code = '110' then population end)
         + max(case when labor_status_code = '140' then population end)), 1) as labor_force_rate
  from census_labor_force.labor_force
  where area_code != '00000' and sex_code = '0' and year = 2020
  group by area_name
  order by labor_force_rate desc
```

<BarChart
  data={lf_pref_ranking}
  x=area_name
  y=labor_force_rate
  title="都道府県別 労働力率（総数・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
  yMin=55
/>

---

## 都道府県：完全失業率ランキング（2020）

完全失業率で見ると、労働力率ランキングとは**ほぼ逆の顔ぶれ**になる。  
雇用機会の限られる**沖縄・青森・福岡**が上位、製造業と共働きが厚い**島根・福井・富山**が下位。

```sql lf_pref_unemployment
  select
    area_name,
    round(
      max(case when labor_status_code = '130' then population end) * 100.0
      / max(case when labor_status_code = '110' then population end), 2) as unemployment_rate
  from census_labor_force.labor_force
  where area_code != '00000' and sex_code = '0' and year = 2020
  group by area_name
  order by unemployment_rate desc
```

<BarChart
  data={lf_pref_unemployment}
  x=area_name
  y=unemployment_rate
  title="都道府県別 完全失業率（総数・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
  yMin=2
/>

---

## ドリルダウン：都道府県別 労働力率・完全失業率の推移

<Dropdown
  data={lf_pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql lf_pref_list
  select distinct area_name, area_code
  from census_labor_force.labor_force
  where area_code != '00000'
  order by area_code
```

```sql lf_pref_trend
  select
    year,
    round(
      max(case when sex_code = '1' and labor_status_code = '110' then population end) * 100.0
      / (max(case when sex_code = '1' and labor_status_code = '110' then population end)
         + max(case when sex_code = '1' and labor_status_code = '140' then population end)), 1) as "男",
    round(
      max(case when sex_code = '2' and labor_status_code = '110' then population end) * 100.0
      / (max(case when sex_code = '2' and labor_status_code = '110' then population end)
         + max(case when sex_code = '2' and labor_status_code = '140' then population end)), 1) as "女"
  from census_labor_force.labor_force
  where area_name = '${inputs.pref.value}'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={lf_pref_trend}
  x=year
  y={['男','女']}
  seriesOrder={['男','女']}
  title="{inputs.pref.value} 男女別の労働力率（%）"
  yFmt="0.0"
  xType=category
/>

```sql lf_pref_unemp_trend
  select
    year,
    round(
      max(case when labor_status_code = '130' then population end) * 100.0
      / max(case when labor_status_code = '110' then population end), 2) as unemployment_rate
  from census_labor_force.labor_force
  where area_name = '${inputs.pref.value}' and sex_code = '0'
  group by year
  order by year
```

<LineChart
  data={lf_pref_unemp_trend}
  x=year
  y=unemployment_rate
  title="{inputs.pref.value} 完全失業率（総数・%）"
  yFmt="0.0"
  yMin=0
  xType=category
/>
