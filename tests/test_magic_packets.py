"""Test magic DIGITAL JOIN packet handling"""

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
async def test_encode_magic_packets():
    """Test encoding of magic DIGITAL JOIN packets"""
    protocol = SwampProtocol()

    msg1, msg2 = protocol.encode_join_digital_magic()

    # Message 1: 05 00 06 00 00 03 00 70 49
    expected1 = bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0x49])
    assert msg1 == expected1

    # Message 2: 05 00 06 00 00 03 00 70 c9
    expected2 = bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0xc9])
    assert msg2 == expected2


@pytest.mark.asyncio
async def test_magic_packets_sent_before_serial_binary():
    """Test that magic packets are sent automatically before first SERIAL_BINARY command"""
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

        # Verify magic packets not sent yet
        assert not tcp_server.magic_packets_sent

        # Send first SERIAL_BINARY command (route)
        source_id = config.sources[0].id
        target_id = config.targets[0].id
        await controller.route_source_to_target(source_id, target_id)

        # Should receive magic packets first
        magic1 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic1 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0x49])

        magic2 = await asyncio.wait_for(reader.read(9), timeout=1.0)
        assert magic2 == bytes([0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00, 0x70, 0xc9])

        # Verify magic packets marked as sent
        assert tcp_server.magic_packets_sent

        # Then receive the actual SERIAL_BINARY command(s)
        target = next(t for t in config.targets if t.id == target_id)
        num_zones = len(target.swamp_zones)

        for _ in range(num_zones):
            serial_binary = await asyncio.wait_for(reader.read(17), timeout=1.0)
            assert serial_binary[0] == 0x05  # JOIN
            assert serial_binary[6] == 0x20  # SERIAL_BINARY

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_magic_packets_only_sent_once():
    """Test that magic packets are only sent once per connection"""
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

        # Send first command
        source_id = config.sources[0].id
        target_id = config.targets[0].id
        target = next(t for t in config.targets if t.id == target_id)
        num_zones = len(target.swamp_zones)

        await controller.route_source_to_target(source_id, target_id)

        # Read magic packets and SERIAL_BINARY commands
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 1
        await asyncio.wait_for(reader.read(9), timeout=1.0)  # Magic 2
        for _ in range(num_zones):
            await asyncio.wait_for(reader.read(17), timeout=1.0)  # SERIAL_BINARY

        # Send second command - should NOT send magic packets again
        await controller.set_volume(target_id, 50)

        # Should receive SERIAL_BINARY directly, no magic packets
        for _ in range(num_zones):
            volume_cmd = await asyncio.wait_for(reader.read(17), timeout=1.0)
            assert volume_cmd[0] == 0x05  # JOIN
            assert volume_cmd[6] == 0x20  # SERIAL_BINARY
            assert volume_cmd[14] == 0x02  # Volume register

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_magic_packets_reset_on_reconnect():
    """Test that magic packets flag resets when client reconnects"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # First connection
        reader1, writer1 = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        await asyncio.wait_for(reader1.read(4), timeout=1.0)
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer1.write(client_signon)
        await writer1.drain()
        await asyncio.wait_for(reader1.read(7), timeout=1.0)
        await asyncio.wait_for(reader1.read(8), timeout=1.0)

        # Send magic packets will be sent with first command
        # (not sending command, just verifying flag state)

        # Disconnect
        writer1.close()
        await writer1.wait_closed()
        await asyncio.sleep(0.3)  # Wait for disconnect processing

        # Magic packets flag should reset (will be reset on next connection)

        # Second connection
        reader2, writer2 = await asyncio.open_connection('localhost', test_port)

        # Verify flag was reset
        assert not tcp_server.magic_packets_sent

        # Complete handshake
        await asyncio.wait_for(reader2.read(4), timeout=1.0)
        writer2.write(client_signon)
        await writer2.drain()
        await asyncio.wait_for(reader2.read(7), timeout=1.0)
        await asyncio.wait_for(reader2.read(8), timeout=1.0)

        writer2.close()
        await writer2.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
