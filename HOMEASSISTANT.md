# SWAMP Controller - Home Assistant Integration

This document describes how to install and use the SWAMP Controller as a Home Assistant integration.

## Overview

The SWAMP Controller integration exposes your Crestron SWAMP multi-zone audio system to Home Assistant. Each target (room/zone) is represented as a media player entity with the following controls:

- **Power**: Turn zones on/off
- **Source Selection**: Choose which audio source to play
- **Volume Control**: Adjust volume levels for each zone

## Features

- Each configured target appears as a separate media player device in Home Assistant
- Real-time state updates from the SWAMP device
- Volume control with slider and +/- buttons
- Source selection from all configured audio sources
- Power on/off control
- Device availability tracking (shows offline when device disconnects)

## Installation

### Prerequisites

1. Your SWAMP controller must be properly configured with a `config.yaml` file
2. Home Assistant must be able to reach the network where SWAMP devices connect

### Step 1: Copy Integration Files

Copy the entire `custom_components/swamp_controller` directory to your Home Assistant configuration directory:

```bash
# If using Home Assistant OS/Supervised
cp -r custom_components/swamp_controller /config/custom_components/

# If using Home Assistant Container
cp -r custom_components/swamp_controller /path/to/homeassistant/config/custom_components/

# If using Home Assistant Core
cp -r custom_components/swamp_controller ~/.homeassistant/custom_components/
```

### Step 2: Copy Configuration File

Ensure your SWAMP configuration file is accessible to Home Assistant:

```bash
# Copy your config.yaml to Home Assistant config directory
cp config/config.yaml /config/swamp_config.yaml
```

### Step 3: Install Python Dependencies

The integration requires the SWAMP controller Python package. You need to make the `swamp` package available to Home Assistant.

**Option A: Install in Home Assistant Python environment**

If you have access to the Home Assistant Python environment:

```bash
# Navigate to your project root
cd /path/to/swamp-controller

# Install the swamp package
pip install -e .
```

**Option B: Copy swamp package to custom_components**

Alternatively, copy the swamp package into the integration:

```bash
cp -r swamp custom_components/swamp_controller/
```

### Step 4: Restart Home Assistant

Restart Home Assistant to load the new integration:

```bash
# Using Home Assistant CLI
ha core restart

# Or restart from the UI:
# Settings > System > Restart
```

### Step 5: Add the Integration

1. Go to **Settings** > **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **"Crestron SWAMP Controller"**
4. Configure the integration:
   - **Configuration File Path**: Path to your `config.yaml` (e.g., `/config/swamp_config.yaml`)
   - **TCP Port**: Port for SWAMP device connections (default: `41794`)
5. Click **Submit**

The integration will:
- Load your configuration
- Start a TCP server on the specified port
- Wait for your SWAMP device(s) to connect
- Create media player entities for each target

## Configuration

### Example config.yaml

Your configuration file should define sources and targets:

```yaml
sources:
  - id: music-a
    name: Player A
    swamp-source-id: 4
  - id: music-b
    name: Player B
    swamp-source-id: 5

targets:
  - id: office
    name: Office
    swamp-zones:
      - unit: 3
        zone: 1
  - id: kitchen
    name: Kitchen
    swamp-zones:
      - unit: 4
        zone: 5
      - unit: 4
        zone: 6
```

### Multiple Zones per Target

Targets can contain multiple SWAMP zones. When you control a target in Home Assistant:
- All zones in that target will be controlled together
- State is reflected from the first (primary) zone
- Commands are broadcast to all zones

## Usage

### Media Player Controls

Each target appears as a media player entity:

**Entity ID**: `media_player.{target_name}`

**Available Controls**:
- Power button: Turn on/off
- Source dropdown: Select audio source
- Volume slider: Adjust volume (0-100%)
- Volume +/- buttons: Step volume up/down by 5%

### Automations

You can use SWAMP media players in Home Assistant automations:

```yaml
# Example: Turn on music in the morning
automation:
  - alias: "Morning Music"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: media_player.turn_on
        target:
          entity_id: media_player.kitchen
      - service: media_player.select_source
        target:
          entity_id: media_player.kitchen
        data:
          source: "Player A"
      - service: media_player.volume_set
        target:
          entity_id: media_player.kitchen
        data:
          volume_level: 0.3
```

### Lovelace Cards

Add media player cards to your dashboard:

```yaml
type: media-control
entity: media_player.kitchen
```

Or use the built-in media player card for a full-featured interface.

## Interactive Console (Debugging)

The interactive console remains available for debugging and manual control. You can run it separately from Home Assistant:

### Running the Console

```bash
# From project root
python -m swamp --config config/config.yaml --port 41794
```

**Note**: If Home Assistant is running with the integration enabled, you'll need to use a different port or stop the HA integration first to avoid port conflicts.

### Console Commands

```
route <source-id> <target-id>     # Route audio source to target
volume <target-id> <level>         # Set volume (0-100)
volume <target-id> +/-<delta>      # Adjust volume
power <target-id> on <source-id>   # Power on with source
power <target-id> off              # Power off
status [target-id]                 # Show status
whois                              # Query device info
list sources                       # List sources
list targets                       # List targets
help                               # Show help
quit/exit                          # Exit
```

### Using Both Together

You can run both Home Assistant and the interactive console simultaneously if you:

1. Use different ports for each instance, OR
2. Run them at different times (console for debugging, HA for automation)

The SWAMP device can only connect to one controller at a time, so ensure only one instance is running on the port the device connects to.

## Troubleshooting

### Integration Not Loading

1. Check Home Assistant logs: **Settings** > **System** > **Logs**
2. Look for errors mentioning `swamp_controller`
3. Verify the `swamp` package is installed/copied correctly

### Entities Not Appearing

1. Check that your config file is valid and accessible
2. Verify the integration loaded successfully in **Devices & Services**
3. Check for errors in the Home Assistant logs

### Device Not Connecting

1. Verify the SWAMP device is configured to connect to the correct IP and port
2. Check firewall rules allow TCP connections on the configured port
3. Use the `status` command in the interactive console to check connection status

### Entities Show as Unavailable

- **Available**: Device is connected and sending data
- **Unavailable**: No connection or no data received in 30+ seconds

Check:
1. Network connectivity between SWAMP device and Home Assistant
2. TCP server is running (check logs)
3. SWAMP device is powered on and configured correctly

### Volume/Source Not Updating

The integration polls the state manager for updates. If changes don't appear:

1. Wait a few seconds for the next poll
2. Check that the device is actually sending updates (use console for debugging)
3. Verify state is updating in the logs with debug logging enabled

Enable debug logging:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.swamp_controller: debug
    swamp: debug
```

## Architecture

The integration consists of:

1. **TCP Server**: Listens for SWAMP device connections on the configured port
2. **Protocol Handler**: Encodes/decodes Crestron Internet Protocol (CIP) messages
3. **State Manager**: Tracks zone states and device connection status
4. **Controller**: Orchestrates routing, volume, and power commands
5. **Media Player Entities**: Home Assistant entities for each target

## Limitations

- Only one SWAMP device connection is supported at a time
- Multi-zone targets show state from the first (primary) zone only
- No separate mute control (power off instead)
- Requires manual configuration file (no auto-discovery)

## Support

For issues, questions, or feature requests, please file an issue at:
https://github.com/yourusername/swamp-controller/issues

## License

[Your license here]
