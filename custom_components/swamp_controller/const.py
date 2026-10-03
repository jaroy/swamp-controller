"""Constants for the SWAMP Controller integration."""

DOMAIN = "swamp_controller"

# Configuration
CONF_CONFIG_FILE = "config_file"
CONF_PORT = "port"

# Defaults
DEFAULT_PORT = 41794
DEFAULT_CONFIG_FILE = "/config/swamp_config.yaml"

# Volume (0-100) a zone is set to when the player is turned on, so enabling a zone
# isn't silent. Overridable globally (`default-volume:`) and per-zone (`default-volume:`
# on a target) in the config file.
DEFAULT_ZONE_VOLUME = 40



def signal_state_updated(entry_id: str) -> str:
    """Dispatcher signal sent when a config entry's SWAMP state changes."""
    return f"{DOMAIN}_{entry_id}_state_updated"


# Services
SERVICE_ROUTE_SOURCE = "route_source"

# Attributes
ATTR_SOURCE_ID = "source_id"
ATTR_TARGET_ID = "target_id"
