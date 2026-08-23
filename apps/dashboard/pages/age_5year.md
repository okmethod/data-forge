---
title: 年齢構成（5歳階級）
sidebar_position: 3
---

データセット: **年齢5歳階級×男女別人口** - 都道府県は 1920〜2020年（21回・85歳以上で終端）、市区町村（サンプル＝印西市）は 1980〜2020年（9回・100歳以上まで）

このページは **全国 → 都道府県ドリルダウン → サンプル市（印西市）ドリルダウン** の順に同じデータを見ていく。都道府県表は85歳以上で終端するが、市区町村（印西市）は **100歳以上まで**刻める。  
（3区分でみた高齢化率は [高齢化率](/age_3class) を、印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

---

## 全国：年齢構造の推移（1920〜2020）

各5歳階級を積み上げると、総人口の拡大（**5,596 万 → 1億2,615 万**）と、色の重心が下（若年）から上（高齢）へ移っていく**構造シフト**が同時に読める。3区分の面グラフ（[高齢化率](/age_3class) ページ）をより細かい18階級に分解したものにあたる。

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

_※ 男性を左向き（負の値）で描くため、ツールチップの男性は負符号で出る（例：「男 −x」＝男性x人）。値の大きさは絶対値で読む。_

_※ 最上段の「85歳以上」は都道府県表に合わせた終端（全国表の85〜89…110歳以上を集約）。_

---

## 都道府県ドリルダウン：県を選んで推移とピラミッドを見る

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

---

## サンプル市ドリルダウン：印西市（1980〜2020・100歳以上まで）

長期・広域の構造シフトを見たところで、粒度を **市区町村** まで下げ、近年（1980〜2020）を1つの市に絞って追う。  
市区町村のデータは都道府県表より細かく、**90〜94／95〜99／100歳以上**まで刻む。ここでは合併畳み込み済みの千葉ニュータウンの街・**印西市**を例にとる。

面グラフは各5歳階級を積み上げたもの。  
1980〜2020年で帯の総厚（＝総人口）が約3倍に伸び、とりわけ上位（高齢）の帯が近年ほど厚みを増していく——街の拡大と高齢化が同時に進んだことが読める。

```sql inzai_age5_area
  select
    year,
    age_class,
    sum(population) as population
  from census_age5_city.by_age5
  where sex_code = '0' and nationality_code = '0'
    and age_class_code not in ('100','999')
  group by year, age_class_code, age_class
  order by year, age_class_code
```

<!-- prettier-ignore -->
<AreaChart
  data={inzai_age5_area}
  x=year
  y=population
  series=age_class
  title="印西市 年齢5歳階級別人口（1980〜2020・総数）"
  sort=false
  colorPalette={['#e8f1fb','#d4e5f6','#c0d9f0','#abccea','#97c0e4','#83b3de','#6fa7d8','#5b9ad2','#478ecc','#3a82c1','#3376ad','#2d6a99','#275e85','#215272','#1b465e','#15394a','#0f2d36','#092138','#06192b','#04121f','#020b13']}
  yFmt="#,##0"
  xType=category
/>

_※ 国籍「総数」で描く（`nationality_code='0'`）。市区町村のデータは年齢不詳（999）を階級外に別途保持するため、ここでは 5歳階級のみを積み上げる。_

### 年を選べる断面：100歳以上まで刻む

同じデータを**断面**で見る。  
都道府県表は「85歳以上」で終端するが、市区町村のデータは **90〜94／95〜99／100歳以上**まで刻む。  
年を切り替えると、上の都道府県ピラミッド（85歳以上で終端）では潰れていた高齢層の内訳が、近年・細粒度まで下りて初めて開くのがわかる（たとえば2020年の100歳以上は27人＝女性26人・男性1人）。

<Dropdown
  data={inzai_year_list}
  name=inzai_year
  value=year
  defaultValue="2020"
  title="年"
/>

```sql inzai_year_list
  select distinct cast(cast(year as integer) as varchar) as year
  from census_age5_city.by_age5
  order by year desc
```

```sql inzai_pyramid_total
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5_city.by_age5
  where sex_code in ('1','2') and nationality_code = '0'
    and age_class_code not in ('100','999') and year = ${inputs.inzai_year.value}
  order by age_class_code desc
```

<!-- prettier-ignore -->
<BarChart
  data={inzai_pyramid_total}
  x=age_class
  y=pop
  series=sex
  title="印西市 年齢5歳階級×男女（{inputs.inzai_year.value}年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
/>

---

<small>出典：政府統計の総合窓口（e-Stat）の国勢調査を加工して作成。データセット別の詳細な出典は <a href="/sources">出典・ライセンス</a> を参照。</small>
