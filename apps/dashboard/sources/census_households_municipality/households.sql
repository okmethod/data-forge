-- サンプル市（千葉県印西市）の世帯の種類別 世帯数・世帯人員（市区町村ミクロ・合併畳み込み済み）。公開範囲＝サンプル市のみ（area_code IN）。
-- ★Evidence はソース結果 parquet を公開ビルドへ丸ごと同梱するため、ここで印西だけに絞る（追加市はコードを足すだけ）。
-- household_type_code は 100=総数 / 110=一般世帯 / 120=施設等の世帯。
-- ★世帯人員(household_members)は 2015/2020 のみ収録＝年範囲が非対称（他年は null）。市区町村では2点しか無く「人口÷世帯数」との差も僅少ゆえ
--   平均世帯人員チャートは出さない（ページは世帯数の推移＝細分化のみ使う）。列は将来用・出典完全性のため残置。
select
  area_code,
  area_name,
  household_type_code,
  household_type,
  year,
  households,
  household_members
from read_parquet('../../data/processed/census_households_municipality_timeseries.parquet')
where area_code in (
  '12231'   -- 千葉県 印西市（2010 に印旛村・本埜村を編入）
)
