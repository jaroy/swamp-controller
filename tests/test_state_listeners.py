"""Test that state changes notify listeners (so UIs update without polling)"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from swamp.core.config_manager import ConfigManager
from swamp.core.controller import SwampController
from swamp.core.state_manager import StateManager
from swamp.protocol.swamp_protocol import SwampProtocol


def make_controller():
    config = ConfigManager.load(Path('config/config.yaml'))
    state_manager = StateManager(config)
    tcp = MagicMock()
    tcp.protocol = SwampProtocol()
    tcp.send_command = AsyncMock()
    return SwampController(config, tcp, state_manager), state_manager


@pytest.mark.asyncio
async def test_device_update_notifies():
    _, state_manager = make_controller()
    calls = []
    state_manager.add_listener(lambda: calls.append(1))
    zone = next(iter(state_manager.state.zones.values()))

    await state_manager.update_from_device({
        'type': 'join', 'join_type': 'serial_binary',
        'unit': zone.unit, 'zone': zone.zone, 'register': 'source', 'value': 4,
    })

    assert calls
    assert zone.source_id == 4


@pytest.mark.asyncio
async def test_commands_notify():
    controller, state_manager = make_controller()
    target = controller.config.targets[0].id
    source = controller.config.sources[0].id
    calls = []
    state_manager.add_listener(lambda: calls.append(1))

    await controller.set_power(target, True, source)
    assert calls
    calls.clear()
    await controller.set_volume(target, 30)
    assert calls
    calls.clear()
    await controller.route_source_to_target(source, target)
    assert calls
    calls.clear()
    await controller.set_power(target, False)
    assert calls


@pytest.mark.asyncio
async def test_remove_listener_and_listener_errors():
    controller, state_manager = make_controller()
    calls = []

    def broken():
        raise RuntimeError('boom')

    state_manager.add_listener(broken)  # must not stop other listeners
    remove = state_manager.add_listener(lambda: calls.append(1))
    state_manager.notify()
    assert calls == [1]

    remove()
    state_manager.notify()
    assert calls == [1]
