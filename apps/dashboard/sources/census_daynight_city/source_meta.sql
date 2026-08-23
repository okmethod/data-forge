-- 出典メタ（citation 等）を Evidence に公開する。
-- パイプラインが各 SQLite に埋め込む _source_meta（output/export.py）を1行へピボットし、
-- 出典ページ（pages/sources.md）でデータ駆動に描画する（citation は手書きしない）。
select
  max(case when key = 'title' then value end)        as title,
  max(case when key = 'provider' then value end)     as provider,
  max(case when key = 'source' then value end)        as source,
  max(case when key = 'dataset_id' then value end)   as dataset_id,
  max(case when key = 'citation' then value end)     as citation
from _source_meta
