# BlueStacks Wi-Fi investigation: network topology diagnostic

## Why this exists

The existing Village Life client uses the original game protocol with a locally patched
endpoint at `10.0.2.2:80`. A Play/Setup instance may be reachable over ADB without
having a functional local HTTP route; conversely, the game may reach localhost while
BlueStacks still has other outbound routes to the internet.

**This tool is an investigation step, not a Wi-Fi fix or an isolation mechanism.**
It does not install firewall rules or edit BlueStacks, user saves, or APKs.

## Known instance information from the project owner's Windows setup

| BlueStacks VM ID | Configured ADB | Live-status ADB | Intended use |
|---|---:|---:|---|
| `Pie64` | 5555 | 5555 | **Unknown**; do not assume it is the Village Life VM |
| `Pie64_4` | 5595 | 5595 | **Unknown**; do not assume it is the Village Life VM |

The user should check which instance contains their dedicated test game using the
Multi-instance Manager. The tool will never silently choose `Pie64_4` because its
port is higher. The launcher continues to bind to the chosen VM ID, path and port.

## Step 1: non-invasive inventory (Wi-Fi stays enabled)

Run from the new repository root on Windows:

```powershell
py -3 windows\tools\diagnose_network.py
```

Or for a known dedicated VM (only after confirming the ID):

```powershell
py -3 windows\tools\diagnose_network.py --instance Pie64_4
```

The first run requires neither a running backend nor a running Android instance.
If the selected VM is running, more process information will appear. This does not
connect a device or start BlueStacks. The diagnostic writes
`windows/network-topology-report.json` (excluded from Git).

The **Network Check** button in the rebuilt Windows launcher runs the default
read-only inventory. **Export Diagnostics** adds its sanitised results to the
private support ZIP. Inspect that ZIP before sending it to maintainers.

If the repository is being tested without a working embedded Python runtime,
install Python 3.11+ locally and use `py -3` as above. This does not require the
new Alpha backend or original proprietary assets.

## Step 2: optional active guest checks

Only after opening and identifying the dedicated VM and enabling its ADB setting:

```powershell
py -3 windows\tools\diagnose_network.py --instance Pie64_4 --probe-guest
```

**Replace `Pie64_4` with the VM ID confirmed in your BlueStacks manager.**
This option attempts bounded network connections from Android to test egress.
It does not modify firewall settings, but it can generate network traffic and is
therefore intentionally opt-in. The script uses the existing ADB connection;
it does not start the VM or restart the ADB daemon.

Three unsuccessful external TCP attempts are merely observations. Even if they
fail, **we have not proved that outbound access is blocked**, particularly
for DNS, UDP, IPv6, or other hosts. No installer should market this as isolated.

## How to interpret the report

- `instances[*].configured_adb_port` versus `live_status_adb_port`: should match.
  A disagreement is `VL-BS-PORT-DIVERGED` in the strict launcher; do not retarget.
- `instances[*].player_process_observed`: whether the host inventory found
  `HD-Player.exe --instance <id>` for that VM, without retaining full command lines.
- `host.processes`: only process image name, PID, and safe VM ID; it is *not*
  an exhaustive map of all BlueStacks networking components.
- `host.observed_tcp_remote_classes`: counts of observed public, loopback,
  private, and other IP classes; **no actual addresses are saved**.
- `host.adapter_categories`: generic Wi-Fi / wired / virtual categories; this
  doesn't prove Windows is online or reveal the full guest route.
- `host.hyperv_firewall_cmdlet_present`: tells us whether the command exists,
  not whether a BlueStacks-specific Hyper-V firewall rule is supported/enforced.
- `guest.probe_checks_all_blocked`: only the tested destinations did not
  connect. `guest.isolation_policy_verified` is **always false** in this stage.

## Before choosing a real isolation policy

1. Identify the dedicated instance and its running `HD-Player.exe` process.
2. Test that `10.0.2.2:80` reaches the actual replacement backend with Wi-Fi on.
3. Determine which host service, VM driver, virtual adapter or hypervisor
   component actually transports the *guest's* outward packets.
4. Prototype a narrowly scoped, reversible allow-local / deny-external policy
   on a **disposable** test instance, never across all BlueStacks instances.
5. Validate real egress restrictions for TCP, UDP, DNS and IPv6; reboot and
   confirm the policy persists, while normal Windows Internet still works.
6. Only after the policy and rollback are verified should we integrate its
   installation into the signed Windows installer.

A Windows Firewall rule for `HD-Player.exe` alone is not sufficient evidence of
isolation. A blocked `1.1.1.1:443` connection is not sufficient evidence either.

## What not to send publicly

Do not share `bluestacks.conf`, full PowerShell process command lines,
firewall rules with local paths, raw network captures, APKs, or player saves.
Share only the **reviewed** diagnostics bundle privately with maintainers.
