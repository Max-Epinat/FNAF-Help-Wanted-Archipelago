"""Websocket-free core of the bridge client: the persisted session state, the bridge file I/O and the
inbox-line formatters. Nothing here imports websockets, tkinter or Archipelago, so it can be driven by any
transport (the standalone websockets client today, an Archipelago launcher client later) and unit-tested alone.
"""

import json
import os
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CLIENT_VERSION = {"class": "Version", "major": 0, "minor": 6, "build": 6}
CLIENT_STATUS_GOAL = 30

# Connection Statuses: DISCONNECTED, CONNECTING, AUTHENTICATING, CONNECTED, ERROR
STATUS_DISCONNECTED = "DISCONNECTED"
STATUS_CONNECTING = "CONNECTING"
STATUS_AUTHENTICATING = "AUTHENTICATING"
STATUS_CONNECTED = "CONNECTED"
STATUS_ERROR = "ERROR"


@dataclass
class BridgeState:
    session_id: str = ""
    seed_name: str = ""
    slot: str = ""
    checked_locations: set[int] = field(default_factory=set)
    pending_locations: set[int] = field(default_factory=set)
    next_item_index: int = 0
    outbox_position: int = 0
    savegame_baseline: set[str] = field(default_factory=set)
    # how many items of the server's list (by index order) have had their one-shot effect applied in
    # the game; sessions saved before this field existed start from their old next_item_index
    applied_item_count: int = 0


GATE_ID_PATTERN = re.compile(r"^[A-Z0-9_]+$")


def format_gate_table_line(level_gates: Any) -> str | None:
    """Build the GATE_TABLE inbox line from slot_data["level_gates"] ({row: gate_id}).

    Returns None when slot_data carries no usable table (the Lua mod then keeps its built-in
    default). Invalid entries are dropped with a [WARN]; they are never forwarded.
    """
    if not isinstance(level_gates, dict) or not level_gates:
        return None
    entries = []
    for row, gate_id in level_gates.items():
        try:
            row_num = int(row)
        except (TypeError, ValueError):
            print(f"[WARN] [SESSION] Ignoring level gate with invalid row {row!r}")
            continue
        if not isinstance(gate_id, str) or not GATE_ID_PATTERN.match(gate_id):
            print(f"[WARN] [SESSION] Ignoring level gate for row {row_num}: invalid gate id {gate_id!r}")
            continue
        entries.append((row_num, gate_id))
    if not entries:
        return None
    return "GATE_TABLE " + ",".join(f"{row}={gate}" for row, gate in sorted(entries))


def format_gate_items_line(gate_items: Any) -> str | None:
    """Build the GATE_ITEMS inbox line from slot_data["gate_items"] ({item_id: gate_id}).

    Same contract as format_gate_table_line: None when absent/unusable, bad entries dropped.
    """
    if not isinstance(gate_items, dict) or not gate_items:
        return None
    entries = []
    for item_id, gate_id in gate_items.items():
        try:
            item_num = int(item_id)
        except (TypeError, ValueError):
            print(f"[WARN] [SESSION] Ignoring gate item with invalid item id {item_id!r}")
            continue
        if not isinstance(gate_id, str) or not GATE_ID_PATTERN.match(gate_id):
            print(f"[WARN] [SESSION] Ignoring gate item {item_num}: invalid gate id {gate_id!r}")
            continue
        entries.append((item_num, gate_id))
    if not entries:
        return None
    return "GATE_ITEMS " + ",".join(f"{item}={gate}" for item, gate in sorted(entries))


def format_applied_items_line(count: int, reset: bool = False) -> str:
    """How many items of the server's list are already applied in the game (monotonic for the game,
    unless `reset` says the server's list shrank and the count was clamped)."""
    return f"APPLIED_ITEMS {int(count)}" + (" reset" if reset else "")


def format_items_snapshot_line(item_ids: list[int]) -> str:
    """Full list of item ids received from the server this connection, in server order."""
    return "RECEIVED_SNAPSHOT " + ",".join(str(i) for i in item_ids)


class BridgeIO:
    def __init__(self, bridge_dir: Path):
        self.bridge_dir = bridge_dir
        self.outbox_path = bridge_dir / "ap_outbox.txt"
        self.inbox_path = bridge_dir / "ap_inbox.txt"
        self.state_path = bridge_dir / "ap_state.json"
        self.status_path = bridge_dir / "connection_state.json"
        self.profile_path = bridge_dir / "connection_profile.json"
        self.sessions_dir = bridge_dir / "sessions"

        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_path.touch(exist_ok=True)
        self.inbox_path.touch(exist_ok=True)

    @staticmethod
    def sanitize_filename(name: str) -> str:
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', str(name)).strip('_')
        return sanitized if sanitized else "default_session"

    def get_session_path(self, session_id: str) -> Path:
        safe_id = self.sanitize_filename(session_id)
        return self.sessions_dir / f"{safe_id}.json"

    def load_session(self, session_id: str) -> BridgeState | None:
        path = self.get_session_path(session_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            checked = {int(v) for v in raw.get("checked_locations", [])}
            pending = {int(v) for v in raw.get("pending_locations", [])}
            next_item = int(raw.get("next_item_index", 0))
            applied_items = int(raw.get("applied_item_count", next_item))
            outbox_pos = int(raw.get("outbox_position", 0))
            baseline = set(raw.get("savegame_baseline", []))
            pending -= checked
            return BridgeState(
                applied_item_count=applied_items,
                session_id=raw.get("session_id", session_id),
                seed_name=raw.get("seed_name", ""),
                slot=raw.get("slot", ""),
                checked_locations=checked,
                pending_locations=pending,
                next_item_index=next_item,
                outbox_position=outbox_pos,
                savegame_baseline=baseline,
            )
        except Exception:
            return None

    def save_session(self, state: BridgeState, loc_id_to_name: dict[int, str] | None = None) -> None:
        checked_names = []
        if loc_id_to_name:
            checked_names = sorted(
                {loc_id_to_name[lid] for lid in state.checked_locations if lid in loc_id_to_name}
            )
        raw = {
            "session_id": state.session_id,
            "seed_name": state.seed_name,
            "slot": state.slot,
            "checked_locations": sorted(state.checked_locations),
            "checked_location_names": checked_names,
            "pending_locations": sorted(state.pending_locations),
            "next_item_index": state.next_item_index,
            "applied_item_count": state.applied_item_count,
            "outbox_position": state.outbox_position,
            "savegame_baseline": sorted(state.savegame_baseline),
        }
        if state.session_id:
            try:
                session_file = self.get_session_path(state.session_id)
                session_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            except Exception:
                pass
        try:
            self.state_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_state(self) -> BridgeState:
        if not self.state_path.exists():
            return BridgeState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            checked = {int(v) for v in raw.get("checked_locations", [])}
            pending = {int(v) for v in raw.get("pending_locations", [])}
            next_item = int(raw.get("next_item_index", 0))
            applied_items = int(raw.get("applied_item_count", next_item))
            outbox_pos = int(raw.get("outbox_position", 0))
            baseline = set(raw.get("savegame_baseline", []))
            pending -= checked
            return BridgeState(
                applied_item_count=applied_items,
                session_id=raw.get("session_id", ""),
                seed_name=raw.get("seed_name", ""),
                slot=raw.get("slot", ""),
                checked_locations=checked,
                pending_locations=pending,
                next_item_index=next_item,
                outbox_position=outbox_pos,
                savegame_baseline=baseline,
            )
        except Exception:
            return BridgeState()

    def save_state(self, state: BridgeState, loc_id_to_name: dict[int, str] | None = None) -> None:
        self.save_session(state, loc_id_to_name)

    def save_connection_status(self, status: str, server: str, slot: str, checked_count: int, received_count: int, last_error: str = "", last_message: str = "") -> None:
        data = {
            "status": status,
            "server": server,
            "slot": slot,
            "checked_count": checked_count,
            "received_count": received_count,
            "last_error": last_error,
            "last_message": last_message,
            "timestamp": time.time(),
        }
        try:
            self.status_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_profile(self) -> dict[str, Any]:
        default_profile = {
            "server_host": "archipelago.gg",
            "server_port": 38281,
            "slot": "Player1",
            "password": "",
            "game": "Five Nights at Freddy's: Help Wanted",
            "auto_connect": False,
        }
        if not self.profile_path.exists():
            self.profile_path.write_text(json.dumps(default_profile, indent=2), encoding="utf-8")
            return default_profile
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
            for k, v in default_profile.items():
                raw.setdefault(k, v)
            return raw
        except Exception:
            return default_profile

    def save_profile(self, profile: dict[str, Any]) -> None:
        try:
            self.profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        except Exception:
            pass

    def read_outbox_lines(self, state: BridgeState) -> list[str]:
        if not self.outbox_path.exists():
            return []
        file_size = self.outbox_path.stat().st_size
        if state.outbox_position > file_size:
            state.outbox_position = 0

        with self.outbox_path.open("r", encoding="utf-8") as handle:
            handle.seek(state.outbox_position)
            chunk = handle.read()
            state.outbox_position = handle.tell()

        lines = [line.strip() for line in chunk.splitlines()]
        return [l for l in lines if l]

    def write_inbox_line(self, text: str) -> None:
        line = text.replace("\n", " ").strip() + "\n"
        with self.inbox_path.open("a", encoding="utf-8") as handle:
            handle.write(line)


# ---- finding the bridge folder -----------------------------------------------------------------------------
# The game mod is the single source of truth for where it reads and writes: its config.lua names the bridge folder.
# Both clients (standalone and launcher) use this, so they always agree with the mod.

MOD_CONFIG_SUBPATH = Path("freddys/Binaries/Win64/Mods/FNAFHWArchipelago/config.lua")
DEFAULT_GAME_ROOTS = (
    Path("C:/Program Files (x86)/Steam/steamapps/common/FNAFVRHelpWanted"),
    Path("C:/Program Files/Steam/steamapps/common/FNAFVRHelpWanted"),
)
STEAM_LIBRARY_FILE = Path("C:/Program Files (x86)/Steam/steamapps/libraryfolders.vdf")


def parse_bridge_dir_from_config(text: str) -> str | None:
    """`bridge_dir = "C:/.../bridge",` from the mod's config.lua (comment lines are ignored)."""
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    match = re.search(r'\bbridge_dir\s*=\s*"([^"]*)"', code)
    return match.group(1).strip() if match and match.group(1).strip() else None


def steam_library_roots(vdf_text: str) -> list[Path]:
    """Game folders in every Steam library listed in libraryfolders.vdf."""
    return [
        Path(path.replace("\\\\", "\\")) / "steamapps" / "common" / "FNAFVRHelpWanted"
        for path in re.findall(r'"path"\s+"([^"]+)"', vdf_text)
    ]


def candidate_game_roots(env: Mapping[str, str] | None = None) -> list[Path]:
    env = os.environ if env is None else env
    roots: list[Path] = []
    if env.get("FNAFHW_GAME_ROOT"):
        roots.append(Path(env["FNAFHW_GAME_ROOT"]))
    roots.extend(DEFAULT_GAME_ROOTS)
    try:
        if STEAM_LIBRARY_FILE.is_file():
            roots.extend(steam_library_roots(STEAM_LIBRARY_FILE.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        pass
    return roots


def find_bridge_dir(env: Mapping[str, str] | None = None, game_roots: Iterable[Path] | None = None) -> Path | None:
    """The bridge folder the game mod uses: FNAFHW_BRIDGE_DIR if set, otherwise the one written in the installed mod's
    config.lua (the mod is the single source of truth for where it reads and writes). None when neither is found."""
    env = os.environ if env is None else env
    explicit = env.get("FNAFHW_BRIDGE_DIR", "").strip()
    if explicit and Path(explicit).is_dir():
        return Path(explicit)
    for root in (candidate_game_roots(env) if game_roots is None else game_roots):
        config = Path(root) / MOD_CONFIG_SUBPATH
        try:
            if config.is_file():
                configured = parse_bridge_dir_from_config(config.read_text(encoding="utf-8", errors="replace"))
                if configured and Path(configured).is_dir():
                    return Path(configured)
        except OSError:
            continue
    return None


class InstanceLock:
    """One client at a time per bridge folder: two clients writing the same inbox/outbox files corrupt each other's state.
    The lock file holds the owner's PID; a lock whose owner is gone is stale and is cleared."""

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.acquired = False

    def acquire(self) -> None:
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(str(os.getpid()))
                self.acquired = True
                return
            except FileExistsError:
                owner_pid = None
                try:
                    raw = self.lock_path.read_text(encoding="utf-8").strip()
                    owner_pid = int(raw) if raw else None
                except Exception:
                    pass

                if owner_pid and self.is_pid_running(owner_pid):
                    raise RuntimeError(f"Another AP bridge client is already running (PID {owner_pid}).")

                try:
                    self.lock_path.unlink(missing_ok=True)
                except Exception:
                    raise RuntimeError("Cannot clear stale lock file.")

    @staticmethod
    def is_pid_running(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
            if handle:
                code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                kernel32.CloseHandle(handle)
                return code.value == 259  # STILL_ACTIVE
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self.lock_path.unlink(missing_ok=True)
        except Exception:
            pass
        self.acquired = False


class SaveAPI:
    """How the core reads and creates game saves. The default uses save_reader.py next to this module; a transport may inject its
    own (the standalone client injects one that resolves through ap_client.main so tests can patch it)."""

    @staticmethod
    def _reader():
        try:
            from . import save_reader  # vendored next to this module inside the apworld
        except ImportError:
            import save_reader  # script mode: ap_client/ is on sys.path
        return save_reader

    def parse(self, data: bytes):
        return self._reader().parse_gvas_save(data)

    def extract_earned(self, parsed) -> list[str]:
        return self._reader().extract_earned_locations(parsed)

    def archipelago_save_path(self) -> Path | None:
        return self._reader().get_archipelago_savegame_path()

    def ensure_clean_save(self):
        return self._reader().ensure_clean_archipelago_save()


class BridgeCore:
    """Transport-independent client logic: session handling, item sync, location checks and save polling.

    Methods never touch a socket. Whatever has to go to the Archipelago server is *returned* as a list of packets
    (dicts), and the transport sends them. What goes to the game is written to the bridge files here.
    A transport tells the core when it can actually send by overriding `can_send` and `notify_status`.
    """

    def __init__(self, bridge_dir: Path, save_api: SaveAPI | None = None, bridge: BridgeIO | None = None):
        self.bridge_dir = bridge_dir
        self.bridge = bridge or BridgeIO(bridge_dir)
        self.save_api = save_api or SaveAPI()

        self.profile = self.bridge.load_profile()
        self.state = self.bridge.load_state()
        self.current_seed_name = self.state.seed_name or ""
        self.location_name_to_id: dict[str, int] = {}
        self.location_id_to_name: dict[int, str] = {}
        self._load_local_locations_json()

        self.status = STATUS_DISCONNECTED
        self.server_str = f"{self.profile.get('server_host', '')}:{self.profile.get('server_port', '')}"
        self.slot = self.profile.get("slot", "")
        self.last_error = ""
        self.last_message = "Bridge initialized"
        self.received_items_count = self.state.next_item_index
        # server's full received-item list for this connection, by index (rebuilt from index 0)
        self._received_item_ids: dict[int, int] = {}
        self.disconnect_requested = False
        self._last_sav_mtime: float = 0.0
        self._last_sav_poll_time: float = 0.0
        # DeathLink: only active when the slot enabled it (slot_data["death_link"]); reset on every connect
        self.death_link_enabled = False
        self._deathlink_times: list[float] = []  # `time` of recent deaths we sent or handled: echoes and repeats are ignored

    # ---- hooks a transport overrides -------------------------------------------------------------------------

    def can_send(self) -> bool:
        """True when packets returned by the core can actually be sent right now."""
        return self.status == STATUS_CONNECTED

    def notify_status(self) -> None:
        """Called after every status change (the standalone client updates its window here)."""

    # ---- status / locations table ----------------------------------------------------------------------------

    def _load_local_locations_json(self) -> None:
        loc_file = self.bridge_dir / "locations.json"  # copied there by the mod installer
        if loc_file.exists():
            try:
                data = json.loads(loc_file.read_text(encoding="utf-8"))
                mapping = data.get("location_name_to_id", {})
                self.location_name_to_id = {k: int(v) for k, v in mapping.items()}
                self.location_id_to_name = {int(v): k for k, v in mapping.items()}
            except Exception as e:
                print(f"[AP Client] Error reading locations.json: {e}")

    def update_status(self, status: str, error: str = "", message: str = "") -> None:
        self.status = status
        if error:
            self.last_error = error
        if message:
            self.last_message = message

        self.bridge.save_connection_status(
            status=self.status,
            server=self.server_str,
            slot=self.slot,
            checked_count=len(self.state.checked_locations),
            received_count=self.received_items_count,
            last_error=self.last_error,
            last_message=self.last_message,
        )
        self.bridge.write_inbox_line(f"STATUS {self.status} {self.last_message}")
        self.notify_status()

    def _save_state(self) -> None:
        self.bridge.save_state(self.state, self.location_id_to_name)

    # ---- packets from the server -----------------------------------------------------------------------------

    def build_connect_packet(self, uuid_text: str) -> dict[str, Any]:
        return {
            "cmd": "Connect",
            "game": self.profile.get("game", "Five Nights at Freddy's: Help Wanted"),
            "name": self.slot,
            "password": self.profile.get("password", ""),
            "uuid": uuid_text,
            "version": CLIENT_VERSION,
            "tags": ["AP"],
            "items_handling": 7,
            "slot_data": True,
        }

    def on_print(self, packet: dict[str, Any]) -> None:
        text = "".join(seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in packet.get("data", []))
        if text.strip():
            self.bridge.write_inbox_line(f"PRINT {text.strip()}")

    def _remember_deathlink_time(self, stamp: float) -> bool:
        """True when this death is new. Remembers the last few, so our own echo and repeated deliveries are ignored."""
        if stamp in self._deathlink_times:
            return False
        self._deathlink_times.append(stamp)
        del self._deathlink_times[:-20]
        return True

    def on_bounced(self, packet: dict[str, Any]) -> None:
        tags = packet.get("tags", [])
        if "DeathLink" not in tags:
            return
        if not self.death_link_enabled:
            return  # DeathLink is off for this slot: never forward a death to the game
        data = packet.get("data", {})
        source = str(data.get("source", "Someone"))
        cause = str(data.get("cause", "Died.")).replace("\n", " ")
        if source == self.slot:
            return  # our own death bounced back
        if not self._remember_deathlink_time(data.get("time", 0)):
            print(f"[SYNC] Ignoring a repeated DeathLink from {source}")
            return
        self.bridge.write_inbox_line(f"DEATHLINK {source}::{cause}")

    def on_connection_refused(self, packet: dict[str, Any]) -> None:
        errors = packet.get("errors", ["Refused by server"])
        err_msg = ", ".join(errors)
        self.update_status(STATUS_ERROR, error=err_msg, message=f"Connection Refused: {err_msg}")
        self.disconnect_requested = True

    def _snapshot_baseline(self, label: str) -> set[str]:
        """Earned locations currently in Playerarchi.sav. Raises if the save cannot be read (callers choose the fallback)."""
        baseline: set[str] = set()
        try:
            sav_path = self.save_api.archipelago_save_path()
            if sav_path and sav_path.exists():
                parsed = self.save_api.parse(sav_path.read_bytes())
                baseline = set(self.save_api.extract_earned(parsed))
                print(f"[AP Client] {label}: {len(baseline)} pre-existing checks.")
        except Exception as e:
            print(f"[AP Client] Warning on {label.lower()}: {e}")
            raise
        return baseline

    def on_connected(self, packet: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle the server's Connected packet. Returns the packets to send (pending checks to flush)."""
        outgoing: list[dict[str, Any]] = []
        server_checked = {int(x) for x in packet.get("checked_locations", [])}
        slot_name = self.slot or "Player"
        seed_name = self.current_seed_name or "unknown_seed"
        session_id = f"{seed_name}_{slot_name}"

        existing_session = self.bridge.load_session(session_id)
        if existing_session:
            print(f"[AP Client] Resuming existing Archipelago session: {session_id}")

            # SERVER IS AUTHORITATIVE: replace checked_locations with current server state.
            # Old local-only checks that the server doesn't have must NOT persist.
            # Only preserve pending locations that the server hasn't already confirmed,
            # as they represent genuinely earned but un-acknowledged checks.
            surviving_pending = existing_session.pending_locations - server_checked
            stale_local = existing_session.checked_locations - server_checked
            if stale_local:
                stale_names = sorted(self.location_id_to_name.get(lid, str(lid)) for lid in stale_local)
                print(f"[AP Client] Discarding {len(stale_local)} stale local checks not on current server: {stale_names}")

            # Re-snapshot the baseline from the current Playerarchi.sav on disk.
            # This prevents pre-existing game state in Playerarchi.sav from being
            # interpreted as "new" progression that should be sent as checks.
            try:
                baseline = self._snapshot_baseline("Re-snapshotted Archipelago save baseline")
            except Exception:
                # Fall back to old baseline if re-snapshot fails
                baseline = existing_session.savegame_baseline

            self.state = BridgeState(
                session_id=session_id,
                seed_name=existing_session.seed_name,
                slot=existing_session.slot,
                checked_locations=set(server_checked),  # SERVER is authoritative
                pending_locations=surviving_pending,
                next_item_index=existing_session.next_item_index,
                applied_item_count=existing_session.applied_item_count,
                outbox_position=existing_session.outbox_position,
                savegame_baseline=baseline,
            )
        else:
            print(f"[AP Client] Initializing NEW Archipelago session: {session_id}")
            # If an old Playerarchi.sav exists from a previous seed, archive it so this new seed starts clean
            try:
                appdata = os.environ.get("LOCALAPPDATA", "")
                if appdata:
                    p_archi = Path(appdata) / "freddys" / "Saved" / "SaveGames" / "Playerarchi.sav"
                    if p_archi.exists():
                        ts = int(time.time() * 1000)
                        bak = p_archi.with_name(f"Playerarchi_{ts}.sav.bak")
                        if bak.exists():
                            bak.unlink(missing_ok=True)
                        p_archi.rename(bak)
                        print(f"[AP Client] Archived previous Playerarchi.sav to {bak.name} for clean new seed!")
            except Exception as e:
                print(f"[AP Client] Note on Playerarchi archive: {e}")

            # Generate fresh, unplayed Playerarchi.sav for the new session
            self.save_api.ensure_clean_save()

            try:
                baseline = self._snapshot_baseline("Archipelago save baseline snapshot")
            except Exception:
                baseline = set()

            outbox_size = self.bridge.outbox_path.stat().st_size if self.bridge.outbox_path.exists() else 0
            self.state = BridgeState(
                session_id=session_id,
                seed_name=seed_name,
                slot=slot_name,
                checked_locations=set(server_checked),
                pending_locations=set(),
                next_item_index=0,
                outbox_position=outbox_size,
                savegame_baseline=baseline,
            )

        self._last_sav_mtime = 0.0
        self.received_items_count = self.state.next_item_index

        if "slot_data" in packet:
            slot_data = packet["slot_data"]
            loc_mapping = slot_data.get("location_name_to_id", {})
            if loc_mapping:
                for k, v in loc_mapping.items():
                    self.location_name_to_id[k] = int(v)
                    self.location_id_to_name[int(v)] = k

        self.update_status(STATUS_CONNECTED, message=f"Connected as '{self.slot}' to {self.server_str}!")
        self.bridge.write_inbox_line("CONNECTED")

        # Notify Lua mod of session change, baseline, and checked locations
        self.bridge.write_inbox_line(f"SESSION_SYNC {session_id}")
        for base_loc in sorted(self.state.savegame_baseline):
            self.bridge.write_inbox_line(f"SESSION_BASELINE {base_loc}")
        for chk_id in sorted(self.state.checked_locations):
            loc_name = self.location_id_to_name.get(chk_id, str(chk_id))
            self.bridge.write_inbox_line(f"CONFIRMED_CHECK {chk_id} {loc_name}")

        # DeathLink is opt-in per slot: subscribe to the tag only when the slot enabled it, and tell the game either way
        self.death_link_enabled = bool((packet.get("slot_data") or {}).get("death_link", False))
        self._deathlink_times.clear()
        self.bridge.write_inbox_line(f"DEATH_LINK_MODE {1 if self.death_link_enabled else 0}")
        # whether the game over after the prize box jumpscare is sent (slot_data of a room made before the option: yes, as always); the mod
        # resets it to "yes" when it reads DEATH_LINK_MODE, so this line must follow it
        gift_box = bool((packet.get("slot_data") or {}).get("death_link_gift_box", True))
        self.bridge.write_inbox_line(f"DEATH_LINK_GIFT_BOX {1 if gift_box else 0}")
        if self.death_link_enabled:
            outgoing.append({"cmd": "ConnectUpdate", "tags": ["AP", "DeathLink"]})
            print("[SESSION] DeathLink is enabled for this slot")

        # Level gate table from slot_data (additive; a failure must never affect connecting)
        try:
            gate_line = format_gate_table_line((packet.get("slot_data") or {}).get("level_gates"))
            if gate_line:
                self.bridge.write_inbox_line(gate_line)
                print(f"[SESSION] Forwarded level gate table to game: {gate_line}")
            else:
                print("[SESSION] No level_gates in slot_data; game keeps its built-in gate table")
            items_line = format_gate_items_line((packet.get("slot_data") or {}).get("gate_items"))
            if items_line:
                self.bridge.write_inbox_line(items_line)
                print(f"[SESSION] Forwarded gate item map to game: {items_line}")
            # The server only sends ReceivedItems when the slot has items, so "no items" would otherwise
            # leave stale authorization from replayed history. Start every connection from an empty,
            # authoritative snapshot; a ReceivedItems packet (index 0) then replaces it with the full list.
            self._received_item_ids.clear()
            self.bridge.write_inbox_line(format_applied_items_line(self.state.applied_item_count))
            self.bridge.write_inbox_line(format_items_snapshot_line([]))
        except Exception as e:
            print(f"[WARN] [SESSION] Could not forward level gate table: {e}")

        # Flush any pending checks for this session
        if self.state.pending_locations:
            pending_names = sorted(self.location_id_to_name.get(lid, str(lid)) for lid in self.state.pending_locations)
            print(f"[AP Client] Flushing {len(self.state.pending_locations)} pending checks: {pending_names}")
            outgoing.append({"cmd": "LocationChecks", "locations": list(self.state.pending_locations)})

        self._save_state()
        return outgoing

    def on_room_update(self, packet: dict[str, Any]) -> None:
        for loc in packet.get("checked_locations", []):
            loc_id = int(loc)
            self.state.checked_locations.add(loc_id)
            self.state.pending_locations.discard(loc_id)
            loc_name = self.location_id_to_name.get(loc_id, str(loc_id))
            self.bridge.write_inbox_line(f"CONFIRMED_CHECK {loc_id} {loc_name}")

        self.update_status(STATUS_CONNECTED, message=f"{len(self.state.checked_locations)} locations checked.")
        self._save_state()

    def on_received_items(self, packet: dict[str, Any]) -> None:
        index = int(packet.get("index", 0))
        items = packet.get("items", [])

        # Authorization snapshot (additive, guarded): the server's full list is the authority,
        # so it is rebuilt from index 0 and never depends on next_item_index.
        snapshot_line = None
        applied_line = None
        try:
            if index == 0:
                self._received_item_ids.clear()
            for offset, item in enumerate(items):
                self._received_item_ids[index + offset] = int(
                    item.get("item", 0) if isinstance(item, dict) else item[0]
                )
            if sorted(self._received_item_ids) == list(range(len(self._received_item_ids))):
                known = len(self._received_item_ids)
                if self.state.applied_item_count > known:
                    print(f"[WARN] [SYNC] Server item list ({known}) is shorter than the applied count "
                          f"({self.state.applied_item_count}); room reset? Clamping, items are not re-applied")
                    self.state.applied_item_count = known
                    applied_line = format_applied_items_line(known, reset=True)
                else:
                    applied_line = format_applied_items_line(self.state.applied_item_count)
                snapshot_line = format_items_snapshot_line(
                    [self._received_item_ids[i] for i in sorted(self._received_item_ids)]
                )
            else:
                print("[WARN] [SYNC] Received item list has gaps; not sending an authorization snapshot")
        except Exception as e:
            print(f"[WARN] [SYNC] Could not build received item snapshot: {e}")

        for offset, item in enumerate(items):
            item_index = index + offset
            if item_index < self.state.next_item_index:
                continue

            item_id = int(item.get("item", 0) if isinstance(item, dict) else item[0])
            player = int(item.get("player", 0) if isinstance(item, dict) else item[2])
            location = int(item.get("location", 0) if isinstance(item, dict) else item[1])
            flags = int(item.get("flags", 0) if isinstance(item, dict) else item[3])

            self.bridge.write_inbox_line(f"ITEM {item_id} {player} {location} {flags} {item_index}")
            self.state.next_item_index = item_index + 1
            self.received_items_count = self.state.next_item_index

        if snapshot_line is not None:
            if applied_line is not None:
                self.bridge.write_inbox_line(applied_line)
            self.bridge.write_inbox_line(snapshot_line)

        self._save_state()
        self.update_status(STATUS_CONNECTED, message=f"Received item #{self.received_items_count}")

    # ---- commands from the game (outbox) ---------------------------------------------------------------------

    def on_items_applied(self, arg: str) -> None:
        """The game reports how many items (by server index order) it has applied. Only ever moves
        forward. It is accepted even before this connection's item list is known (the game may ack
        while the client was down or still connecting); a count above the real list is clamped when
        that list arrives."""
        try:
            count = int(arg.split()[0])
        except (ValueError, IndexError):
            print(f"[WARN] [SYNC] Ignoring malformed ITEMS_APPLIED {arg!r}")
            return
        if count <= self.state.applied_item_count:
            return
        self.state.applied_item_count = count
        self._save_state()
        # echo it so inbox history (replayed by the game at launch) always ends at the latest count
        self.bridge.write_inbox_line(format_applied_items_line(count))
        print(f"[SYNC] Game applied {count} item(s) of this session")

    def location_check_packets(self, arg: str) -> list[dict[str, Any]]:
        try:
            loc_id = int(arg)
        except ValueError:
            self.bridge.write_inbox_line(f"PRINT Invalid location ID: {arg}")
            return []

        loc_name = self.location_id_to_name.get(loc_id, str(loc_id))
        is_checked = loc_id in self.state.checked_locations
        action = "IGNORE" if is_checked else "SEND"
        print(f"[ARCHI] Live check received:\n"
              f"        AP Location = {loc_name} ({loc_id})\n"
              f"        Server Checked = {is_checked}\n"
              f"        Action = {action}")

        if is_checked:
            self.bridge.write_inbox_line(f"PRINT Location already checked: {loc_name}")
            return []

        self.state.pending_locations.add(loc_id)
        if self.can_send():
            self.bridge.write_inbox_line(f"PRINT Check sent to server: {loc_name} ({loc_id})")
            return [{"cmd": "LocationChecks", "locations": [loc_id]}]
        self.bridge.write_inbox_line(f"PRINT Queued check (offline): {loc_name} ({loc_id})")
        return []

    def location_check_name_packets(self, arg: str) -> list[dict[str, Any]]:
        loc_id = self.location_name_to_id.get(arg)
        if loc_id is None:
            self.bridge.write_inbox_line(f"PRINT Unknown location name: {arg}")
            return []
        return self.location_check_packets(str(loc_id))

    def game_command_packets(self, cmd: str, arg: str) -> list[dict[str, Any]]:
        """Commands from the game that are independent of the transport. Returns the packets to send."""
        if cmd == "ITEMS_APPLIED":
            self.on_items_applied(arg)
        elif cmd == "LOCATION_CHECK":
            return self.location_check_packets(arg)
        elif cmd == "LOCATION_CHECK_NAME":
            return self.location_check_name_packets(arg)
        elif cmd == "GOAL":
            if self.can_send():
                self.bridge.write_inbox_line("PRINT Sent Goal packet.")
                return [{"cmd": "StatusUpdate", "status": CLIENT_STATUS_GOAL}]
        elif cmd == "SAY":
            if self.can_send() and arg:
                return [{"cmd": "Say", "text": arg}]
        elif cmd == "SYNC":
            if self.can_send():
                return [{"cmd": "Sync"}]
        elif cmd == "DEATHLINK":
            if self.death_link_enabled and self.can_send():
                payload = {
                    "time": time.time(),
                    "source": self.slot or "FNAF HW Player",
                    "cause": arg or "Got jumpscared by an animatronic.",
                }
                self._remember_deathlink_time(payload["time"])
                return [{"cmd": "Bounce", "tags": ["DeathLink"], "data": payload}]
        elif cmd == "GET_STATUS":
            self.update_status(self.status, message=self.last_message)
        return []

    # ---- game save polling -----------------------------------------------------------------------------------

    def collect_savegame_packets(self) -> list[dict[str, Any]]:
        """Look at Playerarchi.sav (at most once a second, only when it changed) and return the LocationChecks packet
        for newly earned locations. Nothing already in the session baseline is ever sent."""
        if self.status != STATUS_CONNECTED:
            return []

        now = time.time()
        if now - self._last_sav_poll_time < 1.0:
            return []
        self._last_sav_poll_time = now

        sav_path = self.save_api.archipelago_save_path()
        if not sav_path or not sav_path.exists():
            return []

        try:
            mtime = sav_path.stat().st_mtime
            if mtime == self._last_sav_mtime:
                return []
            self._last_sav_mtime = mtime

            data = sav_path.read_bytes()
            parsed = self.save_api.parse(data)
            earned_names = self.save_api.extract_earned(parsed)

            # ONLY evaluate locations that were NOT in the initial baseline snapshot for this session!
            new_earned = [name for name in earned_names if name not in self.state.savegame_baseline]

            new_found = False
            for loc_name in new_earned:
                loc_id = self.location_name_to_id.get(loc_name)
                server_checked = (loc_id in self.state.checked_locations) if loc_id else False
                action = "SEND" if (loc_id and not server_checked) else "IGNORE"
                if loc_id and not server_checked:
                    reason = "New check -> SEND"
                elif server_checked:
                    reason = "Already confirmed on server"
                else:
                    reason = "Unmapped location ID"

                print(f"[ARCHI] Game save check detected:\n"
                      f"        SaveSlot = {sav_path.name}\n"
                      f"        AP Location = {loc_name} ({loc_id})\n"
                      f"        AP Save Checked = True\n"
                      f"        Server Checked = {server_checked}\n"
                      f"        Action = {action}\n"
                      f"        Reason = {reason}")

                if loc_id and not server_checked:
                    if loc_id not in self.state.pending_locations:
                        self.state.pending_locations.add(loc_id)
                        new_found = True

            if self.can_send() and self.state.pending_locations:
                locs_to_send = list(self.state.pending_locations)
                for lid in locs_to_send:
                    name = self.location_id_to_name.get(lid, str(lid))
                    self.bridge.write_inbox_line(f"PRINT SaveGame sync: {name} ({lid})")
                print(f"[AP Client] Dispatched {len(locs_to_send)} location checks to Archipelago server.")
                self._save_state()
                return [{"cmd": "LocationChecks", "locations": locs_to_send}]
            if new_found:
                self._save_state()
        except Exception as e:
            print(f"[WARN] [Save Watcher] Could not process {sav_path.name}: {e}")
        return []
