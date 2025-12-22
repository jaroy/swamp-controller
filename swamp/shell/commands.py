class CommandHandlers:
    """Shell command implementations"""

    def __init__(self, controller):
        self.controller = controller

    async def cmd_route(self, args: list[str], kwargs: dict) -> str:
        """route <source> <target>"""
        if len(args) < 2:
            return "Usage: route <source-id> <target-id>"

        source_id, target_id = args[0], args[1]
        try:
            await self.controller.route_source_to_target(source_id, target_id)
            return f"Routed {source_id} to {target_id}"
        except Exception as e:
            return f"Error: {e}"

    async def cmd_volume(self, args: list[str], kwargs: dict) -> str:
        """volume <target> <level> or volume <target> +/-<delta>"""
        if len(args) < 2:
            return "Usage: volume <target-id> <level>"

        target_id = args[0]
        level_str = args[1]

        try:
            if level_str.startswith(('+', '-')):
                delta = int(level_str)
                zones = self.controller.state.get_zones_for_target(target_id)
                if zones:
                    current_volume = zones[0].volume
                    new_level = max(0, min(100, current_volume + delta))
                    await self.controller.set_volume(target_id, new_level)
                    return f"Adjusted {target_id} volume to {new_level}"
                return f"Error: No zones found for {target_id}"
            else:
                level = int(level_str)
                if not (0 <= level <= 100):
                    return "Error: Volume must be between 0 and 100"
                await self.controller.set_volume(target_id, level)
                return f"Set {target_id} volume to {level}"
        except ValueError:
            return "Error: Invalid volume level"
        except Exception as e:
            return f"Error: {e}"

    async def cmd_power(self, args: list[str], kwargs: dict) -> str:
        """power <target> on <source> | power <target> off"""
        if len(args) < 2:
            return "Usage: power <target-id> on <source-id> | power <target-id> off"

        target_id = args[0]
        power_state = args[1].lower()

        if power_state not in ['on', 'off']:
            return "Error: Power state must be 'on' or 'off'"

        try:
            if power_state == 'on':
                # Power on requires a source
                if len(args) < 3:
                    return "Usage: power <target-id> on <source-id>"
                source_id = args[2]
                await self.controller.set_power(target_id, True, source_id)
                return f"Turned {target_id} on with source {source_id}"
            else:
                # Power off sets source to 0 (no source)
                await self.controller.set_power(target_id, False, None)
                return f"Turned {target_id} off"
        except Exception as e:
            return f"Error: {e}"

    async def cmd_status(self, args: list[str], kwargs: dict) -> str:
        """status [target-id]"""
        try:
            status = await self.controller.get_status()
            output = []

            # Connection status
            if status['connected']:
                output.append("Connection: Connected")
                if status['client_address']:
                    output.append(f"  Client: {status['client_address']}")
                if status['last_message_seconds'] is not None:
                    output.append(f"  Last message: {status['last_message_seconds']:.1f}s ago")
            else:
                output.append("Connection: Disconnected")
                if status['socket_connected']:
                    output.append("  Socket: Connected")
                if status['conn_accepted_sent']:
                    output.append("  Handshake: Complete")
                if status['last_message_seconds'] is not None:
                    output.append(f"  Last message: {status['last_message_seconds']:.1f}s ago (stale)")
                else:
                    output.append("  Last message: Never")
            output.append("")

            if args:
                target_id = args[0]
                targets = [t for t in status['targets'] if t['id'] == target_id]
                if not targets:
                    return f"Error: Unknown target {target_id}"
            else:
                targets = status['targets']

            for target in targets:
                # Check if target has any valid zones
                valid_zones = [z for z in target['zones'] if z.get('source_received', False)]

                if not valid_zones:
                    # No zones have received data yet
                    output.append(f"{target['name']} ({target['id']}): [Waiting for device data]")
                    output.append("")
                else:
                    output.append(f"{target['name']} ({target['id']}):")
                    for zone in target['zones']:
                        if not zone.get('source_received', False):
                            # Zone hasn't received data yet
                            output.append(f"  Unit {zone['unit']} Zone {zone['zone']}: [Not synced]")
                        else:
                            source = f"Source {zone['source']}" if zone['source'] else "No source"
                            power = "On" if zone['power'] else "Off"
                            output.append(f"  Unit {zone['unit']} Zone {zone['zone']}: {power}, Vol: {zone['volume']}, {source}")
                    output.append("")

            return "\n".join(output)
        except Exception as e:
            return f"Error: {e}"

    async def cmd_whois(self, args: list[str], kwargs: dict) -> str:
        """Send WHOIS request to connected device"""
        try:
            await self.controller.send_whois()
            return "WHOIS request sent"
        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    async def cmd_list(self, args: list[str], kwargs: dict) -> str:
        """list sources|targets"""
        if not args:
            return "Usage: list sources|targets"

        list_type = args[0].lower()

        if list_type == 'sources':
            output = ["Available sources:"]
            for source in self.controller.config.sources:
                output.append(f"  {source.id}: {source.name} (SWAMP ID: {source.swamp_source_id})")
            return "\n".join(output)

        elif list_type == 'targets':
            output = ["Available targets:"]
            for target in self.controller.config.targets:
                zones_str = ", ".join([f"U{z.unit}Z{z.zone}" for z in target.swamp_zones])
                output.append(f"  {target.id}: {target.name} ({zones_str})")
            return "\n".join(output)

        else:
            return "Error: Use 'list sources' or 'list targets'"

    async def cmd_help(self, args: list[str], kwargs: dict) -> str:
        """Show help"""
        return """
Available commands:
  route <source> <target>      - Route audio source to target zone
  volume <target> <level>      - Set volume (0-100)
  volume <target> +/-<N>       - Adjust volume relatively
  power <target> on <source>   - Power on with source
  power <target> off           - Power off (sets source to 0)
  status [target]              - Show status
  whois                        - Send WHOIS request to device
  list sources|targets         - List available sources/targets
  help                         - Show this help
  quit                         - Exit
"""
