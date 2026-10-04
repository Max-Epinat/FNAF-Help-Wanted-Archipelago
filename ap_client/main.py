import asyncio
import json
import os
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import websockets

try:
    from save_reader import (
        parse_gvas_save,
        extract_earned_locations,
        get_active_savegame_path,
        ensure_clean_archipelago_save,
        get_archipelago_savegame_path,
        get_normal_savegame_path,
    )
except ImportError:
    from ap_client.save_reader import (
        parse_gvas_save,
        extract_earned_locations,
        get_active_savegame_path,
        ensure_clean_archipelago_save,
        get_archipelago_savegame_path,
        get_normal_savegame_path,
    )

# Pure state, bridge file I/O and formatters live in bridge_core (no websockets / GUI); re-exported here so
# `from ap_client.main import BridgeIO, BridgeState, ...` keeps working.
try:
    from bridge_core import (
        CLIENT_STATUS_GOAL,
        CLIENT_VERSION,
        GATE_ID_PATTERN,
        STATUS_AUTHENTICATING,
        STATUS_CONNECTED,
        STATUS_CONNECTING,
        STATUS_DISCONNECTED,
        STATUS_ERROR,
        BridgeCore,
        BridgeIO,
        BridgeState,
        InstanceLock,
        SaveAPI,
        find_bridge_dir,
        format_applied_items_line,
        format_gate_items_line,
        format_gate_table_line,
        format_items_snapshot_line,
    )
except ImportError:
    from ap_client.bridge_core import (
        CLIENT_STATUS_GOAL,
        CLIENT_VERSION,
        GATE_ID_PATTERN,
        STATUS_AUTHENTICATING,
        STATUS_CONNECTED,
        STATUS_CONNECTING,
        STATUS_DISCONNECTED,
        STATUS_ERROR,
        BridgeCore,
        BridgeIO,
        BridgeState,
        InstanceLock,
        SaveAPI,
        find_bridge_dir,
        format_applied_items_line,
        format_gate_items_line,
        format_gate_table_line,
        format_items_snapshot_line,
    )

BRIDGE_COMMAND_POLL_SECONDS = 0.05
IPC_PORT = 38424



class _MainSaveAPI(SaveAPI):
    """Resolves the save reader through this module's names at call time, so `ap_client.main.<name>` can be patched."""

    def parse(self, data):
        return parse_gvas_save(data)

    def extract_earned(self, parsed):
        return extract_earned_locations(parsed)

    def archipelago_save_path(self):
        return get_archipelago_savegame_path()

    def ensure_clean_save(self):
        return ensure_clean_archipelago_save()


class APBridgeClient(BridgeCore):
    """The standalone websockets transport (plus lock, IPC and window) around BridgeCore."""

    def __init__(self, bridge_dir: Path):
        self.bridge_dir = bridge_dir
        bridge = BridgeIO(bridge_dir)
        self.lock_path = bridge_dir / "ap_client.lock"
        self._instance_lock = InstanceLock(self.lock_path)
        self.lock_acquired = False
        self._acquire_single_instance_lock()

        # session state, item sync, location checks and save polling live in BridgeCore
        super().__init__(bridge_dir, save_api=_MainSaveAPI(), bridge=bridge)

        self.ws: websockets.WebSocketClientProtocol | None = None
        self.gui: Any = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.connect_event = asyncio.Event()
        self.active_session_task: asyncio.Task | None = None

        self._update_status(STATUS_DISCONNECTED, message="Idle. Waiting for connection command.")

    # ---- BridgeCore hooks ----

    def can_send(self) -> bool:
        return self.status == STATUS_CONNECTED and bool(self.ws)

    def notify_status(self) -> None:
        if self.gui:
            self.gui.update_status(self.status, self.last_message)

    # Names used by the GUI, the console and the tests; the logic is in BridgeCore.
    _update_status = BridgeCore.update_status
    _on_room_update = BridgeCore.on_room_update
    _on_received_items = BridgeCore.on_received_items
    _on_items_applied = BridgeCore.on_items_applied

    def schedule_command(self, cmd_line: str) -> None:
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._execute_command(cmd_line), self.loop)


    def _acquire_single_instance_lock(self) -> None:
        self._instance_lock.acquire()
        self.lock_acquired = self._instance_lock.acquired

    @staticmethod
    def _is_pid_running(pid: int) -> bool:
        return InstanceLock.is_pid_running(pid)

    def release_single_instance_lock(self) -> None:
        self._instance_lock.release()
        self.lock_acquired = self._instance_lock.acquired

    def _build_uris(self) -> list[str]:
        host = str(self.profile.get("server_host", "archipelago.gg")).strip()
        port = int(self.profile.get("server_port", 38281))
        scheme = str(self.profile.get("server_scheme", "")).strip().lower()

        if scheme in {"ws", "wss"}:
            return [f"{scheme}://{host}:{port}"]
        if host == "archipelago.gg" or host.endswith(".archipelago.gg"):
            return [f"wss://{host}:{port}", f"ws://{host}:{port}"]
        return [f"ws://{host}:{port}", f"wss://{host}:{port}"]

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        ipc_server = await self._start_ipc_server()
        try:
            # If auto_connect is set in profile, trigger connection immediately
            if self.profile.get("auto_connect", False):
                self.connect_event.set()

            while True:
                # Poll local commands from outbox file
                await self._poll_outbox()
                await self._poll_savegame()

                # If connection requested and not currently connected
                if self.connect_event.is_set() and (self.active_session_task is None or self.active_session_task.done()):
                    self.connect_event.clear()
                    self.disconnect_requested = False
                    self.active_session_task = asyncio.create_task(self._session_loop())

                await asyncio.sleep(BRIDGE_COMMAND_POLL_SECONDS)
        finally:
            if ipc_server:
                ipc_server.close()
                await ipc_server.wait_closed()
            self.release_single_instance_lock()

    async def _start_ipc_server(self):
        try:
            server = await asyncio.start_server(self._handle_ipc_client, "127.0.0.1", IPC_PORT)
            print(f"[AP Client] IPC server listening on 127.0.0.1:{IPC_PORT}")
            return server
        except Exception as e:
            print(f"[AP Client] Could not start IPC server (port in use?): {e}")
            return None

    async def _handle_ipc_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if text:
                    await self._execute_command(text)
                    writer.write(f"OK {self.status} {self.last_message}\n".encode("utf-8"))
                    await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _poll_outbox(self) -> None:
        lines = self.bridge.read_outbox_lines(self.state)
        if not lines:
            return
        for line in lines:
            await self._execute_command(line)
        self.bridge.save_state(self.state, self.location_id_to_name)

    async def _poll_savegame(self) -> None:
        for packet in self.collect_savegame_packets():
            await self._send_packet(packet)

    async def _execute_command(self, line: str) -> None:
        parts = line.split(" ", 1)
        cmd = parts[0].strip().upper()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "SHOW_UI":
            if self.gui:
                self.gui.bring_to_front()
            return

        if cmd == "CONNECT":
            # CONNECT <host> <port> <slot> [password]
            args = arg.split(" ")
            if len(args) >= 3:
                self.profile["server_host"] = args[0]
                self.profile["server_port"] = int(args[1])
                self.profile["slot"] = args[2]
                self.profile["password"] = args[3] if len(args) > 3 else ""
                self.server_str = f"{self.profile['server_host']}:{self.profile['server_port']}"
                self.slot = self.profile["slot"]
                self.bridge.save_profile(self.profile)
                self.disconnect_requested = True
                if self.ws:
                    await self.ws.close()
                self.connect_event.set()
                self._update_status(STATUS_CONNECTING, message=f"Connecting to {self.server_str} as {self.slot}...")
            else:
                # Connect using saved profile
                self.server_str = f"{self.profile['server_host']}:{self.profile['server_port']}"
                self.slot = self.profile["slot"]
                self.connect_event.set()
                self._update_status(STATUS_CONNECTING, message=f"Connecting to {self.server_str}...")
            return

        if cmd == "DISCONNECT":
            self.disconnect_requested = True
            if self.ws:
                await self.ws.close()
            self._update_status(STATUS_DISCONNECTED, message="Disconnected by user request.")
            return

        if cmd == "SAVE_PROFILE":
            # SAVE_PROFILE <host> <port> <slot> [password]
            args = arg.split(" ")
            if len(args) >= 3:
                self.profile["server_host"] = args[0]
                self.profile["server_port"] = int(args[1])
                self.profile["slot"] = args[2]
                self.profile["password"] = args[3] if len(args) > 3 else ""
                self.bridge.save_profile(self.profile)
                self.bridge.write_inbox_line("PRINT Profile saved.")
            return

        for packet in self.game_command_packets(cmd, arg):
            await self._send_packet(packet)


    async def _command_location_check(self, arg: str) -> None:
        for packet in self.location_check_packets(arg):
            await self._send_packet(packet)

    async def _command_location_check_name(self, arg: str) -> None:
        for packet in self.location_check_name_packets(arg):
            await self._send_packet(packet)

    async def _session_loop(self) -> None:
        uris = self._build_uris()
        last_exc: Exception | None = None

        for uri in uris:
            if self.disconnect_requested:
                break
            self._update_status(STATUS_CONNECTING, message=f"Connecting to {uri}...")
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=20, max_size=None) as ws:
                    self.ws = ws
                    self.last_error = ""
                    self._update_status(STATUS_AUTHENTICATING, message=f"Connected to socket. Authenticating as {self.slot}...")

                    while not self.disconnect_requested:
                        await self._poll_outbox()
                        await self._poll_savegame()

                        try:
                            payload = await asyncio.wait_for(ws.recv(), timeout=BRIDGE_COMMAND_POLL_SECONDS)
                            await self._handle_server_payload(payload)
                        except asyncio.TimeoutError:
                            pass

                last_exc = None
                break
            except Exception as e:
                last_exc = e
                if not self.disconnect_requested:
                    self._update_status(STATUS_ERROR, error=str(e), message=f"Failed to connect to {uri}: {e}")

        self.ws = None
        if self.disconnect_requested:
            self._update_status(STATUS_DISCONNECTED, message="Disconnected.")
        elif last_exc:
            self._update_status(STATUS_ERROR, error=str(last_exc), message=f"Connection failed: {last_exc}")

    async def _send_packet(self, packet: dict[str, Any]) -> None:
        if self.ws:
            await self.ws.send(json.dumps([packet]))

    async def _handle_server_payload(self, raw_payload: str) -> None:
        try:
            parsed = json.loads(raw_payload)
            packets = parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return

        for p in packets:
            cmd = p.get("cmd")
            if cmd == "RoomInfo":
                self.current_seed_name = str(p.get("seed_name", ""))
                print(f"[AP Client] RoomInfo received: seed_name='{self.current_seed_name}'")
                await self._send_packet(self.build_connect_packet(str(uuid.uuid4())))
            elif cmd == "Connected":
                self._on_connected(p)
            elif cmd == "ConnectionRefused":
                self.on_connection_refused(p)
            elif cmd == "RoomUpdate":
                self._on_room_update(p)
            elif cmd == "ReceivedItems":
                self._on_received_items(p)
            elif cmd == "PrintJSON":
                self.on_print(p)
            elif cmd == "Bounced":
                self.on_bounced(p)

    def _on_connected(self, packet: dict[str, Any]) -> None:
        for outgoing in self.on_connected(packet):
            asyncio.create_task(self._send_packet(outgoing))




class DesktopGUI:
    def __init__(self, client: APBridgeClient):
        import tkinter as tk
        from tkinter import scrolledtext

        self.client = client
        self.client.gui = self
        self.root = tk.Tk()
        self.root.title("FNAF: Help Wanted - Archipelago Client")
        self.root.geometry("540x540")
        self.root.minsize(480, 440)
        self.root.configure(bg="#181824")

        # Top Header
        hdr = tk.Frame(self.root, bg="#181824")
        hdr.pack(fill="x", padx=16, pady=(12, 6))

        title_box = tk.Frame(hdr, bg="#181824")
        title_box.pack(side="left", fill="y")
        tk.Label(title_box, text="FNAF: Help Wanted", font=("Segoe UI", 13, "bold"), fg="#4da6ff", bg="#181824").pack(anchor="w")
        tk.Label(title_box, text="Archipelago Multiworld Client", font=("Segoe UI", 9), fg="#888899", bg="#181824").pack(anchor="w")

        self.status_pill = tk.Label(hdr, text="● DISCONNECTED", font=("Segoe UI", 10, "bold"), fg="#ff5252", bg="#2a1820", padx=10, pady=4)
        self.status_pill.pack(side="right")

        # Connection Form Frame
        form = tk.LabelFrame(self.root, text=" Connection Settings ", bg="#222232", fg="#9999cc", font=("Segoe UI", 9, "bold"), padx=12, pady=10)
        form.pack(fill="x", padx=16, pady=6)

        # Host & Port in one row
        tk.Label(form, text="Server Host:", bg="#222232", fg="#cccccc", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=3)
        self.ent_host = tk.Entry(form, bg="#2e2e42", fg="#ffffff", insertbackground="#ffffff", relief="flat", font=("Segoe UI", 9))
        self.ent_host.insert(0, str(self.client.profile.get("server_host", "archipelago.gg")))
        self.ent_host.grid(row=0, column=1, sticky="ew", padx=(4, 12), pady=3)

        tk.Label(form, text="Port:", bg="#222232", fg="#cccccc", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", pady=3)
        self.ent_port = tk.Entry(form, width=8, bg="#2e2e42", fg="#ffffff", insertbackground="#ffffff", relief="flat", font=("Segoe UI", 9))
        self.ent_port.insert(0, str(self.client.profile.get("server_port", 38281)))
        self.ent_port.grid(row=0, column=3, sticky="ew", padx=4, pady=3)

        # Slot Name
        tk.Label(form, text="Player Slot:", bg="#222232", fg="#cccccc", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=3)
        self.ent_slot = tk.Entry(form, bg="#2e2e42", fg="#ffffff", insertbackground="#ffffff", relief="flat", font=("Segoe UI", 9))
        self.ent_slot.insert(0, str(self.client.profile.get("slot", "Player1")))
        self.ent_slot.grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=3)

        # Password
        tk.Label(form, text="Password:", bg="#222232", fg="#cccccc", font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", pady=3)
        self.ent_pwd = tk.Entry(form, show="*", bg="#2e2e42", fg="#ffffff", insertbackground="#ffffff", relief="flat", font=("Segoe UI", 9))
        self.ent_pwd.insert(0, str(self.client.profile.get("password", "")))
        self.ent_pwd.grid(row=2, column=1, columnspan=3, sticky="ew", padx=4, pady=3)

        # Auto-connect checkbox
        self.var_autoconnect = tk.BooleanVar(value=bool(self.client.profile.get("auto_connect", False)))
        chk = tk.Checkbutton(form, text="Auto-connect when game launches", variable=self.var_autoconnect,
                             bg="#222232", fg="#aaaaaa", selectcolor="#2e2e42", activebackground="#222232",
                             activeforeground="#ffffff", font=("Segoe UI", 9))
        chk.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 2))
        form.columnconfigure(1, weight=3)
        form.columnconfigure(3, weight=1)

        # Buttons Row
        btn_bar = tk.Frame(self.root, bg="#181824")
        btn_bar.pack(fill="x", padx=16, pady=6)

        self.btn_connect = tk.Button(btn_bar, text="Connect", bg="#00c853", fg="#ffffff", activebackground="#009624",
                                     activeforeground="#ffffff", relief="flat", font=("Segoe UI", 9, "bold"), padx=14, pady=4,
                                     command=self.on_connect_toggle)
        self.btn_connect.pack(side="left", padx=(0, 8))

        self.btn_goal = tk.Button(btn_bar, text="Send Goal (Victory)", bg="#3f51b5", fg="#ffffff",
                                  activebackground="#303f9f", activeforeground="#ffffff", relief="flat",
                                  font=("Segoe UI", 9), padx=10, pady=4, command=self.on_send_goal)
        self.btn_goal.pack(side="left")

        # Launch Game Buttons Row
        launch_bar = tk.Frame(self.root, bg="#181824")
        launch_bar.pack(fill="x", padx=16, pady=(2, 6))

        self.btn_launch_flat = tk.Button(launch_bar, text="🎮 Play Normal (Flat)", bg="#252538", fg="#4da6ff",
                                         activebackground="#353550", activeforeground="#ffffff", relief="flat",
                                         font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                                         command=lambda: self.on_launch_game("normal"))
        self.btn_launch_flat.pack(side="left", padx=(0, 8))

        self.btn_launch_vr = tk.Button(launch_bar, text="🥽 Play in VR", bg="#252538", fg="#b388ff",
                                       activebackground="#353550", activeforeground="#ffffff", relief="flat",
                                       font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                                       command=lambda: self.on_launch_game("vr"))
        self.btn_launch_vr.pack(side="left")

        # Live Activity Log Frame
        log_frame = tk.LabelFrame(self.root, text=" Live Activity Log ", bg="#181824", fg="#9999cc", font=("Segoe UI", 9, "bold"), padx=6, pady=4)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self.log_box = scrolledtext.ScrolledText(log_frame, bg="#111118", fg="#dddddd", font=("Consolas", 9), relief="flat")
        self.log_box.pack(fill="both", expand=True)

        self.log("Archipelago Client initialized. Ready to connect.")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, text: str) -> None:
        tstr = time.strftime("[%H:%M:%S] ")
        def _do_log():
            try:
                self.log_box.insert("end", tstr + text + "\n")
                self.log_box.see("end")
            except Exception:
                pass
        self.root.after(0, _do_log)

    def update_status(self, status: str, message: str = "") -> None:
        def _do_update():
            try:
                color_map = {
                    STATUS_CONNECTED: ("#00e676", "#142d1e", "● CONNECTED"),
                    STATUS_CONNECTING: ("#ffb300", "#302610", "● CONNECTING..."),
                    STATUS_AUTHENTICATING: ("#ffb300", "#302610", "● AUTHENTICATING..."),
                    STATUS_DISCONNECTED: ("#ff5252", "#2d1618", "● DISCONNECTED"),
                    STATUS_ERROR: ("#ff5252", "#2d1618", "● ERROR"),
                }
                fg, bg, label = color_map.get(status, ("#aaaaaa", "#222222", f"● {status}"))
                self.status_pill.config(text=label, fg=fg, bg=bg)

                if status == STATUS_CONNECTED:
                    self.btn_connect.config(text="Disconnect", bg="#e53935", activebackground="#b71c1c")
                else:
                    self.btn_connect.config(text="Connect", bg="#00c853", activebackground="#009624")

                self.update_stats()
                if message:
                    self.log(f"Status [{status}]: {message}")
            except Exception:
                pass
        self.root.after(0, _do_update)

    def update_stats(self) -> None:
        def _do_stats():
            try:
                chk_count = len(self.client.state.checked_locations)
                item_count = self.client.received_items_count
                self.lbl_stats.config(text=f"Checks: {chk_count} / 177 | Items: {item_count}")
            except Exception:
                pass
        self.root.after(0, _do_stats)

    def bring_to_front(self) -> None:
        def _do_bring():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.after_idle(self.root.attributes, "-topmost", False)
                self.root.focus_force()
            except Exception:
                pass
        self.root.after(0, _do_bring)

    def on_connect_toggle(self) -> None:
        if self.client.status in (STATUS_CONNECTED, STATUS_CONNECTING, STATUS_AUTHENTICATING):
            self.client.schedule_command("DISCONNECT")
        else:
            host = self.ent_host.get().strip() or "archipelago.gg"
            port = self.ent_port.get().strip() or "38281"
            slot = self.ent_slot.get().strip() or "Player1"
            pwd = self.ent_pwd.get().strip()
            autoconnect = self.var_autoconnect.get()

            # Save profile
            self.client.profile["server_host"] = host
            try:
                self.client.profile["server_port"] = int(port)
            except ValueError:
                self.client.profile["server_port"] = 38281
            self.client.profile["slot"] = slot
            self.client.profile["password"] = pwd
            self.client.profile["auto_connect"] = autoconnect
            self.client.bridge.save_profile(self.client.profile)

            cmd = f"CONNECT {host} {port} {slot} {pwd}".strip()
            self.client.schedule_command(cmd)

    def on_send_goal(self) -> None:
        self.client.schedule_command("GOAL")
        self.log("Manual Goal packet requested.")

    def on_launch_game(self, mode: str) -> None:
        shipping_exe = Path(r"C:\Program Files (x86)\Steam\steamapps\common\FNAFVRHelpWanted\freddys\Binaries\Win64\freddys-Win64-Shipping.exe")
        bin_dir = shipping_exe.parent
        if not shipping_exe.exists():
            self.log(f"Error: Game executable not found at {shipping_exe}")
            return

        if mode == "normal":
            import subprocess
            subprocess.Popen([str(shipping_exe), "-nohmd"], cwd=str(bin_dir))
            self.log("Launched Help Wanted in Flat / Normal Mode (-nohmd).")
        else:
            import os
            try:
                os.startfile("steam://rungameid/732690")
                self.log("Sent VR launch command to Steam (AppID 732690).")
            except Exception:
                import subprocess
                subprocess.Popen([str(shipping_exe), "-vr"], cwd=str(bin_dir))
                self.log("Launched Help Wanted in VR mode.")

    def on_close(self) -> None:
        self.client.schedule_command("DISCONNECT")
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    # The mod is the single source of truth for the bridge folder (its config.lua), same as for the launcher client.
    bridge_dir = find_bridge_dir()
    if bridge_dir is None:
        print("[AP Client] ERROR: could not find the game mod's bridge folder. Install the mod with "
              "scripts/install-mod.ps1 (it writes the folder into the mod's config.lua) or set FNAFHW_BRIDGE_DIR.")
        sys.exit(1)
    print(f"[AP Client] Bridge folder: {bridge_dir}")
    client = APBridgeClient(bridge_dir)

    is_headless = "--headless" in sys.argv or "-q" in sys.argv or "--no-gui" in sys.argv

    if is_headless:
        try:
            asyncio.run(client.run())
        except KeyboardInterrupt:
            pass
        finally:
            client.release_single_instance_lock()
    else:
        gui = DesktopGUI(client)

        def run_async():
            try:
                asyncio.run(client.run())
            except Exception as e:
                print(f"[AP Client] Background async error: {e}")
            finally:
                client.release_single_instance_lock()

        t = threading.Thread(target=run_async, daemon=True)
        t.start()
        try:
            gui.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            client.release_single_instance_lock()


if __name__ == "__main__":
    main()
