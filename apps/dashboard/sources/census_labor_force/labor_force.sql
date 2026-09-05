-- 労働力状態(3区分)，男女別人口（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する。
-- labor_status_code は 100=総数 / 110=労働力人口 / 120=就業者(110再掲) / 130=完全失業者(110再掲) / 140=非労働力人口 / 999=労働力状態不詳。
-- 労働力率（110/(110+140)）・完全失業率（130/110）は配布側（このページ）が算出する。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  area_level,
  sex_code,
  sex,
  labor_status_code,
  labor_status,
  year,
  population
from (
  select * from read_parquet('../../data/processed/census_labor_force_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_labor_force_prefecture_timeseries.parquet')
)
