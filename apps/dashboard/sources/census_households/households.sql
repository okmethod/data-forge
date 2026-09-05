-- 世帯の種類別 世帯数・世帯人員（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する。
-- household_type_code は 100=総数 / 110=一般世帯 / 120=施設等の世帯。
-- 平均世帯人員は household_members / households で配布側（このページ）が算出する。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  area_level,
  household_type_code,
  household_type,
  year,
  households,
  household_members
from (
  select * from read_parquet('../../data/processed/census_households_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_households_prefecture_timeseries.parquet')
)
