"""Constants for the SWAMP Controller integration."""

DOMAIN = "swamp_controller"

# Configuration
CONF_CONFIG_FILE = "config_file"
CONF_PORT = "port"

# Defaults
DEFAULT_PORT = 41794
DEFAULT_CONFIG_FILE = "/config/swamp_config.yaml"
DEFAULT_LMS_PORT = 9000

# Volume applied to a zone on first play when it has no meaningful level yet, so a
# freshly-played zone isn't silent. Overridable globally (`default-volume:`) and
# per-zone (`default-volume:` on a target) in swamp_config.yaml.
DEFAULT_ZONE_VOLUME = 40

# Services
SERVICE_ROUTE_SOURCE = "route_source"

# Attributes
ATTR_SOURCE_ID = "source_id"
ATTR_TARGET_ID = "target_id"
