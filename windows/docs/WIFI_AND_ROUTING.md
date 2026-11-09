# BlueStacks networking: Wi-Fi-on acceptance gate

## Existing constraints

- The current, verified original-client patch uses `http://10.0.2.2/` with no explicit port. Android therefore connects to **host port 80**.
- The Python 2.11 backend binds `127.0.0.1:80`; the launcher must test that exact port before starting it.
- A different free backend port **does not fix** the client endpoint unless the modified APK is rebuilt and verified to use it. This integration intentionally does **not** silently switch ports.
- BlueStacks `--nat-bind-ip1=127.0.0.1 --nat-localhostreachable1=on` configures NAT, but previously **did not consistently prevent outbound internet access** when Windows Wi-Fi was on. The new code does not treat this XML setting as proof of isolation.

## Current implementation

`tools/platforms/bluestacks/net_assurance.py` verifies the selected VM's loopback NAT configuration and performs three external guest-originating TCP probes. Each reads the **Android shell exit status**, not just `HD-Adb.exe`'s status. A successful connection, missing status marker or tool failure blocks game launch with `VL-NET-EGRESS`. The host-to-guest loopback endpoint is checked separately and produces `VL-NET-LOCAL-ROUTE` when it fails.

**Important limitation:** Blocked probes to three external IP:ports are not proof that all outbound traffic is blocked. This is a fail-closed field-test gate, **not a complete sandbox**. A genuinely safe Wi-Fi-on release requires a verified instance-scoped filtering mechanism and real-world security testing. No firewall rule is installed by these scripts, and no existing protection is bypassed.

## Proposed solutions to test, not yet shipped

1. **Instance-scoped virtual-network filtering**: discover whether this particular BlueStacks version exposes virtual network interfaces or WFP/AppContainer identifiers that allow blocking *only the dedicated VM's* outward traffic while preserving host loopback. Verify with non-probe traffic and restart/reboot tests.
2. **Per-program Windows Defender Firewall**: only if explicitly approved by the player *and* testing proves local loopback still works. Warning: a rule targeting common BlueStacks executables could affect every BlueStacks instance on the PC, so do not install one automatically.
3. **Guest firewall**: only on verified supported configurations with suitable privileges and a tested rollback. Do not assume BlueStacks provides reliable guest root access.
4. **Client endpoint audit**: independently enumerate every remote endpoint in the stock APK and all future downloaded code/assets. Redirecting known hostnames to localhost is not itself full network isolation.

## Tester matrix

| Test | Expected result |
|---|---|
| Windows Wi-Fi on; dedicated VM running; client route to `10.0.2.2:80` | Returns `local-village-service` |
| Windows Wi-Fi on; guest outbound TCP to tested external hosts | All fail with valid Android shell status |
| Guest external probe succeeds | Launcher refuses to start with `VL-NET-EGRESS` |
| ADB offline / `toybox nc` missing | Verification fails closed; not misclassified as isolation |
| Windows Wi-Fi off; same VM | Should still access local backend if configured; not a production substitute |
| Multiple BlueStacks instances installed | Setup/play touches only the selected Pie64 ID |
| Restart of BlueStacks; instance ADB port changed | `VL-BS-INSTANCE-CHANGED` and no automatic re-targeting |

**Ask testers to privately submit the Support ZIP**, the BlueStacks version, whether Wi-Fi was enabled, and the exact error code. Do not ask for full player state or unredacted Android logs publicly.
