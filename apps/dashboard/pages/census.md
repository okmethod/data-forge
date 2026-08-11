---
title: 人口
sidebar_position: 1
---

データセット: **合併畳み込み済みの市区町村別 男女別人口** - 1980〜2020年・全9回分

このページは **全国 → 都道府県の偏在 → ドリルダウン → サンプル市** の順に同じデータを見ていく。  
（印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

---

## 全国：総人口の推移

全国総人口は **2010年の約1億2,806万人をピークに減少局面** へ入った。

```sql national
  select year, sum(population) as population
  from census_prefecture.population
  where sex = '総数'
  group by year
  order by year
```

<LineChart data={national} x=year y=population title="全国総人口" yFmt="#,##0" yMin=110000000 yMax=130000000 xType=category />

---

## 都道府県の偏在：人口増減ランキング

全国では2010年以降減少に転じたが、長期では **増えた地域と減った地域に大きく分かれる**。  
傾向としては東京圏（埼玉・神奈川・千葉）と沖縄が増え、その他地方が減っている。

**起点年・終点年を切り替えて**、期間ごとに分岐がどう変わるかを確認できる。

<!-- 単一選択 Dropdown は先頭オプションが既定になる（defaultValue/ default 属性は非先頭では効かない）。
     そのため既定にしたい年を先頭に置く: 起点=1980 昇順 / 終点=2020 降順。 -->
<Dropdown name=from_year title="起点年">
  <DropdownOption value=1980/>
  <DropdownOption value=1985/>
  <DropdownOption value=1990/>
  <DropdownOption value=1995/>
  <DropdownOption value=2000/>
  <DropdownOption value=2005/>
  <DropdownOption value=2010/>
  <DropdownOption value=2015/>
  <DropdownOption value=2020/>
</Dropdown>
<Dropdown name=to_year title="終点年">
  <DropdownOption value=2020/>
  <DropdownOption value=2015/>
  <DropdownOption value=2010/>
  <DropdownOption value=2005/>
  <DropdownOption value=2000/>
  <DropdownOption value=1995/>
  <DropdownOption value=1990/>
  <DropdownOption value=1985/>
  <DropdownOption value=1980/>
</Dropdown>

```sql pref_change
  with p as (
    select pref_name, year, population
    from census_prefecture.population
    where sex = '総数'
  ),
  chg as (
    select
      a.pref_name,
      round((b.population * 1.0 / a.population - 1) * 100, 1) as change_pct
    from p a
    join p b on a.pref_name = b.pref_name
      and a.year = ${inputs.from_year.value}
      and b.year = ${inputs.to_year.value}
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
title="都道府県別 人口増減率（％）{inputs.from_year.value}→{inputs.to_year.value}"
x=pref_name
y=change_pct
series=trend
swapXY=true
sort=false
yFmt="+0.0;-0.0"
seriesColors={{'減少':'#dc2626', '増加':'#2563eb'}}
seriesOrder={['減少', '増加']}
/>

---

## ドリルダウン：都道府県別 総人口の推移

<Dropdown data={pref_list} name=pref value=pref_name defaultValue="千葉県" title="都道府県" />

```sql pref_list
  select distinct pref_name, pref_code
  from census_prefecture.population
  order by pref_code
```

```sql pref_trend
  select year, population
  from census_prefecture.population
  where sex = '総数' and pref_name = '${inputs.pref.value}'
  order by year
```

<LineChart data={pref_trend} x=year y=population title="{inputs.pref.value} の総人口推移" yFmt="#,##0" xType=category />

---

## サンプル市：千葉県印西市（合併畳み込みの考慮）

市区町村粒度でしか描けないミクロの一例。  
印西市は**1996年に市制施行**され、**2010年に印旛村・本埜村を編入**した。

同じ印西市を「合併畳み込み無し（生の e-Stat）」と「合併畳み込み済み」で **1枚に重ねる** と差が一目で分かる。

- **① 合併畳み込み無し（生 e-Stat）**：市区町村コード 12231 をそのまま並べると、市制前の **1995年以前は存在せず**、2010年の編入で **+47%の不連続なジャンプ**（60,060→88,176）が生じる。
- **② 合併畳み込み済み**：旧境界をまたいで連続した1本の線として、1980年の約3万人から2020年の約10万人まで追える。2010年以降は両者が一致する。

```sql inzai_fold
  -- 畳み込み済み(②)の年を背骨に、①(生)は left join。1995以前は null=非描画。
  -- 両系列を同じ 1980..2020 に揃えることで、seriesOrder で凡例順を変えても xType=category の軸順が崩れない。
  -- （x範囲が違う系列を seriesOrder で先頭にすると、その系列の年範囲が先に軸化されてしまうため）
  with folded as (
    select year, population
    from census_city.population
    where area_name = '印西市' and sex = '総数'
  ),
  raw as (
    select year, population
    from census_city_raw.population
    where sex = '総数'
  )
  select '① 畳み込み無し' as series, f.year, r.population
  from folded f left join raw r on f.year = r.year
  union all
  select '② 畳み込み済み' as series, f.year, f.population
  from folded f
  order by year
```

<LineChart
data={inzai_fold}
x=year
y=population
series=series
title="印西市 総人口：合併畳み込み 無し／有り"
yFmt="#,##0"
yMin=20000
yMax=120000
xType=category
seriesColors={{'① 畳み込み無し': '#dc2626', '② 畳み込み済み': '#2563eb'}}
seriesOrder={['① 畳み込み無し', '② 畳み込み済み']}
/>
