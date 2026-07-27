r"""Forward tick capture — an append-only recorder, not part of the pipeline.

.. important::

   **This script records. It does not ingest, transform, resample, clean, or
   interpret anything, and it is not part of the evaluation path.**

   Everything it writes lands **outside the repository tree** and it refuses
   to start if pointed inside one. Nothing it produces is a snapshot and
   nothing it produces may be read by a feature, a backtest, or a metric
   until it has been ingested through the normal path, with the hashing,
   manifesting and validation that path applies. Until then these files are
   raw broker output sitting on a disk.

Why it exists
-------------

``EVALUATION.md`` §10 specifies a session-dependent spread with an event
multiplier and forbids a constant. The probe establishes that no historical
bid/ask series exists for this feed to calibrate that from: genuine ticks go
back ~0.4 years against the 10.87 years of dense H1 history that ``H-006``
declares admissible, and the ``spread`` field on bars is the spread at
bar-record time rather than anything that could have been paid. ``H-005``
registers the resulting deviation and names the exit condition — this capture,
matured across a full annual cycle.

That is the entire purpose. Every day not captured is a day of the exit
condition that will never be recoverable, which is why this starts now and
why it is built to survive reboots rather than to be restarted by hand.

What "append-only" means here
-----------------------------

Strictly. The day's data file is opened for append and is never seeked,
truncated, rewritten, or repaired — including when the previous run died
mid-write and left a partial line. A partial line is a defect, and
``DATA_CONTRACT.md`` §6 puts the handling of defects in the ingestion layer,
where they are marked invalid, rather than in a recorder that would silently
erase the evidence that anything went wrong.

Integrity is carried by an append-only hash chain rather than by a
rewritten checksum. Each flush appends one record covering the byte range it
wrote, the SHA-256 of that range, and the SHA-256 of the whole file through
its end. On resume the chain is checked against the file:

- file size == last recorded end            → clean resume
- file size >  last recorded end            → an unrecorded tail from a
  crash. It is **kept**, and a ``RECOVERED`` chain record is appended over
  it so that ingestion can see exactly which bytes were never confirmed.
- file size <  last recorded end            → the file was altered by
  something other than this script. The day is marked ``.TAMPERED`` and
  capture for it **refuses to continue**.

Requirements
------------

- Windows. The ``MetaTrader5`` package ships only ``win_amd64`` wheels.
- A running MT5 terminal, logged in, with the symbol in Market Watch.
- ``pip install MetaTrader5``.

Credentials are never read, never printed, never stored, and never needed by
this script. It attaches to a terminal that is already logged in; the
terminal's own auto-login is configured in the terminal, not here. The
account login number is masked wherever it is recorded.

Usage::

    python capture_ticks.py --symbol GOLD --out D:\\mt5_ticks

Running it so it survives reboots is documented at the bottom of this file
under "SURVIVING REBOOTS".
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import platform
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType
from typing import Any, Final

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_SYMBOL: Final = "GOLD"
DEFAULT_POLL_SECONDS: Final = 10.0
# How far back to ask on the very first poll of a fresh day file. MT5 serves
# ticks from its own cache, so a generous window costs little and closes the
# hole left by a restart that spanned a few minutes.
COLD_START_LOOKBACK_MINUTES: Final = 30
# Re-attach rather than exit when the terminal goes away. A recorder that
# quits because MT5 was restarted defeats the point of running it unattended.
RECONNECT_SECONDS: Final = 30.0
TAIL_READ_BYTES: Final = 65_536

CSV_HEADER: Final = "time,time_msc,bid,ask,last,volume,flags,volume_real\n"
CHAIN_HEADER: Final = (
    "seq,start,end,segment_sha256,cumulative_sha256,status,written_utc\n"
)

_stop_requested = False


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------


def host_utc_naive() -> datetime:
    """Return the host's true UTC as a naive datetime.

    MT5 range queries take naive datetimes and interpret them on the
    **server's** clock, so this is a starting point to be offset from, never
    a bound that is correct on its own.

    Returns:
        Naive datetime holding the host's UTC reading.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def log(message: str, log_path: Path | None = None) -> None:
    """Print a timestamped line and append it to the capture log.

    Args:
        message: Text to record.
        log_path: Log file, or ``None`` for stdout only.
    """
    line = f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}Z  {message}"
    print(line, flush=True)
    if log_path is not None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


# --------------------------------------------------------------------------
# Environment and safety
# --------------------------------------------------------------------------


def require_windows_mt5() -> Any:
    """Import MetaTrader5, failing with a useful message if impossible.

    Returns:
        The imported ``MetaTrader5`` module.

    Raises:
        SystemExit: If the platform or package is unavailable.
    """
    if platform.system() != "Windows":
        print("FATAL: this recorder must run on Windows.")
        print("  The MetaTrader5 package ships only win_amd64 wheels and")
        print(f"  declares Platform: Windows. Detected: {platform.system()}.")
        raise SystemExit(2)
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError:
        print("FATAL: MetaTrader5 is not installed.")
        print("  Run:  pip install MetaTrader5")
        raise SystemExit(2) from None
    return mt5


def assert_outside_any_repo(out_dir: Path) -> None:
    """Refuse to write anywhere inside a git working tree.

    The instruction that this data stays out of the repository is not a
    convention to be remembered at the call site — a recorder running
    unattended for a year will outlive whoever remembered it. It is checked
    here, every start, against the real filesystem.

    Args:
        out_dir: Resolved output directory.

    Raises:
        SystemExit: If ``out_dir`` is inside a git working tree.
    """
    for parent in [out_dir, *out_dir.parents]:
        if (parent / ".git").exists():
            print("FATAL: refusing to write inside a git repository.")
            print(f"  output dir : {out_dir}")
            print(f"  repo root  : {parent}")
            print("  Captured ticks are raw broker output. They enter the")
            print("  pipeline only by being ingested through the normal path,")
            print("  never by being committed. Choose a path outside any repo.")
            raise SystemExit(2)


def request_stop(signum: int, frame: FrameType | None) -> None:
    """Ask the capture loop to finish the current flush and exit.

    Args:
        signum: Signal number.
        frame: Current stack frame.
    """
    global _stop_requested
    _stop_requested = True
    print(f"\n[signal {signum}] finishing current flush, then exiting.", flush=True)


# --------------------------------------------------------------------------
# The append-only day file and its hash chain
# --------------------------------------------------------------------------


class TamperedError(RuntimeError):
    """Raised when a day's file is shorter than its hash chain records."""


class DayFile:
    """One calendar day of ticks: append-only data plus an append-only chain.

    The day is the **server's** calendar day, because the server clock is the
    only clock the tick timestamps carry. Converting to UTC would require the
    offset, which is exactly one of the things this data exists to pin down —
    so the conversion belongs in ingestion, after the offset is known, not
    here. Each session's provenance record stores the host's true UTC
    alongside the server's clock reading, which is what makes the conversion
    recoverable later.
    """

    def __init__(self, root: Path, symbol: str, day: str) -> None:
        """Open (or create) the day's files and verify the chain.

        Args:
            root: Per-symbol output directory.
            symbol: Symbol string.
            day: Server calendar day as ``YYYY-MM-DD``.

        Raises:
            TamperedError: If the data file is shorter than the chain records.
        """
        self.symbol = symbol
        self.day = day
        self.data_path = root / f"{symbol}-{day}.csv"
        self.chain_path = root / f"{symbol}-{day}.csv.sha256chain"
        self.meta_path = root / f"{symbol}-{day}.meta.jsonl"
        self._seq = 0
        self._confirmed_end = 0
        self._running = hashlib.sha256()
        self._prepare()

    # -- setup ------------------------------------------------------------

    def _prepare(self) -> None:
        """Create files if absent, otherwise verify and rebuild state.

        Raises:
            TamperedError: If the data file is shorter than the chain records.
        """
        if not self.chain_path.exists():
            with self.chain_path.open("w", encoding="utf-8") as handle:
                handle.write(CHAIN_HEADER)

        if not self.data_path.exists():
            self._append_bytes(CSV_HEADER.encode("utf-8"), status="OK")
            return

        records = self._read_chain()
        if records:
            self._seq = int(records[-1]["seq"])
            self._confirmed_end = int(records[-1]["end"])

        size = self.data_path.stat().st_size
        if size < self._confirmed_end:
            marker = self.data_path.with_suffix(".csv.TAMPERED")
            marker.write_text(
                f"data file is {size} bytes; hash chain records "
                f"{self._confirmed_end} bytes confirmed written.\n"
                f"detected {datetime.now(UTC).isoformat()}\n",
                encoding="utf-8",
            )
            raise TamperedError(
                f"{self.data_path.name}: {size} bytes on disk, "
                f"{self._confirmed_end} confirmed by the chain"
            )

        # Rebuild the running hash over the confirmed prefix, then fold in any
        # unconfirmed tail as a RECOVERED segment. The tail is never removed:
        # a partial line is evidence and belongs in front of the ingestion
        # layer, which marks defects invalid under DATA_CONTRACT §6.
        with self.data_path.open("rb") as handle:
            remaining = self._confirmed_end
            while remaining > 0:
                chunk = handle.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self._running.update(chunk)
                remaining -= len(chunk)
            tail = handle.read()

        if tail:
            self._record_segment(tail, self._confirmed_end, status="RECOVERED")

    def _read_chain(self) -> list[dict[str, str]]:
        """Parse the chain sidecar.

        Returns:
            One dict per record, in order.
        """
        lines = self.chain_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return []
        fields = lines[0].split(",")
        out: list[dict[str, str]] = []
        for line in lines[1:]:
            values = line.split(",")
            if len(values) == len(fields):
                out.append(dict(zip(fields, values, strict=True)))
        return out

    # -- writing ----------------------------------------------------------

    def _record_segment(self, payload: bytes, start: int, status: str) -> None:
        """Fold a byte range into the running hash and append a chain record.

        Args:
            payload: The bytes occupying ``[start, start + len(payload))``.
            start: Byte offset of the segment.
            status: ``OK`` for bytes this process wrote, ``RECOVERED`` for a
                tail found on disk that no chain record covered.
        """
        self._running.update(payload)
        self._seq += 1
        end = start + len(payload)
        record = ",".join(
            [
                str(self._seq),
                str(start),
                str(end),
                hashlib.sha256(payload).hexdigest(),
                self._running.hexdigest(),
                status,
                datetime.now(UTC).isoformat(),
            ]
        )
        with self.chain_path.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")
            handle.flush()
        self._confirmed_end = end

    def _append_bytes(self, payload: bytes, status: str) -> None:
        """Append to the data file, then confirm it in the chain.

        The order matters and is deliberate: data first, chain second. A crash
        between the two leaves an unconfirmed tail, which resume detects and
        marks ``RECOVERED``. The reverse order would leave the chain claiming
        bytes that do not exist, which resume would have to read as tampering.

        Args:
            payload: Bytes to append.
            status: Chain record status.
        """
        if not payload:
            return
        start = self.data_path.stat().st_size if self.data_path.exists() else 0
        with self.data_path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
        self._record_segment(payload, start, status=status)

    def append_ticks(self, rows: list[str]) -> None:
        """Append formatted tick rows as one confirmed segment.

        Args:
            rows: CSV lines without trailing newlines.
        """
        if rows:
            self._append_bytes(("\n".join(rows) + "\n").encode("utf-8"), status="OK")

    def append_session_record(self, payload: dict[str, object]) -> None:
        """Append one provenance record for a capture session.

        Args:
            payload: JSON-serialisable provenance fields.
        """
        with self.meta_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()

    # -- resume -----------------------------------------------------------

    def last_cursor(self) -> tuple[int, set[str]]:
        """Return the resume cursor read back from the data actually written.

        Deriving the cursor from the file rather than from a state file
        removes the failure mode where the two disagree: there is nothing to
        disagree with. The returned set holds the identity of every tick
        already recorded at that millisecond, since MT5 can deliver several
        within one and re-serves them on an overlapping request.

        Returns:
            ``(last_time_msc, identities_at_that_millisecond)``, or
            ``(0, set())`` if the file holds no ticks yet.
        """
        size = self.data_path.stat().st_size
        with self.data_path.open("rb") as handle:
            handle.seek(max(0, size - TAIL_READ_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")

        lines = [ln for ln in tail.splitlines() if ln and not ln.startswith("time,")]
        if not lines:
            return 0, set()

        # A trailing partial line from a crash is left on disk but must not be
        # trusted as a cursor.
        if not tail.endswith("\n"):
            lines = lines[:-1]
        if not lines:
            return 0, set()

        last_msc = 0
        for line in reversed(lines):
            with contextlib.suppress(ValueError, IndexError):
                last_msc = int(line.split(",")[1])
                break
        if last_msc == 0:
            return 0, set()

        seen = {ln for ln in lines if ln.split(",")[1:2] == [str(last_msc)]}
        return last_msc, seen


# --------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------


def format_tick(tick: Any) -> str:
    """Render one MT5 tick as a CSV line, without transforming anything.

    Every field the terminal supplies is written through verbatim. Selecting
    or deriving columns here would put a decision in the recorder that
    belongs in ingestion, and would make the raw record unreproducible.

    Args:
        tick: One row of an MT5 tick array.

    Returns:
        A CSV line with no trailing newline.
    """
    return (
        f"{int(tick['time'])},{int(tick['time_msc'])},"
        f"{float(tick['bid']):.5f},{float(tick['ask']):.5f},"
        f"{float(tick['last']):.5f},{int(tick['volume'])},"
        f"{int(tick['flags'])},{float(tick['volume_real']):.5f}"
    )


def connect(mt5: Any, symbol: str, log_path: Path) -> bool:
    """Attach to the terminal and select the symbol.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        log_path: Capture log.

    Returns:
        True if attached and the symbol resolved.
    """
    if not mt5.initialize():
        log(f"initialize failed: {mt5.last_error()}", log_path)
        return False
    if mt5.symbol_info(symbol) is None:
        log(f"symbol {symbol!r} not found on this account", log_path)
        mt5.shutdown()
        return False
    mt5.symbol_select(symbol, True)
    return True


def session_record(mt5: Any, symbol: str) -> dict[str, object]:
    """Build the provenance record written at each session start.

    The pairing of the host's true UTC with the server's clock reading is the
    load-bearing field: tick timestamps are server wall-clock, so without a
    contemporaneous UTC reference the series cannot be converted to UTC after
    the fact — and a broker that changes its clock rule mid-history would be
    undetectable.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.

    Returns:
        JSON-serialisable provenance fields.
    """
    account = mt5.account_info()
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    version = mt5.version()

    server_clock = (
        datetime.fromtimestamp(tick.time, tz=UTC).replace(tzinfo=None).isoformat()
        if tick is not None
        else None
    )
    return {
        "record": "capture_session_start",
        "host_utc": datetime.now(UTC).isoformat(),
        "server_clock_reading": server_clock,
        "symbol": symbol,
        "symbol_digits": getattr(info, "digits", None),
        "symbol_point": getattr(info, "point", None),
        "symbol_spread_float": getattr(info, "spread_float", None),
        "account_server": getattr(account, "server", None),
        "account_company": getattr(account, "company", None),
        "account_login": "masked",
        "terminal_build": version[1] if version else None,
        "script": Path(__file__).name,
        "note": "raw broker output; not ingested, not a snapshot",
    }


def poll_once(
    mt5: Any,
    symbol: str,
    day_files: dict[str, DayFile],
    root: Path,
    cursor: tuple[int, set[str]],
    log_path: Path,
    session: dict[str, object],
    session_written: set[str],
) -> tuple[int, set[str]]:
    """Fetch, de-duplicate and append one batch of ticks.

    Args:
        mt5: The MetaTrader5 module.
        symbol: Symbol string.
        day_files: Open day files, keyed by server date string.
        root: Per-symbol output directory.
        cursor: ``(last_time_msc, identities_at_that_millisecond)``.
        log_path: Capture log.
        session: This session's provenance record.
        session_written: Server days that already carry it. Mutated.

    Returns:
        The updated cursor.
    """
    last_msc, seen = cursor
    if last_msc:
        start = datetime.fromtimestamp(last_msc / 1000.0, tz=UTC).replace(tzinfo=None)
    else:
        start = host_utc_naive() - timedelta(minutes=COLD_START_LOOKBACK_MINUTES)

    # The upper bound is generous on purpose: the request is in server time,
    # server time may lead host UTC by hours, and a bound computed from host
    # time would silently drop everything recent.
    end = host_utc_naive() + timedelta(days=2)

    ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        return cursor

    by_day: dict[str, list[str]] = {}
    new_last, new_seen = last_msc, seen
    for tick in ticks:
        msc = int(tick["time_msc"])
        if msc < last_msc:
            continue
        line = format_tick(tick)
        if msc == last_msc and line in seen:
            continue
        day = (
            datetime.fromtimestamp(int(tick["time"]), tz=UTC)
            .replace(tzinfo=None)
            .strftime("%Y-%m-%d")
        )
        by_day.setdefault(day, []).append(line)
        if msc > new_last:
            new_last, new_seen = msc, {line}
        elif msc == new_last:
            new_seen = new_seen | {line}

    written = 0
    for day, rows in sorted(by_day.items()):
        if day not in day_files:
            day_files[day] = DayFile(root, symbol, day)
            log(f"opened {day_files[day].data_path.name}", log_path)
        # Provenance is written per day, on first write, rather than once per
        # session into whichever file happened to be open. A day file that
        # cannot say which session, terminal build and server clock produced
        # it is not convertible to UTC later, and the day the recorder opens a
        # brand-new file is exactly the day a once-per-session record would
        # have had nowhere to go.
        if day not in session_written:
            day_files[day].append_session_record({**session, "server_day": day})
            session_written.add(day)
        day_files[day].append_ticks(rows)
        written += len(rows)

    if written:
        log(f"+{written} ticks, cursor {new_last}", log_path)
    return new_last, new_seen


def capture(symbol: str, out_dir: Path, poll_seconds: float) -> int:
    """Run the capture loop until interrupted.

    Args:
        symbol: Symbol string.
        out_dir: Output root, already verified to be outside any repository.
        poll_seconds: Seconds between polls.

    Returns:
        Process exit code.
    """
    mt5 = require_windows_mt5()

    root = out_dir / symbol
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / "capture.log"

    log(f"capture starting — symbol {symbol}, out {root}", log_path)
    log("append-only; nothing here is ingested until it goes through the", log_path)
    log("normal path. This process never reads or stores credentials.", log_path)

    day_files: dict[str, DayFile] = {}
    cursor: tuple[int, set[str]] = (0, set())
    session: dict[str, object] = {}
    session_written: set[str] = set()
    connected = False
    resumed = False

    while not _stop_requested:
        if not connected:
            connected = connect(mt5, symbol, log_path)
            if not connected:
                log(
                    f"terminal unavailable; retry in {RECONNECT_SECONDS:.0f}s",
                    log_path,
                )
                _sleep_interruptible(RECONNECT_SECONDS)
                continue
            log("attached to terminal", log_path)

            session = session_record(mt5, symbol)
            session_written = set()

            # Candidate days are named on the *server's* calendar while this
            # clock reads host UTC, and the server may lead or lag it by
            # hours. Checking one day either side costs nothing and stops a
            # resume from silently cold-starting across a boundary.
            today = host_utc_naive()
            for offset in (1, 0, -1):
                day = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
                if (root / f"{symbol}-{day}.csv").exists():
                    try:
                        day_files[day] = DayFile(root, symbol, day)
                    except TamperedError as exc:
                        log(f"FATAL: {exc}", log_path)
                        log("refusing to append to an altered file.", log_path)
                        mt5.shutdown()
                        return 3
                    candidate = day_files[day].last_cursor()
                    if candidate[0] > cursor[0]:
                        cursor = candidate
                        resumed = True
            log(
                f"resumed at cursor {cursor[0]}"
                if resumed
                else "no prior data; cold start",
                log_path,
            )

        try:
            cursor = poll_once(
                mt5, symbol, day_files, root, cursor, log_path, session, session_written
            )
        except TamperedError as exc:
            log(f"FATAL: {exc}", log_path)
            log("refusing to append to an altered file.", log_path)
            mt5.shutdown()
            return 3
        # A recorder must not die because one poll went wrong. Anything
        # narrower would let an unanticipated terminal error end a year of
        # capture silently.
        except Exception as exc:
            log(f"poll failed ({type(exc).__name__}: {exc}); re-attaching", log_path)
            with contextlib.suppress(Exception):
                mt5.shutdown()
            connected = False
            _sleep_interruptible(RECONNECT_SECONDS)
            continue

        _sleep_interruptible(poll_seconds)

    log("stop requested; shutting down cleanly", log_path)
    with contextlib.suppress(Exception):
        mt5.shutdown()
    return 0


def _sleep_interruptible(seconds: float) -> None:
    """Sleep in short slices so a stop request is honoured promptly.

    Args:
        seconds: Total seconds to wait.
    """
    deadline = time.monotonic() + seconds
    while not _stop_requested and time.monotonic() < deadline:
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the capture.

    Args:
        argv: Command line, or ``None`` for ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Append-only MT5 tick recorder. Writes outside the repo.",
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument(
        "--out",
        required=True,
        help="output root. Must be outside any git repository.",
    )
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    args = parser.parse_args(argv)

    out_dir = Path(args.out).expanduser().resolve()
    assert_outside_any_repo(out_dir)

    signal.signal(signal.SIGINT, request_stop)
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, request_stop)

    return capture(args.symbol, out_dir, args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())


# ==========================================================================
# SURVIVING REBOOTS — Windows Task Scheduler
# ==========================================================================
#
# The recorder handles everything except the machine going down: it re-attaches
# on its own when the terminal is restarted, resumes from the data it has
# already written, and never needs its state reset by hand. Only a reboot needs
# something outside the process, and that is Task Scheduler's job.
#
# Two things must come back after a reboot, in this order:
#
#   1. The MT5 terminal, logged in. Configure this INSIDE the terminal —
#      Tools > Options > Server > "Save account and password", and leave the
#      terminal open. Nothing about credentials belongs in this script or in
#      the scheduled task.
#   2. This recorder.
#
# Register the task from an ADMINISTRATOR PowerShell prompt. Substitute your
# own paths; use full paths everywhere, because a scheduled task starts with
# no useful working directory:
#
#     $py   = "C:\Python312\python.exe"
#     $capt = "C:\tools\capture_ticks.py"
#     $out  = "D:\mt5_ticks"
#
#     $action  = New-ScheduledTaskAction -Execute $py `
#                  -Argument "`"$capt`" --symbol GOLD --out `"$out`""
#     $trigger = New-ScheduledTaskTrigger -AtStartup
#     $settings = New-ScheduledTaskSettingsSet `
#                  -RestartInterval (New-TimeSpan -Minutes 1) `
#                  -RestartCount 999 `
#                  -ExecutionTimeLimit ([TimeSpan]::Zero) `
#                  -MultipleInstances IgnoreNew `
#                  -DontStopIfGoingOnBatteries `
#                  -AllowStartIfOnBatteries `
#                  -StartWhenAvailable
#
#     Register-ScheduledTask -TaskName "MT5 tick capture" `
#         -Action $action -Trigger $trigger -Settings $settings `
#         -User $env:USERNAME -RunLevel Limited
#
# Why each setting is there, since a wrong one fails silently for months:
#
#   -AtStartup                     survives reboots without a login
#   -RestartCount 999              a crash restarts within a minute
#   -ExecutionTimeLimit Zero       no 3-day default kill; this runs for a year
#   -MultipleInstances IgnoreNew   a reboot race never gets two writers
#   -StartWhenAvailable            a missed start is picked up late, not skipped
#
# Two instances writing the same day file would interleave partial lines. The
# hash chain would catch it after the fact, but IgnoreNew prevents it.
#
# CHECK IT WORKS, TWICE:
#
#   Start-ScheduledTask -TaskName "MT5 tick capture"
#   Get-ScheduledTaskInfo -TaskName "MT5 tick capture"      # LastTaskResult 0
#   Get-Content D:\mt5_ticks\GOLD\capture.log -Tail 20 -Wait
#
# Then reboot and confirm the log picks up again on its own. A capture that
# was never tested across a real reboot is a capture you will discover was
# dead when you go looking for the year of data.
#
# VERIFYING INTEGRITY LATER — no special tooling:
#
#   The last chain record's `cumulative_sha256` is the SHA-256 of the whole
#   file through its `end` offset. On any machine:
#
#     head -c <end> GOLD-2026-07-27.csv | sha256sum
#
#   must equal that field. Any record whose status is RECOVERED marks bytes
#   that were on disk but never confirmed — a crash mid-write. They are kept
#   deliberately, and ingestion decides what to do with them.
#
# WHAT HAPPENS TO THIS DATA:
#
#   Nothing, until it is ingested through the normal path. These files are not
#   a snapshot, are not hashed into any manifest, and are not readable by a
#   feature, a backtest or a metric. They are the exit condition for H-005 and
#   nothing else until that ingestion exists.
