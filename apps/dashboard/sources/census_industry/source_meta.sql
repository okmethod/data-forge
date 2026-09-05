-- 出典メタ（citation 等）を Evidence に公開する。全国＋都道府県の2 meta.json を結合し1行に集約。
-- 単一 e-Stat ID の帳票は全国/県で meta が同一になるため重複排除する（2 ID の帳票は両方を列挙）。
-- 出典ページ（pages/sources.md）でデータ駆動に描画する（citation は手書きしない・" / " 区切りで全文列挙）。
with m as (
  select title, provider, source, dataset_id, citation, 1 as ord
  from read_json('../../data/processed/census_industry_national_timeseries.meta.json')
  union all
  select title, provider, source, dataset_id, citation, 2 as ord
  from read_json('../../data/processed/census_industry_prefecture_timeseries.meta.json')
),
d as (
  select title, provider, source, dataset_id, citation, min(ord) as ord
  from m
  group by title, provider, source, dataset_id, citation
)
select
  string_agg(title, ' / ' order by ord)      as title,
  any_value(provider)                         as provider,
  any_value(source)                           as source,
  string_agg(dataset_id, ', ' order by ord)  as dataset_id,
  string_agg(citation, ' / ' order by ord)   as citation
from d
