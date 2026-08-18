---
title: 産業
sidebar_position: 8
---

データセット: **産業（大分類）別 就業者数** - 全国 1995〜2020年（6回）／都道府県 2005〜2020年（4回）。

このページでは、[労働力](/labor_force) に続く**就業構造**を、**「どの産業で働いているか」**の軸で見ていく。  
主役は **産業別就業者数** と **産業構成比（＝各産業就業者数 ÷ 総数）**で、高齢化（[人口ピラミッド](/pyramid)）と対にすると「**産業構造の転換（製造業 → 医療・福祉）**」が読める。  
（市区町村粒度は持たないため、印西市を軸にした横断は扱わない）

_※ 産業大分類は平成19年改訂後の「産業大分類2015」体系。「Ｔ分類不能の産業」も実カテゴリとして保持し、総数＝Σ大分類が成立する。_

---

## 全国：製造業は縮小・医療福祉は倍増（産業構造の転換）

主要産業の就業者数を追うと、**製造業は 1995 年の約 1,317 万人から 2020 年の 906 万人へ縮小**（生産の海外移転・自動化）、一方で **医療・福祉は 359 万人から 763 万人へ倍増**（高齢化）し、2020 年には製造業・卸売小売業に迫る規模になっている。

```sql ind_national_trend
  select
    year,
    max(case when industry_code = '170' then workers end) as "製造業",
    max(case when industry_code = '290' then workers end) as "医療，福祉",
    max(case when industry_code = '160' then workers end) as "建設業",
    max(case when industry_code = '200' then workers end) as "情報通信業"
  from census_industry.industry
  where area_code = '00000' and sex_code = '0'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={ind_national_trend}
  x=year
  y={['製造業','医療，福祉','建設業','情報通信業']}
  title="全国 主要産業の就業者数"
  yFmt="#,##0"
  xType=category
/>

---

## 全国：産業別就業者数ランキング（2020）

2020 年時点で就業者が最も多いのは **製造業・卸売小売業・医療福祉**の 3 産業。  
女性は医療福祉（577 万人）に、男性は製造業（621 万人）に多く、**産業ごとに男女構成が大きく異なる**。

```sql ind_national_ranking
  select industry, workers
  from census_industry.industry
  where area_code = '00000' and sex_code = '0' and year = 2020 and industry_code != '100'
  order by workers desc
```

<BarChart
  data={ind_national_ranking}
  x=industry
  y=workers
  title="全国 産業別就業者数（総数・2020年）"
  swapXY=true
  sort=false
  yFmt="#,##0"
/>

---

## 都道府県：産業別 就業者比率ランキング（2020）

産業構成には地域差がある。
産業を選ぶと、その産業に従事する就業者の比率（＝当該産業 ÷ 総数）で都道府県を並べ替える。  
**製造業**では **滋賀・静岡・愛知・岐阜**など中京・東海の工業県が上位に来る一方、**医療，福祉**や**農業，林業**に切り替えると全く別の地域が上位となっている。

<Dropdown
  data={ind_list}
  name=ind
  value=industry_code
  label=industry
  defaultValue="170"
  title="産業"
/>

```sql ind_list
  select distinct industry_code, industry
  from census_industry.industry
  where industry_code != '100'
  order by industry_code
```

```sql ind_pref_ranking
  select
    area_name,
    round(
      max(case when industry_code = '${inputs.ind.value}' then workers end) * 100.0
      / max(case when industry_code = '100' then workers end), 1) as pct
  from census_industry.industry
  where area_code != '00000' and sex_code = '0' and year = 2020
  group by area_name
  order by pct desc
```

<BarChart
  data={ind_pref_ranking}
  x=area_name
  y=pct
  title="都道府県別 {inputs.ind.label} 就業者比率（総数・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
/>

---

## ドリルダウン：都道府県別の産業構成（2020）

<Dropdown
  data={ind_pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql ind_pref_list
  select distinct area_name, area_code
  from census_industry.industry
  where area_code != '00000'
  order by area_code
```

```sql ind_pref_composition
  select
    industry,
    round(workers * 100.0 / (
      select workers from census_industry.industry i2
      where i2.area_name = '${inputs.pref.value}'
        and i2.sex_code = '0' and i2.year = 2020 and i2.industry_code = '100'
    ), 1) as share
  from census_industry.industry
  where area_name = '${inputs.pref.value}'
    and sex_code = '0' and year = 2020 and industry_code != '100'
  order by share desc
```

<BarChart
  data={ind_pref_composition}
  x=industry
  y=share
  title="{inputs.pref.value} 産業構成比（総数・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
/>
