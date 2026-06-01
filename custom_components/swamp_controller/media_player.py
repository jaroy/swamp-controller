"""Support for SWAMP Controller media players."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from swamp.models.state import ZoneState

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# On turn-on, ramp the zone volume up to its default over this duration (in this many
# steps) so it fades in rather than jumping instantly.
VOLUME_RAMP_SECONDS = 2.0
VOLUME_RAMP_STEPS = 20

# Features the zone gains when it's routed to a source that has an upstream player to
# proxy (e.g. Music Assistant): transport controls forwarded to that player.
UPSTREAM_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SWAMP media player based on a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    controller = data["controller"]
    config = data["config"]
    global_default = data["zone_default_volume"]
    per_target = data["zone_default_volumes"]
    upstream_players = data["source_upstream_players"]

    # Create a media player entity for each target
    entities = []
    for target in config.targets:
        entities.append(
            SwampMediaPlayer(
                controller,
                target,
                config_entry,
                default_volume=per_target.get(target.id, global_default),
                upstream_players=upstream_players,
            )
        )

    async_add_entities(entities, True)
    _LOGGER.info("Added %d SWAMP media player entities", len(entities))


class SwampMediaPlayer(MediaPlayerEntity):
    """Representation of a SWAMP target as a media player."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(
        self,
        controller,
        target,
        config_entry: ConfigEntry,
        default_volume: int,
        upstream_players: dict[int, str] | None = None,
    ) -> None:
        """Initialize the SWAMP media player."""
        self._controller = controller
        self._target = target
        self._config_entry = config_entry
        self._default_volume = default_volume
        self._ramp_task: asyncio.Task | None = None
        # Map of swamp_source_id -> upstream HA media_player entity_id (the player
        # that actually renders that source, e.g. Music Assistant). Empty if none.
        self._upstream_players = upstream_players or {}
        self._unsub_upstream = None

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

        # Features the zone always has (independent of source). Transport controls are
        # added dynamically by `supported_features` when on a proxied source.
        self._base_features = (
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

    def _upstream_entity_id(self) -> str | None:
        """Entity_id of the upstream player for the zone's current source, if any."""
        zone = self._get_primary_zone()
        if not zone or zone.source_id is None or zone.source_id == 0:
            return None
        return self._upstream_players.get(zone.source_id)

    def _upstream_state(self):
        """State object of the current source's upstream player, if available."""
        entity_id = self._upstream_entity_id()
        if not entity_id or self.hass is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state

    def _upstream_attr(self, attr: str):
        """Read an attribute from the current source's upstream player."""
        state = self._upstream_state()
        return state.attributes.get(attr) if state else None

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

        # On a proxied source, mirror the upstream player's transport state (playing/
        # paused/idle/buffering) so the zone tile reflects what's actually happening.
        upstream = self._upstream_state()
        if upstream is not None and upstream.state != STATE_OFF:
            try:
                return MediaPlayerState(upstream.state)
            except ValueError:
                return MediaPlayerState.ON

        # Device is on with a source (no upstream, or upstream is off/idle-unknown)
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
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features, adding transport controls on a proxied source."""
        features = self._base_features
        if self._upstream_entity_id() is not None:
            features |= UPSTREAM_FEATURES
        return features

    @property
    def media_title(self) -> str | None:
        """Title of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_title")

    @property
    def media_artist(self) -> str | None:
        """Artist of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_artist")

    @property
    def media_album_name(self) -> str | None:
        """Album of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_album_name")

    @property
    def media_album_artist(self) -> str | None:
        """Album artist of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_album_artist")

    @property
    def media_track(self) -> int | None:
        """Track number of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_track")

    @property
    def media_content_id(self) -> str | None:
        """Content ID of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_content_id")

    @property
    def media_content_type(self) -> str | None:
        """Content type of currently playing media (from the upstream player)."""
        return self._upstream_attr("media_content_type")

    @property
    def media_duration(self) -> int | None:
        """Duration of currently playing media in seconds (from the upstream player)."""
        return self._upstream_attr("media_duration")

    @property
    def media_position(self) -> int | None:
        """Position of currently playing media in seconds (from the upstream player)."""
        return self._upstream_attr("media_position")

    @property
    def media_position_updated_at(self):
        """When the media position was last updated (from the upstream player)."""
        return self._upstream_attr("media_position_updated_at")

    @property
    def entity_picture(self) -> str | None:
        """Album art for the zone, proxied from the upstream player when present."""
        picture = self._upstream_attr("entity_picture")
        if picture:
            return picture
        return super().entity_picture

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

        # Show the zone "on" at 0 volume immediately, then ramp up in the background
        # so the UI reflects it right away and the slider visibly climbs.
        await self._begin_ramp(self._default_volume)

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        self._cancel_ramp()
        await self._controller.set_power(self._target.id, False)
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        self._cancel_ramp()  # a manual volume change cancels an in-progress ramp
        volume_percent = int(volume * 100)
        await self._controller.set_volume(self._target.id, volume_percent)
        self.async_write_ha_state()

    async def _begin_ramp(self, target_volume: int) -> None:
        """Set the zone to 0 and reflect it now, then ramp up in the background."""
        await self._controller.set_volume(self._target.id, 0)
        self.async_write_ha_state()
        self._cancel_ramp()
        self._ramp_task = self.hass.async_create_background_task(
            self._ramp_volume(target_volume), name=f"swamp_volume_ramp_{self._target.id}"
        )

    def _cancel_ramp(self) -> None:
        """Cancel an in-progress volume ramp, if any."""
        if self._ramp_task is not None and not self._ramp_task.done():
            self._ramp_task.cancel()
        self._ramp_task = None

    async def _ramp_volume(self, target_volume: int) -> None:
        """Ramp 0 -> target_volume over VOLUME_RAMP_SECONDS, pushing state each step."""
        interval = VOLUME_RAMP_SECONDS / VOLUME_RAMP_STEPS
        try:
            for step in range(1, VOLUME_RAMP_STEPS + 1):
                level = round(target_volume * step / VOLUME_RAMP_STEPS)
                await self._controller.set_volume(self._target.id, level)
                self.async_write_ha_state()
                if step < VOLUME_RAMP_STEPS:
                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def async_added_to_hass(self) -> None:
        """Subscribe to the upstream players so the zone updates the moment they do."""
        await super().async_added_to_hass()
        entity_ids = list(set(self._upstream_players.values()))
        if not entity_ids:
            return

        @callback
        def _upstream_changed(event: Event) -> None:
            # Only repaint when the change is for the source this zone is on right now.
            if event.data.get("entity_id") == self._upstream_entity_id():
                self.async_write_ha_state()

        self._unsub_upstream = async_track_state_change_event(
            self.hass, entity_ids, _upstream_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any in-progress ramp and unsubscribe when the entity goes away."""
        self._cancel_ramp()
        if self._unsub_upstream is not None:
            self._unsub_upstream()
            self._unsub_upstream = None

    async def _forward_to_upstream(self, service: str) -> None:
        """Forward a transport command to the current source's upstream player."""
        entity_id = self._upstream_entity_id()
        if entity_id is None:
            _LOGGER.debug(
                "%s: no upstream player for current source; ignoring %s",
                self._target.id,
                service,
            )
            return
        _LOGGER.debug("[proxy] %s forwarding %s -> %s", self._target.id, service, entity_id)
        await self.hass.services.async_call(
            "media_player",
            service,
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_media_play(self) -> None:
        """Send play to the upstream player."""
        await self._forward_to_upstream("media_play")

    async def async_media_pause(self) -> None:
        """Send pause to the upstream player."""
        await self._forward_to_upstream("media_pause")

    async def async_media_stop(self) -> None:
        """Send stop to the upstream player."""
        await self._forward_to_upstream("media_stop")

    async def async_media_next_track(self) -> None:
        """Skip to the next track on the upstream player."""
        await self._forward_to_upstream("media_next_track")

    async def async_media_previous_track(self) -> None:
        """Skip to the previous track on the upstream player."""
        await self._forward_to_upstream("media_previous_track")

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
        """Select input source (implicitly powers the zone on)."""
        if source not in self._source_id_map:
            _LOGGER.warning("Unknown source: %s", source)
            return

        # If the zone is currently off, selecting a source powers it on, so apply
        # the default-volume ramp (same as turning it on). If it's already on, just
        # switch the source and leave the current volume alone.
        zone = self._get_primary_zone()
        was_off = zone is None or zone.source_id is None or zone.source_id == 0

        source_id = self._source_id_map[source]
        await self._controller.route_source_to_target(source_id, self._target.id)

        if was_off:
            await self._begin_ramp(self._default_volume)

    async def async_update(self) -> None:
        """Update the entity state."""
        # State is read directly from state_manager which is updated by the TCP server
        # No need to do anything here, just trigger a state update
        pass
