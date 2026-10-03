"""Hard-restart button for the SWAMP Controller integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import async_hard_restart
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SWAMP hard-restart button based on a config entry."""
    async_add_entities([SwampHardRestartButton(config_entry)])


class SwampHardRestartButton(ButtonEntity):
    """Drop every device connection and set the integration up from scratch."""

    _attr_has_entity_name = True
    _attr_name = "Hard restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the button."""
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_hard_restart"
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}}

    async def async_press(self) -> None:
        """Hard-restart the integration."""
        await async_hard_restart(self.hass, self._config_entry)
