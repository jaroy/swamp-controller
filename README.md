# SWAMP Controller

Interactive command-line controller for Crestron SWAMP media amplifier systems.

## Features

- **Interactive Shell**: User-friendly command prompt with autocomplete
- **TCP Server**: Listens for connections from SWAMP devices
- **State Management**: Maintains local state synchronized with device
- **Multi-zone Support**: Commands automatically broadcast to all zones in a target
- **Pluggable Protocol**: Protocol handler designed for easy extension
- **Home Assistant Integration**: Native HA integration with media player entities

## Home Assistant Integration

This project includes a **Home Assistant integration** that exposes your Crestron SWAMP system as media player entities in Home Assistant. Each target (room/zone) appears as a controllable media player with volume control, source selection, and power control.

### Installation via HACS (Recommended)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![PyPI](https://img.shields.io/pypi/v/crestron-swamp-controller)](https://pypi.org/project/crestron-swamp-controller/)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - Open HACS in Home Assistant
   - Go to "Integrations"
   - Click the three dots menu (top right) and select "Custom repositories"
   - Add `https://github.com/jaroy/swamp-controller` as an Integration
   - Click "Add"
3. Find "Crestron SWAMP Controller" in HACS and click "Download"
4. Restart Home Assistant
5. Add the integration through Settings > Devices & Services > Add Integration

The `crestron-swamp-controller` package will be automatically installed from PyPI when you add the integration.

See [HOMEASSISTANT.md](HOMEASSISTANT.md) for more detailed installation instructions and configuration options.

### Features
- Media player entity for each target/zone
- Real-time state updates from SWAMP device
- Volume control (0-100%)
- Source selection from configured sources
- Power on/off control
- Device availability tracking

---

## CLI Installation

1. Ensure Python 3.12+ is installed
2. Create and activate virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Linux/Mac
   # or
   .venv\Scripts\activate  # On Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Edit `config/config.yaml` to define your audio sources and target zones:

```yaml
sources:
  - id: music-a
    name: Player A
    swamp-source-id: 4

targets:
  - id: office-terrace
    name: Office Terrace
    swamp-zones:
      - unit: 3
        zone: 1
```

### On the SWAMP
We have to tell the SWAMP to connect to us instead of a Crestron processor.
Use these TELNET commands:
```
adds 51 <IP address> 4 <port>
reboot
```

Note that you can see the currently configured controller with the `ipt` command:
```
$ telnet 192.168.1.89
Trying 192.168.1.89...
Connected to 192.168.1.89.
Escape character is '^]'.

SWAMP Control Console
Connected to Host: SWAMP-00107FE7C4CD

SWAMP>ipt
CIP_ID  Type    Status     DevID  Port   IP Address/SiteName
    51  GWAY    ONLINE        4   41794  010.194.005.251
```

## Usage

Start the controller:
```bash
python -m swamp
```

Or with custom port:
```bash
python -m swamp --port 41794
```

Or with custom config:
```bash
python -m swamp --config /path/to/config.yaml
```

## Available Commands

Once the shell is running, you can use these commands:

### Route audio source to target
```
route <source-id> <target-id>
```
Example: `route music-a office`

### Set volume
```
volume <target-id> <level>
```
Example: `volume office 75`

### Adjust volume relatively
```
volume <target-id> +/-<delta>
```
Example: `volume office +10` or `volume office -5`

### Power control
```
power <target-id> on <source-id>
power <target-id> off
```
Power on requires a source (zones need a source to be "on"). Power off sets the source to 0.

Examples:
- `power office on music-a` - Power on office with music-a as source
- `power office off` - Power off office

### Show status
```
status [target-id]
```
Example: `status office` or `status` (shows all)

### Send WHOIS request
```
whois
```
Sends a WHOIS request (0f 00 01 02) to the connected SWAMP device. This is automatically sent when a device connects.

### List sources or targets
```
list sources
list targets
```

### Get help
```
help
```

### Exit
```
quit
```

## Architecture
The controller works by impersonating a Crestron processor gateway, e.g. a Crestron CP3. The client
is the SWAMP and it connects to our server which then establishes the communication link.

```
User Shell (REPL)
       ↓
Controller (orchestration)
       ↓
State Manager (zone/source mapping)
       ↓
Protocol Handler (pluggable)
       ↓
TCP Server (asyncio)
```

### Components

- **Models**: Data classes for configuration and state
- **Core**: Configuration loading, state management, orchestration
- **Protocol**: Abstract protocol handler with stub implementation
- **Network**: Asyncio TCP server for SWAMP device connections
- **Shell**: Command parser and interactive REPL

## Protocol Implementation
The Protocol Handler partially implements the Crestron Internet Protocol (CIP), a proprietary protocol 
for communication between Crestron devices. Only the message types for basic control of the SWAMP system
are implemented.

### Message Format
All CIP messages follow this format:
- **Byte 0**: Message type
- **Bytes 1-2**: Remaining length (total bytes - 3) in big-endian
- **Bytes 3+**: Payload

Example: `0a 00 0a 00 51 a3 42 40 02 00 00 00 00`
- Type: `0x0a` (CLIENT_SIGNON)
- Length: `0x00 0x0a` = 10 bytes remaining
- Payload: `00 51 a3 42 40 02 00 00 00 00` (10 bytes)
- Total: 1 + 2 + 10 = 13 bytes

### Implemented Messages
- **WHOIS** (`0f 00 01 02`) - Sent automatically when client connects, also available via `whois` command
- **PING** (`0d 00 02 00 00`) - Automatically detected and triggers PONG response. Sent periodically in the background.
- **PONG** (`0e 00 02 00 00`) - Sent automatically in response to PING
- **CLIENT_SIGNON** (`0a ...`) - Sent by device on connect, triggers CONN_ACCEPTED response
- **CONN_ACCEPTED** (`02 00 04 00 00 00 03`) - Sent automatically in response to CLIENT_SIGNON
- **JOIN** (`05 ...`) - The actual control messages for setting and getting information about the SWAMP

### Unknown Message Handling
Any message not recognized will be printed to the console in hex format, making it easy to discover and implement new message types.

Example output:
```
Unknown message type ff (4 bytes): ff aa bb cc
Recognized but unimplemented message type 0a (13 bytes): 0a 00 0a 00 51 a3 42 40 02 00 00 00 00
```

### Adding New Message Types
To add support for a new message type, edit `swamp/protocol/swamp_protocol.py`:

1. Add the message type to `decode_message()` dispatcher
2. Create a `_decode_message_type_XX()` method
3. Implement encoding methods if needed:
   - `encode_route_command()` - Route audio source to zone
   - `encode_volume_command()` - Set zone volume
   - `encode_power_command()` - Control zone power

## Development

Run tests:
```bash
pytest
```

The test suite uses dynamic port allocation (via `get_free_port()`) to avoid conflicts with running instances of the controller.

Enable debug logging:
```bash
python -m swamp --log-level DEBUG
```

Run on a different port:
```bash
python -m swamp --port 41795
```

## License

Copyright © 2025
