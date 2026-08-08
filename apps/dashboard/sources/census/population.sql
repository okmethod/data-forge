-- 国勢調査 2020 人口（配布用テーブル）をそのまま取り込む。
-- is_current は SQLite 上では 0/1 の INTEGER。
select
  area_code,
  area_name,
  area_level,
  sex_code,
  sex,
  year,
  population,
  is_current
from population
