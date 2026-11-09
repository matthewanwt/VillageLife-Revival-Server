"""Deadline-based BlueStacks ADB orchestration with bounded per-attempt timeouts.

Only the configured serial is addressed. Never kill the global ADB daemon or touch
other BlueStacks instances.
"""
from __future__ import annotations
from dataclasses import dataclass
import subprocess
import time
from pathlib import Path
from runtime_errors import VillageRuntimeError

FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class ADBResult:
    code: int
    output: str


class ADBClient:
    def __init__(self, executable: Path, serial: str):
        self.executable = Path(executable)
        self.serial = serial
        self.last_error = ""

    def _call(self, *args, timeout=12, serial=True):
        command = [str(self.executable)]
        if serial:
            command += ["-s", self.serial]
        command += [str(v) for v in args]
        try:
            p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=max(.1, timeout), creationflags=FLAGS)
            # ADB and Android shell can use different native encodings. Never crash
            # because of corrupt output bytes; preserve replacement markers.
            return ADBResult(p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace"))
        except subprocess.TimeoutExpired as ex:
            self.last_error = f"ADB command timed out after {timeout:.1f}s ({args[0] if args else 'command'})."
            return ADBResult(124, self.last_error)
        except OSError as ex:
            self.last_error = f"ADB executable could not run: {type(ex).__name__}."
            return ADBResult(127, self.last_error)

    def command(self, *args, timeout=15):
        return self._call(*args, timeout=timeout)

    def connect(self, timeout=8):
        return self._call("connect", self.serial, timeout=timeout, serial=False)

    def wait_for_boot(self, *, deadline_seconds=300, progress=None, clock=time.monotonic, sleep=time.sleep):
        """Retry transport and guest boot until an overall monotonic deadline.

        A hung connect consumes at most one bounded attempt. This deliberately
        doesn't terminate an otherwise booting emulator after one timeout.
        """
        until = clock() + deadline_seconds
        attempt = 0
        last = "not started"
        while clock() < until:
            attempt += 1
            remaining = until - clock()
            # Short initial attempts avoid 10 second stalls; longer retries help
            # slower machines after BlueStacks has started loading Android.
            per_call = min(max(3.0, 2.0 + attempt * 1.2), 12.0, max(.1, remaining / 2))
            connect = self.connect(timeout=per_call)
            if connect.code not in (0,):
                last = connect.output.strip()[-250:]
            boot = self.command("shell", "getprop", "sys.boot_completed", timeout=per_call)
            if boot.code == 0 and boot.output.strip() == "1":
                if progress:
                    progress(f"Android ready after {attempt} connection checks.")
                return attempt
            last = (boot.output or connect.output).strip()[-250:] or "waiting for Android to boot"
            if progress and (attempt == 1 or attempt % 4 == 0):
                progress(f"Waiting for Android on {self.serial}: attempt {attempt}. Last response: {last}")
            wait = min(0.6 + min(attempt * .45, 4.0), max(0, until - clock()))
            if wait > 0:
                sleep(wait)
        raise VillageRuntimeError(
            "VL-ADB-BOOT-TIMEOUT",
            f"BlueStacks instance did not finish booting within {deadline_seconds} seconds.",
            "Verify that this instance is running and ADB is enabled, then retry. Export diagnostics if this persists.",
            details=f"serial={self.serial}; attempts={attempt}; last={last}",
        )
