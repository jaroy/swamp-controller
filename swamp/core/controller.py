import logging
from ..models.config import AppConfig


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

    async def set_power(self, target_id: str, power_on: bool, source_id: str | None = None) -> None:
        """Set power for target (really just routes source to zone)

        Power on requires a source_id. Power off sets source to 0.
        """
        zones = self.state.get_zones_for_target(target_id)

        if power_on:
            if not source_id:
                raise ValueError("Power on requires a source_id")
            # Power on = route source to zone
            source = self.state.get_source_by_id(source_id)
            swamp_source_id = source.swamp_source_id
            logger.info(f"Powering on {target_id} with source {source_id} ({len(zones)} zones)")

            for zone_state in zones:
                # Use route command for power on (sets the actual source)
                command_bytes = await self.tcp.protocol.encode_route_command(
                    zone_state.unit, zone_state.zone, swamp_source_id
                )
                await self.tcp.send_command(command_bytes)
                zone_state.power = True
                zone_state.source_id = swamp_source_id
        else:
            # Power off = route source 0 (no source) to zone
            logger.info(f"Powering off {target_id} ({len(zones)} zones)")

            for zone_state in zones:
                command_bytes = await self.tcp.protocol.encode_power_command(
                    zone_state.unit, zone_state.zone, False
                )
                await self.tcp.send_command(command_bytes)
                zone_state.power = False
                zone_state.source_id = None

    async def send_whois(self) -> None:
        """Send WHOIS request to connected device"""
        logger.info("Sending WHOIS request")
        whois_bytes = await self.tcp.protocol.encode_whois()
        await self.tcp.send_command(whois_bytes)

    async def get_status(self) -> dict:
        """Get current system status"""
        state = self.state.state

        # Calculate time since last message
        time_since_last = None
        if state.last_message_received:
            from datetime import datetime
            time_since_last = (datetime.now() - state.last_message_received).total_seconds()

        return {
            'connected': state.connected,
            'socket_connected': state.socket_connected,
            'conn_accepted_sent': state.conn_accepted_sent,
            'client_address': state.client_address,
            'last_message_seconds': time_since_last,
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
                            'source': z.source_id,
                            'source_received': z.source_received
                        }
                        for z in self.state.get_zones_for_target(target.id)
                    ]
                }
                for target in self.config.targets
            ]
        }
