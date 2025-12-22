"""Support for SWAMP Controller media players."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from swamp.models.state import ZoneState

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SWAMP media player based on a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    controller = data["controller"]
    config = data["config"]

    # Create a media player entity for each target
    entities = []
    for target in config.targets:
        entities.append(SwampMediaPlayer(controller, target, config_entry))

    async_add_entities(entities, True)
    _LOGGER.info("Added %d SWAMP media player entities", len(entities))


class SwampMediaPlayer(MediaPlayerEntity):
    """Representation of a SWAMP target as a media player."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, controller, target, config_entry: ConfigEntry) -> None:
        """Initialize the SWAMP media player."""
        self._controller = controller
        self._target = target
        self._config_entry = config_entry

        # Set unique ID and device info
        self._attr_unique_id = f"{config_entry.entry_id}_{target.id}"
        self._attr_name = target.name

        # Get all available sources
        self._source_list = [source.name for source in controller.config.sources]
        self._source_id_map = {
            source.name: source.id for source in controller.config.sources
        }
        self._swamp_source_to_name = {
            source.swamp_source_id: source.name
            for source in controller.config.sources
        }

        # Set supported features
        self._attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
        )

        self._attr_source_list = self._source_list

    @property
    def device_info(self):
        """Return device information about this SWAMP target."""
        return {
            "identifiers": {(DOMAIN, f"{self._config_entry.entry_id}_{self._target.id}")},
            "name": self._target.name,
            "manufacturer": "Crestron",
            "model": "SWAMP Zone",
            "via_device": (DOMAIN, self._config_entry.entry_id),
        }

    def _get_zones(self) -> list[ZoneState]:
        """Get all zones for this target."""
        return self._controller.state.get_zones_for_target(self._target.id)

    def _get_primary_zone(self) -> ZoneState:
        """Get the primary zone (first zone) for this target."""
        zones = self._get_zones()
        return zones[0] if zones else None

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        zone = self._get_primary_zone()
        if not zone:
            return MediaPlayerState.OFF

        # Check if device is connected
        if not self._controller.state.state.connected:
            return MediaPlayerState.OFF

        # If source_id is None or 0, device is off
        if zone.source_id is None or zone.source_id == 0:
            return MediaPlayerState.OFF

        # Device is on with a source
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        zone = self._get_primary_zone()
        if not zone:
            return None

        # Convert from 0-100 to 0.0-1.0
        return zone.volume / 100.0

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        zone = self._get_primary_zone()
        if not zone or zone.source_id is None or zone.source_id == 0:
            return None

        # Map swamp_source_id to source name
        return self._swamp_source_to_name.get(zone.source_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Entity is available if device is connected
        return self._controller.state.state.connected

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        # Default to first source if not already playing
        zone = self._get_primary_zone()
        if zone and (zone.source_id is None or zone.source_id == 0):
            # Use the first configured source
            first_source = self._controller.config.sources[0]
            await self._controller.set_power(
                self._target.id, True, first_source.id
            )
        else:
            # Already has a source, just turn it on with existing source
            current_source_name = self.source
            if current_source_name and current_source_name in self._source_id_map:
                source_id = self._source_id_map[current_source_name]
                await self._controller.set_power(self._target.id, True, source_id)
            else:
                # Fallback to first source
                first_source = self._controller.config.sources[0]
                await self._controller.set_power(
                    self._target.id, True, first_source.id
                )

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self._controller.set_power(self._target.id, False)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert from 0.0-1.0 to 0-100
        volume_percent = int(volume * 100)
        await self._controller.set_volume(self._target.id, volume_percent)

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        zone = self._get_primary_zone()
        if zone:
            new_volume = min(100, zone.volume + 5)
            await self._controller.set_volume(self._target.id, new_volume)

    async def async_volume_down(self) -> None:
        """Volume down the media player."""
        zone = self._get_primary_zone()
        if zone:
            new_volume = max(0, zone.volume - 5)
            await self._controller.set_volume(self._target.id, new_volume)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if source in self._source_id_map:
            source_id = self._source_id_map[source]
            await self._controller.route_source_to_target(source_id, self._target.id)
        else:
            _LOGGER.warning("Unknown source: %s", source)

    async def async_update(self) -> None:
        """Update the entity state."""
        # State is read directly from state_manager which is updated by the TCP server
        # No need to do anything here, just trigger a state update
        pass
