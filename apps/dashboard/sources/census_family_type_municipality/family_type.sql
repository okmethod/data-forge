-- サンプル市（千葉県印西市）の世帯の家族類型（16区分）別 一般世帯数（市区町村ミクロ・合併畳み込み済み）。公開範囲＝サンプル市のみ（area_code IN）。
-- ★Evidence はソース結果 parquet を公開ビルドへ丸ごと同梱するため、ここで印西だけに絞る（追加市はコードを足すだけ）。
-- family_type_code は 100=総数 / 110=親族のみ / 120=核家族 …（4階層ツリー）… 290=単独 / 999=不詳。単独世帯割合は 290/100 で配布側（ページ）が算出する。
-- ★市区町村ミクロは 2005〜2020（新分類の遡及集計が 2005 始まり。1995/2000 は旧分類しか無く非互換ゆえ不採用）。
-- ★世帯人員(household_members)は 2005/2010 のみ収録＝年範囲が非対称（他年は null）。ページでは世帯数（単独世帯割合）のみ使う。列は将来用・出典完全性のため残置。
select
  area_code,
  area_name,
  family_type_code,
  family_type,
  family_type_level,
  year,
  households,
  household_members
from read_parquet('../../data/processed/census_family_type_municipality_timeseries.parquet')
where area_code in (
  '12231'   -- 千葉県 印西市（2010 に印旛村・本埜村を編入）
)
