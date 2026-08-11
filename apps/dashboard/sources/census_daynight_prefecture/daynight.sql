-- 昼夜間人口（夜間＝常住地 / 昼間＝従業地・通学地）を都道府県粒度で（デモの公開粒度＝都道府県まで）。
-- ★県集約・県名マスタはパイプラインへ一元化済（spatial_rollup.aggregate_to_admin の _PREFECTURES）。
--   接続先 census_daynight_population_prefecture_timeseries.sqlite は既に県粒度なので、ここは素の射影のみ。
--   従来この SQL にベタ書きしていた 47 行 VALUES 県マスタ＋group by は撤廃した。
-- 全国値はページ側で pref を跨いで合計（全県の和＝全国。昼間=夜間＝国内通勤は相殺）。
select
  substr(area_code, 1, 2) as pref_code,
  area_name as pref_name,
  year,
  daynight_code,
  daynight,
  population
from daynight_population
