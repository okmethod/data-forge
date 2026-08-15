"""出力層（精製済み DataFrame を配布成果物へ書き出す最終段）。

ソース非依存。`export_all` が Parquet / CSV / SQLite / DuckDB の4形式へ出力し、
全成果物に出典表記（citation）を同梱する（export.py 参照）。入力側は持たない
（将来 input が要れば別モジュールへ分離する）。
"""

from data_forge.output.export import export_all

__all__ = ["export_all"]
