"""Test zone validity tracking (source_received flag)"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from swamp.core.controller import SwampController
from swamp.models.state import ZoneState
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_zone_initially_not_valid():
    """Test that zones are initially marked as not having received data"""
    config = ConfigManager.load(Path('config/config.yaml'))
    state_manager = StateManager(config)

    # Get first zone
    target = config.targets[0]
    zone_config = target.swamp_zones[0]
    zone_state = state_manager.state.zones.get((zone_config.unit, zone_config.zone))

    assert zone_state is not None
    assert zone_state.source_received == False


@pytest.mark.asyncio
async def test_zone_valid_after_source_received():
    """Test that zone is marked valid after receiving source data"""
    config = ConfigManager.load(Path('config/config.yaml'))
    state_manager = StateManager(config)

    # Get first zone
    target = config.targets[0]
    zone_config = target.swamp_zones[0]
    unit = zone_config.unit
    zone = zone_config.zone

    zone_state = state_manager.state.zones.get((unit, zone))
    assert zone_state.source_received == False

    # Simulate receiving source data
    message = {
        'type': 'join',
        'join_type': 'serial_binary',
        'unit': unit,
        'zone': zone,
        'register': 'source',
        'value': 5
    }
    await state_manager.update_from_device(message)

    # Now should be marked as valid
    assert zone_state.source_received == True
    assert zone_state.source_id == 5


@pytest.mark.asyncio
async def test_zone_not_valid_after_volume_only():
    """Test that zone is NOT marked valid after only receiving volume (needs source)"""
    config = ConfigManager.load(Path('config/config.yaml'))
    state_manager = StateManager(config)

    # Get first zone
    target = config.targets[0]
    zone_config = target.swamp_zones[0]
    unit = zone_config.unit
    zone = zone_config.zone

    zone_state = state_manager.state.zones.get((unit, zone))
    assert zone_state.source_received == False

    # Simulate receiving only volume data
    message = {
        'type': 'join',
        'join_type': 'serial_binary',
        'unit': unit,
        'zone': zone,
        'register': 'volume',
        'value': 75
    }
    await state_manager.update_from_device(message)

    # Should NOT be marked as valid (only source register marks it valid)
    assert zone_state.source_received == False
    assert zone_state.volume == 75


@pytest.mark.asyncio
async def test_status_display_waiting_for_data():
    """Test that status shows 'Waiting for device data' when no zones are valid"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    # Get status before receiving any data
    status = await controller.get_status()

    # All zones should not have source_received
    for target in status['targets']:
        for zone in target['zones']:
            assert zone['source_received'] == False


@pytest.mark.asyncio
async def test_status_display_after_source_received():
    """Test that status shows zone details after receiving source data"""
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
        await asyncio.wait_for(reader.read(4), timeout=1.0)
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()
        await asyncio.wait_for(reader.read(7), timeout=1.0)
        await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Get first zone from config
        target = config.targets[0]
        zone_config = target.swamp_zones[0]
        unit = zone_config.unit
        zone = zone_config.zone

        # Send source data for this zone
        source_msg = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            unit, 0x08, 0x20, zone, 0x05, 0x14, 0x00, 0x01, 0x00, 0x05
        ])
        writer.write(source_msg)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Get status
        status = await controller.get_status()

        # Find the zone we updated
        target_status = next(t for t in status['targets'] if t['id'] == target.id)
        zone_status = next(z for z in target_status['zones'] if z['unit'] == unit and z['zone'] == zone)

        # This zone should now be valid
        assert zone_status['source_received'] == True
        assert zone_status['source'] == 5

        # Other zones in the same target should still be not valid
        other_zones = [z for z in target_status['zones'] if not (z['unit'] == unit and z['zone'] == zone)]
        if other_zones:
            assert all(not z['source_received'] for z in other_zones)

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_integration_zone_becomes_valid():
    """Integration test: zone starts invalid, becomes valid after source received"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect as device
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        await asyncio.wait_for(reader.read(4), timeout=1.0)
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()
        await asyncio.wait_for(reader.read(7), timeout=1.0)
        await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Initially, all zones should not be valid
        target = config.targets[0]
        zone_config = target.swamp_zones[0]
        zone_state = state_manager.state.zones.get((zone_config.unit, zone_config.zone))
        assert zone_state.source_received == False

        # Send source data
        source_msg = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            zone_config.unit, 0x08, 0x20, zone_config.zone, 0x05, 0x14, 0x00, 0x01, 0x00, 0x03
        ])
        writer.write(source_msg)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Now zone should be valid
        assert zone_state.source_received == True
        assert zone_state.source_id == 3

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
