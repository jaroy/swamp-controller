"""Test recovery from stale / replaced device connections, and message framing"""

import asyncio
import pytest
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network import tcp_server as tcp_server_module
from swamp.network.tcp_server import SwampTcpServer
from tests.test_helpers import get_free_port

CLIENT_SIGNON = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
PING = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
PONG = bytes([0x0e, 0x00, 0x02, 0x00, 0x00])


async def start_server():
    port = get_free_port()
    state_manager = StateManager(ConfigManager.load(Path('config/config.yaml')))
    server = SwampTcpServer(port, SwampProtocol(), state_manager)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)
    return port, server, state_manager.state, task


async def stop_server(task):
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except asyncio.CancelledError:
        pass


async def connect_and_sign_on(port):
    reader, writer = await asyncio.open_connection('localhost', port)
    await asyncio.wait_for(reader.readexactly(4), timeout=1.0)  # WHOIS
    writer.write(CLIENT_SIGNON)
    await writer.drain()
    await asyncio.wait_for(reader.readexactly(7), timeout=1.0)  # CONN_ACCEPTED
    await asyncio.wait_for(reader.readexactly(8), timeout=1.0)  # JOIN UPDATE
    return reader, writer


async def assert_closed_by_server(reader):
    """The server dropped the connection: we see EOF or a reset."""
    try:
        data = await asyncio.wait_for(reader.read(100), timeout=2.0)
        assert data == b''
    except ConnectionResetError:
        pass


@pytest.mark.asyncio
async def test_old_connection_dying_does_not_clobber_new_one():
    """A replaced connection ending later must not mark the live one disconnected"""
    port, server, state, task = await start_server()
    try:
        reader_a, writer_a = await connect_and_sign_on(port)
        reader_b, writer_b = await connect_and_sign_on(port)

        # The new connection replaces the old one, which the server drops
        await assert_closed_by_server(reader_a)
        writer_a.transport.abort()
        await asyncio.sleep(0.2)

        assert state.connected
        assert server.client_writer is not None
        assert state.connections == 2
        assert state.last_disconnected is None  # the live connection never dropped

        # The live connection still works
        writer_b.write(PING)
        await writer_b.drain()
        assert await asyncio.wait_for(reader_b.readexactly(5), timeout=1.0) == PONG
        writer_b.close()
    finally:
        await stop_server(task)


@pytest.mark.asyncio
async def test_stop_drops_live_connection_promptly():
    """Shutdown must not wait on the device to close its side"""
    port, server, state, task = await start_server()
    reader, writer = await connect_and_sign_on(port)

    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=3.0)
    except asyncio.CancelledError:
        pass

    await assert_closed_by_server(reader)
    assert not server.is_listening
    assert not state.connected
    assert state.last_disconnect_reason == 'server stopped'


@pytest.mark.asyncio
async def test_stale_connection_is_dropped(monkeypatch):
    """A connection that goes silent is dropped so the device reconnects"""
    monkeypatch.setattr(tcp_server_module, 'PING_INTERVAL', 0.1)
    monkeypatch.setattr(tcp_server_module, 'STALE_TIMEOUT', 0.5)
    port, server, state, task = await start_server()
    try:
        reader, writer = await connect_and_sign_on(port)
        assert state.connected

        # Never answer the server's PINGs
        await asyncio.sleep(1.0)

        assert not state.socket_connected
        assert state.last_disconnect_reason.startswith('stale')
        writer.transport.abort()
    finally:
        await stop_server(task)


@pytest.mark.asyncio
async def test_messages_split_and_coalesced_across_reads():
    """Messages are framed by their length header, not by read boundaries"""
    port, server, state, task = await start_server()
    try:
        reader, writer = await asyncio.open_connection('localhost', port)
        await asyncio.wait_for(reader.readexactly(4), timeout=1.0)  # WHOIS

        # CLIENT_SIGNON split across two writes
        writer.write(CLIENT_SIGNON[:5])
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.write(CLIENT_SIGNON[5:])
        await writer.drain()
        await asyncio.wait_for(reader.readexactly(7), timeout=1.0)  # CONN_ACCEPTED
        await asyncio.wait_for(reader.readexactly(8), timeout=1.0)  # JOIN UPDATE
        assert state.connected

        # Two PINGs in one write -> two PONGs
        writer.write(PING + PING)
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(10), timeout=1.0) == PONG + PONG
        assert state.undecoded_messages == 0
        writer.close()
    finally:
        await stop_server(task)
