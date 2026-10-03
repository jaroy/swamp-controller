"""Diagnostic sensors for the SWAMP Controller connection."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from swamp.models.state import DeviceState
from swamp.network.tcp_server import SwampTcpServer

from .const import DOMAIN

# Connection state lives in plain Python objects with no change callbacks; poll it.
SCAN_INTERVAL = timedelta(seconds=10)

CONNECTION_STATUSES = [
    "connected",
    "signing_on",
    "waiting_for_device",
    "stale",
    "server_down",
]


def _connection_status(server: SwampTcpServer, state: DeviceState) -> str:
    """Summarize where the connection is in its lifecycle."""
    if not server.is_listening:
        return "server_down"
    if not state.socket_connected:
        return "waiting_for_device"
    if not state.conn_accepted_sent:
        return "signing_on"
    if state.connected:
        return "connected"
    return "stale"  # socket open and signed on, but nothing received recently


def _timestamp(value: datetime | None) -> datetime | None:
    """The library records naive local times; HA needs them timezone-aware."""
    return value.astimezone() if value else None


@dataclass(frozen=True, kw_only=True)
class SwampSensorDescription(SensorEntityDescription):
    """Describes a SWAMP diagnostic sensor."""

    value_fn: Callable[[SwampTcpServer, DeviceState], Any]


SENSORS: tuple[SwampSensorDescription, ...] = (
    SwampSensorDescription(
        key="connection_status",
        name="Connection status",
        device_class=SensorDeviceClass.ENUM,
        options=CONNECTION_STATUSES,
        value_fn=_connection_status,
    ),
    SwampSensorDescription(
        key="device_address",
        name="Device address",
        value_fn=lambda server, state: state.client_address,
    ),
    SwampSensorDescription(
        key="last_message",
        name="Last message received",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda server, state: _timestamp(state.last_message_received),
    ),
    SwampSensorDescription(
        key="last_connected",
        name="Last connected",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda server, state: _timestamp(state.last_connected),
    ),
    SwampSensorDescription(
        key="last_disconnected",
        name="Last disconnected",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda server, state: _timestamp(state.last_disconnected),
    ),
    SwampSensorDescription(
        key="last_disconnect_reason",
        name="Last disconnect reason",
        value_fn=lambda server, state: state.last_disconnect_reason,
    ),
    SwampSensorDescription(
        key="connections",
        name="Connections since restart",
        value_fn=lambda server, state: state.connections,
    ),
    SwampSensorDescription(
        key="undecoded_messages",
        name="Undecoded messages",
        value_fn=lambda server, state: state.undecoded_messages,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SWAMP diagnostic sensors based on a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        SwampDiagnosticSensor(data["tcp_server"], data["state_manager"].state, config_entry, description)
        for description in SENSORS
    )


class SwampDiagnosticSensor(SensorEntity):
    """A read-out of the SWAMP connection's health."""

    entity_description: SwampSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        server: SwampTcpServer,
        state: DeviceState,
        config_entry: ConfigEntry,
        description: SwampSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._server = server
        self._state = state
        self._attr_unique_id = f"{config_entry.entry_id}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}}

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.entity_description.value_fn(self._server, self._state)
