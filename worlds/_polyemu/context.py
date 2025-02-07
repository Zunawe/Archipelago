"""
A module containing context and functions relevant to running the client. This module should only be imported for type
checking or launching the client, otherwise it will probably cause circular import issues.
"""

import asyncio
import enum
import subprocess
from typing import Any
import sys

from CommonClient import CommonContext, ClientCommandProcessor, get_base_parser, server_loop, logger, gui_enabled
import Patch
import Utils

from .broker import CLIENT_PORT
# from . import PolyEmuContext, ConnectionStatus, NotConnectedError, RequestFailedError, connect, disconnect, get_hash, \
#     get_script_version, get_system, ping
from . import PolyEmuContext, ConnectionStatus, NotConnectedError, RequestFailedError, connect, disconnect, ping, read, get_platform
from .client import PolyEmuClient, AutoPolyEmuClientRegister
from .enums import PLATFORMS


EXPECTED_SCRIPT_VERSION = 1


class AuthStatus(enum.IntEnum):
    NOT_AUTHENTICATED = 0
    NEED_INFO = 1
    PENDING = 2
    AUTHENTICATED = 3


class PolyEmuClientCommandProcessor(ClientCommandProcessor):
    def _cmd_bh(self):
        """Shows the current status of the client's connection to BizHawk"""
        if isinstance(self.ctx, PolyEmuClientContext):
            if self.ctx.polyemu_ctx.connection_status == ConnectionStatus.NOT_CONNECTED:
                logger.info("BizHawk Connection Status: Not Connected")
            elif self.ctx.polyemu_ctx.connection_status == ConnectionStatus.TENTATIVE:
                logger.info("BizHawk Connection Status: Tentatively Connected")
            elif self.ctx.polyemu_ctx.connection_status == ConnectionStatus.CONNECTED:
                logger.info("BizHawk Connection Status: Connected")


class PolyEmuClientContext(CommonContext):
    command_processor = PolyEmuClientCommandProcessor
    auth_status: AuthStatus
    password_requested: bool
    client_handler: PolyEmuClient | None
    slot_data: dict[str, Any] | None = None
    rom_hash: str | None = None
    polyemu_ctx: PolyEmuContext

    watcher_timeout: float
    """The maximum amount of time the game watcher loop will wait for an update from the server before executing"""

    def __init__(self, server_address: str | None, password: str | None):
        super().__init__(server_address, password)
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        self.password_requested = False
        self.client_handler = None
        self.polyemu_ctx = PolyEmuContext()
        self.watcher_timeout = 0.5

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago BizHawk Client"
        return ui

    def on_package(self, cmd, args):
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", None)
            self.auth_status = AuthStatus.AUTHENTICATED

        if self.client_handler is not None:
            self.client_handler.on_package(self, cmd, args)

    async def server_auth(self, password_requested: bool=False):
        self.password_requested = password_requested

        if self.polyemu_ctx.connection_status != ConnectionStatus.CONNECTED:
            logger.info("Awaiting connection to BizHawk before authenticating")
            return

        if self.client_handler is None:
            return

        # Ask handler to set auth
        if self.auth is None:
            self.auth_status = AuthStatus.NEED_INFO
            await self.client_handler.set_auth(self)

            # Handler didn't set auth, ask user for slot name
            if self.auth is None:
                await self.get_username()

        if password_requested and not self.password:
            self.auth_status = AuthStatus.NEED_INFO
            await super(PolyEmuClientContext, self).server_auth(password_requested)

        await self.send_connect()
        self.auth_status = AuthStatus.PENDING

    async def disconnect(self, allow_autoreconnect: bool=False):
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        await super().disconnect(allow_autoreconnect)


async def _game_watcher(ctx: PolyEmuClientContext):
    showed_connecting_message = False
    showed_connected_message = False
    showed_no_handler_message = False

    while not ctx.exit_event.is_set():
        try:
            await asyncio.wait_for(ctx.watcher_event.wait(), ctx.watcher_timeout)
        except asyncio.TimeoutError:
            pass

        ctx.watcher_event.clear()

        try:
            if ctx.polyemu_ctx.connection_status == ConnectionStatus.NOT_CONNECTED:
                showed_connected_message = False

                if not showed_connecting_message:
                    logger.info("Waiting to connect to BizHawk...")
                    showed_connecting_message = True

                # Since a call to `connect` can take a while to return, this will cancel connecting
                # if the user has decided to close the client.
                connect_task = asyncio.create_task(connect(ctx.polyemu_ctx), name="BrokerConnect")
                exit_task = asyncio.create_task(ctx.exit_event.wait(), name="ExitWait")
                await asyncio.wait([connect_task, exit_task], return_when=asyncio.FIRST_COMPLETED)

                if exit_task.done():
                    connect_task.cancel()
                    return

                if not connect_task.result():
                    continue

                # showed_no_handler_message = False

                # script_version = await get_script_version(ctx.polyemu_ctx)

                # if script_version != EXPECTED_SCRIPT_VERSION:
                #     logger.info(f"Connector script is incompatible. Expected version {EXPECTED_SCRIPT_VERSION} but "
                #                 f"got {script_version}. Disconnecting.")
                #     disconnect(ctx.polyemu_ctx)
                #     continue

            # showed_connecting_message = False

            await ping(ctx.polyemu_ctx)

            # if not showed_connected_message:
            #     showed_connected_message = True
            #     logger.info("Connected to BizHawk")

            # game_id = await get_game_id(ctx.polyemu_ctx)
            # if ctx.rom_hash is not None and ctx.rom_hash != rom_hash:
            #     if ctx.server is not None and not ctx.server.socket.closed:
            #         logger.info(f"ROM changed. Disconnecting from server.")

            #     ctx.auth = None
            #     ctx.username = None
            #     ctx.client_handler = None
            #     ctx.finished_game = False
            #     await ctx.disconnect(False)
            # ctx.rom_hash = rom_hash

            if ctx.client_handler is None:
                system = await get_platform(ctx.polyemu_ctx)
                ctx.client_handler = await AutoPolyEmuClientRegister.get_handler(ctx, system)

                if ctx.client_handler is None:
                    if not showed_no_handler_message:
                        logger.info("No handler was found for this game. Double-check that the apworld is installed "
                                    "correctly and that you loaded the right ROM file.")
                        showed_no_handler_message = True
                    continue
                else:
                    showed_no_handler_message = False
                    logger.info(f"Running handler for {ctx.client_handler.game}")
        except RequestFailedError as exc:
            logger.info(f"Lost connection to emulator: {exc.args[0]}")
            continue
        except (ExceptionGroup, NotConnectedError):
            continue

        # Server auth
        if ctx.server is not None and not ctx.server.socket.closed:
            if ctx.auth_status == AuthStatus.NOT_AUTHENTICATED:
                Utils.async_start(ctx.server_auth(ctx.password_requested))
        else:
            ctx.auth_status = AuthStatus.NOT_AUTHENTICATED

        # Call the handler's game watcher
        await ctx.client_handler.game_watcher(ctx)


def _run_game(rom: str):
    import os
    auto_start = Utils.get_settings().PolyEmuclient_options.rom_start

    if auto_start is True:
        emuhawk_path = Utils.get_settings().PolyEmuclient_options.emuhawk_path
        subprocess.Popen(
            [
                emuhawk_path,
                f"--lua={Utils.local_path('data', 'lua', 'connector_bizhawk_generic.lua')}",
                os.path.realpath(rom),
            ],
            cwd=Utils.local_path("."),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif isinstance(auto_start, str):
        import shlex

        subprocess.Popen(
            [
                *shlex.split(auto_start),
                os.path.realpath(rom)
            ],
            cwd=Utils.local_path("."),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )


def _patch_and_run_game(patch_file: str):
    try:
        metadata, output_file = Patch.create_rom_file(patch_file)
        _run_game(output_file)
        return metadata
    except Exception as exc:
        logger.exception(exc)
        return {}


def launch(*launch_args: str) -> None:
    async def main():
        parser = get_base_parser()
        parser.add_argument("patch_file", default="", type=str, nargs="?", help="Path to an Archipelago patch file")
        args = parser.parse_args(launch_args)

        if args.patch_file != "":
            metadata = _patch_and_run_game(args.patch_file)
            if "server" in metadata:
                args.connect = metadata["server"]

        ctx = PolyEmuClientContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

        async def is_broker_running():
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", CLIENT_PORT)
                writer.close()
                await writer.wait_closed()
                return True
            except (ConnectionRefusedError, ConnectionResetError, OSError):
                return False

        if not await is_broker_running():
            subprocess.Popen(
                [sys.executable, "worlds/_polyemu/broker.py", f"--log_directory={Utils.user_path('logs')}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS if Utils.is_windows else 0,
            )

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        watcher_task = asyncio.create_task(_game_watcher(ctx), name="GameWatcher")

        try:
            await watcher_task
        except Exception as e:
            logger.exception(e)

        await ctx.exit_event.wait()
        await ctx.shutdown()

    Utils.init_logging("PolyEmuClient", exception_logger="Client")
    import colorama
    colorama.init()
    asyncio.run(main())
    colorama.deinit()
