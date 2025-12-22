"""End-to-end integration tests"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from swamp.core.controller import SwampController
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_route_command_end_to_end():
    """Test complete route command flow: controller -> network -> device"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect as device
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        await asyncio.wait_for(reader.read(4), timeout=1.0)  # WHOIS
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()
        await asyncio.wait_for(reader.read(7), timeout=1.0)  # CONN_ACCEPTED
        await asyncio.wait_for(reader.read(8), timeout=1.0)  # JOIN UPDATE

        # Use controller to send route command
        # From config: sources have IDs like "tv", "spotify", etc.
        # targets have IDs like "loggia", "kitchen", etc.
        # We'll use the first source and target from config
        source_id = config.sources[0].id
        target_id = config.targets[0].id

        # Send route command
        await controller.route_source_to_target(source_id, target_id)

        # Device should receive magic packets first (before first SERIAL_BINARY)
        magic1 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic1 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0x49])

        magic2 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic2 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0xc9])

        # Then device should receive SERIAL_BINARY JOIN messages (one per zone in target)
        target = next(t for t in config.targets if t.id == target_id)
        num_zones = len(target.swamp_zones)

        for _ in range(num_zones):
            # Receive the SERIAL_BINARY message
            msg = await asyncio.wait_for(reader.read(17), timeout=1.0)

            # Verify it's a proper SERIAL_BINARY source command
            assert msg[0] == 0x05   # JOIN
            assert msg[6] == 0x20   # SERIAL_BINARY
            assert msg[14] == 0x01  # Source register
            # Source value should match config
            source = next(s for s in config.sources if s.id == source_id)
            source_value = int.from_bytes(msg[15:17], 'big')
            assert source_value == source.swamp_source_id

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_volume_command_end_to_end():
    """Test complete volume command flow: controller -> network -> device"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect as device
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        await asyncio.wait_for(reader.read(4), timeout=1.0)  # WHOIS
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()
        await asyncio.wait_for(reader.read(7), timeout=1.0)  # CONN_ACCEPTED
        await asyncio.wait_for(reader.read(8), timeout=1.0)  # JOIN UPDATE

        # Use controller to set volume to 75%
        target_id = config.targets[0].id

        await controller.set_volume(target_id, 75)

        # Device should receive magic packets first (before first SERIAL_BINARY)
        magic1 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic1 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0x49])

        magic2 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic2 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0xc9])

        # Then device should receive SERIAL_BINARY JOIN messages (one per zone in target)
        target = next(t for t in config.targets if t.id == target_id)
        num_zones = len(target.swamp_zones)

        for _ in range(num_zones):
            # Receive the SERIAL_BINARY message
            msg = await asyncio.wait_for(reader.read(17), timeout=1.0)

            # Verify it's a proper SERIAL_BINARY volume command
            assert msg[0] == 0x05   # JOIN
            assert msg[6] == 0x20   # SERIAL_BINARY
            assert msg[14] == 0x02  # Volume register
            # Volume should be ~75% of 0xFFFF
            volume_raw = int.from_bytes(msg[15:17], 'big')
            volume_pct = int((volume_raw / 0xFFFF) * 100)
            assert 74 <= volume_pct <= 76

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_bidirectional_state_sync():
    """Test that state updates from device are reflected in controller state"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect as device
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        await asyncio.wait_for(reader.read(4), timeout=1.0)  # WHOIS
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()
        await asyncio.wait_for(reader.read(7), timeout=1.0)  # CONN_ACCEPTED
        await asyncio.wait_for(reader.read(8), timeout=1.0)  # JOIN UPDATE

        # Get first zone from config
        target = config.targets[0]
        zone_config = target.swamp_zones[0]
        unit = zone_config.unit
        zone = zone_config.zone

        # Device sends SERIAL_BINARY update: source changed to 5
        update_msg = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            unit, 0x08, 0x20, zone, 0x05, 0x14, 0x00, 0x01, 0x00, 0x05
        ])
        writer.write(update_msg)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify state was updated
        zone_state = state_manager.state.zones.get((unit, zone))
        assert zone_state is not None
        assert zone_state.source_id == 5

        # Device sends another update: volume to 80%
        volume_80 = int(0.8 * 0xFFFF)
        vol_hi = (volume_80 >> 8) & 0xFF
        vol_lo = volume_80 & 0xFF
        update_msg2 = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            unit, 0x08, 0x20, zone, 0x05, 0x14, 0x00, 0x02, vol_hi, vol_lo
        ])
        writer.write(update_msg2)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify volume was updated
        assert 79 <= zone_state.volume <= 81

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
