-- 産業(大分類)×男女別就業者数（全国 area_code=00000 ＋47都道府県）。
-- 接続先 census_industry_timeseries.sqlite は既に全国＋県粒度なので素の射影＋pref_code 派生のみ。
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
from industry
