from dataclasses import dataclass


@dataclass
class RouteCommand:
    """Route a source to a target"""
    source_id: str
    target_id: str


@dataclass
class VolumeCommand:
    """Set or adjust volume"""
    target_id: str
    level: int | None = None
    delta: int | None = None


@dataclass
class PowerCommand:
    """Power control"""
    target_id: str
    power_on: bool
