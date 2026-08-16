-- 職業(大分類・major12)×男女別就業者数（全国 area_code=00000 ＋47都道府県）。
-- 接続先 census_occupation_major12_timeseries.sqlite は既に全国＋県粒度なので素の射影＋pref_code 派生のみ。
-- occupation_code は 100=総数 / 110〜220=職業大分類12区分（220=分類不能の職業＝実カテゴリ）。
-- 職業構成比（各職業/総数）は配布側（このページ）が算出する。
-- ⚠ major10 とは occupation_code の意味が違う（同符号でも指す職業が別）ため join・比較不可。
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
from occupation_major12
