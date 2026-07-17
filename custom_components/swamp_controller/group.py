"""Pure (Home-Assistant-independent) logic for SWAMP zone groups.

A *zone group* is a virtual media player that fans a single source selection and a
single "master" volume out to several member targets. Each member carries its own
volume ``scale`` (a gain multiplier) so rooms with different speaker sensitivities
stay balanced under one slider: master 0-100 maps to ``master * scale`` for each
member, clamped to 0-100.

This module deliberately imports nothing from Home Assistant so the parsing and
scaling math can be unit-tested standalone. The HA entity that uses it lives in
``media_player.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GroupMember:
    """One target in a zone group, with its volume gain multiplier."""

    target_id: str
    scale: float = 1.0


@dataclass
class ZoneGroup:
    """A virtual media player fanning source + master volume over members."""

    id: str
    name: str
    members: list[GroupMember] = field(default_factory=list)
    # Master level (0-100) applied on power-on; falls back to the integration
    # default when None.
    default_volume: int | None = None


def parse_groups(raw_groups) -> list[ZoneGroup]:
    """Build ZoneGroup objects from the raw ``groups:`` YAML list.

    Each group needs ``id``, ``name`` and a ``members`` list. A member may be a
    plain target-id string (scale 1.0) or a mapping with ``target`` and optional
    ``scale``. Malformed entries raise ValueError so setup fails loudly rather
    than silently dropping a room.
    """
    groups: list[ZoneGroup] = []
    for raw in raw_groups or []:
        group_id = raw.get("id")
        name = raw.get("name")
        if not group_id or not name:
            raise ValueError(f"Group is missing 'id' or 'name': {raw!r}")

        members: list[GroupMember] = []
        for raw_member in raw.get("members", []):
            if isinstance(raw_member, str):
                members.append(GroupMember(target_id=raw_member))
                continue
            target_id = raw_member.get("target")
            if not target_id:
                raise ValueError(
                    f"Group '{group_id}' has a member with no 'target': {raw_member!r}"
                )
            scale = raw_member.get("scale", 1.0)
            members.append(GroupMember(target_id=target_id, scale=float(scale)))

        if not members:
            raise ValueError(f"Group '{group_id}' has no members")

        groups.append(
            ZoneGroup(
                id=group_id,
                name=name,
                members=members,
                default_volume=raw.get("default-volume"),
            )
        )
    return groups


def scale_member_volume(master_percent: float, scale: float) -> int:
    """Map a group master level (0-100) to a member's level (0-100), clamped."""
    level = round(master_percent * scale)
    return max(0, min(100, level))


def derive_master_from_member(member_percent: float, scale: float) -> int:
    """Invert scaling to seed the master slider from a member's current level.

    Used once at startup so the master reflects roughly where the rooms already
    are. A non-positive scale can't be inverted, so treat it as 0.
    """
    if scale <= 0:
        return 0
    level = round(member_percent / scale)
    return max(0, min(100, level))
