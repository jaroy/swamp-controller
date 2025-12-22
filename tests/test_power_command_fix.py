"""Test power command uses correct source ID"""

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
async def test_power_on_uses_correct_source():
    """Test that power on command uses the actual source ID, not defaulting to 1"""
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

        # Find a source with swamp_source_id != 1 to test with
        test_source = None
        for source in config.sources:
            if source.swamp_source_id != 1:
                test_source = source
                break

        if not test_source:
            pytest.skip("No source with swamp_source_id != 1 in config")

        # Get first target
        target_id = config.targets[0].id
        target = config.targets[0]
        num_zones = len(target.swamp_zones)

        # Send power on command with our test source
        await controller.set_power(target_id, True, test_source.id)

        # Should receive magic packets first
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 1
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 2

        # Then receive SERIAL_BINARY commands for each zone
        for _ in range(num_zones):
            msg = await asyncio.wait_for(reader.read(17), timeout=1.0)

            # Verify it's a SERIAL_BINARY source command
            assert msg[0] == 0x05   # JOIN
            assert msg[6] == 0x20   # SERIAL_BINARY
            assert msg[14] == 0x01  # Source register

            # Verify the source ID matches our test source, NOT 1
            source_value = int.from_bytes(msg[15:17], 'big')
            assert source_value == test_source.swamp_source_id, \
                f"Expected source {test_source.swamp_source_id}, got {source_value}"

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_power_off_sets_source_zero():
    """Test that power off sets source to 0"""
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

        # Get first target
        target_id = config.targets[0].id
        target = config.targets[0]
        num_zones = len(target.swamp_zones)

        # Send power off command
        await controller.set_power(target_id, False, None)

        # Should receive magic packets first
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 1
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 2

        # Then receive SERIAL_BINARY commands for each zone
        for _ in range(num_zones):
            msg = await asyncio.wait_for(reader.read(17), timeout=1.0)

            # Verify it's a SERIAL_BINARY source command
            assert msg[0] == 0x05   # JOIN
            assert msg[6] == 0x20   # SERIAL_BINARY
            assert msg[14] == 0x01  # Source register

            # Verify the source ID is 0 (off)
            source_value = int.from_bytes(msg[15:17], 'big')
            assert source_value == 0, f"Expected source 0 (off), got {source_value}"

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_route_vs_power_consistency():
    """Test that route and power commands use the same source ID"""
    config = ConfigManager.load(Path('config/config.yaml'))
    state_manager = StateManager(config)

    # Get test source
    test_source = config.sources[0]
    target = config.targets[0]
    zone = target.swamp_zones[0]

    # Initialize zone state
    from swamp.models.state import ZoneState
    zone_key = (zone.unit, zone.zone)
    if zone_key not in state_manager.state.zones:
        state_manager.state.zones[zone_key] = ZoneState(unit=zone.unit, zone=zone.zone)

    # Mock controller
    class MockTcp:
        def __init__(self):
            self.protocol = SwampProtocol()
            self.commands_sent = []

        async def send_command(self, data: bytes):
            self.commands_sent.append(data)

    tcp = MockTcp()
    controller = SwampController(config, tcp, state_manager)

    # Send route command
    await controller.route_source_to_target(test_source.id, target.id)
    route_command = tcp.commands_sent[0]

    # Reset
    tcp.commands_sent.clear()

    # Send power on command with same source
    await controller.set_power(target.id, True, test_source.id)
    power_command = tcp.commands_sent[0]

    # Both should encode the same source ID
    route_source = int.from_bytes(route_command[15:17], 'big')
    power_source = int.from_bytes(power_command[15:17], 'big')

    assert route_source == power_source == test_source.swamp_source_id, \
        f"Route and power commands should use same source ID: route={route_source}, power={power_source}, expected={test_source.swamp_source_id}"
