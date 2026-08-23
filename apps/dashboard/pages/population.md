---
title: 人口
sidebar_position: 1
---

データセット: **男女別人口** - 都道府県は長期系列（1920〜2020＋2025速報）、市区町村は合併畳み込み済み（1980〜2020＋2025速報）

このページは **全国 → 都道府県の偏在 → 都道府県ドリルダウン → サンプル市（印西市）ドリルダウン** の順に同じデータを見ていく。  
（人口を**年齢で切った**先の高齢化・年齢構造は [高齢化率](/age_3class) と [人口ピラミッド](/age_5year) を、印西市を軸にした横断的な読み解きは [印西市ケーススタディ](/inzai) を参照）

---

## 全国：総人口の推移

全国総人口は一世紀で **約5,600万人（1920年）→ 約1億2,806万人（2010年）へ倍増** し、その **2010年をピークに減少局面** へ入った（都道府県の長期系列を全県合計）。

```sql national
  select year, sum(population) as population
  from census_prefecture.population
  where sex = '総数'
  group by year
  order by year
```

<LineChart
  data={national}
  x=year
  y=population
  title="全国総人口（1920〜2025）"
  yFmt="#,##0"
  xFmt="####"
/>

_※ 末尾の2025年は**速報値**（人口速報集計）。2020年までは確定値。_

---

## 都道府県の偏在：人口増減ランキング（1920→2020）

1920→2020 の一世紀では **ほぼ全県が増加**（減少は島根県のみ）。
ただし伸び幅は大きく異なり、**神奈川・埼玉・千葉・東京の東京圏が数倍規模で突出**し、地方ほど伸びが小さい。  
一方、**起点を1980以降に切り替える**と様相が変わる。
全国が2010年以降の減少に向かう近年は **増える地域と減る地域に分岐**し、東京圏（埼玉・神奈川・千葉）と沖縄が増え、その他地方が減っている。

**起点年・終点年を切り替えて**、期間ごとに分岐がどう変わるかを確認できる。

<!--
都道府県は census_prefecture（長期系列）を参照するため 1920〜2020 まで遡れる（市区町村=1980〜 とは別系列）。
単一選択 Dropdown は先頭オプションが既定になる。defaultValue/ default 属性は非先頭では効かない。
そのため既定にしたい年を先頭に置く: 起点=1920 昇順 / 終点=2020 降順。
※1945 は沖縄が null（米軍統治下で未実施）。1945 が起点/終点だと沖縄は増減計算が null になり棒が出ない。
-->
<Dropdown name=from_year title="起点年">
  <DropdownOption value=1920/>
  <DropdownOption value=1925/>
  <DropdownOption value=1930/>
  <DropdownOption value=1935/>
  <DropdownOption value=1940/>
  <DropdownOption value=1945/>
  <DropdownOption value=1950/>
  <DropdownOption value=1955/>
  <DropdownOption value=1960/>
  <DropdownOption value=1965/>
  <DropdownOption value=1970/>
  <DropdownOption value=1975/>
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
  <DropdownOption value=1975/>
  <DropdownOption value=1970/>
  <DropdownOption value=1965/>
  <DropdownOption value=1960/>
  <DropdownOption value=1955/>
  <DropdownOption value=1950/>
  <DropdownOption value=1945/>
  <DropdownOption value=1940/>
  <DropdownOption value=1935/>
  <DropdownOption value=1930/>
  <DropdownOption value=1925/>
  <DropdownOption value=1920/>
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

<!-- prettier-ignore -->
<BarChart
  data={pref_change}
  x=pref_name
  y=change_pct
  series=trend
  title="都道府県別 人口増減率（％）{inputs.from_year.value}→{inputs.to_year.value}"
  swapXY=true
  sort=false
  seriesOrder={['減少', '増加']}
  seriesColors={{'減少':'#dc2626', '増加':'#2563eb'}}
  yFmt="+0.0;-0.0"
/>

---

## 都道府県ドリルダウン：都道府県別 総人口の推移

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

<LineChart
  data={pref_trend}
  x=year
  y=population
  title="{inputs.pref.value} の総人口推移（1920〜2025）"
  yFmt="#,##0"
  xFmt="####"
/>

_※ 末尾の2025年は**速報値**。2020年までは確定値。_

---

## サンプル市ドリルダウン：千葉県印西市（合併畳み込みの考慮）

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
    -- 合併畳み込みの方法論デモ（1980-2020）に集中。2025速報は総人口推移の各図で表示する。
    where area_name = '印西市' and sex = '総数' and data_status = 'confirmed'
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

<!-- prettier-ignore -->
<LineChart
  data={inzai_fold}
  x=year
  y=population
  series=series
  title="印西市 総人口：合併畳み込み 無し／有り"
  seriesOrder={['① 畳み込み無し', '② 畳み込み済み']}
  seriesColors={{'① 畳み込み無し': '#dc2626', '② 畳み込み済み': '#2563eb'}}
  yFmt="#,##0"
  yMin=20000
  yMax=120000
  xType=category
/>
