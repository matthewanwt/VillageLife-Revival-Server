# Release gate and remaining work

**No complete installer is shipped. Both Inno Setup build scripts deliberately fail with `VL-INSTALLER-NOT-READY`.** This avoids distributing an API-only installer or implicitly launching the old backend. There is **no old server runtime fallback**.

## Functional gaps before real original-XAPK acceptance

1. Reimplement and validate every original RPC required in a clean client launch and login, beyond the limited tutorial, startup, area and deterministic tasks already implemented. Preserve exact response contracts and secure per-account state. Missing-operation reporter provides operation name/count only.
2. Complete all central gameplay mechanics against recovered authored definitions: construction, recurring building resource production, fatigue/needs, farming/harvesting variations, quests, rewards, social/family/marriage/pregnancy, character ageing, placements, habitat capacity, shops and genuine Riverside/Mountain interaction and progression. Do not invent original rules in the absence of evidence; record missing operations with reproducible fixtures.
3. Verify client asset responses and both manifests against the **actual** XAPK/OBB, correct APK patching and stable signing identity, appropriate Android package/expansion install order, and proof the installed client opens a playable normal village.
4. Complete the managed BlueStacks first-run wizard: detect existing install, guide an unsupported/unknown automatic creation through Multi-instance Manager, rescan after creation, select by internal ID, verify current port and persistent fingerprint, targeted ADB install of the selected instance only. Recover only after explicit approval if any instance is already populated.
5. Verify Wi-Fi-on network policy at the actual BlueStacks guest boundary: allow `10.0.2.2:80`, block external IPv4, IPv6, DNS, UDP and alternate paths under enforcement, without interfering with normal Windows internet. Our collected `ip route get 1.1.1.1` showed a guest route via 10.0.2.2, **not isolation**. A few failed probes are not proof. Do not disable isolation guards.
6. Real preserved-save migration requires complete gameplay-semantic field translation and verified round trips. Current importer retains original profile and save data, including unknown fields, but this alone does not prove playability. Test migration on **copies** representing each play stage, then verify original source hashes and new-game state (villagers/relations, tasks, inventories, buildings, quests, areas).
7. Validate multi-instance isolation, restart, error recovery, first launch, upgrading/uninstalling without losing saves, installer signing, Windows 10/11 clean PCs and hardware/performance variance. Keep immutable source archives and private data outside Git/distribution.

## Automated acceptance criteria

- Original-XAPK login, client rendering and **real save -> game action -> server persistence -> restart -> same world**, without executing or importing historical backend modules.
- Two instances with different player IDs and saves remain separate, and altered or deleted saved instance settings trigger a user-facing choice, never silent default selection.
- All required game operations respond with verified original response schemas. No hidden 501s during standard interactions or fabricated success.
- Installer/launcher can complete fresh setup with guided BlueStacks creation and local XAPK preparation without manual ADB commands. Backups and migrations are idempotent and reversible.
- Wi-Fi enabled on Windows works while *verified* Android guest egress restrictions remain in effect.

## Current evidence

39 applicable synthetic/unit tests passed on Linux; additionally, an opt-in original-protocol HTTP smoke test passed using the user's real extracted game definitions and a preserved-save test import. Native endpoint patch offsets verified uniquely in the user-supplied original APK. **Windows C# compilation, real XAPK boot/play and safe networking are not tested here.** Do not call this a release candidate or assume it is playable.
