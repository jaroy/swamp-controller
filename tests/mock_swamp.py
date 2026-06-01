"""Standalone mock SWAMP device for live integration testing.

The real SWAMP amp dials *into* the integration's TCP server and the integration
pushes CIP route/volume commands to it. With no physical amp on the test rig, this
script plays the amp: it connects to the integration's TCP server, completes the
sign-on handshake, answers PINGs, and prints every route/volume command it receives
as a JSON line (so an end-to-end test can assert what the integration sent).

Usage:
    python -m tests.mock_swamp --host 192.168.122.151 --port 41794
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from swamp.protocol.swamp_protocol import SwampProtocol

# Same example payload the real device sends; triggers CONN_ACCEPTED + JOIN UPDATE.
CLIENT_SIGNON = bytes([0x0a, 0x00, 0x0a, 0x00, 0x51, 0xa3, 0x42, 0x40, 0x02, 0x00, 0x00, 0x00, 0x00])
PING = bytes([0x0d, 0x00, 0x02, 0x00, 0x00])
PONG = bytes([0x0e, 0x00, 0x02, 0x00, 0x00])


def emit(obj: dict) -> None:
    """Print one JSON line and flush so a watching test sees it immediately."""
    print(json.dumps(obj), flush=True)


async def read_message(reader: asyncio.StreamReader) -> bytes | None:
    """Read one framed CIP message: [type][len:2][payload:len]."""
    header = await reader.readexactly(3)
    length = int.from_bytes(header[1:3], "big")
    payload = await reader.readexactly(length) if length else b""
    return header + payload


async def keepalive(writer: asyncio.StreamWriter) -> None:
    while True:
        await asyncio.sleep(5)
        writer.write(PING)
        await writer.drain()


async def run(host: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    emit({"event": "connected", "host": host, "port": port})

    writer.write(CLIENT_SIGNON)
    await writer.drain()

    protocol = SwampProtocol()
    ka = asyncio.create_task(keepalive(writer))
    try:
        while True:
            try:
                data = await read_message(reader)
            except asyncio.IncompleteReadError:
                emit({"event": "disconnected"})
                break
            message = await protocol.decode_message(data)
            if not message:
                continue
            if message.get("type") == "ping":
                writer.write(PONG)
                await writer.drain()
            elif message.get("type") == "join" and message.get("join_type") == "serial_binary":
                register = message.get("register")
                if register in ("source", "volume"):
                    emit(
                        {
                            "event": "command",
                            "register": register,
                            "unit": message.get("unit"),
                            "zone": message.get("zone"),
                            "value": message.get("value"),
                        }
                    )
    finally:
        ka.cancel()
        writer.close()
        await writer.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock SWAMP device")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=41794)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
