from datetime import datetime
from ..models.config import AppConfig, Source
from ..models.state import DeviceState, ZoneState


class StateManager:
    """Manages device state and zone mappings"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.state = DeviceState()
        self._initialize_zones()

    def _initialize_zones(self) -> None:
        """Create ZoneState for all configured zones"""
        for target in self.config.targets:
            for sz in target.swamp_zones:
                key = (sz.unit, sz.zone)
                if key not in self.state.zones:
                    self.state.zones[key] = ZoneState(unit=sz.unit, zone=sz.zone)

    async def update_from_device(self, message: dict) -> None:
        """Update state from device message"""
        self.state.last_update = datetime.now()

        msg_type = message.get('type')

        # Handle JOIN SERIAL_BINARY messages
        if msg_type == 'join' and message.get('join_type') == 'serial_binary':
            unit = message.get('unit')
            zone = message.get('zone')
            register = message.get('register')
            value = message.get('value')

            if unit is None or zone is None or register is None or value is None:
                return

            key = (unit, zone)
            if key in self.state.zones:
                zone_state = self.state.zones[key]
                if register == 'source':
                    zone_state.source_id = value
                    zone_state.source_received = True  # Mark as having received data
                elif register == 'volume':
                    zone_state.volume = value

        # Handle legacy zone_update messages
        elif msg_type == 'zone_update':
            unit = message.get('unit')
            zone = message.get('zone')
            key = (unit, zone)

            if key in self.state.zones:
                zone_state = self.state.zones[key]
                if 'power' in message:
                    zone_state.power = message['power']
                if 'volume' in message:
                    zone_state.volume = message['volume']
                if 'source_id' in message:
                    zone_state.source_id = message['source_id']
                if 'muted' in message:
                    zone_state.muted = message['muted']

    def get_zones_for_target(self, target_id: str) -> list[ZoneState]:
        """Map high-level target to SWAMP zones"""
        target = self._find_target(target_id)
        if not target:
            raise ValueError(f"Unknown target: {target_id}")

        return [
            self.state.zones[(sz.unit, sz.zone)]
            for sz in target.swamp_zones
        ]

    def get_source_by_id(self, source_id: str) -> Source:
        """Look up source by ID"""
        for source in self.config.sources:
            if source.id == source_id:
                return source
        raise ValueError(f"Unknown source: {source_id}")

    def _find_target(self, target_id: str):
        """Find target by ID"""
        for target in self.config.targets:
            if target.id == target_id:
                return target
        return None
