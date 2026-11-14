# Development security rules

- Bind the NEW HTTP API to localhost only (`127.0.0.1`); don't expose it to a public network without authentication, TLS and explicit server-hardening review.
- Do not run the original APK against this development API: the original binary RPC is missing and has no old-server fallback.
- Installed game data and accounts live under `%LOCALAPPDATA%\VillageLifeRevivalNext`, not in Program Files, Git or BlueStacks images. Uninstalling a test manager does not erase player saves.
- The production/release installer does not include original game assets. The separately labelled private reliability-test installer includes only the user-supplied XAPK and its local table/inventory files for the explicitly invited tester; it excludes the duplicate OBB, saves, signing identity, credentials, and original server source. The OBB is extracted from the XAPK during setup.
- Missing-request aggregation stores RPC names and JSON key/type shapes only. Startup and area responses also record aggregate entity-type counts and material-source template-ID counts, but no entity IDs. It never writes request values or bodies, headers, query strings, IP addresses, call IDs, session tokens, save contents or player identities to the exported report.
- Export diagnostics before sharing and review locally; report labels intentionally state that network isolation is not verified.
- Guest Wi-Fi isolation must be established using enforced, revocable, instance-scoped policy and TCP/UDP/DNS/IPv6 tests before broader testing. A configured BlueStacks NAT address is not sufficient.
- BlueStacks instance binding uses explicit internal IDs, checks live ADB port and saved installation and display-name hints; it never falls back to an unrelated instance.
