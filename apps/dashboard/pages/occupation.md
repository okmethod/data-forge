---
title: 職業
sidebar_position: 9
---

データセット: **職業（大分類）別 就業者数**

職業大分類は 2009年12月の改訂で 10→12 区分に再編されたため、このページは改訂の前後を 2 つのグループに分けて併載する。

- **旧分類（10区分）**: 全国 1950〜2005年（12回分）／都道府県 1980〜2005年（6回）
- **現行分類（12区分）**: 全国 1995〜2020年（6回分）／都道府県 2005〜2020年（4回）

[産業](/industry) が「**どの産業で働いているか**」なら、職業は「**どんな仕事に就いているか**」の軸で、全国 → 都道府県のスケールで見ていく。  
主役は **職業別就業者数** と **職業構成比（＝各職業就業者数 ÷ 総数）**で、[人口ピラミッド](/age_5year) の高齢化と対にすると「**職業構成の転換（農林漁業 → 生産工程 → 事務・専門技術）**」が読める。  
（市区町村粒度は持たないため、印西市を軸にした横断は扱わない）

> ⚠ **旧分類（10区分）と現行分類（12区分）は、同じ符号でも指す職業が違う**（例：符号Ａは旧＝専門的・技術的／現行＝管理的）。  
> 2009年12月の改訂で「分類不能の職業」も含めコードを 1 対 1 で対応づけられないため、**両者は繋がず別々の系列として見る**。  
> 「分類不能の職業」も実カテゴリとして保持しており、総数＝Σ大分類が成立する。

まず**時系列で職業構成の 70 年**を追い（旧分類 → 現行分類の順）、そのうえで**最新 2020 年のスナップショット**（ランキング・地域差・県ドリルダウン）を見ていく。  
時系列 2 本は分類改訂で繋がらないため、別々の 2 枚に分ける。

---

## 長期：農林漁業から生産工程・労務へ（旧分類・1950→2005）

改訂前の旧分類（10区分）を使うと **1950 年まで職業構成の大転換を延伸**できる。  
**農林漁業は 1950 年の約 1,729 万人（総数の約半分）から 2005 年の 294 万人へ激減**し、入れ替わりに **生産工程・労務が 834 万人 → 1,742 万人へ倍増**した。
戦後の農業国から工業・サービス経済への移行が、職業構成にそのまま表れている。

```sql occ10_national_trend
  select
    year,
    max(case when occupation_code = '170' then workers end) as "農林漁業作業者",
    max(case when occupation_code = '190' then workers end) as "生産工程・労務",
    max(case when occupation_code = '130' then workers end) as "事務従事者",
    max(case when occupation_code = '140' then workers end) as "販売従事者"
  from census_occupation_major10.occupation
  where area_code = '00000' and sex_code = '0'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={occ10_national_trend}
  x=year
  y={['農林漁業作業者','生産工程・労務','事務従事者','販売従事者']}
  title="全国 主要職業の就業者数（旧分類・1950〜2005年）"
  yFmt="#,##0"
  xType=category
/>

_※ 旧分類は 1985〜1995 年で「県積み上げ＝全国」が大分類内訳で厳密一致しない（総数は一致）。
全国長期系列と県系列で分類境界が異なる原資料由来のため、上の全国系列を県の積み上げと突き合わせないこと。_

---

## 近年：事務・専門技術が二強へ（現行分類・1995→2020）

> ⚠ ここから下は**現行分類（12区分）**。  
> 上の旧分類とは符号の意味が異なり（Ａ＝管理的／Ｉ＝輸送・機械運転など）、**接続しない別系列**として読むこと（1995〜2005 は両分類が併存するが値も一致しない）。

工業からサービス・知識経済への移行が続く。  
**専門技術は 793 万人 → 1,028 万人へ増加**（サービス経済化・
医療福祉の担い手増）、一方 **生産工程は 1,114 万人 → 764 万人へ縮小**（製造業の縮小・自動化）。  
事務は横ばい（1,173→1,167 万人）だが、2020 年時点で **事務・専門技術が二強**となっている。

```sql occ12_national_trend
  select
    year,
    max(case when occupation_code = '130' then workers end) as "事務従事者",
    max(case when occupation_code = '120' then workers end) as "専門的・技術的",
    max(case when occupation_code = '180' then workers end) as "生産工程従事者",
    max(case when occupation_code = '150' then workers end) as "サービス職業"
  from census_occupation_major12.occupation
  where area_code = '00000' and sex_code = '0'
  group by year
  order by year
```

<!-- prettier-ignore -->
<LineChart
  data={occ12_national_trend}
  x=year
  y={['事務従事者','専門的・技術的','生産工程従事者','サービス職業']}
  title="全国 主要職業の就業者数（現行分類・1995〜2020年）"
  yFmt="#,##0"
  xType=category
/>

---

## 全国：職業別就業者数ランキング（現行分類・2020）

事務・専門技術・生産工程の 3 職業が上位。  
**事務と専門技術は男女差が小さい／逆転**する一方（事務は女性が男性の約 1.6 倍）、**生産工程は男性が女性の 2 倍超**で、職業ごとに男女構成が大きく異なる。

```sql occ12_national_ranking
  select occupation, workers
  from census_occupation_major12.occupation
  where area_code = '00000' and sex_code = '0' and year = 2020 and occupation_code != '100'
  order by workers desc
```

<BarChart
  data={occ12_national_ranking}
  x=occupation
  y=workers
  title="全国 職業別就業者数（総数・現行分類・2020年）"
  swapXY=true
  sort=false
  yFmt="#,##0"
/>

---

## 都道府県の偏在：職業別 就業者比率ランキング（現行分類・2020）

職業構成には地域差がある。  
職業を選ぶと、その職業に従事する就業者の比率（＝当該職業 ÷ 総数）で都道府県を並べ替える。  
**専門的・技術的職業**では **東京・神奈川**など大都市圏が上位に来る一方、**農林漁業**や**サービス職業**に切り替えると全く別の地域が上位となる。

<Dropdown
  data={occ12_list}
  name=occ
  value=occupation_code
  label=occupation
  defaultValue="120"
  title="職業"
/>

```sql occ12_list
  select distinct occupation_code, occupation
  from census_occupation_major12.occupation
  where occupation_code != '100'
  order by occupation_code
```

```sql occ12_pref_ranking
  select
    area_name,
    round(
      max(case when occupation_code = '${inputs.occ.value}' then workers end) * 100.0
      / max(case when occupation_code = '100' then workers end), 1) as pct
  from census_occupation_major12.occupation
  where area_code != '00000' and sex_code = '0' and year = 2020
  group by area_name
  order by pct desc
```

<BarChart
  data={occ12_pref_ranking}
  x=area_name
  y=pct
  title="都道府県別 {inputs.occ.label} 就業者比率（総数・現行分類・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
/>

---

## 都道府県ドリルダウン：都道府県別の職業構成（現行分類・2020）

<Dropdown
  data={occ12_pref_list}
  name=pref
  value=area_name
  defaultValue="千葉県"
  title="都道府県"
/>

```sql occ12_pref_list
  select distinct area_name, area_code
  from census_occupation_major12.occupation
  where area_code != '00000'
  order by area_code
```

```sql occ12_pref_composition
  select
    occupation,
    round(workers * 100.0 / (
      select workers from census_occupation_major12.occupation o2
      where o2.area_name = '${inputs.pref.value}'
        and o2.sex_code = '0' and o2.year = 2020 and o2.occupation_code = '100'
    ), 1) as share
  from census_occupation_major12.occupation
  where area_name = '${inputs.pref.value}'
    and sex_code = '0' and year = 2020 and occupation_code != '100'
  order by share desc
```

<BarChart
  data={occ12_pref_composition}
  x=occupation
  y=share
  title="{inputs.pref.value} 職業構成比（総数・現行分類・2020年）"
  swapXY=true
  sort=false
  yFmt="0.0"
/>

---

<small>出典：政府統計の総合窓口（e-Stat）の国勢調査を加工して作成。データセット別の詳細な出典は <a href="/sources">出典・ライセンス</a> を参照。</small>
