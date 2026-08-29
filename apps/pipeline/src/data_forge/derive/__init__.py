"""派生層（基底データセットを時系列へ合成する段）。

2つの処理フローを持つ:

- 縫合（StitchedDataset）
    各回帳票（年ごと別 ID）を year 軸で結合し時系列化。
    速報 splice まではこの段が持つ（area 非依存）。
    合併畳込（aggregate_to_base）・空間集約（prefecture/region）は area/（参照層）の
    責務で、orchestrate が縫合の後に別ステップとして配線する（この段には埋め込まない）。
- 射影（ProjectedDataset）
    e-Stat 既製の時系列帳票（1 ID が全年）を area 軸で union するだけ。
    年の縫合も area master も持たない。

構成:
    combine.py    … 純粋な DataFrame 変換（combine_years / union_areas）
    orchestrate.py … fetch→clean→合成の配線・area 集約の呼び出し（load / build_atoms）

外部（cli 等）はこの `__init__` の再エクスポートだけを使い、内部ファイルには触れない。
"""

from data_forge.derive.combine import combine_years, union_areas
from data_forge.derive.orchestrate import JOIN_CHOICES, build_atoms, load

__all__ = ["JOIN_CHOICES", "build_atoms", "combine_years", "load", "union_areas"]
