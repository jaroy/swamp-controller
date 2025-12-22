import logging
from swamp.models.config import AppConfig


logger = logging.getLogger(__name__)


class SwampController:
    """Main coordinator - orchestrates all layers"""

    def __init__(self, config: AppConfig, tcp_server, state_manager):
        self.config = config
        self.tcp = tcp_server
        self.state = state_manager

    async def route_source_to_target(self, source_id: str, target_id: str) -> None:
        """High-level routing command"""
        source = self.state.get_source_by_id(source_id)
        zones = self.state.get_zones_for_target(target_id)

        logger.info(f"Routing {source.name} to {target_id} ({len(zones)} zones)")

        for zone_state in zones:
            command_bytes = await self.tcp.protocol.encode_route_command(
                zone_state.unit, zone_state.zone, source.swamp_source_id
            )
            await self.tcp.send_command(command_bytes)

            zone_state.source_id = source.swamp_source_id

    async def set_volume(self, target_id: str, level: int) -> None:
        """Set volume for target"""
        zones = self.state.get_zones_for_target(target_id)

        logger.info(f"Setting {target_id} volume to {level} ({len(zones)} zones)")

        for zone_state in zones:
            command_bytes = await self.tcp.protocol.encode_volume_command(
                zone_state.unit, zone_state.zone, level
            )
            await self.tcp.send_command(command_bytes)

            zone_state.volume = level

    async def set_power(self, target_id: str, power_on: bool) -> None:
        """Set power for target"""
        zones = self.state.get_zones_for_target(target_id)

        logger.info(f"Setting {target_id} power to {'on' if power_on else 'off'} ({len(zones)} zones)")

        for zone_state in zones:
            command_bytes = await self.tcp.protocol.encode_power_command(
                zone_state.unit, zone_state.zone, power_on
            )
            await self.tcp.send_command(command_bytes)

            zone_state.power = power_on

    async def get_status(self) -> dict:
        """Get current system status"""
        return {
            'connected': self.state.state.connected,
            'targets': [
                {
                    'id': target.id,
                    'name': target.name,
                    'zones': [
                        {
                            'unit': z.unit,
                            'zone': z.zone,
                            'power': z.power,
                            'volume': z.volume,
                            'source': z.source_id
                        }
                        for z in self.state.get_zones_for_target(target.id)
                    ]
                }
                for target in self.config.targets
            ]
        }
