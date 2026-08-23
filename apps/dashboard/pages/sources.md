---
title: 出典・ライセンス
sidebar_position: 100
---

本ダッシュボードのデータは、すべて **政府統計の総合窓口（e-Stat）** で公開されている国勢調査を、
取得・クレンジング・精製したものである。下表の出典表記は各データセットに埋め込まれたメタ情報
（パイプラインが出力時に付与）をそのまま読み出しており、**手書きしていない**。

- 出典元：総務省統計局「国勢調査」（[e-Stat](https://www.e-stat.go.jp/)）
- 利用条件：本データの利用は [e-Stat 利用規約](https://www.e-stat.go.jp/terms-of-use)（政府標準利用規約 2.0 準拠・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja) 互換）に従う
- 加工：本プロジェクトが取得・クレンジング・集計・可視化を実施。**加工の責任は本プロジェクトにあり、加工内容について e-Stat／総務省が保証するものではない**
- 商用利用：可（e-Stat 利用規約により許諾）

## データセット別 出典表記

```sql all_sources
select '人口' as dataset, '都道府県' as grain, 1 as ord, m.* from census_prefecture.source_meta m
union all
select '人口', '市区町村（合併畳み込み済）', 2, m.* from census_city.source_meta m
union all
select '人口', '市区町村（合併畳み込み無し・比較用）', 3, m.* from census_city_raw.source_meta m
union all
select '年齢構成（3区分）', '都道府県', 10, m.* from census_age_prefecture.source_meta m
union all
select '年齢構成（3区分）', '市区町村', 11, m.* from census_age_city.source_meta m
union all
select '年齢構成（5歳階級）', '都道府県', 20, m.* from census_age5.source_meta m
union all
select '年齢構成（5歳階級）', '市区町村', 21, m.* from census_age5_city.source_meta m
union all
select '昼夜間人口', '都道府県', 30, m.* from census_daynight_prefecture.source_meta m
union all
select '昼夜間人口', '市区町村', 31, m.* from census_daynight_city.source_meta m
union all
select '世帯', '都道府県', 40, m.* from census_households.source_meta m
union all
select '家族類型', '都道府県', 50, m.* from census_family_type.source_meta m
union all
select '労働力', '都道府県', 60, m.* from census_labor_force.source_meta m
union all
select '産業', '都道府県', 70, m.* from census_industry.source_meta m
union all
select '職業（10区分）', '都道府県', 80, m.* from census_occupation_major10.source_meta m
union all
select '職業（12区分）', '都道府県', 81, m.* from census_occupation_major12.source_meta m
order by ord
```

{#each all_sources as s}

#### {s.dataset}（{s.grain}）

- 統計表：{s.title}
- 提供：{s.provider}（政府統計コード {s.dataset_id}）

<Details title="出典表記（全文）">
  <ol>
  {#each s.citation.split(" / ") as c}
    <li>- <small>{c}</small></li>
  {/each}
  </ol>
</Details>

{/each}
