# Memory offsets vs packet updates

Packet IDs reshuffle when Bigpoint rebuilds `main.swf`. The numbers in
[`xenomit-flash-client/src/native_state.cpp`](../../xenomit-flash-client/src/native_state.cpp)
are **Flash Player AVM object layout** for two pinned OCX builds, not wire
opcodes. A new SWF does not contain `ScreenManager+240`. Decompiling it yields
field **names and trait order**, not those integers.

Do **not** fold offset rewriting into `xenomit-packet-updater`. Share the same
**job contract** (manifest + exit codes, no git commit inside the tool) if an
offset pod is added later.

## Why packets automate and offsets do not (yet)

| Signal | Packets | Native offsets |
|--------|---------|----------------|
| Source of truth | `getLibcomModuleId()` in AS3 modules | Flash OCX heap layout + game ScriptObject slots |
| Recoverable from SWF alone | Yes (class → id + read/write ops) | Trait **order/names** only |
| Stability | IDs change every client rebuild | OCX-pinned; game layout changes less often than IDs |
| Existing tooling | `extract_modules.py` → schema | Pattern scan + class/method-id guards in C++; `tools/probe` |

Native mode today accepts only OCX SHA-256
`B0475512D5AD449DFA7D21B5A2645CB1711D2CE98B42C9FE000B5FBC0F8231BD` (DarkFlash)
and `9B39ACE01E557A4A4D469BBB4EC7ADF27D18B9CF3B1CB96AB201ACDEFABAE9F0` (stock
same-version). Method IDs `9581` / `17459` / `17461` gate the walk. Docs state
explicitly that the profile is version-specific.

## Contract for a future offset job

Use a parallel CLI/pod with `kind: "offset"` on the manifest. Inputs: SWF +
OCX hash (and a live capture environment when rediscovery is required). Still
no commit/push/deploy inside the tool.

1. **Independent trigger.** Packet-id remaps do not move AVM fields. Run the
   offset job when decompiled trait order of the walked classes changes, or the
   OCX hash leaves the pinned set. Packet rollout can proceed while
   native-memory bots stay on the previous client build.

2. **Static half (same decompile as packets).** Diff AS3 slots for `Main`,
   `ScreenManager`, `Map`, `Ship`, `Location`, health traits. Unchanged order →
   C++ offsets stay valid; emit a clean manifest and exit 0. Ruffle
   ([`xenomit-client`](../../xenomit-client)) binds slots by name and only needs
   a report if a consumed name disappears.

3. **Dynamic half (layout break).** A capture pod runs the existing native
   probe against a logged-in client. Rediscovery: current pattern scan + class
   names + method-id search. Candidate offsets stay data until probe parity
   against the AS bridge passes (fail-closed rules already in
   `native_state.cpp`: class name, method ids, NaN coords, map id, stale nav).
   Promotion into `native_state.cpp` is a reviewed apply — same idea as packet
   exit `30`.

4. **Roll preference.** Prefer rolling packet-updated bots on the
   Ruffle/named-slot backend first. Native-memory bots wait for the reviewed
   offset manifest.

## Suggested exit codes (mirror packets)

| Code | Meaning |
|------|---------|
| 0 | Trait order / OCX unchanged |
| 10 | Static check clean after game update (offsets still valid) |
| 30 | Layout break; candidates need review before C++ apply |
| 1 | Tool / probe failure |

Infra that schedules packet pods can schedule offset pods with the same shape:
artifact in → working tree / data out → orchestrator rebuilds and rolls the
affected bot client images.
