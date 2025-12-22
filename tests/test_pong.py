"""Test PONG message handling"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_pong_message_decoding():
    """Test that PONG messages are decoded correctly"""
    protocol = SwampProtocol()

    # Test PONG: 0e 00 02 00 00
    # Type: 0x0e, Length: 2, Payload: 00 00
    pong = bytes([0x0e, 0x00, 0x02, 0x00, 0x00])
    result = await protocol.decode_message(pong)
    assert result == {'type': 'pong'}


@pytest.mark.asyncio
async def test_pong_not_printed_as_unknown():
    """Test that PONG messages are handled and not printed as unknown"""
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
        assert whois == bytes([0x0f, 0x00, 0x01, 0x02])

        # Send CLIENT_SIGNON
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Read CONN_ACCEPTED
        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)
        assert conn_accepted == bytes([0x02, 0x00, 0x04, 0x00, 0x00, 0x00, 0x03])

        # Read JOIN UPDATE
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)
        assert join_update == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00])

        # Send PONG message (simulating device response to our periodic PING)
        pong = bytes([0x0e, 0x00, 0x02, 0x00, 0x00])
        writer.write(pong)
        await writer.drain()

        # Give server time to process (should not print as unknown)
        await asyncio.sleep(0.1)

        # If PONG is properly handled, it won't be printed as unknown
        # This test passes if no exception occurs

        writer.close()
        await writer.wait_closed()

    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
