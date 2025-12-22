from dataclasses import dataclass


@dataclass
class SwampZone:
    """Represents a SWAMP unit+zone pair"""
    unit: int
    zone: int


@dataclass
class Source:
    """Audio source configuration"""
    id: str
    name: str
    swamp_source_id: int


@dataclass
class Target:
    """Target zone/speaker configuration"""
    id: str
    name: str
    swamp_zones: list[SwampZone]


@dataclass
class AppConfig:
    """Application configuration"""
    sources: list[Source]
    targets: list[Target]
