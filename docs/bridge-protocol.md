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
- `ap_inbox.txt` is **append-only and never truncated**, and the mod **re-reads it from the start on every game
  launch**. All state sent through it must therefore be safe to replay in order: the last line of each kind wins.
  Since every connect writes a self-contained block (see "Order at every connect") and `SESSION_SYNC` resets what the earlier blocks set, the mod
  replays **only the last block** (from the `CONNECTED` before the last `SESSION_SYNC` on) in that first pass and logs
  `[SYNC] Inbox replay: skipped N line(s)`. Lines appended later are all delivered. A new line kind must keep working under this rule: anything
  that has to survive a launch must be re-sent in every connect block.
- `ap_outbox.txt` is read by the client from a persisted position (`outbox_position` in the session file).

## Client -> mod (`ap_inbox.txt`)

| Line | Meaning |
| :--- | :--- |
| `STATUS <state> <message>` | Connection status (`CONNECTING`, `CONNECTED`, ...). |
| `CONNECTED` | The AP handshake finished. |
| `SESSION_SYNC <seed>_<slot>` | A (re)connect to this session. Session id = seed + slot. |
| `SESSION_BASELINE <location name>` | A location already earned in `Playerarchi.sav` when the session started (not to be sent as new). |
| `CONFIRMED_CHECK <id> <name>` | The server confirmed this location. |
| `PRINT <text>` | Text from the server, shown in the mod log. |
| `ITEM <id> <player> <loc> <flags> <index>` | Informational only. Item effects are **not** driven by this line any more. |
| `GATE_TABLE <row>=<GATE>,...` | Level rows that are gated, from `slot_data["level_gates"]`. Absent => the mod's built-in default. |
| `GATE_ITEMS <itemId>=<GATE>,...` | Which received item authorizes which gate, from `slot_data["gate_items"]`. |
| `APPLIED_ITEMS <n> [reset]` | How many items of the server's list (server order) already had their one-shot effect applied. `reset` means the server's list was shorter and `n` was clamped (the mod must lower its count). |
| `RECEIVED_SNAPSHOT <id>,<id>,...` | **All** items of the current connection, in server index order (possibly empty). Replaces the previous snapshot wholesale. |
| `DEATH_LINK_MODE 1\|0` | Whether this slot enabled DeathLink (`slot_data["death_link"]`). Sent at every connect, before the gate table. Must stay ahead of the `DEATHLINK` handler (both start with `DEATH`). |
| `DEATHLINK <source>::<cause>` | A death from another player. Only forwarded when DeathLink is enabled, never our own echo, never the same death twice. |

### Order at every connect

```text
SESSION_SYNC, SESSION_BASELINE*, CONFIRMED_CHECK*, DEATH_LINK_MODE, [GATE_TABLE], [GATE_ITEMS], APPLIED_ITEMS n, RECEIVED_SNAPSHOT (empty)
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
| `SYNC` | Ask the server for the item list (`Sync`). |
| `SAY <text>` | Chat message. |
| `DEATHLINK <cause>` | The player died: send a DeathLink (ignored by the client unless DeathLink is enabled for the slot). |
| `ITEMS_APPLIED <count>` | The mod applied items up to `count` (server order). Only moves forward; the client persists it and echoes `APPLIED_ITEMS <count>` into the inbox so replayed history ends at the latest value. Accepted even before this connection's list is known; a count above the real list is clamped when the list arrives. |

## Exactly-once item effects

The server's list is the source of truth. The client keeps `applied_item_count` per session (`<bridge>/sessions/<seed>_<slot>.json`;
sessions saved before the field existed start from their old `next_item_index`). `Scripts/lib/item_sync.lua` applies items
`applied+1 ..` in order via `ExactHooks.apply_received_item`, stops at the first item that cannot be applied yet (retry every
second; nothing is skipped), and acknowledges with `ITEMS_APPLIED`. Result (VERIFIED in game): nothing is lost to the startup
race, nothing is applied twice across reconnects or game/client restarts, and a restarted room clamps instead of re-granting.

Known limit: a crash between applying an effect and the client persisting the acknowledgement can re-apply the last item once.

## Session isolation

Authorization and item state are keyed by the session id (`seed_slot`). On `SESSION_SYNC` with a **new** id the mod clears
item-derived authorization, debug grants and the item count; on every `SESSION_SYNC` it resets the gate table and gate item map
to defaults (the client re-sends them when `slot_data` has them). Nothing is ever read from `Playerarchi.sav`.
