"""The SWAMP Controller integration."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from swamp.core.config_manager import ConfigManager
from swamp.core.state_manager import StateManager
from swamp.core.controller import SwampController
from swamp.protocol.swamp_protocol import SwampProtocol
from swamp.network.tcp_server import SwampTcpServer

from .const import CONF_CONFIG_FILE, CONF_PORT, DEFAULT_ZONE_VOLUME, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


def _load_raw_yaml(path: Path) -> dict:
    """Load the config YAML as a plain dict (for keys ConfigManager doesn't parse)."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


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

    # Power-on default volume: global `default-volume`, overridable per target.
    # (These keys are ignored by ConfigManager, so we parse the raw YAML for them.)
    try:
        raw = await hass.async_add_executor_job(_load_raw_yaml, config_file)
    except Exception as err:  # pragma: no cover - already validated above
        raise ConfigEntryNotReady(f"Failed to load config: {err}") from err

    global_default_volume = raw.get("default-volume", DEFAULT_ZONE_VOLUME)
    target_default_volumes = {
        t["id"]: t["default-volume"]
        for t in raw.get("targets", [])
        if "default-volume" in t
    }

    # Optional per-source `upstream-player`: the HA media_player entity that actually
    # renders that source's audio into the SWAMP input (e.g. the Music Assistant
    # player). When a zone is routed to such a source, the zone entity proxies that
    # player's transport state, now-playing metadata, and playback controls.
    # (Also a ConfigManager-ignored key, so parse it from the raw YAML.) Keyed by
    # swamp-source-id to match `ZoneState.source_id`.
    source_upstream_players = {
        s["swamp-source-id"]: s["upstream-player"]
        for s in raw.get("sources", [])
        if s.get("upstream-player")
    }
    _LOGGER.debug("Source upstream players (swamp_source_id -> entity): %s", source_upstream_players)

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
        "zone_default_volume": global_default_volume,
        "zone_default_volumes": target_default_volumes,
        "source_upstream_players": source_upstream_players,
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
