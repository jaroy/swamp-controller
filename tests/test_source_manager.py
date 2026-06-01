"""Unit tests for the SourceManager (zone -> render-source allocation)."""

import sys
from pathlib import Path

# SourceManager lives in the HA integration layer (no Home Assistant deps).
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "custom_components" / "swamp_controller")
)

import pytest

from source_manager import RenderSource, SourceManager, SourceUnavailable


def make_manager() -> SourceManager:
    return SourceManager(
        sources=[RenderSource(id="whole-house", name="Whole-House", swamp_source_id=4, lms_player_id="aa:bb")]
    )


def test_allocate_returns_and_records_source():
    mgr = make_manager()
    src = mgr.allocate("kitchen")
    assert src.swamp_source_id == 4
    assert src.lms_player_id == "aa:bb"
    assert mgr.get_renderer("kitchen") is src


def test_allocate_without_sources_raises():
    mgr = SourceManager(sources=[])
    with pytest.raises(SourceUnavailable):
        mgr.allocate("kitchen")
    assert mgr.default_source is None


def test_get_renderer_unknown_target_is_none():
    assert make_manager().get_renderer("nowhere") is None


def test_release_returns_source_only_when_last_zone():
    mgr = make_manager()
    mgr.allocate("kitchen")
    mgr.allocate("library")  # second zone shares the single DAC

    # Releasing one zone: renderer still in use -> nothing to stop.
    assert mgr.release("kitchen") is None
    # Releasing the last zone: renderer now free -> return it so caller stops it.
    freed = mgr.release("library")
    assert freed is not None and freed.lms_player_id == "aa:bb"


def test_release_unknown_target_is_none():
    assert make_manager().release("nowhere") is None
