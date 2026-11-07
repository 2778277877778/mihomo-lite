"""Profile metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProfileKind(StrEnum):
    LOCAL = "local"
    SUBSCRIPTION = "subscription"

    @property
    def label(self) -> str:
        return "Local file" if self is ProfileKind.LOCAL else "Subscription"


@dataclass
class Profile:
    """One imported configuration.

    The bytes always live in profiles/<id>/original.yaml; this object is the
    index entry so the UI can render a list without touching the files.
    """

    id: str
    name: str
    kind: ProfileKind = ProfileKind.LOCAL
    url: str = ""
    updated_at: float = 0.0
    size: int = 0
    proxy_count: int = 0
    group_count: int = 0
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "url": self.url,
            "updated_at": self.updated_at,
            "size": self.size,
            "proxy_count": self.proxy_count,
            "group_count": self.group_count,
            "note": self.note,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        try:
            kind = ProfileKind(str(data.get("kind", "local")))
        except ValueError:
            kind = ProfileKind.LOCAL
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "unnamed")),
            kind=kind,
            url=str(data.get("url", "")),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
            size=int(data.get("size", 0) or 0),
            proxy_count=int(data.get("proxy_count", 0) or 0),
            group_count=int(data.get("group_count", 0) or 0),
            note=str(data.get("note", "")),
            extra=dict(data.get("extra") or {}),
        )
