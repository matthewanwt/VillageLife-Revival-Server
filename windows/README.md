# Windows integration status

The repository contains a **new backend-only Windows development manager** and Inno Setup source, but **there is no tested, complete game installer yet**. The original APK-facing `/web/ClientService/Login` and `/web/ClientService/Process` endpoints are partially implemented in the independent backend. Full game behaviour is not.

The Inno Setup build scripts deliberately stop with `VL-INSTALLER-NOT-READY` rather than releasing an incomplete installer. This is intentional, in accordance with the project requirement for a single finished installer rather than a partial test installer.

Already available for development: discover Pie64 instances, bind an exact internal ID, validate display name/ADB port/install-path changes, read-only network diagnostics, and standalone SQLite-backed new server. Missing: guided first-run instance creation/selection UI, targeted APK/OBB install, verified Windows binary build, all original gameplay, real save migration semantics, and a tested Wi-Fi-on isolation policy.

Source: `windows/launcher/`, `windows/installer/`. Current operational and acceptance gaps: `docs/REMAINING_GAMEPLAY.md`. XAPK is a private local build input, not a Git or public release asset without appropriate distribution rights.
