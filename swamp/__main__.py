import argparse
import asyncio
import logging
from pathlib import Path

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.core.controller import SwampController
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer
from swamp.shell.parser import CommandParser
from swamp.shell.commands import CommandHandlers
from swamp.shell.repl import InteractiveShell


def setup_logging(level: str):
    """Setup logging configuration"""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def main_async():
    """Main async entry point"""
    parser = argparse.ArgumentParser(description='SWAMP Media Controller')
    parser.add_argument('--port', type=int, default=41794,
                       help='TCP port to listen on for SWAMP device (default: 41794)')
    parser.add_argument('--config', type=Path,
                       default=Path('config/config.yaml'),
                       help='Path to configuration file (default: config/config.yaml)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Logging level (default: INFO)')

    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    logger.info('Starting SWAMP Controller')

    try:
        config = ConfigManager.load(args.config)
        logger.info(f'Loaded config: {len(config.sources)} sources, {len(config.targets)} targets')
    except Exception as e:
        logger.error(f'Failed to load config: {e}')
        return 1

    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(args.port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    cmd_parser = CommandParser()
    handlers = CommandHandlers(controller)

    cmd_parser.register('route', handlers.cmd_route)
    cmd_parser.register('volume', handlers.cmd_volume)
    cmd_parser.register('power', handlers.cmd_power)
    cmd_parser.register('status', handlers.cmd_status)
    cmd_parser.register('whois', handlers.cmd_whois)
    cmd_parser.register('list', handlers.cmd_list)
    cmd_parser.register('help', handlers.cmd_help)

    shell = InteractiveShell(cmd_parser, handlers)

    print(f"SWAMP Controller v0.1.0")
    print(f"Listening for SWAMP device on port {args.port}")
    print(f"Type 'help' for available commands\n")

    server_task = asyncio.create_task(tcp_server.start())

    try:
        await shell.run()
    except KeyboardInterrupt:
        logger.info('Interrupted by user')
    finally:
        logger.info('Shutting down')
        # Close any active client connections first
        if tcp_server.client_writer and not tcp_server.client_writer.is_closing():
            try:
                tcp_server.client_writer.close()
                await asyncio.wait_for(
                    tcp_server.client_writer.wait_closed(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                logger.warning('Timeout waiting for client connection to close')
            except Exception as e:
                logger.debug(f'Error closing client connection: {e}')

        # Cancel server task (the async with context will close the server)
        server_task.cancel()
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except asyncio.CancelledError:
            logger.debug('Server task cancelled successfully')
        except asyncio.TimeoutError:
            logger.warning('Timeout waiting for server to close')
        except Exception as e:
            logger.debug(f'Error during server shutdown: {e}')

    return 0


def main():
    """Main entry point"""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    exit(main())
