-- サンプル市（千葉県印西市）の年齢3区分×男女別人口。公開範囲＝サンプル市のみ（area_code IN）。
-- 都道府県集計 census_age3class_prefecture とは別に、印西市だけを市区町村粒度で材料化する
-- （ケーススタディの主役。追加したい市はコードを足すだけ）。
select
  area_code,
  area_name,
  sex_code,
  sex,
  age_class_code,
  age_class,
  year,
  population
from read_parquet('../../data/processed/census_age3class_municipality_timeseries.parquet')
where area_code in (
  '12231'   -- 千葉県 印西市
)
