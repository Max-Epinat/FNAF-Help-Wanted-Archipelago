"""Archipelago launcher client for FNAF Help Wanted.

Runs inside the Archipelago launcher (a `CommonContext` client, like the FNaF World one) and drives the same transport-free
`BridgeCore` as the standalone client in ap_client/main.py. It talks to the game mod through the bridge files
(ap_inbox.txt / ap_outbox.txt); nothing about the mod or its protocol changes.

`bridge_core.py` and `save_reader.py` are not committed in this package: scripts/build-apworld.ps1 copies them in from
ap_client/ and bridge/ (see scripts/vendored_client_files.json), so there is a single source for that logic.

Imported lazily by the launcher component only. Generation never imports it.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import typing
from pathlib import Path

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop

from .bridge_core import (
    STATUS_AUTHENTICATING,
    STATUS_CONNECTED,
    STATUS_DISCONNECTED,
    STATUS_ERROR,
    BridgeCore,
    InstanceLock,
    SaveAPI,
    find_bridge_dir,
)
from .data import GAME_NAME, LOCATION_OFFSET, LOCATION_TABLE

BRIDGE_COMMAND_POLL_SECONDS = 0.05
# Connection commands of the standalone client: in the launcher, Archipelago owns the connection.
TRANSPORT_COMMANDS = frozenset({"SHOW_UI", "CONNECT", "DISCONNECT", "SAVE_PROFILE"})

# ---- the client --------------------------------------------------------------------------------------------------


class LauncherCore(BridgeCore):
    """BridgeCore whose "can I send?" follows the live Archipelago connection."""

    def __init__(self, bridge_dir: Path, ctx: "FNAFHWContext"):
        self._ctx = ctx
        super().__init__(bridge_dir, save_api=SaveAPI())

    def can_send(self) -> bool:
        return self.status == STATUS_CONNECTED and self._ctx.is_connected()


class FNAFHWCommandProcessor(ClientCommandProcessor):
    def _cmd_bridge(self):
        """Show the bridge folder shared with the game mod and the state of the session."""
        ctx = self.ctx
        if ctx.core is None:
            self.output(f"Bridge not available: {ctx.bridge_error}")
            return
        state = ctx.core.state
        self.output(f"Bridge folder: {ctx.bridge_dir}")
        self.output(f"Session: {state.session_id or '(none yet)'}  status: {ctx.core.status}")
        self.output(f"Checked: {len(state.checked_locations)}  pending: {len(state.pending_locations)}  "
                    f"items received: {ctx.core.received_items_count}  applied in game: {state.applied_item_count}")


class FNAFHWContext(CommonContext):
    command_processor = FNAFHWCommandProcessor
    game = GAME_NAME
    items_handling = 0b111  # full remote: the server sends every item, including the ones we start with

    def __init__(self, server_address: str | None, password: str | None):
        super().__init__(server_address, password)
        self.core: LauncherCore | None = None
        self.bridge_dir: Path | None = None
        self.instance_lock: InstanceLock | None = None
        self.bridge_error = ""
        self._room_seed = ""  # from RoomInfo: the session id is seed + slot, so it must never be guessed
        self._open_bridge()

    # -- bridge setup --

    def _open_bridge(self) -> None:
        self.bridge_dir = find_bridge_dir()
        if self.bridge_dir is None:
            self.bridge_error = ("could not find the bridge folder. Install the game mod with scripts/install-mod.ps1 "
                                 "(it writes the folder into the mod's config.lua) or set FNAFHW_BRIDGE_DIR.")
            logger.error("FNAF Help Wanted: " + self.bridge_error)
            return
        lock = InstanceLock(self.bridge_dir / "ap_client.lock")
        try:
            lock.acquire()
        except RuntimeError as exc:
            self.bridge_error = f"{exc} Close the other client first (two clients corrupt each other's state)."
            logger.error("FNAF Help Wanted: " + self.bridge_error)
            return
        self.instance_lock = lock
        self.core = LauncherCore(self.bridge_dir, self)
        # the apworld knows every location id; do not depend on a locations.json next to the bridge
        self.core.location_name_to_id = {name: LOCATION_OFFSET + data.code for name, data in LOCATION_TABLE.items()}
        self.core.location_id_to_name = {loc_id: name for name, loc_id in self.core.location_name_to_id.items()}
        logger.info(f"FNAF Help Wanted: bridge folder {self.bridge_dir}")

    def is_connected(self) -> bool:
        server = getattr(self, "server", None)
        if server is None:
            return False
        socket = getattr(server, "socket", None)
        return bool(getattr(socket, "open", True)) if socket is not None else False

    def _send(self, packets: list[dict[str, typing.Any]]) -> None:
        if packets:
            asyncio.create_task(self.send_msgs(packets))

    # -- Archipelago callbacks --

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        if self.core is not None:
            self.core.slot = self.auth or ""
            self.core.server_str = self.server_address or ""
            self.core.update_status(STATUS_AUTHENTICATING, message=f"Authenticating as {self.core.slot}...")
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        core = self.core
        if core is None:
            return
        if cmd == "RoomInfo":
            self._room_seed = str(args.get("seed_name", "") or "")
        elif cmd == "Connected":
            seed = self._room_seed or str(getattr(self, "seed_name", "") or "")
            if not seed:
                # A wrong session id would archive the player's Playerarchi.sav and start a fresh one: refuse instead of guessing.
                message = "the server did not tell the seed name; not starting a session (your saves were not touched)"
                logger.error("FNAF Help Wanted: " + message)
                core.update_status(STATUS_ERROR, error=message, message=message)
                return
            core.current_seed_name = seed
            core.slot = self.auth or core.slot
            core.server_str = self.server_address or core.server_str
            self._send(core.on_connected(args))
        elif cmd == "RoomUpdate":
            core.on_room_update(args)
        elif cmd == "ReceivedItems":
            core.on_received_items(args)
        elif cmd == "PrintJSON":
            core.on_print(args)
        elif cmd == "Bounced":
            core.on_bounced(args)
        elif cmd == "ConnectionRefused":
            core.on_connection_refused(args)

    async def connection_closed(self):
        await super().connection_closed()
        if self.core is not None:
            self.core.update_status(STATUS_DISCONNECTED, message="Disconnected.")

    async def shutdown(self):
        await super().shutdown()
        if self.instance_lock is not None:
            self.instance_lock.release()

    def run_gui(self):
        from kvui import GameManager

        class FNAFHWManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago FNAF Help Wanted Client"

        self.ui = FNAFHWManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


def merge_location_checks(packets: list[dict[str, typing.Any]]) -> list[dict[str, typing.Any]]:
    """One LocationChecks packet with every location once (a live check and a save poll can name the same location in the
    same pass); every other packet is kept as is, in order."""
    merged: list[dict[str, typing.Any]] = []
    locations: list[int] = []
    index: int | None = None
    for packet in packets:
        if packet.get("cmd") == "LocationChecks":
            for location in packet.get("locations", []):
                if location not in locations:
                    locations.append(location)
            if index is None:
                index = len(merged)
                merged.append({"cmd": "LocationChecks", "locations": locations})
        else:
            merged.append(packet)
    return merged


async def watch_bridge_once(ctx: FNAFHWContext) -> None:
    """One pass: execute what the game wrote to the outbox, then look at the save for newly earned locations."""
    core = ctx.core
    if core is None:
        return
    packets: list[dict[str, typing.Any]] = []
    lines = core.bridge.read_outbox_lines(core.state)
    for line in lines:
        parts = line.split(" ", 1)
        cmd = parts[0].strip().upper()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd in TRANSPORT_COMMANDS:
            logger.info(f"FNAF Help Wanted: ignoring '{cmd}' from the game; connect with the Archipelago client instead")
            continue
        packets.extend(core.game_command_packets(cmd, arg))
    if lines:
        core._save_state()
    packets.extend(core.collect_savegame_packets())
    if packets and ctx.is_connected():
        await ctx.send_msgs(merge_location_checks(packets))


async def game_watcher(ctx: FNAFHWContext) -> None:
    while not ctx.exit_event.is_set():
        try:
            await watch_bridge_once(ctx)
        except Exception as exc:  # the watcher must survive anything the game writes
            logger.exception(f"FNAF Help Wanted bridge watcher error: {exc}")
        await asyncio.sleep(BRIDGE_COMMAND_POLL_SECONDS)


def parse_client_args(parser, argv: list[str] | None = None):
    """The launcher may start the client with extra arguments (a component name, an archipelago:// link): never exit on them."""
    if not any("--name" in action.option_strings for action in parser._actions):
        parser.add_argument("--name", default=None, help="Slot name to connect as.")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        logger.info(f"FNAF Help Wanted: ignoring extra command line arguments {unknown}")
    url = getattr(args, "url", None)
    if url and str(url).startswith("archipelago:"):  # anything else (e.g. a component name) is not a connection link
        try:
            from CommonClient import handle_url_arg

            args = handle_url_arg(args, parser=parser)  # fills connect/password/name from the link
        except (Exception, SystemExit) as exc:  # argparse's parser.error() raises SystemExit
            logger.info(f"FNAF Help Wanted: could not use the connection link ({exc!r})")
    return args


def main(argv: list[str] | None = None):
    """Entry point of the launcher client. `argv` are the arguments the launcher passed to the component (None: sys.argv)."""
    Utils.init_logging("FNAFHWClient", exception_logger="Client")

    async def _main():
        multiprocessing.freeze_support()
        logger.info("FNAF Help Wanted client starting")
        parser = get_base_parser(description="FNAF Help Wanted client, for text interfacing.")
        args = parse_client_args(parser, argv)

        ctx = FNAFHWContext(args.connect, args.password)
        if getattr(args, "name", None):
            ctx.auth = args.name  # skips the slot name prompt
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        watcher = asyncio.create_task(game_watcher(ctx), name="FNAFHWBridgeWatcher")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()
        await watcher

    import colorama

    colorama.init()
    try:
        asyncio.run(_main())
    except BaseException as exc:  # a silent death of a launcher client is the worst failure: always leave a trace in the log
        logger.exception(f"FNAF Help Wanted client stopped: {exc!r}")
        raise
    finally:
        colorama.deinit()


if __name__ == "__main__":
    main()
