"""出典メタ（ソース非依存の共通型）。

出力物に同梱する出典情報を、特定のデータソースに依存しない形で表す。
`citation`（出典表記）は各ソースが自身の利用規約に沿って組み立てる責務を持ち、
共通層（io/export）はこの型を受け取って書き出すだけにする。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceMeta:
    """データセットの出典メタ。"""

    source: str  # ソース識別子（例: "estat"）
    dataset_id: str  # ソース内のデータセット識別子（例: e-Stat の statsDataId）
    title: str  # データセット名称
    provider: str  # 作成機関（例: 総務省）
    citation: str  # 出典表記（ソースが規約に沿って生成）
    attributes: dict[str, str] = field(default_factory=dict)  # ソース固有の補足

    def flat(self) -> dict[str, str]:
        """SQLite の key-value テーブル向けにフラットな辞書へ。"""
        base = {
            "source": self.source,
            "dataset_id": self.dataset_id,
            "title": self.title,
            "provider": self.provider,
            "citation": self.citation,
        }
        base.update(self.attributes)
        return base
