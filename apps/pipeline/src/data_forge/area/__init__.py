"""地域参照層（area・アトム軸スタースキーマ）。

データセット非依存の地域マスタ。コード軸は JIS（全国地方公共団体コード）。
fact = 各年アトム（標準的な市区町村）を合併イベントで基準年へ前方 rollup し、
合併をまたぐ連続時系列を得る。
ソース非依存ではない（アトム抽出は e-Stat 前提）。

モジュール（各 docstring が実装の正典）:
    atoms          … アトム抽出（fact 層の grain）
    events         … 合併イベント parsed⊕overrides（生CSV正規化 history/ingest）
    mapping        … rollup（アトム→基準年・推移閉包）
    aggregate      … 時間軸集約 aggregate_to_base / crosswalk
    spatial_rollup … 空間軸集約 prefecture / region
    reconcile      … 人口保存チェック・孤児アトム検出（検算エンジン）
    specs          … 検算のスペック定義（CrossFactSpec・crossfact 登録簿 CROSSFACT。pin 値は data_forge.known_pins）

why・保証する不変量（検証結果）は docs/distributions/area_master.md。
"""
