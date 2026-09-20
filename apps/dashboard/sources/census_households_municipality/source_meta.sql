select
  title,
  provider,
  source,
  dataset_id,
  citation
from read_json('../../data/processed/census_households_municipality_timeseries.meta.json')
