---
title: 国勢調査 人口ダッシュボード
---

2020年 国勢調査（男女別人口）の可視化サンプル。データソースは `data/processed/census_population_2020.sqlite`。

## 全国の男女別人口

```sql national
  select sex, population
  from census.population
  where area_level = 1 and year = 2020
  order by sex_code
```

<DataTable data={national} />

## 都道府県別 総人口 ランキング

```sql prefectures
  select area_name, population
  from census.population
  where area_level = 2 and sex = '総数' and year = 2020
  order by population desc
```

<BarChart
    data={prefectures}
    title="都道府県別 総人口（2020）"
    x=area_name
    y=population
    swapXY=true
/>
