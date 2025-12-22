from typing import Callable
import shlex


class CommandParser:
    """Parses user input into command objects"""

    def __init__(self):
        self.commands: dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        """Register command handler"""
        self.commands[name] = handler

    def parse(self, line: str) -> tuple[str | None, list[str], dict[str, str]]:
        """Parse command line into (command, args, kwargs)"""
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            return None, [], {}

        if not tokens:
            return None, [], {}

        command = tokens[0]
        args = []
        kwargs = {}

        for token in tokens[1:]:
            if '=' in token:
                k, v = token.split('=', 1)
                kwargs[k] = v
            else:
                args.append(token)

        return command, args, kwargs
