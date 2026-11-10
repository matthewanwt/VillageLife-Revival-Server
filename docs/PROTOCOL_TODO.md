# Required original client protocol work

The original APK is patched for a legacy binary `ClientService` protocol, usually contacting `10.0.2.2:80`. This repository's NEW server currently exposes `http://127.0.0.1:8765/v1`. An HTTP routing change alone does **not** make the original APK compatible; it needs verified binary login, process and session behaviour, and the game systems behind those messages.

The application deliberately returns `404` or `501` for unimplemented `/web/*` requests, records a privacy-safe endpoint summary, and does not execute the historical 2.11 server as a fallback.

Planned work (separate milestones): packet fixtures with owner consent and no private IDs; request decoding; account/session mapping; client response encoding; initial world/area data; buildings/background jobs; family and travel rules; save parity; Wi-Fi-on enforced guest egress isolation; installer and regression test validation on Windows.
