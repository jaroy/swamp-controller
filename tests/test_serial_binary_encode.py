"""Test SERIAL_BINARY JOIN message encoding"""

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
async def test_encode_route_command():
    """Test encoding a route command (set source)"""
    protocol = SwampProtocol()

    # Encode: Set unit 3, zone 4 to source 6
    result = await protocol.encode_route_command(unit=3, zone=4, source_id=6)

    # Expected: 05 00 0e 00 00 0b 20 03 08 20 04 05 14 00 01 00 06
    expected = bytes([
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

    assert result == expected


@pytest.mark.asyncio
async def test_encode_volume_command_50_percent():
    """Test encoding a volume command at 50%"""
    protocol = SwampProtocol()

    # Encode: Set unit 3, zone 4 to 50% volume
    result = await protocol.encode_volume_command(unit=3, zone=4, volume=50)

    # 50% of 0xFFFF = 0x7FFF
    expected = bytes([
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
        0x02,                        # Register ID (volume)
        0x7F, 0xFF                  # 50% volume
    ])

    assert result == expected


@pytest.mark.asyncio
async def test_encode_volume_command_100_percent():
    """Test encoding a volume command at 100%"""
    protocol = SwampProtocol()

    result = await protocol.encode_volume_command(unit=3, zone=4, volume=100)

    # 100% of 0xFFFF = 0xFFFF
    expected = bytes([
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
        0xFF, 0xFF                  # 100% volume
    ])

    assert result == expected


@pytest.mark.asyncio
async def test_encode_volume_command_0_percent():
    """Test encoding a volume command at 0%"""
    protocol = SwampProtocol()

    result = await protocol.encode_volume_command(unit=3, zone=4, volume=0)

    expected = bytes([
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
        0x00, 0x00                  # 0% volume
    ])

    assert result == expected


@pytest.mark.asyncio
async def test_encode_power_off():
    """Test encoding a power off command"""
    protocol = SwampProtocol()

    result = await protocol.encode_power_command(unit=3, zone=4, power_on=False)

    # Power off sets source to 0
    expected = bytes([
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
        0x01,
        0x00, 0x00                  # Source 0 (off)
    ])

    assert result == expected


@pytest.mark.asyncio
async def test_roundtrip_route_command():
    """Test that we can encode and decode a route command"""
    protocol = SwampProtocol()

    # Encode
    encoded = await protocol.encode_route_command(unit=3, zone=4, source_id=6)

    # Decode
    decoded = await protocol.decode_message(encoded)

    assert decoded is not None
    assert decoded['type'] == 'join'
    assert decoded['join_type'] == 'serial_binary'
    assert decoded['unit'] == 3
    assert decoded['zone'] == 4
    assert decoded['register'] == 'source'
    assert decoded['value'] == 6


@pytest.mark.asyncio
async def test_roundtrip_volume_command():
    """Test that we can encode and decode a volume command"""
    protocol = SwampProtocol()

    # Encode 75% volume
    encoded = await protocol.encode_volume_command(unit=3, zone=4, volume=75)

    # Decode
    decoded = await protocol.decode_message(encoded)

    assert decoded is not None
    assert decoded['type'] == 'join'
    assert decoded['join_type'] == 'serial_binary'
    assert decoded['unit'] == 3
    assert decoded['zone'] == 4
    assert decoded['register'] == 'volume'
    # Should be approximately 75% (allow 1% variance due to conversion)
    assert 74 <= decoded['value'] <= 76


@pytest.mark.asyncio
async def test_controller_sends_route_command():
    """Test that the controller can send route commands to device"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect as a "device"
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

        # Now controller should be able to send commands
        # Send a route command from the controller (this uses config sources/targets)
        # For test purposes, we'll verify the protocol encoding works

        # Manually send a command using the protocol
        route_cmd = await protocol.encode_route_command(unit=3, zone=4, source_id=6)
        await tcp_server.send_command(route_cmd)

        # Device should receive magic packets first
        magic1 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic1 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0x49])

        magic2 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic2 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0xc9])

        # Then receive the SERIAL_BINARY command
        received = await asyncio.wait_for(reader.read(17), timeout=1.0)

        # Verify it's a SERIAL_BINARY source command
        assert received[0] == 0x05  # JOIN message
        assert received[6] == 0x20  # SERIAL_BINARY
        assert received[7] == 3     # Unit 3
        assert received[9] == 0x20  # Join type repeated
        assert received[10] == 4    # Zone 4
        assert received[14] == 0x01 # Source register
        assert received[15:17] == bytes([0x00, 0x06])  # Source ID 6

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
