import asyncio
import logging
from datetime import datetime


logger = logging.getLogger(__name__)

# How often we PING the device. It answers each one, so a live connection never goes
# quiet for longer than this.
PING_INTERVAL = 10

# Drop the connection if nothing at all has been received for this long. The device
# only reconnects when it sees its socket close, so a half-open (stale) connection
# would otherwise leave every zone unavailable indefinitely.
STALE_TIMEOUT = 60

# Give up on a write that can't drain within this long (dead peer, full send buffer).
DRAIN_TIMEOUT = 5

# Message header: type (1 byte) + big-endian length of the rest (2 bytes).
HEADER_LEN = 3


class SwampTcpServer:
    """Manages TCP server accepting connections from SWAMP device

    The device holds a single connection open to us. If it reconnects, the new
    connection replaces (and drops) the old one; only the current connection may
    change the shared connection state.
    """

    def __init__(self, port: int, protocol_handler, state_manager):
        self.port = port
        self.protocol = protocol_handler
        self.state_manager = state_manager
        self.server = None
        self.client_writer = None
        self.client_address = None
        self.client_handler_task = None
        self.magic_packets_sent = False
        # Every open connection -> its handler task (normally just the current one).
        self._connections: dict[asyncio.StreamWriter, asyncio.Task] = {}
        # Why we dropped a connection, recorded just before aborting it.
        self._close_reasons: dict[asyncio.StreamWriter, str] = {}

    @property
    def is_listening(self) -> bool:
        """True while the server is accepting connections."""
        return self.server is not None and self.server.is_serving()

    async def start(self):
        """Start TCP server listening on port; runs until cancelled."""
        self.server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port
        )

        addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f'TCP server listening on {addrs}')

        try:
            # Not serve_forever(): on cancel it waits for every connection to close
            # gracefully, which never happens with a stale one.
            await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            logger.info('Server task cancelled, shutting down')
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop listening and forcibly drop every connection. Safe to call repeatedly."""
        if self.server is not None:
            self.server.close()

        for writer in list(self._connections):
            self._drop(writer, 'server stopped')

        tasks = [t for t in self._connections.values() if t is not asyncio.current_task()]
        if tasks:
            await asyncio.wait(tasks, timeout=2.0)

        if self.server is not None:
            try:
                await asyncio.wait_for(self.server.wait_closed(), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning('Timeout waiting for server to close')

    async def close(self):
        """Close the server (alias for stop)."""
        await self.stop()

    def _drop(self, writer: asyncio.StreamWriter, reason: str) -> None:
        """Abort a connection immediately (RST, no graceful flush)."""
        self._close_reasons.setdefault(writer, reason)
        writer.transport.abort()

    async def _write(self, writer: asyncio.StreamWriter, data: bytes) -> None:
        """Write and drain, dropping the connection if the peer stops accepting data."""
        writer.write(data)
        try:
            await asyncio.wait_for(writer.drain(), timeout=DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            self._drop(writer, f'write stalled for {DRAIN_TIMEOUT}s')
            raise ConnectionError('SWAMP connection stalled')

    async def _periodic_ping(self, writer: asyncio.StreamWriter):
        """Send PING every PING_INTERVAL seconds; drop the connection if it goes stale."""
        state = self.state_manager.state
        ping_bytes = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
        try:
            while self.client_writer is writer:
                await asyncio.sleep(PING_INTERVAL)
                if self.client_writer is not writer:
                    break

                last = state.last_message_received or state.last_connected
                if last and (datetime.now() - last).total_seconds() > STALE_TIMEOUT:
                    logger.warning(
                        f'No data from SWAMP for over {STALE_TIMEOUT}s; '
                        'dropping connection so it reconnects'
                    )
                    self._drop(writer, f'stale: no data for {STALE_TIMEOUT}s')
                    break
                connected_for = (datetime.now() - state.last_connected).total_seconds()
                if not state.conn_accepted_sent and connected_for > STALE_TIMEOUT:
                    logger.warning(
                        f'SWAMP never signed on within {STALE_TIMEOUT}s; '
                        'dropping connection so it reconnects'
                    )
                    self._drop(writer, f'no sign-on within {STALE_TIMEOUT}s')
                    break

                try:
                    await self._write(writer, ping_bytes)
                    logger.debug('Sent periodic PING')
                except Exception as e:
                    logger.error(f'Error sending periodic PING: {e}')
                    self._drop(writer, f'ping failed: {e}')
                    break
        except asyncio.CancelledError:
            logger.debug('Periodic PING task cancelled')

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming SWAMP device connection"""
        address = writer.get_extra_info('peername')
        logger.info(f'SWAMP device connected from {address}')

        # The device only keeps one connection; a new one means any old one is dead.
        for old in list(self._connections):
            logger.warning(f'New SWAMP connection from {address}; dropping previous connection')
            self._drop(old, 'replaced by new connection')

        self._connections[writer] = asyncio.current_task()
        self.client_writer = writer
        self.client_address = address

        # Update state
        state = self.state_manager.state
        state.socket_connected = True
        state.client_address = f'{address[0]}:{address[1]}' if address else None
        state.conn_accepted_sent = False
        state.last_message_received = None
        state.last_connected = datetime.now()
        state.connections += 1
        self.magic_packets_sent = False  # Reset for new connection

        # Send WHOIS automatically on connection
        try:
            whois_bytes = await self.protocol.encode_whois()
            await self._write(writer, whois_bytes)
            logger.info(f'Sent WHOIS to {address}')
        except Exception as e:
            logger.error(f'Error sending WHOIS: {e}')

        # Start periodic PING task
        ping_task = asyncio.create_task(self._periodic_ping(writer))

        reason = 'closed by device'
        buffer = b''
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    logger.info(f'Connection closed by {address}')
                    break

                logger.debug(f'Received {len(data)} bytes from SWAMP')

                if self.client_writer is writer:
                    state.last_message_received = datetime.now()

                # TCP is a byte stream: one read may hold several messages, or part of
                # one. Split on the length header and keep any remainder for next time.
                buffer += data
                while len(buffer) >= HEADER_LEN:
                    total = HEADER_LEN + int.from_bytes(buffer[1:3], 'big')
                    if len(buffer) < total:
                        break
                    message_bytes, buffer = buffer[:total], buffer[total:]
                    await self._handle_message(message_bytes, writer)

        except asyncio.CancelledError:
            logger.info('Connection handler cancelled')
        except Exception as e:
            logger.error(f'Error in connection handler: {e}')
            reason = f'error: {e}'
        finally:
            # Cancel periodic PING
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

            reason = self._close_reasons.pop(writer, reason)
            self._connections.pop(writer, None)

            # Only the current connection owns the shared state. A replaced (stale)
            # connection dying later must not mark the live one as disconnected.
            if self.client_writer is writer:
                state.socket_connected = False
                state.conn_accepted_sent = False
                state.client_address = None
                state.last_disconnected = datetime.now()
                state.last_disconnect_reason = reason
                self.client_writer = None
                self.client_address = None
            logger.info(f'SWAMP connection from {address} ended: {reason}')

            writer.transport.abort()

    async def _handle_message(self, data: bytes, writer: asyncio.StreamWriter) -> None:
        """Decode and act on one complete message from the device."""
        state = self.state_manager.state
        try:
            message = await self.protocol.decode_message(data)
            if message:
                msg_type = message.get('type')

                # Handle PING with automatic PONG response
                if msg_type == 'ping':
                    logger.debug('Received PING, sending PONG')
                    pong_bytes = await self.protocol.encode_pong()
                    await self._write(writer, pong_bytes)
                # Handle PONG (response to our periodic PING)
                elif msg_type == 'pong':
                    logger.debug('Received PONG')
                # Handle JOIN messages from device
                elif msg_type == 'join':
                    join_type = message.get('join_type', 'unknown')
                    if join_type == 'serial_binary':
                        # Update state from SERIAL_BINARY register data
                        unit = message.get('unit')
                        zone = message.get('zone')
                        register = message.get('register')
                        value = message.get('value')

                        if unit is not None and zone is not None and register and value is not None:
                            logger.info(f'Unit {unit} Zone {zone}: {register} = {value}')
                            await self.state_manager.update_from_device(message)
                        else:
                            logger.debug(f'Received JOIN (serial_binary) - incomplete data')
                    else:
                        logger.debug(f'Received JOIN ({join_type})')
                # Handle CLIENT_SIGNON with automatic CONN_ACCEPTED response
                elif msg_type == 'client_signon':
                    logger.info(f'Received CLIENT_SIGNON: {message.get("payload")}')
                    conn_accepted_bytes = await self.protocol.encode_conn_accepted()
                    await self._write(writer, conn_accepted_bytes)
                    if self.client_writer is writer:
                        state.conn_accepted_sent = True
                    logger.info('Sent CONN_ACCEPTED - connection established')

                    # Send JOIN UPDATE 100ms later
                    await asyncio.sleep(0.1)
                    join_update_bytes = await self.protocol.encode_join_update()
                    await self._write(writer, join_update_bytes)
                    logger.info('Sent JOIN UPDATE')
                # Handle recognized but not-yet-implemented message types
                elif msg_type and msg_type.startswith('unknown_'):
                    state.undecoded_messages += 1
                    hex_str = ' '.join(f'{b:02x}' for b in data)
                    print(f'Recognized but unimplemented message type {data[0]:02x} ({len(data)} bytes): {hex_str}')
                    logger.info(f'Message type {data[0]:02x}: {hex_str}')
                else:
                    # Update state for other messages
                    await self.state_manager.update_from_device(message)
            else:
                # Message not recognized at all - print raw bytes
                state.undecoded_messages += 1
                hex_str = ' '.join(f'{b:02x}' for b in data)
                print(f'Unknown message type {data[0]:02x} ({len(data)} bytes): {hex_str}')
                logger.warning(f'Unknown message type {data[0]:02x}: {hex_str}')
        except ConnectionError:
            raise
        except Exception as e:
            # Error during decoding - print raw bytes
            state.undecoded_messages += 1
            hex_str = ' '.join(f'{b:02x}' for b in data)
            print(f'Failed to decode message ({len(data)} bytes): {hex_str}')
            logger.error(f'Error decoding message: {e} - Raw data: {hex_str}')

    async def send_command(self, data: bytes):
        """Send command to connected SWAMP device

        Automatically sends magic DIGITAL JOIN packets before first SERIAL_BINARY message.
        """
        writer = self.client_writer
        if not writer:
            raise ConnectionError("No SWAMP device connected")

        # Check if this is a SERIAL_BINARY message (JOIN type 0x05, join type 0x20)
        is_serial_binary = (
            len(data) >= 7 and
            data[0] == 0x05 and  # JOIN message
            data[6] == 0x20       # SERIAL_BINARY join type
        )

        # Send magic packets before first SERIAL_BINARY message
        if is_serial_binary and not self.magic_packets_sent:
            logger.info('Sending magic DIGITAL JOIN packets')
            msg1, msg2 = self.protocol.encode_join_digital_magic()

            await self._write(writer, msg1)
            logger.debug('Sent magic packet 1')

            await self._write(writer, msg2)
            logger.debug('Sent magic packet 2')

            # Wait 100ms after sending magic packets
            await asyncio.sleep(0.1)

            self.magic_packets_sent = True
            logger.info('Magic packets sent, ready for SERIAL_BINARY commands')

        try:
            await self._write(writer, data)
            logger.debug(f'Sent {len(data)} bytes to SWAMP')
        except Exception as e:
            logger.error(f'Error sending command: {e}')
            raise
