"""出典メタ（ソース非依存の共通型）。

出力物に同梱する出典情報を、特定のデータソースに依存しない形で表す。
`citation`（出典表記）は各ソースが自身の利用規約に沿って組み立てる責務を持ち、
共通層（output/export）はこの型を受け取って書き出すだけにする。
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


def combine_meta(metas: list[SourceMeta], *, title: str) -> SourceMeta:
    """複数データセットの出典メタを1つに束ねる（派生データセット用）。

    結合表は全ての元表を出典に明記する必要があるため、dataset_id と citation を
    連結する。source / provider は先頭を採用（同一ソース内の結合を想定）。
    """
    if not metas:
        raise ValueError("combine_meta: metas が空です")
    return SourceMeta(
        source=metas[0].source,
        dataset_id=", ".join(m.dataset_id for m in metas),
        title=title,
        provider=metas[0].provider,
        citation=" / ".join(m.citation for m in metas),
        attributes={"combined_from": ", ".join(m.dataset_id for m in metas)},
    )
