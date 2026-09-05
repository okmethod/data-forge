-- 出典メタ（citation 等）を Evidence に公開する。
-- パイプラインが配布物に併記する <stem>.meta.json（output/export.py）を読み、
-- 出典ページ（pages/sources.md）でデータ駆動に描画する（citation は手書きしない）。
select
  title,
  provider,
  source,
  dataset_id,
  citation
from read_json('../../data/processed/census_population_prefecture_timeseries.meta.json')
