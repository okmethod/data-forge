"""軸インベントリのスナップショット差分検出（新年度スキーマ・ドリフトの自動検出）。

入口ガード（`schema.validate_stats_data`）は骨格の構造崩れしか見ず、
軸（`CLASS_INF.CLASS_OBJ`）の増減・意味の入れ替わりは passthrough で素通しする。
確定版の新年度投入で cleaner を手当てする際、この軸構成の変化を機械検出できないと
「一時的なテスト空白」に落ちる（docs/data-quality-assurance.md 未カバー領域「新年度スキーマ」）。

本モジュールは統計表（`cache_key` 単位＝statsDataId × 絞り込み）ごとに軸シグネチャ
（`{軸ID: 名称 + 分類コード集合}`）をスナップショットとしてリポジトリに固定し、
取得済みレスポンスと突合して差分を出す。差分の判定規約:

- **area / time は固定しない**: 市区町村コード・調査年コードは年で正当に変動するため、
  存在（軸ID＋名称）のみを見てコードは pin しない。
- **分類軸（tab / cat0N）はコードも固定**: cleaner が依拠する不変条件ゆえ、
  コードの増減＝ドリフトとして扱う。
  `replace_strict` は writing 時に未知コードを弾くが、それは「その年の cleaner を走らせた後」であり、
  投入前に軸構成の変化を知る計器が別に要る。

スナップショットは data ではなくスキーマのメタ情報ゆえリポジトリにコミットする（正典＝`schema_snapshots.json`）。
新年度確定版の投入手順は「取得 → `schema-check --update` で差分を確認しつつスナップショット更新 → cleaner 追補」。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "SignatureDiff",
    "axis_signature",
    "diff_signature",
    "load_registry",
    "save_registry",
]

# area/time は年で正当に変動するためコードを pin せず存在のみ見る軸ID。
_UNPINNED_AXES = frozenset({"area", "time"})

# スナップショットの正典（スキーマのメタ情報＝コミット対象。data ではない）。
_REGISTRY_PATH = Path(__file__).with_name("schema_snapshots.json")


def _as_list(value: Any) -> list[Any]:
    """e-Stat は要素1件だと配列でなく単一 dict を返すため常にリスト化する。"""
    return value if isinstance(value, list) else [value]


def axis_signature(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """生レスポンスから軸シグネチャ `{軸ID: {"name": 名称, "codes": [...]}}` を抽出する。

    area/time は `codes` を持たない（存在＋名称のみ）。分類軸は `codes` にソート済みの
    分類コード集合を持つ。JSON へそのままシリアライズできる素の dict で返す。
    """
    class_objs = _as_list(raw["GET_STATS_DATA"]["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"])
    sig: dict[str, dict[str, Any]] = {}
    for obj in class_objs:
        axis_id = obj["@id"]
        entry: dict[str, Any] = {"name": obj.get("@name", "")}
        if axis_id not in _UNPINNED_AXES:
            entry["codes"] = sorted(item["@code"] for item in _as_list(obj["CLASS"]))
        sig[axis_id] = entry
    return sig


@dataclass(frozen=True)
class SignatureDiff:
    """期待（スナップショット）と実測の軸シグネチャの差分。"""

    axes_added: list[str] = field(default_factory=list)  # 実測にだけ在る軸ID
    axes_removed: list[str] = field(default_factory=list)  # スナップショットにだけ在る軸ID
    name_changed: dict[str, tuple[str, str]] = field(default_factory=dict)  # 軸ID → (旧名, 新名)
    codes_added: dict[str, list[str]] = field(default_factory=dict)  # 分類軸 → 増えたコード
    codes_removed: dict[str, list[str]] = field(default_factory=dict)  # 分類軸 → 消えたコード

    @property
    def has_drift(self) -> bool:
        return bool(self.axes_added or self.axes_removed or self.name_changed or self.codes_added or self.codes_removed)


def diff_signature(expected: dict[str, dict[str, Any]], actual: dict[str, dict[str, Any]]) -> SignatureDiff:
    """スナップショット `expected` に対する実測 `actual` の差分を計算する。

    コード差は両者が `codes` を持つ軸（＝分類軸）だけで見る（area/time は pin しない）。
    """
    exp_ids, act_ids = set(expected), set(actual)
    name_changed: dict[str, tuple[str, str]] = {}
    codes_added: dict[str, list[str]] = {}
    codes_removed: dict[str, list[str]] = {}
    for axis_id in sorted(exp_ids & act_ids):
        exp, act = expected[axis_id], actual[axis_id]
        if exp.get("name", "") != act.get("name", ""):
            name_changed[axis_id] = (exp.get("name", ""), act.get("name", ""))
        exp_codes, act_codes = exp.get("codes"), act.get("codes")
        if exp_codes is not None and act_codes is not None:
            if added := sorted(set(act_codes) - set(exp_codes)):
                codes_added[axis_id] = added
            if removed := sorted(set(exp_codes) - set(act_codes)):
                codes_removed[axis_id] = removed
    return SignatureDiff(
        axes_added=sorted(act_ids - exp_ids),
        axes_removed=sorted(exp_ids - act_ids),
        name_changed=name_changed,
        codes_added=codes_added,
        codes_removed=codes_removed,
    )


def load_registry(path: Path | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """スナップショット registry を読む（未作成なら空 dict）。キーは `fetch.cache_key`。"""
    p = path or _REGISTRY_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any], path: Path | None = None) -> None:
    """スナップショット registry を安定順で書く（diff レビューしやすいよう整形）。"""
    p = path or _REGISTRY_PATH
    p.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
