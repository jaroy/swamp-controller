import asyncio
import logging
from datetime import datetime


logger = logging.getLogger(__name__)


class SwampTcpServer:
    """Manages TCP server accepting connections from SWAMP device"""

    def __init__(self, port: int, protocol_handler, state_manager):
        self.port = port
        self.protocol = protocol_handler
        self.state_manager = state_manager
        self.server = None
        self.client_writer = None
        self.client_address = None
        self.client_handler_task = None
        self.magic_packets_sent = False

    async def start(self):
        """Start TCP server listening on port"""
        self.server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port
        )

        addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f'TCP server listening on {addrs}')

        try:
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            logger.info('Server task cancelled, shutting down')
            raise

    async def _periodic_ping(self, writer: asyncio.StreamWriter):
        """Send PING every 10 seconds"""
        try:
            while True:
                await asyncio.sleep(10)
                if self.state_manager.state.socket_connected:
                    try:
                        ping_bytes = await self.protocol.encode_pong()  # PONG structure is same as PING
                        # Actually encode PING (0x0d)
                        ping_bytes = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
                        writer.write(ping_bytes)
                        await writer.drain()
                        logger.debug('Sent periodic PING')
                    except Exception as e:
                        logger.error(f'Error sending periodic PING: {e}')
                        break
        except asyncio.CancelledError:
            logger.debug('Periodic PING task cancelled')

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming SWAMP device connection"""
        self.client_address = writer.get_extra_info('peername')
        logger.info(f'SWAMP device connected from {self.client_address}')

        self.client_writer = writer

        # Update state
        self.state_manager.state.socket_connected = True
        self.state_manager.state.client_address = str(self.client_address)
        self.state_manager.state.conn_accepted_sent = False
        self.magic_packets_sent = False  # Reset for new connection

        # Send WHOIS automatically on connection
        try:
            whois_bytes = await self.protocol.encode_whois()
            writer.write(whois_bytes)
            await writer.drain()
            logger.info(f'Sent WHOIS to {self.client_address}')
        except Exception as e:
            logger.error(f'Error sending WHOIS: {e}')

        # Start periodic PING task
        ping_task = asyncio.create_task(self._periodic_ping(writer))

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    logger.info(f'Connection closed by {self.client_address}')
                    break

                logger.debug(f'Received {len(data)} bytes from SWAMP')

                # Update last message received time
                self.state_manager.state.last_message_received = datetime.now()

                try:
                    message = await self.protocol.decode_message(data)
                    if message:
                        msg_type = message.get('type')

                        # Handle PING with automatic PONG response
                        if msg_type == 'ping':
                            logger.debug('Received PING, sending PONG')
                            pong_bytes = await self.protocol.encode_pong()
                            writer.write(pong_bytes)
                            await writer.drain()
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
                            writer.write(conn_accepted_bytes)
                            await writer.drain()
                            self.state_manager.state.conn_accepted_sent = True
                            logger.info('Sent CONN_ACCEPTED - connection established')

                            # Send JOIN UPDATE 100ms later
                            await asyncio.sleep(0.1)
                            join_update_bytes = await self.protocol.encode_join_update()
                            writer.write(join_update_bytes)
                            await writer.drain()
                            logger.info('Sent JOIN UPDATE')
                        # Handle recognized but not-yet-implemented message types
                        elif msg_type and msg_type.startswith('unknown_'):
                            hex_str = ' '.join(f'{b:02x}' for b in data)
                            print(f'Recognized but unimplemented message type {data[0]:02x} ({len(data)} bytes): {hex_str}')
                            logger.info(f'Message type {data[0]:02x}: {hex_str}')
                        else:
                            # Update state for other messages
                            await self.state_manager.update_from_device(message)
                    else:
                        # Message not recognized at all - print raw bytes
                        hex_str = ' '.join(f'{b:02x}' for b in data)
                        print(f'Unknown message type {data[0]:02x} ({len(data)} bytes): {hex_str}')
                        logger.warning(f'Unknown message type {data[0]:02x}: {hex_str}')
                except Exception as e:
                    # Error during decoding - print raw bytes
                    hex_str = ' '.join(f'{b:02x}' for b in data)
                    print(f'Failed to decode message ({len(data)} bytes): {hex_str}')
                    logger.error(f'Error decoding message: {e} - Raw data: {hex_str}')

        except asyncio.CancelledError:
            logger.info('Connection handler cancelled')
        except Exception as e:
            logger.error(f'Error in connection handler: {e}')
        finally:
            # Cancel periodic PING
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

            # Reset connection state
            self.state_manager.state.socket_connected = False
            self.state_manager.state.conn_accepted_sent = False
            self.state_manager.state.client_address = None
            self.client_writer = None
            self.client_address = None
            writer.close()
            await writer.wait_closed()

    async def send_command(self, data: bytes):
        """Send command to connected SWAMP device

        Automatically sends magic DIGITAL JOIN packets before first SERIAL_BINARY message.
        """
        if not self.client_writer:
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

            self.client_writer.write(msg1)
            await self.client_writer.drain()
            logger.debug('Sent magic packet 1')

            self.client_writer.write(msg2)
            await self.client_writer.drain()
            logger.debug('Sent magic packet 2')

            # Wait 100ms after sending magic packets
            await asyncio.sleep(0.1)

            self.magic_packets_sent = True
            logger.info('Magic packets sent, ready for SERIAL_BINARY commands')

        try:
            self.client_writer.write(data)
            await self.client_writer.drain()
            logger.debug(f'Sent {len(data)} bytes to SWAMP')
        except Exception as e:
            logger.error(f'Error sending command: {e}')
            raise

    async def close(self):
        """Close the server"""
        # Close any active client connection
        if self.client_writer:
            try:
                self.client_writer.close()
                await self.client_writer.wait_closed()
            except Exception as e:
                logger.debug(f'Error closing client connection: {e}')

        # Close the server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
