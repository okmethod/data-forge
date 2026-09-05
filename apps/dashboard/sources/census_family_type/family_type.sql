-- 世帯の家族類型（16区分）別 一般世帯数・世帯人員（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する。
-- family_type_code は 100=総数 / 110=親族のみ / 120=核家族 …（4階層ツリー）… 290=単独 / 999=不詳。
-- family_type_level（1〜4）でツリー粒度を選ぶ。単独世帯割合は 290/100 で配布側（ページ）が算出する。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  area_level,
  family_type_code,
  family_type,
  family_type_level,
  year,
  households,
  household_members
from (
  select * from read_parquet('../../data/processed/census_family_type_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_family_type_prefecture_timeseries.parquet')
)
