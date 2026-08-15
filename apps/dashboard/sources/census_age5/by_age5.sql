-- 年齢5歳階級×男女別人口（全国 area_code=00000 ＋47都道府県）。
-- 接続先 census_population_by_age5_timeseries.sqlite は既に全国＋県粒度なので素の射影のみ。
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
from population_by_age5
