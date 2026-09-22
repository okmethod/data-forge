---
title: 家族類型
sidebar_position: 6
---

データセット: **世帯の家族類型（16区分）別 一般世帯数・世帯人員** - 都道府県は1995〜2020年（6回）、市区町村は2005〜2020年（合併畳み込み済み）

[世帯](/households)ページが**世帯の大きさ**（平均世帯人員）を見たのに対し、このページでは**世帯の中身＝家族構成**を、全国 → 都道府県 → 市区町村のスケールで見ていく。  
見せ方は2つ——**1地域の経年変化は全類型の構成比（%）**で単身化や夫婦世帯と子育て世帯を読み、**多数地域の横断比較は単独世帯割合（＝単独世帯 ÷ 総世帯・単身化の代表指標）**で見る。

---

## 全国：家族類型の構成比の変化（%）

単独世帯だけでなく全類型の割合を並べると、四半世紀の**世帯構造の変化**がまとめて読める。
かつて最大だった**夫婦と子供の世帯が 34.2%（1995）→ 25.0%（2020）**へ縮み、**単独世帯が 25.6% → 38.0%**へ最大区分に躍り出た。
三世代同居を含む**その他の親族世帯も 15.4% → 6.8%**へ半減し、**夫婦のみ・ひとり親と子供**は微増。世帯の小型化が全類型の割合として現れている。

```sql ft_composition_national
  with base as (
    select year, family_type_code, households
    from census_family_type.family_type
    where area_code = '00000'
  ),
  tot as (
    select year, households as total from base where family_type_code = '100'
  ),
  cat as (
    select
      year,
      case family_type_code
        when '290' then '単独世帯'
        when '130' then '夫婦のみ'
        when '140' then '夫婦と子供'
        when '150' then 'ひとり親と子供'
        when '160' then 'ひとり親と子供'
        when '170' then 'その他の親族世帯'
        when '280' then '非親族を含む世帯'
        when '999' then '不詳'
      end as category,
      households
    from base
    where family_type_code in ('290', '130', '140', '150', '160', '170', '280', '999')
  )
  select c.year, c.category, round(sum(c.households) * 100.0 / t.total, 1) as pct
  from cat c
  join tot t using (year)
  group by c.year, c.category, t.total
  order by c.year, c.category
```

<!-- prettier-ignore -->
<BarChart
  data={ft_composition_national}
  x=year
  y=pct
  series=category
  title="全国 家族類型の構成比（%・100%積み上げ）"
  yFmt="0.0"
  xType=category
  type=stacked
  sort=false
  seriesOrder={['夫婦と子供','夫婦のみ','ひとり親と子供','その他の親族世帯','単独世帯','非親族を含む世帯','不詳']}
  seriesColors={{'夫婦と子供':'#4e79a7','夫婦のみ':'#59a14f','ひとり親と子供':'#edc948','その他の親族世帯':'#b07aa1','単独世帯':'#f28e2b','非親族を含む世帯':'#76b7b2','不詳':'#bab0ac'}}
/>

_※ 7 区分は総数（100）に一致する相互排他の分割（核家族＝夫婦のみ＋夫婦と子供＋ひとり親と子供／その他の親族世帯＝三世代等）。各年の合計が 100% になるよう構成比で示す。_

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

## 都道府県ドリルダウン：都道府県別 家族類型の構成比の推移

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

```sql ft_pref_composition
  with tot as (
    select year, households as total
    from census_family_type.family_type
    where area_name = '${inputs.pref.value}' and family_type_code = '100'
  ),
  cat as (
    select
      year,
      case family_type_code
        when '290' then '単独世帯'
        when '130' then '夫婦のみ'
        when '140' then '夫婦と子供'
        when '150' then 'ひとり親と子供'
        when '160' then 'ひとり親と子供'
        when '170' then 'その他の親族世帯'
        when '280' then '非親族を含む世帯'
        when '999' then '不詳'
      end as category,
      households
    from census_family_type.family_type
    where area_name = '${inputs.pref.value}'
      and family_type_code in ('290', '130', '140', '150', '160', '170', '280', '999')
  )
  select c.year, c.category, round(sum(c.households) * 100.0 / t.total, 1) as pct
  from cat c
  join tot t using (year)
  group by c.year, c.category, t.total
  order by c.year, c.category
```

<!-- prettier-ignore -->
<BarChart
  data={ft_pref_composition}
  x=year
  y=pct
  series=category
  title="{inputs.pref.value} 家族類型の構成比（%・100%積み上げ）"
  yFmt="0.0"
  xType=category
  type=stacked
  sort=false
  seriesOrder={['夫婦と子供','夫婦のみ','ひとり親と子供','その他の親族世帯','単独世帯','非親族を含む世帯','不詳']}
  seriesColors={{'夫婦と子供':'#4e79a7','夫婦のみ':'#59a14f','ひとり親と子供':'#edc948','その他の親族世帯':'#b07aa1','単独世帯':'#f28e2b','非親族を含む世帯':'#76b7b2','不詳':'#bab0ac'}}
/>

---

## 市区町村ミクロ：印西市は「夫婦と子供」が主体の子育て世帯の街

市区町村粒度でしか描けないミクロの一例。
全類型の構成比で見ると、**千葉県印西市**は**夫婦と子供の世帯が 2020 年でも 39.8%**（全国 25.0%）と突出して高く、子育て世帯の街であることが数字に表れる。
一方で **単独世帯は 15.5%（2005）→ 20.1%（2020）**、**夫婦のみは 17.1% → 25.0%** と上昇し、三世代等の**その他の親族世帯は 14.5% → 6.4%** へ半減——初期入居世代の高齢化に沿って街の中でも小型化が進む。
ただしこれは**シェア（割合）**の話で、実数では夫婦と子供も含めほぼ全類型が増えている（減ったのは三世代等のみ）。
割合と実数で逆転するこの読みは [印西市ケーススタディ](/inzai) を参照。

```sql ft_inzai_composition
  with tot as (
    select year, households as total
    from census_family_type_municipality.family_type
    where family_type_code = '100'
  ),
  cat as (
    select
      year,
      case family_type_code
        when '290' then '単独世帯'
        when '130' then '夫婦のみ'
        when '140' then '夫婦と子供'
        when '150' then 'ひとり親と子供'
        when '160' then 'ひとり親と子供'
        when '170' then 'その他の親族世帯'
        when '280' then '非親族を含む世帯'
        when '999' then '不詳'
      end as category,
      households
    from census_family_type_municipality.family_type
    where family_type_code in ('290', '130', '140', '150', '160', '170', '280', '999')
  )
  select c.year, c.category, round(sum(c.households) * 100.0 / t.total, 1) as pct
  from cat c
  join tot t using (year)
  group by c.year, c.category, t.total
  order by c.year, c.category
```

<!-- prettier-ignore -->
<BarChart
  data={ft_inzai_composition}
  x=year
  y=pct
  series=category
  title="印西市 家族類型の構成比（%・100%積み上げ・合併畳み込み済み）"
  yFmt="0.0"
  xType=category
  type=stacked
  sort=false
  seriesOrder={['夫婦と子供','夫婦のみ','ひとり親と子供','その他の親族世帯','単独世帯','非親族を含む世帯','不詳']}
  seriesColors={{'夫婦と子供':'#4e79a7','夫婦のみ':'#59a14f','ひとり親と子供':'#edc948','その他の親族世帯':'#b07aa1','単独世帯':'#f28e2b','非親族を含む世帯':'#76b7b2','不詳':'#bab0ac'}}
/>

_※ 市区町村ミクロは 2005〜2020 年（新分類の遡及集計が 2005 始まり）。人口・世帯の増加とあわせた横断は [印西市ケーススタディ](/inzai) を参照。_

---

_出典：政府統計の総合窓口（e-Stat）の国勢調査を加工して作成。データセット別の詳細な出典は [出典・ライセンス](/sources) を参照。_
