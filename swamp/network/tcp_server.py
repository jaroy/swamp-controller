import asyncio
import logging


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

    async def start(self):
        """Start TCP server listening on port"""
        self.server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port
        )

        addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f'TCP server listening on {addrs}')

        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming SWAMP device connection"""
        self.client_address = writer.get_extra_info('peername')
        logger.info(f'SWAMP device connected from {self.client_address}')

        self.client_writer = writer
        self.state_manager.state.connected = True

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    logger.info(f'Connection closed by {self.client_address}')
                    break

                logger.debug(f'Received {len(data)} bytes from SWAMP')

                try:
                    message = await self.protocol.decode_message(data)
                    if message:
                        await self.state_manager.update_from_device(message)
                except Exception as e:
                    logger.error(f'Error decoding message: {e}')

        except asyncio.CancelledError:
            logger.info('Connection handler cancelled')
        except Exception as e:
            logger.error(f'Error in connection handler: {e}')
        finally:
            self.state_manager.state.connected = False
            self.client_writer = None
            self.client_address = None
            writer.close()
            await writer.wait_closed()

    async def send_command(self, data: bytes):
        """Send command to connected SWAMP device"""
        if not self.client_writer:
            raise ConnectionError("No SWAMP device connected")

        try:
            self.client_writer.write(data)
            await self.client_writer.drain()
            logger.debug(f'Sent {len(data)} bytes to SWAMP')
        except Exception as e:
            logger.error(f'Error sending command: {e}')
            raise

    async def close(self):
        """Close the server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
