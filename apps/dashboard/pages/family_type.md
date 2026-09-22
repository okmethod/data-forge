---
title: 家族類型
sidebar_position: 6
---

データセット: **世帯の家族類型（16区分）別 一般世帯数・世帯人員** - 都道府県は1995〜2020年（6回）、市区町村は2005〜2020年（合併畳み込み済み）

[世帯](/households)ページが**世帯の大きさ**（平均世帯人員）を見たのに対し、このページでは**世帯の中身＝家族構成**を、全国 → 都道府県 → 市区町村のスケールで見ていく。  
主役は **単独世帯割合（＝単独世帯 ÷ 総世帯）**で、その上昇が**単身化**を表す。

---

## 全国：単独世帯割合の上昇（単身化）

一人暮らし（単独世帯）が全世帯に占める割合は、**1995 年の約 26% → 2020 年の約 38%** へと四半世紀で大きく伸びた。
核家族化のさらに先にある**単身化**の進行を示す。

```sql ft_tandoku_national
  select
    total.year,
    round(single.households * 100.0 / total.households, 1) as tandoku_pct
  from (
    select year, households from census_family_type.family_type
    where area_code = '00000' and family_type_code = '100'
  ) total
  join (
    select year, households from census_family_type.family_type
    where area_code = '00000' and family_type_code = '290'
  ) single using (year)
  order by total.year
```

<LineChart
  data={ft_tandoku_national}
  x=year
  y=tandoku_pct
  title="全国 単独世帯割合（単独世帯 ÷ 総世帯・%）"
  yFmt="0.0"
  yMin=0
  xType=category
/>

_※ 分母の総世帯（総数）には家族類型不詳を含む（総数ベース）。_

---

## 全国：家族類型の構成（親族のみ／単独／非親族／不詳）

世帯を家族構成の大区分で分けると、**親族のみの世帯**がほぼ横ばい（2010 年をピークに微減）にとどまる一方で、**単独世帯**が一貫して伸び続ける。

```sql ft_composition_national
  select
    year,
    family_type,
    households
  from census_family_type.family_type
  where area_code = '00000'
    and family_type_code in ('110', '290', '280', '999')
  order by year, family_type_code
```

<!-- prettier-ignore -->
<BarChart
  data={ft_composition_national}
  x=year
  y=households
  series=family_type
  title="全国 家族類型別 一般世帯数（大区分・積み上げ）"
  yFmt="#,##0"
  xType=category
  sort=false
  seriesColors={{'親族のみの世帯':'#4e79a7','単独世帯':'#f28e2b','非親族を含む世帯':'#76b7b2','家族類型不詳':'#bab0ac'}}
/>

_※ 大区分（親族のみ 110／非親族 280／単独 290／不詳 999）は総数（100）に一致する。核家族（120）等は「親族のみ」の内訳（再掲）のため積み上げには含めない。_

---

## 都道府県の偏在：単独世帯割合ランキング（2020）

同じ 2020 年でも、単身世帯の割合は県によって大きく異なる。  
進学・就業で若年単身が集まる**東京**が最も高く、三世代同居が残る地方は低い。

```sql ft_pref_ranking
  select
    total.area_name,
    round(single.households * 100.0 / total.households, 1) as tandoku_pct
  from (
    select area_name, households from census_family_type.family_type
    where area_code != '00000' and year = 2020 and family_type_code = '100'
  ) total
  join (
    select area_name, households from census_family_type.family_type
    where area_code != '00000' and year = 2020 and family_type_code = '290'
  ) single using (area_name)
  order by tandoku_pct desc
```

<BarChart
  data={ft_pref_ranking}
  x=area_name
  y=tandoku_pct
  title="都道府県別 単独世帯割合（2020年・%）"
  swapXY=true
  sort=false
  yFmt="0.0"
  yMin=20
/>

---

## 都道府県ドリルダウン：都道府県別 単独世帯割合の推移

<Dropdown
  data={ft_pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql ft_pref_list
  select distinct area_name, area_code
  from census_family_type.family_type
  where area_code != '00000'
  order by area_code
```

```sql ft_pref_trend
  select
    total.year,
    round(single.households * 100.0 / total.households, 1) as tandoku_pct
  from (
    select year, households from census_family_type.family_type
    where area_name = '${inputs.pref.value}' and family_type_code = '100'
  ) total
  join (
    select year, households from census_family_type.family_type
    where area_name = '${inputs.pref.value}' and family_type_code = '290'
  ) single using (year)
  order by total.year
```

<LineChart
  data={ft_pref_trend}
  x=year
  y=tandoku_pct
  title="{inputs.pref.value} 単独世帯割合（%）"
  yFmt="0.0"
  yMin=0
  xType=category
/>

---

## 市区町村ミクロ：印西市も単身化は進むが、全国より大幅に低い

市区町村粒度でしか描けないミクロの一例。
子育て世帯が流入し続ける**千葉県印西市**でも、単独世帯割合は **2005 年の 15.5% → 2020 年の 20.1%** へと上昇している。
ただし全国（2020 年 約38%）を大きく下回り、家族世帯（親族のみ）が主体の街であることが読める。

```sql ft_inzai_trend
  select
    total.year,
    round(single.households * 100.0 / total.households, 1) as tandoku_pct
  from (
    select year, households from census_family_type_municipality.family_type
    where family_type_code = '100'
  ) total
  join (
    select year, households from census_family_type_municipality.family_type
    where family_type_code = '290'
  ) single using (year)
  order by total.year
```

<LineChart
  data={ft_inzai_trend}
  x=year
  y=tandoku_pct
  title="印西市 単独世帯割合（単独世帯 ÷ 総世帯・%・合併畳み込み済み）"
  yFmt="0.0"
  yMin=0
  xType=category
/>

_※ 市区町村ミクロは 2005〜2020 年（新分類の遡及集計が 2005 始まり）。人口・世帯の増加とあわせた横断は [印西市ケーススタディ](/inzai) を参照。_

---

_出典：政府統計の総合窓口（e-Stat）の国勢調査を加工して作成。データセット別の詳細な出典は [出典・ライセンス](/sources) を参照。_
