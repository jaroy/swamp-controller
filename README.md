# SWAMP Controller

Interactive command-line controller for Crestron SWAMP media amplifier systems.

## Features

- **Interactive Shell**: User-friendly command prompt with autocomplete
- **TCP Server**: Listens for connections from SWAMP devices
- **State Management**: Maintains local state synchronized with device
- **Multi-zone Support**: Commands automatically broadcast to all zones in a target
- **Pluggable Protocol**: Protocol handler designed for easy extension

## Installation

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
power <target-id> on|off
```
Example: `power office on`

### Show status
```
status [target-id]
```
Example: `status office` or `status` (shows all)

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

The protocol handler is currently a stub that raises `NotImplementedError`. To implement the actual SWAMP protocol:

1. Edit `swamp/protocol/swamp_protocol.py`
2. Implement the encoding methods:
   - `encode_route_command()`
   - `encode_volume_command()`
   - `encode_power_command()`
   - `decode_message()`
   - `encode_query_state()`

## Development

Run tests:
```bash
pytest
```

Enable debug logging:
```bash
python -m swamp --log-level DEBUG
```

## Project Structure

```
swamp-controller/
├── config/
│   └── config.yaml          # Configuration file
├── swamp/
│   ├── __main__.py          # Entry point
│   ├── models/              # Data models
│   │   ├── config.py
│   │   ├── state.py
│   │   └── commands.py
│   ├── core/                # Core logic
│   │   ├── config_manager.py
│   │   ├── state_manager.py
│   │   └── controller.py
│   ├── protocol/            # Protocol handling
│   │   ├── base.py
│   │   └── swamp_protocol.py
│   ├── network/             # TCP server
│   │   └── tcp_server.py
│   └── shell/               # Interactive shell
│       ├── parser.py
│       ├── commands.py
│       └── repl.py
├── tests/                   # Test suite
├── requirements.txt         # Dependencies
├── pyproject.toml          # Project metadata
└── README.md               # This file
```

## License

Copyright © 2025
