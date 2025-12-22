from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ZoneState:
    """State of a single SWAMP zone"""
    unit: int
    zone: int
    power: bool = False
    volume: int = 0
    source_id: int | None = None
    muted: bool = False


@dataclass
class DeviceState:
    """Complete SWAMP device state"""
    zones: dict[tuple[int, int], ZoneState] = field(default_factory=dict)
    connected: bool = False
    last_update: datetime | None = None
