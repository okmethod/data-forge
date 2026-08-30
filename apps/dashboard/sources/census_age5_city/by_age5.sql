-- サンプル市（千葉県印西市）の年齢5歳階級×男女×国籍別人口。公開範囲＝サンプル市のみ（area_code IN）。
-- ★Evidence はソース結果 parquet を公開ビルドへ丸ごと同梱するため、ここで印西だけに絞る（追加市はコードを足すだけ）。
-- ★ミクロ系列は nationality（0=総数 / 1=日本人）2軸を持つ＝ページ側は必ず nationality_code で絞ること
--   （無指定だと総数×日本人が二重計上）。日本人スライスは 1990 年以降のみ収録＝年範囲が非対称。
-- age_class_code は e-Stat コードそのまま（100=総数 / 110〜310=5歳階級で 310=100歳以上 / 999=年齢不詳）で辞書順＝年齢昇順。
select
  area_code,
  area_name,
  sex_code,
  sex,
  nationality_code,
  nationality,
  age_class_code,
  age_class,
  year,
  population
from population_by_age5
where area_code in (
  '12231'   -- 千葉県 印西市（2010 に印旛村・本埜村を編入）
)
