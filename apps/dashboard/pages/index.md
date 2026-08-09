---
title: 国勢調査 人口ダッシュボード
---

合併畳み込み済みの市区町村別 人口を **2005〜2020年** の長期時系列で可視化する。
データソースは `data/processed/census_population_timeseries.sqlite`（市区町村粒度・全4国勢調査年）。

このダッシュボードの公開範囲は、デモ向けとして **都道府県粒度まで＋サンプル市区町村** としている。

## 全国総人口の推移

日本全体の人口は **2010年をピーク（約1億2,806万人）に減少局面** へ入った。

```sql national
  select year, sum(population) as population
  from census.prefecture_population
  where sex = '総数'
  group by year
  order by year
```

<LineChart data={national} x=year y=population title="全国総人口" yFmt="#,##0" yMin=125000000 yMax=130000000 xType=category />

## 各都道府県 人口増減ランキング（2005 → 2020）

全国では減っても、**増えた地域と減った地域に大きく分かれる**。東京圏・沖縄が伸び、東北・地方が大きく減る。

```sql pref_change
  with p as (
    select pref_name, year, population
    from census.prefecture_population
    where sex = '総数'
  ),
  chg as (
    select
      a.pref_name,
      round((b.population * 1.0 / a.population - 1) * 100, 1) as change_pct
    from p a
    join p b on a.pref_name = b.pref_name and a.year = 2005 and b.year = 2020
  )
  select
    pref_name,
    change_pct,
    case when change_pct >= 0 then '増加' else '減少' end as trend
  from chg
  order by change_pct desc
```

<BarChart
    data={pref_change}
    title="都道府県別 人口増減率（％）"
    x=pref_name
    y=change_pct
    series=trend
    swapXY=true
    sort=false
    yFmt="+0.0;-0.0"
    colorPalette={['#2563eb', '#dc2626']}
/>

## 都道府県別 総人口の推移

<Dropdown data={pref_list} name=pref value=pref_name defaultValue="千葉県" title="都道府県" />

```sql pref_list
  select distinct pref_name, pref_code
  from census.prefecture_population
  order by pref_code
```

```sql pref_trend
  select year, population
  from census.prefecture_population
  where sex = '総数' and pref_name = '${inputs.pref.value}'
  order by year
```

<LineChart data={pref_trend} x=year y=population title="{inputs.pref.value} の総人口推移" yFmt="#,##0" xType=category />

## サンプル市区町村: 千葉県 印西市

市区町村別・長期時系列のサンプル。印西市は **2010年に印旛村・本埜村を編入**したが、
合併畳み込みにより **旧境界をまたいで連続した1本の線** として人口増加を追える（生 e-Stat では年ごとに区分が変わり作れない）。

```sql inzai
  select year, population
  from census.sample_cities
  where area_name = '印西市' and sex = '総数'
  order by year
```

<LineChart data={inzai} x=year y=population title="印西市 の総人口推移（合併畳み込み済み）" yFmt="#,##0"  yMin=60000 yMax=120000 xType=category />
