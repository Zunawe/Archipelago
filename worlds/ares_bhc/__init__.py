from __future__ import annotations

from typing import TYPE_CHECKING

from worlds.AutoWorld import World
import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext


class DummyWorld(World):
    game = "Dummy World"
    item_name_to_id = {}
    location_name_to_id = {}


class DummyClient(BizHawkClient):
    game = "Dummy World"
    system = "N64"

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        return True

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        print(await bizhawk.read(ctx.bizhawk_ctx, [(0xB0000020, 4, "System Bus")]))
        print(await bizhawk.read(ctx.bizhawk_ctx, [(0x00000024, 4, "ROM")]))
        pass
