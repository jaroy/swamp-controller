"""Test server shutdown behavior"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_shutdown_with_connected_client():
    """Test that server shuts down gracefully even with connected client"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    # Start server
    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Connect client
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS
        await asyncio.wait_for(reader.read(4), timeout=1.0)

        # Send CLIENT_SIGNON
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED and JOIN UPDATE
        await asyncio.wait_for(reader.read(7), timeout=1.0)  # CONN_ACCEPTED
        await asyncio.wait_for(reader.read(8), timeout=1.0)  # JOIN UPDATE

        # Verify client is connected
        assert tcp_server.client_writer is not None
        assert state_manager.state.socket_connected

        # Now simulate shutdown - close client connection first
        if tcp_server.client_writer and not tcp_server.client_writer.is_closing():
            tcp_server.client_writer.close()
            await asyncio.wait_for(tcp_server.client_writer.wait_closed(), timeout=1.0)

        # Cancel server task
        server_task.cancel()

        # Should complete within timeout
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except asyncio.CancelledError:
            pass  # Expected

        # Close our client connection
        writer.close()
        await writer.wait_closed()

    except asyncio.TimeoutError:
        pytest.fail("Shutdown timed out - server is hanging")
    finally:
        # Cleanup
        if not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_shutdown_without_client():
    """Test that server shuts down gracefully without any connected client"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    # Start server
    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Verify no client connected
        assert tcp_server.client_writer is None

        # Cancel server task
        server_task.cancel()

        # Should complete within timeout
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except asyncio.CancelledError:
            pass  # Expected

    except asyncio.TimeoutError:
        pytest.fail("Shutdown timed out - server is hanging")
    finally:
        # Cleanup
        if not server_task.done():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
