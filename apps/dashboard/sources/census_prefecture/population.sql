-- 都道府県別 人口時系列（デモの公開粒度＝都道府県まで）。
-- ★県集約・県名マスタはパイプラインへ一元化済（spatial_rollup.aggregate_to_admin の _PREFECTURES）。
--   接続先 census_population_prefecture_timeseries.sqlite は既に県粒度なので、ここは素の射影のみ。
--   従来この SQL にベタ書きしていた 47 行 VALUES 県マスタ＋group by は撤廃した。
-- area_code は県 JIS コード（"13000" 等）。従来互換のため先頭2桁を pref_code として提供する。
select
  substr(area_code, 1, 2) as pref_code,
  area_name as pref_name,
  year,
  sex_code,
  sex,
  population
from population
