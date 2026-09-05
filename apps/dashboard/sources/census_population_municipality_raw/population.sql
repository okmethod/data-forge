-- サンプル市（千葉県印西市）の「畳み込み無し（生）」人口。合併畳み込み有り/無しの比較用。
-- 参照先 census_population_municipality_timeseries_raw.parquet は population_municipality_timeseries を
-- --join なし（union=生）で出力したもの＝各年が当時の境界のまま。印西市(12231)は市制(1996)後の2000年
-- 以降のみ存在し、2010年の印旛村・本埜村編入で不連続にジャンプする（生では連続時系列を作れない）。
-- 公開範囲＝サンプル市のみ（area_code IN）。
select
  area_code,
  area_name,
  sex_code,
  sex,
  year,
  population
from read_parquet('../../data/processed/census_population_municipality_timeseries_raw.parquet')
where area_code in (
  '12231'   -- 千葉県 印西市
)
