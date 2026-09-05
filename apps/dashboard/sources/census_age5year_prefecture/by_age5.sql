-- 年齢5歳階級×男女別人口（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する（全国はベースライン）。
-- age_class_code は e-Stat コードそのまま（100=総数 / 110〜310=5歳階級 / 999=年齢不詳）で
-- 辞書順＝年齢昇順。ピラミッドや高齢化率は 100・999 を除いた 5歳階級だけを使う。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  year,
  sex_code,
  sex,
  age_class_code,
  age_class,
  population
from (
  select * from read_parquet('../../data/processed/census_age5year_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_age5year_prefecture_timeseries.parquet')
)
