-- 職業(旧大分類・major10)×男女別就業者数（全国 area_code=00000 ＋47都道府県）。
-- 排他粒度のため全国と県は別 parquet。ここで union し「全国＋県」の1論理テーブルへ合成する。
-- occupation_code は 100=総数 / 110〜200=職業大分類10区分（200=分類不能の職業＝実カテゴリ）。
-- 職業構成比（各職業/総数）は配布側（このページ）が算出する。
-- ⚠ major12 とは occupation_code の意味が違う（同符号でも指す職業が別）ため join・比較不可。
--   さらに major10 は 1985-1995 で「県積み上げ＝全国」が大分類内訳で厳密一致しない（総数は一致）。
select
  area_code,
  area_name,
  substr(area_code, 1, 2) as pref_code,
  area_level,
  sex_code,
  sex,
  occupation_code,
  occupation,
  year,
  workers
from (
  select * from read_parquet('../../data/processed/census_occupation_major10_national_timeseries.parquet')
  union all
  select * from read_parquet('../../data/processed/census_occupation_major10_prefecture_timeseries.parquet')
)
