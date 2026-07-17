"""Tests for zone-group parsing and volume scaling (HA-independent logic).

`group.py` lives under `custom_components/` and imports nothing from Home
Assistant, so we load it directly by file path — importing it as a package would
pull in the HA-dependent package __init__.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_GROUP_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "swamp_controller"
    / "group.py"
)
_spec = importlib.util.spec_from_file_location("swamp_group_under_test", _GROUP_PATH)
group = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass with `from __future__ import annotations`
# resolves the class's module via sys.modules.
sys.modules[_spec.name] = group
_spec.loader.exec_module(group)


# --- scale_member_volume ---------------------------------------------------

def test_scale_unity_is_identity():
    assert group.scale_member_volume(50, 1.0) == 50
    assert group.scale_member_volume(0, 1.0) == 0
    assert group.scale_member_volume(100, 1.0) == 100


def test_scale_damps_hot_room():
    # A room with scale 0.6 plays quieter than the master.
    assert group.scale_member_volume(50, 0.6) == 30
    assert group.scale_member_volume(100, 0.6) == 60


def test_scale_rounds_to_nearest_int():
    assert group.scale_member_volume(55, 0.6) == 33  # 33.0
    assert group.scale_member_volume(45, 0.7) == 31  # 31.4999… -> 31
    assert group.scale_member_volume(65, 0.5) == 32  # 32.5 -> 32 (round-half-to-even)


def test_scale_clamps_to_0_100():
    # scale > 1.0 (boost) is clamped at the top.
    assert group.scale_member_volume(80, 1.5) == 100
    assert group.scale_member_volume(100, 2.0) == 100
    assert group.scale_member_volume(0, 2.0) == 0


# --- derive_master_from_member --------------------------------------------

def test_derive_inverts_scaling():
    # A member at 30 with scale 0.6 came from master 50.
    assert group.derive_master_from_member(30, 0.6) == 50
    assert group.derive_master_from_member(50, 1.0) == 50


def test_derive_roundtrips_with_scale():
    for master in (0, 10, 25, 50, 75, 100):
        member = group.scale_member_volume(master, 0.6)
        # Inverting should land back near the original master (within rounding).
        assert abs(group.derive_master_from_member(member, 0.6) - master) <= 1


def test_derive_clamps_and_handles_nonpositive_scale():
    assert group.derive_master_from_member(100, 0.5) == 100  # 200 -> clamped
    assert group.derive_master_from_member(50, 0) == 0
    assert group.derive_master_from_member(50, -1) == 0


# --- parse_groups ----------------------------------------------------------

def test_parse_none_and_empty():
    assert group.parse_groups(None) == []
    assert group.parse_groups([]) == []


def test_parse_full_group():
    groups = group.parse_groups(
        [
            {
                "id": "main-house",
                "name": "Main House",
                "default-volume": 55,
                "members": [
                    {"target": "great-room"},
                    {"target": "kitchen", "scale": 0.6},
                ],
            }
        ]
    )
    assert len(groups) == 1
    g = groups[0]
    assert g.id == "main-house"
    assert g.name == "Main House"
    assert g.default_volume == 55
    assert [(m.target_id, m.scale) for m in g.members] == [
        ("great-room", 1.0),
        ("kitchen", 0.6),
    ]


def test_parse_member_shorthand_string():
    groups = group.parse_groups(
        [{"id": "g", "name": "G", "members": ["great-room", "kitchen"]}]
    )
    assert [(m.target_id, m.scale) for m in groups[0].members] == [
        ("great-room", 1.0),
        ("kitchen", 1.0),
    ]
    assert groups[0].default_volume is None


def test_parse_missing_id_or_name_raises():
    with pytest.raises(ValueError):
        group.parse_groups([{"name": "no id", "members": ["a"]}])
    with pytest.raises(ValueError):
        group.parse_groups([{"id": "no-name", "members": ["a"]}])


def test_parse_member_without_target_raises():
    with pytest.raises(ValueError):
        group.parse_groups([{"id": "g", "name": "G", "members": [{"scale": 0.5}]}])


def test_parse_group_without_members_raises():
    with pytest.raises(ValueError):
        group.parse_groups([{"id": "g", "name": "G", "members": []}])
