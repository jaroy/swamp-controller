import yaml
from pathlib import Path
from ..models.config import AppConfig, Source, Target, SwampZone


class ConfigManager:
    """Loads and validates configuration"""

    @staticmethod
    def load(config_path: Path) -> AppConfig:
        """Load config from YAML file"""
        with open(config_path) as f:
            data = yaml.safe_load(f)

        sources = [
            Source(
                id=s['id'],
                name=s['name'],
                swamp_source_id=s['swamp-source-id']
            )
            for s in data['sources']
        ]

        targets = [
            Target(
                id=t['id'],
                name=t['name'],
                swamp_zones=[
                    SwampZone(unit=z['unit'], zone=z['zone'])
                    for z in t['swamp-zones']
                ]
            )
            for t in data['targets']
        ]

        return AppConfig(sources=sources, targets=targets)
