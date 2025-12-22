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
        """power <target> on|off"""
        if len(args) < 2:
            return "Usage: power <target-id> on|off"

        target_id = args[0]
        power_state = args[1].lower()

        if power_state not in ['on', 'off']:
            return "Error: Power state must be 'on' or 'off'"

        try:
            power_on = power_state == 'on'
            await self.controller.set_power(target_id, power_on)
            return f"Turned {target_id} {'on' if power_on else 'off'}"
        except Exception as e:
            return f"Error: {e}"

    async def cmd_status(self, args: list[str], kwargs: dict) -> str:
        """status [target-id]"""
        try:
            status = await self.controller.get_status()
            output = []
            output.append(f"Connection: {'Connected' if status['connected'] else 'Disconnected'}")
            output.append("")

            if args:
                target_id = args[0]
                targets = [t for t in status['targets'] if t['id'] == target_id]
                if not targets:
                    return f"Error: Unknown target {target_id}"
            else:
                targets = status['targets']

            for target in targets:
                output.append(f"{target['name']} ({target['id']}):")
                for zone in target['zones']:
                    source = f"Source {zone['source']}" if zone['source'] else "No source"
                    power = "On" if zone['power'] else "Off"
                    output.append(f"  Unit {zone['unit']} Zone {zone['zone']}: {power}, Vol: {zone['volume']}, {source}")
                output.append("")

            return "\n".join(output)
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
  route <source> <target>  - Route audio source to target zone
  volume <target> <level>  - Set volume (0-100)
  volume <target> +/-<N>   - Adjust volume relatively
  power <target> on|off    - Control power
  status [target]          - Show status
  list sources|targets     - List available sources/targets
  help                     - Show this help
  quit                     - Exit
"""
