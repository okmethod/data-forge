---
title: 印西市ケーススタディ
sidebar_position: 99
---

3つのデータセット（[人口](/population)・[年齢構成](/age_3class)・[昼夜間人口](/daynight)）を横断し、**人口増加を続ける街・千葉県印西市**を1つのケースに、人口・世代構成・昼夜間人口の3側面から日本の人口動態を読む。
（各データセット単体の全国→都道府県の見取り図は各ページを参照）

合併畳み込み済みの市区町村粒度（1980〜2020年・全9回分）だからこそ描ける分析のデモ。

---

## 1. 全国は横ばい、印西市は40年で3.4倍

全国人口は2010年の約1億2,806万人をピークに減少へ転じた。

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
  title="全国総人口"
  yFmt="#,##0"
  yMin=110000000
  yMax=130000000
  xType=category
/>

_※ 末尾の2025年は**速報値**（人口速報集計）。2020年までは確定値。_

同じ40年を **1980年=100 の指数** で並べると差は歴然。  
全国は +7.8%、千葉県は +32.7% にとどまるが、**印西市は 342.4（＝3.4倍）** に膨らんだ。  
印旛村・本埜村を編入した2010年の合併をまたいでも、畳み込み済みの市区町村時系列なら **旧境界を越えて連続比較** できる。  
（一方、生 e-Stat では年ごとに区分が変わるため、合併前後で不連続なジャンプが発生する）

```sql pop_index
  with series as (
    select '全国' as region, year, sum(population) as pop
    from census_prefecture.population where sex = '総数' group by year
    union all
    select '千葉県' as region, year, sum(population) as pop
    from census_prefecture.population where sex = '総数' and pref_name = '千葉県' group by year
    union all
    select '印西市' as region, year, population as pop
    from census_city.population where sex = '総数'
  )
  select s.region, s.year, round(s.pop * 100.0 / b.pop, 1) as idx
  from series s
  join (select region, pop from series where year = 1980) b on s.region = b.region
  order by s.region, s.year
```

<LineChart
  data={pop_index}
  x=year
  y=idx
  series=region
  title="人口指数（1980年=100）"
  yFmt="0.0"
  xType=category
/>

_※ 末尾の2025年は**速報値**。2020年までは確定値。_

---

## 2. 印西市の人口：3万人から10万人へ

印西市は **1980年の約3万人から2020年の約10万人** へ一貫して増加した。  
2010年の印旛村・本埜村編入も、合併畳み込みにより **連続した1本の線** として追える。

```sql inzai_pop
  select year, population
  from census_city.population
  where area_name = '印西市' and sex = '総数'
  order by year
```

<LineChart
  data={inzai_pop}
  x=year
  y=population
  title="印西市 総人口（合併畳み込み済み）"
  yFmt="#,##0"
  yMin=20000
  yMax=115000
  xType=category
/>

_※ 末尾の2025年は**速報値**（人口速報集計）。2020年までは確定値。_

---

## 3. 世代構成の変化：若い街も高齢化する

印西市の高齢化率は **農村 → 若返り → 再び高齢化** というU字を描く。  
1980年は 12.5%と全国（9.1%）を上回る農村だったが、千葉ニュータウンの宅地開発で若い世代が流入し **1995年の 10.7% を底に全国を下回る若い街**へ。
その後は全国と同様に再上昇し、2020年は 23.2%（全国 28.7%）。

```sql aging_compare
  select '印西市' as region, year,
    round(sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end), 1) as aging_pct
  from census_age_city.by_age where sex_code = '0' group by year
  union all
  select '全国' as region, year,
    round(sum(case when age_class_code = '3' then population end) * 100.0
      / sum(case when age_class_code in ('1','2','3') then population end), 1) as aging_pct
  from census_age_prefecture.by_age where sex_code = '0' group by year
  order by region, year
```

<LineChart
  data={aging_compare}
  x=year
  y=aging_pct
  series=region
  title="高齢化率（％）印西市 vs 全国"
  yFmt="0.0"
  yMin=0
  yMax=35
  xType=category
/>

年齢**5歳階級**×男女の人口ピラミッドを1980年と2020年で見比べると、**両年に共通する形**が浮かぶ——**子ども世代（0〜14歳）とその親世代（20〜40代）が厚く、その間の若者（10代後半〜20代）がへこむ**。1980年はうっすらと、2020年にははっきりと現れるこの形は、進学・就職で若者が転出し子育て期の家族が流入する、郊外の子育て世帯の街の断面だ（第4節のベッドタウン構造とも符合する）。  
40年の変化は、この“子・親のふたこぶと若者のくびれ”を保ったまま **規模が約3倍** に膨らんだことと、2020年には **初期入居世代が高齢化して60〜70代にもう一つのふくらみ** が加わったこと——高齢化そのものは全国と同じ方向だ。3区分では潰れてしまうこの凹凸が、5歳階級だからこそ形として読める。

```sql pyramid_1980
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5_city.by_age5
  where sex_code in ('1','2') and nationality_code = '0'
    and age_class_code not in ('100','999') and year = 1980
  order by age_class_code desc
```

```sql pyramid_2020
  select
    age_class,
    sex,
    case when sex_code = '1' then -population else population end as pop
  from census_age5_city.by_age5
  where sex_code in ('1','2') and nationality_code = '0'
    and age_class_code not in ('100','999') and year = 2020
  order by age_class_code desc
```

<Grid cols=2>

<!-- prettier-ignore -->
<BarChart
  data={pyramid_1980}
  x=age_class
  y=pop
  series=sex
  title="印西市 年齢5歳階級×男女人口（1980年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
  yMin=-4000
  yMax=4000
/>

<!-- prettier-ignore -->
<BarChart
  data={pyramid_2020}
  x=age_class
  y=pop
  series=sex
  title="印西市 年齢5歳階級×男女人口（2020年）"
  swapXY=true
  type=stacked
  sort=false
  seriesOrder={['男','女']}
  yMin=-4000
  yMax=4000
/>

</Grid>

_※ 国籍「総数」で描く。より細かい国籍別（総数／日本人）の対比は [人口ピラミッド](/age_5year) ページを参照。_

---

## 4. 昼夜間人口：東京圏のベッドタウン

印西市は **昼間人口が夜間人口を下回る**（＝昼間は人が流出する）典型的なベッドタウン。  
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

## 5. 全国の中の印西市

印西市が属する千葉県は、40年スパンで **人口が増えた側**（+32.7%）にある。  
全国では2010年以降減少に転じたが、長期では増えた地域と減った地域に大きく分かれ、**東京圏（埼玉・神奈川・千葉）と沖縄が伸び、東北・地方が大きく減る**。

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
    join p b on a.pref_name = b.pref_name and a.year = 1980 and b.year = 2020
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
  title="都道府県別 人口増減率（％・1980→2020）"
  swapXY=true
  sort=false
  colorPalette={['#2563eb', '#dc2626']}
  yFmt="+0.0;-0.0"
/>

より詳しい全国の傾向は [人口](/population)・[年齢構成と高齢化](/age_3class)・[昼夜間人口](/daynight) を参照。
