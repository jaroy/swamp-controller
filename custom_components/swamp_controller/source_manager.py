"""Maps SWAMP zones (targets) to the audio source / renderer backing them.

A "render source" is a SWAMP analog input (``swamp_source_id``) fed by a squeezelite
player (``lms_player_id``) that a real LMS can drive. Playing to a zone allocates one
of these sources, routes it to the zone on the SWAMP, and renders via its LMS player.

v1 has a single DAC, so allocation is trivial (always the one MA-rendered source).
The per-renderer "active zones" bookkeeping is the seam for multi-DAC: with several
DACs each source/renderer is independent, so zone-groups can play different content
(SWAMP routing provides the hardware sync; #independent streams == #DACs).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderSource:
    """A SWAMP input rendered by a squeezelite/LMS player."""

    id: str
    name: str
    swamp_source_id: int
    lms_player_id: str


@dataclass
class SourceManager:
    """Allocates render sources to zones and tracks which zones are active."""

    sources: list[RenderSource]
    # target_id -> source.id currently backing it
    _assignments: dict[str, str] = field(default_factory=dict)

    def allocate(self, target_id: str) -> RenderSource:
        """Pick (and record) the render source backing ``target_id`` for playback.

        v1: a single MA-rendered source, so this always returns it. Multi-DAC would
        reuse a group's source or pick a free renderer here.
        """
        if not self.sources:
            raise SourceUnavailable("No MA-rendered SWAMP sources are configured")
        source = self.sources[0]
        self._assignments[target_id] = source.id
        _LOGGER.debug("Allocated source %s to target %s", source.id, target_id)
        return source

    def get_renderer(self, target_id: str) -> RenderSource | None:
        """Return the source currently backing ``target_id``, if any."""
        source_id = self._assignments.get(target_id)
        if source_id is None:
            return None
        return next((s for s in self.sources if s.id == source_id), None)

    def release(self, target_id: str) -> RenderSource | None:
        """Mark ``target_id`` inactive.

        Returns the source it was using *iff* no other active zone shares that
        renderer (so the caller can stop the renderer); otherwise ``None``.
        """
        source_id = self._assignments.pop(target_id, None)
        if source_id is None:
            return None
        if source_id in self._assignments.values():
            return None  # another zone still using this renderer
        return next((s for s in self.sources if s.id == source_id), None)

    @property
    def default_source(self) -> RenderSource | None:
        """The source used when a zone has no explicit assignment (v1: the only one)."""
        return self.sources[0] if self.sources else None


class SourceUnavailable(Exception):
    """Raised when no render source can be allocated."""
