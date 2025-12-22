"""Test SERIAL_BINARY JOIN message handling"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_serial_binary_source_decoding():
    """Test that SERIAL_BINARY source messages are decoded correctly"""
    protocol = SwampProtocol()

    # Example: 05 00 0e 00 00 0b 20 03 08 20 04 05 14 00 01 00 06
    # Message type: 0x05 (JOIN)
    # Remaining length: 0x000e (14 bytes)
    # Inner length: 0x00000b (11 bytes)
    # Join type: 0x20 (SERIAL_BINARY)
    # Unit: 03, Zone: 04
    # Register: 0x01 (source), Value: 0x0006 (source id 6)
    message = bytes([
        0x05, 0x00, 0x0e,           # Message header
        0x00, 0x00, 0x0b,           # Inner length (11)
        0x20,                        # Join type (SERIAL_BINARY)
        0x03,                        # Unit 3
        0x08,                        # Remaining length
        0x20,                        # Join type repeated
        0x04,                        # Zone 4
        0x05,                        # Remaining length
        0x14,                        # Register msg type
        0x00,                        # 0x00
        0x01,                        # Register ID (source)
        0x00, 0x06                  # Source ID 6
    ])

    result = await protocol.decode_message(message)

    assert result is not None
    assert result['type'] == 'join'
    assert result['join_type'] == 'serial_binary'
    assert result['unit'] == 3
    assert result['zone'] == 4
    assert result['register'] == 'source'
    assert result['value'] == 6


@pytest.mark.asyncio
async def test_serial_binary_volume_decoding():
    """Test that SERIAL_BINARY volume messages are decoded correctly"""
    protocol = SwampProtocol()

    # SERIAL_BINARY message for volume = 50% (0x7fff of 0xffff)
    message = bytes([
        0x05, 0x00, 0x0e,           # Message header
        0x00, 0x00, 0x0b,           # Inner length (11)
        0x20,                        # Join type (SERIAL_BINARY)
        0x03,                        # Unit 3
        0x08,                        # Remaining length
        0x20,                        # Join type repeated
        0x04,                        # Zone 4
        0x05,                        # Remaining length
        0x14,                        # Register msg type
        0x00,                        # 0x00
        0x02,                        # Register ID (volume)
        0x7f, 0xff                  # Volume ~50% of 0xffff
    ])

    result = await protocol.decode_message(message)

    assert result is not None
    assert result['type'] == 'join'
    assert result['join_type'] == 'serial_binary'
    assert result['unit'] == 3
    assert result['zone'] == 4
    assert result['register'] == 'volume'
    # Should convert 0x7fff to approximately 50% (49-50)
    assert 49 <= result['value'] <= 50


@pytest.mark.asyncio
async def test_serial_binary_volume_max():
    """Test volume at maximum (100%)"""
    protocol = SwampProtocol()

    message = bytes([
        0x05, 0x00, 0x0e,
        0x00, 0x00, 0x0b,
        0x20,
        0x03,
        0x08,
        0x20,
        0x04,
        0x05,
        0x14,
        0x00,
        0x02,
        0xff, 0xff                  # Volume 100% (0xffff)
    ])

    result = await protocol.decode_message(message)
    assert result['value'] == 100


@pytest.mark.asyncio
async def test_serial_binary_volume_min():
    """Test volume at minimum (0%)"""
    protocol = SwampProtocol()

    message = bytes([
        0x05, 0x00, 0x0e,
        0x00, 0x00, 0x0b,
        0x20,
        0x03,
        0x08,
        0x20,
        0x04,
        0x05,
        0x14,
        0x00,
        0x02,
        0x00, 0x00                  # Volume 0%
    ])

    result = await protocol.decode_message(message)
    assert result['value'] == 0


@pytest.mark.asyncio
async def test_serial_binary_state_update_source():
    """Test that SERIAL_BINARY source updates are applied to state"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    # Initialize state
    zone_key = (3, 4)
    if zone_key not in state_manager.state.zones:
        from swamp.models.state import ZoneState
        state_manager.state.zones[zone_key] = ZoneState(unit=3, zone=4)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS
        await asyncio.wait_for(reader.read(4), timeout=1.0)

        # Send CLIENT_SIGNON and complete handshake
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED and JOIN UPDATE
        await asyncio.wait_for(reader.read(7), timeout=1.0)
        await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Send SERIAL_BINARY source update
        serial_binary_msg = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            0x03, 0x08, 0x20, 0x04, 0x05, 0x14, 0x00, 0x01, 0x00, 0x06
        ])
        writer.write(serial_binary_msg)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify state was updated
        zone_state = state_manager.state.zones.get((3, 4))
        assert zone_state is not None
        assert zone_state.source_id == 6

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_serial_binary_state_update_volume():
    """Test that SERIAL_BINARY volume updates are applied to state"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    # Initialize state
    zone_key = (3, 4)
    if zone_key not in state_manager.state.zones:
        from swamp.models.state import ZoneState
        state_manager.state.zones[zone_key] = ZoneState(unit=3, zone=4)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS
        await asyncio.wait_for(reader.read(4), timeout=1.0)

        # Send CLIENT_SIGNON and complete handshake
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED and JOIN UPDATE
        await asyncio.wait_for(reader.read(7), timeout=1.0)
        await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Send SERIAL_BINARY volume update (75% = 0xbfff)
        serial_binary_msg = bytes([
            0x05, 0x00, 0x0e,
            0x00, 0x00, 0x0b,
            0x20,
            0x03, 0x08, 0x20, 0x04, 0x05, 0x14, 0x00, 0x02, 0xbf, 0xff
        ])
        writer.write(serial_binary_msg)
        await writer.drain()

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify state was updated
        zone_state = state_manager.state.zones.get((3, 4))
        assert zone_state is not None
        # Should be approximately 75% (74-76)
        assert 74 <= zone_state.volume <= 76

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
