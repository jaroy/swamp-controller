"""Test JOIN UPDATE message"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port


@pytest.mark.asyncio
async def test_join_update_after_conn_accepted():
    """Test that JOIN UPDATE is sent 100ms after CONN_ACCEPTED"""
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

        # Read JOIN UPDATE (should arrive ~100ms after CONN_ACCEPTED)
        join_update = await asyncio.wait_for(reader.read(8), timeout=1.0)
        assert join_update == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00]), \
            f"Expected JOIN UPDATE but got: {' '.join(f'{b:02x}' for b in join_update)}"

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
async def test_join_update_encoding():
    """Test that JOIN UPDATE message is encoded correctly"""
    protocol = SwampProtocol()

    # Test with default payload (0x00)
    join_update = await protocol.encode_join_update()
    assert join_update == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00])

    # Test with custom payload
    join_update_custom = await protocol.encode_join_update(0x42)
    assert join_update_custom == bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x42])


@pytest.mark.asyncio
async def test_join_message_decoding():
    """Test that JOIN messages are decoded correctly"""
    protocol = SwampProtocol()

    # JOIN UPDATE message
    join_update_msg = bytes([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00])
    result = await protocol.decode_message(join_update_msg)

    assert result is not None
    assert result['type'] == 'join'
    assert result['join_type'] == 'update'
    assert result['join_data'] == '00'
