-- 産業(大分類)×男女別就業者数（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する。
-- industry_code は 100=総数 / 120〜330=産業大分類20区分（330=分類不能の産業＝実カテゴリ）。
-- 産業構成比（各産業/総数）は配布側（このページ）が算出する。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  area_level,
  sex_code,
  sex,
  industry_code,
  industry,
  year,
  workers
from (
  select * from read_parquet('../../data/processed/census_industry_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_industry_prefecture_timeseries.parquet')
)
