"""Config flow for SWAMP Controller integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from swamp.core.config_manager import ConfigManager

from .const import CONF_CONFIG_FILE, CONF_PORT, DEFAULT_CONFIG_FILE, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_FILE, default=DEFAULT_CONFIG_FILE): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    config_file = Path(data[CONF_CONFIG_FILE])

    # Validate config file exists and is readable
    try:
        config = await hass.async_add_executor_job(ConfigManager.load, config_file)
    except FileNotFoundError as err:
        raise CannotConnect(f"Config file not found: {config_file}") from err
    except Exception as err:
        raise InvalidConfig(f"Invalid config file: {err}") from err

    # Return info that you want to store in the config entry.
    return {
        "title": "SWAMP Controller",
        "sources": len(config.sources),
        "targets": len(config.targets),
    }


@config_entries.HANDLERS.register(DOMAIN)
class ConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for SWAMP Controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidConfig:
                errors["base"] = "invalid_config"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidConfig(HomeAssistantError):
    """Error to indicate there is invalid configuration."""
