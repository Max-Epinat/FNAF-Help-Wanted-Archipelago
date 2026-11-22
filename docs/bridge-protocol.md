# Bridge protocol (client <-> UE4SS mod)

The client (launcher client or standalone `ap_client/main.py`) and the Lua mod talk through two plain-text files in the **bridge folder**
(inside the installed mod folder by default; its location is written in the mod's `config.lua`, see [architecture.md](architecture.md)).
Everything here is **VERIFIED** against the code and in-game runs unless marked otherwise.

```text
AP server <-websocket-> client --<bridge>/ap_inbox.txt--> Lua mod (game)
                               <--<bridge>/ap_outbox.txt--
```

## File rules (read before touching these files by hand)

- One command per line, **UTF-8 / ASCII, no BOM**. A line is `COMMAND <payload>`; commands are matched by prefix, so
  a new command name must not start with an existing one (this is why the item snapshot is `RECEIVED_SNAPSHOT`,
  not `ITEMS_...`: the `ITEM` handler matches by its first four characters).
- **PowerShell `>>` writes UTF-16**, which the mod cannot read (the line is silently ignored). Append from Git Bash
  (`printf 'LINE\n' >> <bridge>/ap_inbox.txt`) or `Add-Content -Encoding ascii`.
- `ap_inbox.txt` is **append-only while a client runs** (the client compacts it once, at start: see below), and the mod **re-reads it from the start on every game
  launch**. All state sent through it must therefore be safe to replay in order: the last line of each kind wins.
  Since every connect writes a self-contained block (see "Order at every connect") and `SESSION_SYNC` resets what the earlier blocks set, the mod
  replays **only the last block** (from the `CONNECTED` before the last `SESSION_SYNC` on) in that first pass and logs
  `[SYNC] Inbox replay: skipped N line(s)`. Lines appended later are all delivered. A new line kind must keep working under this rule: anything
  that has to survive a launch must be re-sent in every connect block.
  **Compaction (client start, `BridgeIO.compact_inbox`).** Every `ReceivedItems` packet appends a snapshot of the whole item list, so a long session grows the file quadratically. When a client starts (it holds the instance lock, so nothing else writes) it rewrites the inbox as what the mod would end up with anyway: from the last connect block on, without `STATUS` / `PRINT` lines, with only the newest `RECEIVED_SNAPSHOT` and `APPLIED_ITEMS`; nothing is rewritten when that saves less than 4 KB. A mod that is already running sees the file shorter than what it has read, and reads it again from the start **as history** (a `DEATHLINK` in it is not applied twice). The block must keep starting with `CONNECTED` + `SESSION_SYNC`.
- `ap_outbox.txt` is read by the client from a persisted position (`outbox_position` in the session file). Mods before the bare `CONNECT` put the room
  password in it (`CONNECT <host> <port> <slot> <password>`), and nothing truncates it: at start the client overwrites those passwords with `*`, in place and
  with the same length, in the part it has already executed (`BridgeIO.scrub_outbox_passwords`).

## The saved password (standalone client)

The password is **not** in `connection_profile.json`. It is stored encrypted in `connection_secret.dat` as `dpapi:<base64>` (Windows DPAPI, tied to the
Windows account and to this program: another user or another PC cannot read it; there it is simply asked for again). Only the client reads and writes
that file. Outside Windows (tests only; the game is Windows only) there is no such store and the value is `plain:<base64>`, which is not encryption.

The Lua panel cannot encrypt, so a password the player sets there (`ap_connect <host> <port> <slot> [password]`) goes to the **drop file**
`connection_password.txt` (plain text, the exact password, an empty file meaning "no password"). The client encrypts it into the secret file and deletes the drop
file whenever it reads the profile: at start, and on every bare `CONNECT`. Until a client has run, the drop file is the one place a password is in plain
text. The panel shows `(saved)` while a secret or a non-empty drop file exists and never shows the password; Backspace on that row forgets it.

A profile from an older version that still has `"password"` is migrated at the next client start (moved into the secret file and removed from the profile).
If the password cannot be encrypted it is left where it was, with a warning, rather than lost.

## Client -> mod (`ap_inbox.txt`)

| Line | Meaning |
| :--- | :--- |
| `STATUS <state> <message>` | Connection status (`CONNECTING`, `CONNECTED`, ...). |
| `CONNECTED` | The AP handshake finished. |
| `SESSION_SYNC <seed>_<slot>` | A (re)connect to this session. Session id = seed + slot. |
| `SESSION_BASELINE <location name>` | A location already earned in the session's save when the session started (not to be sent as new). |
| `CONFIRMED_CHECK <id> <name>` | The server confirmed this location. |
| `PRINT <text>` | Text from the server, shown in the mod log. |
| `ITEM <id> <player> <loc> <flags> <index>` | Informational only. Item effects are **not** driven by this line any more. |
| `GATE_TABLE <row>=<GATE>,...` | Level rows that are gated, from `slot_data["level_gates"]`. Absent => the mod's built-in default. |
| `GATE_ITEMS <itemId>=<GATE>,...` | Which received item authorizes which gate, from `slot_data["gate_items"]`. |
| `APPLIED_ITEMS <n> [reset]` | How many items of the server's list (server order) already had their one-shot effect applied. `reset` means the server's list was shorter and `n` was clamped (the mod must lower its count). |
| `RECEIVED_SNAPSHOT <id>,<id>,...` | **All** items of the current connection, in server index order (possibly empty). Replaces the previous snapshot wholesale. |
| `DEATH_LINK_MODE 1\|0` | Whether this slot enabled DeathLink (`slot_data["death_link"]`). Sent at every connect, before the gate table. Must stay ahead of the `DEATHLINK` handler (both start with `DEATH`). |
| `DEATH_LINK_GIFT_BOX 1\|0` | Whether the game over after the prize gift box jumpscare is sent as a death (`slot_data["death_link_gift_box"]`, default `1` when the key is missing, i.e. rooms made before the option). Sent at every connect, **right after** `DEATH_LINK_MODE` (the mod resets it to `1` when it reads that line). Only matters while DeathLink is on. An older mod ignores the line. |
| `RANDOMIZED_GROUPS prizes=1\|0 faz_tokens=1\|0 tapes=1\|0` | Which location groups the slot randomizes (`slot_data["randomize_prizes"]`, `["randomize_faz_tokens"]`, `["randomize_glitch_tapes"]`, each default `1` when the key is missing, i.e. rooms made before the toggles). Sent at every connect, after `DEATH_LINK_GIFT_BOX` (so after `SESSION_SYNC`, which resets the mod to "all randomized"). A group at `0` is vanilla in game: the mod stops overriding the tape count (`tapes`) and the TV token count (`faz_tokens`). `prizes` is informational (prizes are only checks). A key that is missing or not `0` / `1` means randomized. An older mod ignores the line. |
| `SAVE_SLOT <name>` | The save slot (file name without `.sav`) of this session: `Playerarchi_<seed>_<slot>`, only `[A-Za-z0-9_-]`, or `Playerarchi` for a session made before one save per multiworld. Sent at every connect, after `RANDOMIZED_GROUPS` (so after `SESSION_SYNC`, which resets the mod to the shared `Playerarchi`). The mod makes the game use that slot and loads the file into memory once. A name that is not a safe file name is ignored. An older mod ignores the line. |
| `DEATHLINK <source>::<cause>` | A death from another player. Only forwarded when DeathLink is enabled, never our own echo, never the same death twice. |

### Order at every connect

```text
SESSION_SYNC, SESSION_BASELINE*, CONFIRMED_CHECK*, DEATH_LINK_MODE, DEATH_LINK_GIFT_BOX, RANDOMIZED_GROUPS, SAVE_SLOT, [GATE_TABLE], [GATE_ITEMS], APPLIED_ITEMS n, RECEIVED_SNAPSHOT (empty)
```

When DeathLink is enabled the client also sends `ConnectUpdate` with tags `AP, DeathLink` right after `Connected`, which is what makes the server
deliver other players' deaths.

then, when the server sends `ReceivedItems`: `ITEM*` (new indexes only), `APPLIED_ITEMS n [reset]`, `RECEIVED_SNAPSHOT <ids>`.

The empty snapshot at connect is deliberate: the server sends **no** `ReceivedItems` when a slot has none (VERIFIED), so
without it, authorization replayed from old inbox history would never be cleared.

## Mod -> client (`ap_outbox.txt`)

| Line | Meaning |
| :--- | :--- |
| `LOCATION_CHECK <id>` / `LOCATION_CHECK_NAME <name>` | A location was earned. |
| `GOAL` | Goal reached. |
| `CONNECT` / `DISCONNECT` | (Standalone client only; the launcher client ignores them.) Connect with the saved `connection_profile.json` (read again at every bare `CONNECT`, so what the panel just wrote is used), or drop the connection. The mod writes the profile first and sends a bare `CONNECT`, so **the password never goes through the outbox** (an append-only file nothing truncates) **and never into the profile** (see "The saved password"). `CONNECT <host> <port> <slot> [password]` is still accepted from older mods; a bad port is refused with a `PRINT`. |
| `SYNC` | Ask the server for the item list (`Sync`). |
| `SAY <text>` | Chat message. |
| `DEATHLINK <cause>` | The player died: send a DeathLink (ignored by the client unless DeathLink is enabled for the slot). |
| `ITEMS_APPLIED <count>` | The mod applied items up to `count` (server order). Only moves forward; the client persists it and echoes `APPLIED_ITEMS <count>` into the inbox so replayed history ends at the latest value. Accepted even before this connection's list is known; a count above the real list is clamped when the list arrives. |

## Exactly-once item effects

The server's list is the source of truth. The client keeps `applied_item_count` per session (`<bridge>/sessions/<seed>_<slot>.json`;
sessions saved before the field existed start from their old `next_item_index`). `Scripts/lib/item_sync.lua` applies items
`applied+1 ..` in order via `ExactHooks.apply_received_item`, stops at the first item that cannot be applied yet (retry every
second; nothing is skipped because of the startup race, but an item that still fails after `ItemSync.GIVE_UP_SECONDS` = 5 minutes is given up with an `[ERROR]` line in the log, so one item that can never be applied cannot hold back the items behind it and the acknowledgement for good), and acknowledges with `ITEMS_APPLIED`. Result (VERIFIED in game): nothing is lost to the startup
race, nothing is applied twice across reconnects or game/client restarts, and a restarted room clamps instead of re-granting.

Known limit: a crash between applying an effect and the client persisting the acknowledgement can re-apply the last item once.

## Session isolation

Authorization and item state are keyed by the session id (`seed_slot`). On `SESSION_SYNC` with a **new** id the mod clears
item-derived authorization, debug grants and the item count; on every `SESSION_SYNC` it resets the gate table and gate item map
to defaults (the client re-sends them when `slot_data` has them). Nothing is ever read from `Playerarchi.sav`.
