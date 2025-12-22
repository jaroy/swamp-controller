"""The SWAMP Controller integration."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.core.controller import SwampController
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer

from .const import CONF_CONFIG_FILE, CONF_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SWAMP Controller from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config_file = Path(entry.data[CONF_CONFIG_FILE])
    port = entry.data[CONF_PORT]

    _LOGGER.info("Setting up SWAMP Controller with config: %s, port: %d", config_file, port)

    try:
        # Load configuration
        config = ConfigManager.load(config_file)
        _LOGGER.info(
            "Loaded config: %d sources, %d targets",
            len(config.sources),
            len(config.targets),
        )
    except Exception as err:
        _LOGGER.error("Failed to load config: %s", err)
        raise ConfigEntryNotReady(f"Failed to load config: {err}") from err

    # Create core components
    protocol = SwampProtocol()
    state_manager = StateManager(config)
    tcp_server = SwampTcpServer(port, protocol, state_manager)
    controller = SwampController(config, tcp_server, state_manager)

    # Store controller and components in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "controller": controller,
        "tcp_server": tcp_server,
        "state_manager": state_manager,
        "config": config,
        "server_task": None,
    }

    # Start TCP server
    server_task = asyncio.create_task(tcp_server.start())
    hass.data[DOMAIN][entry.entry_id]["server_task"] = server_task

    _LOGGER.info("SWAMP Controller TCP server started on port %d", port)

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading SWAMP Controller")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Stop the TCP server
        data = hass.data[DOMAIN][entry.entry_id]
        tcp_server = data["tcp_server"]
        server_task = data["server_task"]

        # Close any active client connections
        if tcp_server.client_writer and not tcp_server.client_writer.is_closing():
            try:
                tcp_server.client_writer.close()
                await asyncio.wait_for(
                    tcp_server.client_writer.wait_closed(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for client connection to close")
            except Exception as err:
                _LOGGER.debug("Error closing client connection: %s", err)

        # Cancel server task
        if server_task:
            server_task.cancel()
            try:
                await asyncio.wait_for(server_task, timeout=2.0)
            except asyncio.CancelledError:
                _LOGGER.debug("Server task cancelled successfully")
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for server to close")
            except Exception as err:
                _LOGGER.debug("Error during server shutdown: %s", err)

        # Remove data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
