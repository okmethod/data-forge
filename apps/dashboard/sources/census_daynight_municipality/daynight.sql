-- サンプル市（千葉県印西市）の昼夜間人口。公開範囲＝サンプル市のみ（area_code IN）。
-- 都道府県の census_daynight_prefecture とは別に、印西市だけを市区町村粒度で材料化する。
select
  area_code,
  area_name,
  area_level,
  daynight_code,
  daynight,
  year,
  population
from read_parquet('../../data/processed/census_daynight_municipality_timeseries.parquet')
where area_code in (
  '12231'   -- 千葉県 印西市
)
