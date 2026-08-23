---
title: 昼夜間人口
sidebar_position: 4
---

データセット: **合併畳み込み済みの市区町村別 昼夜間人口（夜間＝常住地ベース / 昼間＝従業地・通学地ベース）** - 1990〜2020年・全7回分

このページは **全国 → 都道府県の偏在 → 都道府県ドリルダウン → サンプル市（印西市）ドリルダウン** の順に同じデータを見ていく。  
（印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

**昼夜間人口比率 ＝ 昼間人口 ÷ 夜間人口 × 100**。
100 を超えると昼間に人が流入する「働きに来る側」、下回ると昼間に人が流出する「ベッドタウン側」を意味する。

---

## 全国：昼＝夜（つまり、昼夜間は"偏在"の指標）

全国で見ると、国内では流入と流出が相殺するため **常に昼間人口=夜間人口（比率=100）**となる。  
つまり昼夜間人口は全国の合計では意味を持たず、**地域間の偏り（どこへ働きに行くか）を測る指標**である。

```sql national_dn
  select year, daynight, sum(population) as population
  from census_daynight_prefecture.daynight
  group by year, daynight_code, daynight
  order by year, daynight_code
```

<LineChart
  data={national_dn}
  x=year
  y=population
  series=daynight
  title="全国 昼間／夜間人口（両者は一致）"
  yFmt="#,##0"
  xType=category
/>

そのため、以降は都道府県・市区町村の偏在として読む。

---

## 都道府県の偏在：昼夜間人口比率ランキング（2020）

**東京都が 116.1 と突出**して人を集め、大阪・京都・愛知が続く。  
逆に**埼玉（89.6）・千葉・奈良・神奈川** は東京圏のベッドタウンとして昼間に人口が流出する。

```sql dn_ratio
  select
    pref_name,
    round(
      max(case when daynight_code = '1' then population end) * 100.0
      / max(case when daynight_code = '0' then population end)
    , 1) as ratio
  from census_daynight_prefecture.daynight
  where year = 2020
  group by pref_name
  order by ratio desc
```

<BarChart
  data={dn_ratio}
  x=pref_name
  y=ratio
  title="都道府県別 昼夜間人口比率（2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
  yMin=85
/>

---

## 都道府県ドリルダウン：都道府県別 昼夜間人口比率の推移

<Dropdown 
  data={dn_pref_list}
  name=dnpref
  value=pref_name
  defaultValue="東京都"
  title="都道府県"
/>

```sql dn_pref_list
  select distinct pref_name, pref_code
  from census_daynight_prefecture.daynight
  order by pref_code
```

```sql dn_pref_trend
  select year,
    round(
      max(case when daynight_code = '1' then population end) * 100.0
      / max(case when daynight_code = '0' then population end)
    , 1) as ratio
  from census_daynight_prefecture.daynight
  where pref_name = '${inputs.dnpref.value}'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={dn_pref_trend}
  x=year y=ratio
  title="{inputs.dnpref.value} の昼夜間人口比率の推移"
  yFmt="0.0"
  xType=category >
  <ReferenceLine
    y=100
    label="昼夜均衡"
    labelPosition=aboveEnd color=negative
  />
</LineChart>

---

## サンプル市ドリルダウン：千葉県印西市

市区町村粒度でしか描けないミクロの一例。  
印西市は **昼間人口が夜間人口を下回る** 典型的なベッドタウン。  
ただし **昼夜間人口比率は2000年の81.3から2020年の90.6へ上昇** し、街に昼間の働き口が増えて職住近接が進んでいることがうかがえる。

```sql inzai_dn
  select year, daynight, population
  from census_daynight_city.daynight
  order by year, daynight_code
```

<LineChart
  data={inzai_dn}
  x=year
  y=population
  series=daynight
  title="印西市 昼間／夜間人口"
  yFmt="#,##0"
  xType=category
/>

```sql inzai_dn_ratio
  select year,
    round(max(case when daynight_code = '1' then population end) * 100.0
      / max(case when daynight_code = '0' then population end), 1) as ratio
  from census_daynight_city.daynight
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={inzai_dn_ratio}
  x=year
  y=ratio
  title="印西市 昼夜間人口比率"
  yFmt="0.0"
  yMin=75
  yMax=105
  xType=category >
  <ReferenceLine
    y=100
    label="昼夜均衡"
    labelPosition=aboveEnd
    color=negative
  />
</LineChart>

---

<small>出典：政府統計の総合窓口（e-Stat）の国勢調査を加工して作成。データセット別の詳細な出典は <a href="/sources">出典・ライセンス</a> を参照。</small>
