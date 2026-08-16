---
title: 人口ピラミッド
sidebar_position: 2
---

データセット: **年齢5歳階級（0〜4／…／85歳以上）×男女別人口** - 1920〜2020年（21回）・全国＋都道府県。

このページでは、**一世紀分の5歳階級の年齢構造**を、を全国 → 都道府県のスケールで見ていく。  
（市区町村粒度は持たないため、印西市を軸にした横断は扱わない）

---

## 全国：年齢構造の推移（1920〜2020）

各5歳階級を積み上げると、総人口の拡大（**5,596 万 → 1億2,615 万**）と、色の重心が下（若年）から上（高齢）へ移っていく**構造シフト**が同時に読める。3区分の面グラフ（[高齢化率](/aging) ページ）をより細かい18階級に分解したものにあたる。

```sql area_national
  select
    year,
    age_class,
    sum(population) as population
  from census_age5.by_age5
  where area_code = '00000' and sex_code = '0'
    and age_class_code not in ('100','999')
  group by year, age_class_code, age_class
  order by year, age_class_code
```

<!-- prettier-ignore -->
<AreaChart
  data={area_national}
  x=year
  y=population
  series=age_class
  title="全国 年齢5歳階級別人口（1920〜2020）"
  sort=false
  colorPalette={['#e8f1fb','#d4e5f6','#c0d9f0','#abccea','#97c0e4','#83b3de','#6fa7d8','#5b9ad2','#478ecc','#3a82c1','#3376ad','#2d6a99','#275e85','#215272','#1b465e','#15394a','#0f2d36','#092138']}
  yFmt="#,##0"
  xType=category
/>

_※ 各図は年齢不詳を除いた5歳階級のみを描く（不詳は「総数−合計」で導出し別途保持）。若年→高齢を薄→濃で配色。1945年は簡易な人口調査（沖縄県を含まない等）のため前後の年と厳密には連続しない。_

---

## 全国：年を選べるピラミッド

同じデータを**断面**で見る。年を切り替えると、**1920年の富士山型 → 2020年の壺型**という一世紀の転換が形として分かる（縦軸は ±500万人で固定＝総人口の拡大も同時に読める）。

<Dropdown
  data={year_list}
  name=year
  value=year
  defaultValue="2020"
  title="年"
/>

```sql year_list
  select distinct cast(cast(year as integer) as varchar) as year
  from census_age5.by_age5
  order by year desc
```

```sql pyramid_national
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5.by_age5
  where area_code = '00000' and sex_code in ('1','2')
    and age_class_code not in ('100','999') and year = ${inputs.year.value}
  order by age_class_code desc
```

<!-- prettier-ignore -->
<BarChart
  data={pyramid_national}
  x=age_class
  y=pop
  series=sex
  title="全国 年齢5歳階級×男女（{inputs.year.value}年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
  yMin=-5000000
  yMax=5000000
/>

_※ 最上段の「85歳以上」は都道府県表に合わせた終端（全国表の85〜89…110歳以上を集約）。_

---

## 都道府県：県を選んで推移とピラミッドを見る

粒度を都道府県まで下げる。県を選ぶと**構造の推移（面）**と、年を選んだ**断面（ピラミッド）**を同じ県で並べて確認できる。県別の縦軸は自動（県の規模に追随）。

<Dropdown
  data={pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql pref_list
  select distinct area_name, area_code
  from census_age5.by_age5
  where area_code != '00000'
  order by area_code
```

```sql pref_area
  select
    year,
    age_class,
    sum(population) as population
  from census_age5.by_age5
  where area_name = '${inputs.pref.value}' and sex_code = '0'
    and age_class_code not in ('100','999')
  group by year, age_class_code, age_class
  order by year, age_class_code
```

<!-- prettier-ignore -->
<AreaChart
  data={pref_area}
  x=year
  y=population
  series=age_class
  title="{inputs.pref.value} 年齢5歳階級別人口（1920〜2020）"
  sort=false
  colorPalette={['#e8f1fb','#d4e5f6','#c0d9f0','#abccea','#97c0e4','#83b3de','#6fa7d8','#5b9ad2','#478ecc','#3a82c1','#3376ad','#2d6a99','#275e85','#215272','#1b465e','#15394a','#0f2d36','#092138']}
  yFmt="#,##0"
  xType=category
/>

<Dropdown
  data={year_list}
  name=pref_year
  value=year
  defaultValue="2020"
  title="年"
/>

```sql pyramid_pref
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5.by_age5
  where area_name = '${inputs.pref.value}' and sex_code in ('1','2')
    and age_class_code not in ('100','999') and year = ${inputs.pref_year.value}
  order by age_class_code desc
```

<!-- prettier-ignore -->
<BarChart
  data={pyramid_pref}
  x=age_class
  y=pop
  series=sex
  title="{inputs.pref.value} 年齢5歳階級×男女（{inputs.pref_year.value}年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
/>
