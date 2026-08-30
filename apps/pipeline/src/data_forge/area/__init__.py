"""地域参照層（area・アトム軸スタースキーマ）。

データセット非依存の地域マスタ。コード軸は JIS（全国地方公共団体コード）。
fact = 各年の標準的な市区町村（アトム, atoms.py）／dim 相当 = 合併イベントによる
rollup（mapping.py）。集約は aggregate.py、人口保存と孤児検出は reconcile.py。
アトム抽出は各ソースの area 表現に依存する点に注意（現状は e-Stat 前提）。
設計は docs/distributions/area_master.md を参照。
"""
