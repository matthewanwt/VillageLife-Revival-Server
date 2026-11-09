# Versioned development API (`/v1`)

**Not compatible with the original APK yet.** The old `/web/ClientService/Login`
and `/web/ClientService/Process` are not implemented in the new HTTP adapter.

The server binds `127.0.0.1` only. Every endpoint other than `/health`
requires a strong bearer token generated through the local CLI, stored only as
a SHA-256 digest in SQLite. Tokens should be protected and eventually replaced
with short-lived sessions/device onboarding for community use.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness (no account data) |
| GET | `/v1/villages` | List own village metadata |
| POST | `/v1/villages` with `{}` | Create **empty development fixture** |
| GET | `/v1/villages/<id>` | Read own versioned save |
| POST | `/v1/villages/<id>/actions` | Dispatch verified action |
| POST | `/v1/villages/<id>/tick` with `{}` | Reconcile due timers, not rewards |

Example new-client action request (currently most original actions return 501):

```json
{
  "action": "area.change",
  "operationKey": "device-event-00001",
  "expectedRevision": 0,
  "data": {"areaId": 1}
}
```

Expected responses include `401` unauthenticated, `404` resource not owned,
`409` revision/idempotency conflict, `400` invalid data and `501` original rule
not ported. Request size is limited to 1 MiB. No CORS headers are enabled.

For original game binary protocol, see `src/villagelife/protocol/` and
`legacy_reference/backend/server.py` (reference only). A future adapter must
preserve content encoding, RPC error mappings and original response shapes.
