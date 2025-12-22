"""Test complete SWAMP connection handshake"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_complete_handshake():
    """Test the complete connection handshake sequence

    1. Device connects
    2. Controller sends WHOIS
    3. Device sends CLIENT_SIGNON
    4. Controller sends CONN_ACCEPTED
    5. Controller sends JOIN UPDATE (100ms later)
    6. Device sends PING
    7. Controller sends PONG
    """
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        # Step 1: Device connects
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Step 2: Controller sends WHOIS
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)
        assert whois == bytes([0x0f, 0x00, 0x01, 0x02]), "Should receive WHOIS"

        # Step 3: Device sends CLIENT_SIGNON
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Step 4: Controller sends CONN_ACCEPTED
        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)
        assert conn_accepted == bytes([0x02, 0x00, 0x04, 0x00, 0x00, 0x00, 0x03]), "Should receive CONN_ACCEPTED"

        # Step 5: Controller sends JOIN UPDATE (100ms after CONN_ACCEPTED)
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)
        assert join_update == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00]), "Should receive JOIN UPDATE"

        # Step 6: Device sends PING
        ping = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
        writer.write(ping)
        await writer.drain()

        # Step 7: Controller sends PONG
        pong = await asyncio.wait_for(reader.read(5), timeout=1.0)
        assert pong == bytes([0x0e, 0x00, 0x02, 0x00, 0x00]), "Should receive PONG"

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        await tcp_server.close()
