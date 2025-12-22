"""Integration tests for SWAMP controller"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.core.controller import SwampController
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_ping_pong():
    """Test PING/PONG exchange"""
    # Use a free port for testing, NOT the default 41794
    test_port = get_free_port()

    # Setup
    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    # Start server
    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)  # Wait for server to start

    try:
        # Connect as client
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)
        assert whois == bytes([0x0f, 0x00, 0x01, 0x02])

        # Send PING
        ping = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
        writer.write(ping)
        await writer.drain()

        # Receive PONG
        pong = await asyncio.wait_for(reader.read(5), timeout=1.0)
        assert pong == bytes([0x0e, 0x00, 0x02, 0x00, 0x00])

        writer.close()
        await writer.wait_closed()

    finally:
        # Cleanup
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await tcp_server.close()


@pytest.mark.asyncio
async def test_whois_on_connect():
    """Test that WHOIS is sent automatically on connection"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Should receive WHOIS immediately
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)
        assert whois == bytes([0x0f, 0x00, 0x01, 0x02])

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await tcp_server.close()


@pytest.mark.asyncio
async def test_message_type_dispatcher():
    """Test that messages are dispatched by type"""
    protocol = SwampProtocol()

    # Test PING (0x0d)
    ping = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
    result = await protocol.decode_message(ping)
    assert result == {'type': 'ping'}

    # Test CLIENT_SIGNON (0x0a)
    client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
    result = await protocol.decode_message(client_signon)
    assert result['type'] == 'client_signon'
    assert 'payload' in result

    # Test completely unknown type
    unknown = bytes([0xff, 0x00, 0x02, 0xaa, 0xbb])
    result = await protocol.decode_message(unknown)
    assert result is None

    # Test incomplete message (should return None)
    incomplete = bytes([0x0a, 0x00, 0x0a])
    result = await protocol.decode_message(incomplete)
    assert result is None
