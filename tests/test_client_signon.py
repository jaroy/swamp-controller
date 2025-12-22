"""Test CLIENT_SIGNON and CONN_ACCEPTED"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_client_signon_conn_accepted():
    """Test that CLIENT_SIGNON triggers automatic CONN_ACCEPTED response"""
    test_port = get_free_port()

    config = ConfigManager.load(Path('config/config.yaml'))
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(test_port, protocol, state_manager)

    server_task = asyncio.create_task(tcp_server.start())
    await asyncio.sleep(0.3)

    try:
        reader, writer = await asyncio.open_connection('localhost', test_port)

        # Read WHOIS (sent automatically on connect)
        whois = await asyncio.wait_for(reader.read(4), timeout=1.0)
        assert whois == bytes([0x0f, 0x00, 0x01, 0x02])

        # Send CLIENT_SIGNON
        # 0a 00 0a 00 51 a3 42 40 02 00 00 00 00
        # Type: 0x0a, Length: 10, Payload: 00 51 a3 42 40 02 00 00 00 00
        client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
        writer.write(client_signon)
        await writer.drain()

        # Should receive CONN_ACCEPTED
        # 02 00 04 00 00 00 03
        # Type: 0x02, Length: 4, Payload: 00 00 00 03
        conn_accepted = await asyncio.wait_for(reader.read(7), timeout=1.0)
        assert conn_accepted == bytes([0x02, 0x00, 0x04, 0x00, 0x00, 0x00, 0x03])

        # Should also receive JOIN UPDATE (100ms after CONN_ACCEPTED)
        # 05 00 05 00 00 02 03 00
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)
        assert join_update == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00])

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
async def test_message_length_parsing():
    """Test that message lengths are parsed correctly"""
    protocol = SwampProtocol()

    # Test PING: 0d 00 02 00 00
    # Type: 0x0d, Length: 2, Payload: 00 00
    ping = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
    result = await protocol.decode_message(ping)
    assert result == {'type': 'ping'}

    # Test CLIENT_SIGNON with 10-byte payload
    client_signon = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
    result = await protocol.decode_message(client_signon)
    assert result['type'] == 'client_signon'
    assert len(bytes.fromhex(result['payload'])) == 10

    # Test incomplete message (should return None)
    incomplete = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51])  # Only 5 bytes, needs 13
    result = await protocol.decode_message(incomplete)
    assert result is None
