from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from swamp.shell.parser import CommandParser
from swamp.shell.commands import CommandHandlers


class InteractiveShell:
    """Interactive REPL for SWAMP controller"""

    def __init__(self, parser: CommandParser, handlers: CommandHandlers):
        self.parser = parser
        self.handlers = handlers
        self.session: PromptSession | None = None

    async def run(self) -> None:
        """Run interactive shell loop"""
        completer = WordCompleter(
            list(self.parser.commands.keys()),
            ignore_case=True
        )

        self.session = PromptSession(
            message='swamp> ',
            completer=completer
        )

        print("SWAMP Controller - Type 'help' for commands")

        while True:
            try:
                line = await self.session.prompt_async()

                if not line.strip():
                    continue

                command, args, kwargs = self.parser.parse(line)

                if command == 'quit' or command == 'exit':
                    break

                if command is None:
                    continue

                if command not in self.parser.commands:
                    print(f"Unknown command: {command}. Type 'help' for available commands.")
                    continue

                handler = self.parser.commands[command]
                result = await handler(args, kwargs)
                print(result)

            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")

        print("Goodbye!")
