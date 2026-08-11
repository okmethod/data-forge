-- サンプル市区町村（デモに使う数件のみ）。
-- ★Evidence はソースの結果 parquet を公開ビルドに丸ごと同梱する（ページのクエリ内容と無関係）。
--   生の市区町村パススルーを置くと build/data/.../population.parquet に 20,880 行がそのまま載る。
--   → 公開範囲を絞るため、ここでは対象の数件だけを材料化する。
--   追加したい市はコードを足すだけ。
-- data_status で確定(confirmed 1980-2020)と速報(preliminary 2025)を区別する。
-- ページ側は人口の図には2025速報も表示し「※速報」を明示する。
select
  area_code,
  area_name,
  area_level,
  sex_code,
  sex,
  year,
  population,
  data_status
from population
where area_code in (
  '12231'   -- 千葉県 印西市（2010 に印旛村・本埜村を編入）
)
