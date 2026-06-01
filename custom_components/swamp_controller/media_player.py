"""SWAMP zones as Home Assistant media players.

Each SWAMP target (room/zone-group) is a media player. Music Assistant adopts these
via its "Home Assistant Players" provider and streams audio to them. On play we:
  1. allocate the render source backing the zone (v1: the single MA-fed DAC),
  2. route that source to the zone and set the zone volume on the SWAMP over TCP,
  3. hand MA's stream URL to the squeezelite that feeds that SWAMP input, via a real
     LMS (the only thing that can make the MA-streamed audio actually render).
Transport controls and now-playing state are forwarded to / mirrored from that LMS
player; volume maps to the SWAMP zone (the LMS player's own volume is pinned to full
so only the SWAMP attenuates).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from swamp.models.state import ZoneState

from .const import DOMAIN
from .lms_client import LmsClient, LmsError
from .source_manager import SourceManager, SourceUnavailable

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)

# Pin the LMS player's software volume to full so only the SWAMP attenuates.
LMS_REFERENCE_VOLUME = 100

_LMS_MODE_TO_STATE = {
    "play": MediaPlayerState.PLAYING,
    "pause": MediaPlayerState.PAUSED,
    "stop": MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a media player per SWAMP target."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    global_default = data["zone_default_volume"]
    per_target = data["zone_default_volumes"]
    entities = [
        SwampZoneMediaPlayer(
            controller=data["controller"],
            target=target,
            source_manager=data["source_manager"],
            lms=data["lms_client"],
            config_entry=config_entry,
            default_volume=per_target.get(target.id, global_default),
        )
        for target in data["config"].targets
    ]
    async_add_entities(entities, True)
    _LOGGER.info("Added %d SWAMP zone media players", len(entities))


class SwampZoneMediaPlayer(MediaPlayerEntity):
    """A SWAMP zone exposed as a media player for Music Assistant."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        controller,
        target,
        source_manager: SourceManager,
        lms: LmsClient,
        config_entry: ConfigEntry,
        default_volume: int,
    ) -> None:
        self._controller = controller
        self._target = target
        self._sources = source_manager
        self._lms = lms
        self._config_entry = config_entry
        self._default_volume = default_volume

        self._attr_unique_id = f"{config_entry.entry_id}_{target.id}"
        # has_entity_name + a named device => the player takes the device (room) name.
        self._attr_name = None

        self._attr_state = MediaPlayerState.IDLE
        self._muted = False
        self._premute_volume_pct: int | None = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self._config_entry.entry_id}_{self._target.id}")},
            "name": self._target.name,
            "manufacturer": "Crestron",
            "model": "SWAMP Zone",
        }

    # --- SWAMP zone helpers ----------------------------------------------

    def _primary_zone(self) -> ZoneState | None:
        zones = self._controller.state.get_zones_for_target(self._target.id)
        return zones[0] if zones else None

    def _renderer(self):
        """The render source currently/last backing this zone."""
        return self._sources.get_renderer(self._target.id) or self._sources.default_source

    async def _route_and_set_volume(self, source) -> None:
        """Route ``source`` to this zone and apply the current zone volume (best effort)."""
        zone = self._primary_zone()
        volume_pct = zone.volume if (zone and zone.volume > 0) else self._default_volume
        try:
            await self._controller.route_source_to_target(source.id, self._target.id)
            await self._controller.set_volume(self._target.id, volume_pct)
        except ConnectionError as err:
            _LOGGER.warning("SWAMP not connected; zone routing skipped: %s", err)

    # --- play / transport -------------------------------------------------

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Render ``media_id`` (an MA stream URL) in this zone."""
        try:
            source = self._sources.allocate(self._target.id)
        except SourceUnavailable as err:
            _LOGGER.error("Cannot play to %s: %s", self._target.id, err)
            return

        await self._route_and_set_volume(source)

        try:
            # Only the SWAMP attenuates; keep the renderer at reference volume.
            await self._lms.set_volume(source.lms_player_id, LMS_REFERENCE_VOLUME)
            await self._lms.play_url(source.lms_player_id, media_id)
        except (LmsError, OSError) as err:
            _LOGGER.error("Failed to render on LMS player %s: %s", source.lms_player_id, err)
            return

        self._apply_metadata(kwargs.get("extra") or {})
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    def _apply_metadata(self, extra: dict[str, Any]) -> None:
        """Display the now-playing metadata MA passed alongside the stream URL."""
        meta = extra.get("metadata") if isinstance(extra, dict) else None
        meta = meta or {}
        self._attr_media_title = meta.get("title")
        self._attr_media_artist = meta.get("artist")
        self._attr_media_album_name = meta.get("album")
        self._attr_media_image_url = meta.get("image_url") or meta.get("image")
        duration = meta.get("duration")
        self._attr_media_duration = int(duration) if duration else None

    async def async_media_pause(self) -> None:
        if source := self._renderer():
            await self._lms.pause(source.lms_player_id)
            self._attr_state = MediaPlayerState.PAUSED
            self.async_write_ha_state()

    async def async_media_play(self) -> None:
        if source := self._renderer():
            await self._lms.unpause(source.lms_player_id)
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        if source := self._renderer():
            await self._lms.stop(source.lms_player_id)
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        if source := self._renderer():
            await self._lms.next_track(source.lms_player_id)

    async def async_media_previous_track(self) -> None:
        if source := self._renderer():
            await self._lms.previous_track(source.lms_player_id)

    async def async_media_seek(self, position: float) -> None:
        if source := self._renderer():
            await self._lms.seek(source.lms_player_id, position)

    # --- power ------------------------------------------------------------

    async def async_turn_on(self) -> None:
        """Resume the renderer if one is assigned; otherwise just reflect 'on/idle'.

        A zone has no audio until something is played to it, so with no assigned
        renderer this only flips the tile to idle (play is what actually starts it).
        """
        if source := self._sources.get_renderer(self._target.id):
            await self._lms.unpause(source.lms_player_id)
            self._attr_state = MediaPlayerState.PLAYING
        else:
            self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Disable the zone on the SWAMP; stop the renderer if no zone still needs it."""
        freed = self._sources.release(self._target.id)
        try:
            await self._controller.set_power(self._target.id, False)
        except ConnectionError as err:
            _LOGGER.warning("SWAMP not connected; power-off skipped: %s", err)
        if freed is not None:
            await self._lms.stop(freed.lms_player_id)
        self._attr_state = MediaPlayerState.OFF
        self.async_write_ha_state()

    # --- volume (maps to the SWAMP zone) ---------------------------------

    async def async_set_volume_level(self, volume: float) -> None:
        pct = int(round(volume * 100))
        try:
            await self._controller.set_volume(self._target.id, pct)
        except ConnectionError as err:
            _LOGGER.warning("SWAMP not connected; volume change skipped: %s", err)
        self._muted = False
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        zone = self._primary_zone()
        if zone:
            await self.async_set_volume_level(min(100, zone.volume + 5) / 100)

    async def async_volume_down(self) -> None:
        zone = self._primary_zone()
        if zone:
            await self.async_set_volume_level(max(0, zone.volume - 5) / 100)

    async def async_mute_volume(self, mute: bool) -> None:
        zone = self._primary_zone()
        if mute and not self._muted:
            self._premute_volume_pct = zone.volume if zone else None
            await self.async_set_volume_level(0)
            self._muted = True
        elif not mute and self._muted:
            restore = self._premute_volume_pct if self._premute_volume_pct is not None else 50
            await self.async_set_volume_level(restore / 100)
            self._muted = False
        self.async_write_ha_state()

    # --- reported state ---------------------------------------------------

    @property
    def volume_level(self) -> float | None:
        zone = self._primary_zone()
        return None if zone is None else zone.volume / 100.0

    @property
    def is_volume_muted(self) -> bool:
        return self._muted

    async def async_update(self) -> None:
        """Mirror playback state/position from the backing LMS player."""
        source = self._sources.get_renderer(self._target.id)
        if source is None:
            # Zone isn't actively backed by a renderer right now.
            if self._attr_state == MediaPlayerState.PLAYING:
                self._attr_state = MediaPlayerState.IDLE
            return
        try:
            status = await self._lms.status(source.lms_player_id)
        except (LmsError, OSError) as err:
            _LOGGER.debug("LMS status poll failed for %s: %s", source.lms_player_id, err)
            return

        mode = status.get("mode")
        if mode in _LMS_MODE_TO_STATE:
            self._attr_state = _LMS_MODE_TO_STATE[mode]

        position = status.get("time")
        if position is not None:
            self._attr_media_position = int(position)
            self._attr_media_position_updated_at = dt_util.utcnow()
        duration = status.get("duration")
        if duration:
            self._attr_media_duration = int(duration)
