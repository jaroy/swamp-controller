"""Test connection status and periodic PING"""

import asyncio
import pytest
from pathlib import Path
from datetime import datetime

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_connection_status_tracking():
    """Test that connection status is tracked correctly"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Initially not connected
        assert not state_manager.state.connected

        # Connect
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Socket connected but not fully connected yet
        await asyncio.sleep(0.1)
        assert state_manager.state.socket_connected
        assert not state_manager.state.conn_accepted_sent
        assert not state_manager.state.connected  # Not fully connected yet

        # Read WHOIS
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)

        # Send CLIENT_SIGNON
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED
        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)

        # Read JOIN UPDATE (sent 100ms after CONN_ACCEPTED)
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Now fully connected
        assert state_manager.state.socket_connected
        assert state_manager.state.conn_accepted_sent
        assert state_manager.state.last_message_received is not None
        assert state_manager.state.connected  # Fully connected!

        writer.close()
        await writer.wait_closed()

        # After disconnect
        await asyncio.sleep(0.2)
        assert not state_manager.state.socket_connected
        assert not state_manager.state.connected

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await tcp_server.close()


@pytest.mark.asyncio
async def test_periodic_ping():
    """Test that periodic PING is sent every 10 seconds"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)

        # Send CLIENT_SIGNON to complete handshake
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED
        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)

        # Read JOIN UPDATE (sent 100ms after CONN_ACCEPTED)
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Wait for first periodic PING (should arrive in ~10 seconds, we'll wait 11)
        # Note: We wait a bit less for the test to run faster
        await asyncio.sleep(10.5)

        # Try to read PING
        ping = await asyncio.wait_for(reader.read(5), timeout=2.0)
        assert ping == bytes([0x0d, 0x00, 0x02, 0x00, 0x00]), "Should receive periodic PING"

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
async def test_connection_timeout():
    """Test that connection is considered disconnected if no message for 30s"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Complete handshake
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)

        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)

        # Read JOIN UPDATE (sent 100ms after CONN_ACCEPTED)
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)

        # Should be connected now
        assert state_manager.state.connected

        # Manually set last message to 31 seconds ago
        from datetime import timedelta
        state_manager.state.last_message_received = datetime.now() - timedelta(seconds=31)

        # Check connection status - should be disconnected now
        assert not state_manager.state.connected

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await tcp_server.close()
