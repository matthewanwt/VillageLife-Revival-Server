# Missing original-client request reports (development test)

## Why

An unimplemented `Client*/*` RPC can cause a lost connection or missing game
function. The compatible 2.11 backend now records a **small separate** record
for each distinct failed original-client operation, without changing the
response returned by the server. Unknown legacy endpoints are recorded too.
The purpose is to prioritise recovery work for building functions, area
transitions, villager actions and future gameplay modules.

## Source of truth

The instrumented compatibility backend lives at
`legacy_reference/backend/server.py` and `missing_requests.py`, copied to the
**staged** `backend/` directory by `Build-TestInstaller.ps1`.
The new modular `src/villagelife` server has NOT yet been substituted for it.

- Native Process and Community endpoint operations that return `501` are recorded.
- Explicit `400` responses mentioning a rule not being implemented are noted
  as `known_rule_gap` (not every validation error).
- Unknown HTTP GET is recorded as `404`; unknown decoded POST as `501`.
- Crashed POST handlers are recorded as `500` with no body data.
- Known successful calls and ordinary 400 validation failures are omitted.
- The HTTP response is **left unchanged**. A `501` is not transformed into
  fake success; the missing feature still needs engineering.

## Data locations

On a staged test installation:

- Private temporary source: `backend/private_state/diagnostics/missing_requests.jsonl`
- User-visible export: `support/VillageLife-MissingRequests-<timestamp>.zip`

Both directories are ignored by Git. The source file is bounded/rotated at
1 MiB and in-memory repeats are throttled; no raw HTTP bodies, login headers,
email addresses, villager names, save files, client IPs or device IDs are
stored in this telemetry. Only static-style operation names and hashed unknown
route signatures are recorded. A small number of reports may be missed on
crash, or counts reset after restart. This is discovery telemetry, not a
complete audit or a reliable request counter.

## Player instructions

1. Run the game, reproduce an issue, then stop or leave it running.
2. In the launcher, click **Export Missing Requests**.
3. Open and review the ZIP's `missing-requests-summary.json`.
4. Send it **privately** to a trusted developer. No full saves or raw request
   logs should be requested publicly.

An empty report means nothing missing was captured, not that the game is fully
implemented. Network-level failures that never reach this backend are outside
this reporter's scope. For those, use Export Diagnostics separately.
