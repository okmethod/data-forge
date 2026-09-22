select
  title,
  provider,
  source,
  dataset_id,
  citation
from read_json('../../data/processed/census_family_type_municipality_timeseries.meta.json')
