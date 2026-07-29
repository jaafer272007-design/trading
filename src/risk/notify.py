"""Alerts, and where they go — a channel is configuration, not a rewrite.

The channel is undecided. Terminal output and a file are what exist today; a
phone, a chat webhook or a desktop notification are all plausible and none of
them should require touching anything that computes a number. So everything
that raises an alert talks to :class:`Notifier`, which is one method, and the
implementations below are the ones that need no credentials and no network.

Throttling is part of the interface for a reason
------------------------------------------------

A monitor that reads every sixty seconds will re-raise a standing condition
every sixty seconds. A time-in-trade alert on a position held for a week is
correct on all ten thousand of those readings, and a channel that receives all
ten thousand is a channel nobody reads. :class:`ThrottledNotifier` suppresses a
repeat of the same ``(code, key)`` inside a window.

It never suppresses an **escalation**. If the same condition comes back at a
higher severity it passes immediately, because the whole point of a severity is
that a change in it is news. An alert that got worse while being throttled is
exactly the alert that must not be swallowed.

No clock is read here
---------------------

Every alert carries the instant it was raised, supplied by the caller.
Nothing in this module calls ``datetime.now``. That keeps the throttle
testable to the second and keeps the whole core free of hidden state, which is
the same rule ``CLAUDE.md`` sets for the feature layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable


class Severity(StrEnum):
    """How much an alert wants attention.

    Ordered by :data:`SEVERITY_RANK` rather than by the enum, because
    ``StrEnum`` compares as text and ``"CRITICAL" < "INFO"`` alphabetically,
    which is the wrong way round and would silently invert every escalation
    check.
    """

    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


#: Severity order. See :class:`Severity` for why this is not the enum order.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARN: 1,
    Severity.CRITICAL: 2,
}


class AlertCode(StrEnum):
    """What kind of condition an alert reports."""

    #: A position has been open longer than the configured threshold.
    TIME_IN_TRADE = "TIME_IN_TRADE"
    #: Financing paid on one position has reached a share of equity.
    CARRY_HEAVY = "CARRY_HEAVY"
    #: Financing alone reaches the broker's stop-out within the alert horizon.
    MARGIN_STOPOUT_NEAR = "MARGIN_STOPOUT_NEAR"
    #: The account is already at or past an intervention level.
    MARGIN_BREACHED = "MARGIN_BREACHED"
    #: The day's drawdown has reached the configured limit.
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    #: Open positions have reached the configured maximum.
    MAX_POSITIONS = "MAX_POSITIONS"
    #: The broker's financing exceeds the registered substitute.
    SWAP_DIVERGENCE = "SWAP_DIVERGENCE"
    #: A position is open with no stop loss attached.
    NO_STOP_LOSS = "NO_STOP_LOSS"
    #: The terminal is not connected to the broker.
    TERMINAL_DISCONNECTED = "TERMINAL_DISCONNECTED"
    #: The monitor's heartbeat is older than the staleness threshold.
    HEARTBEAT_STALE = "HEARTBEAT_STALE"
    #: A quantity could not be computed and was refused.
    REFUSAL = "REFUSAL"


@dataclass(frozen=True, slots=True)
class Alert:
    """One condition worth telling someone about.

    Attributes:
        code: What kind of condition.
        severity: How much attention it wants.
        subject: What it is about — a ticket, a symbol, or the account.
        detail: One or more sentences a person can act on.
        raised_at: When it was raised, timezone-aware UTC. Supplied by the
            caller; nothing in this module reads a clock.
        key: Throttling key, distinguishing two instances of the same code.
            A ticket number, usually.
    """

    code: AlertCode
    severity: Severity
    subject: str
    detail: str
    raised_at: datetime
    key: str = ""

    def __post_init__(self) -> None:
        """Refuse a naive timestamp.

        Raises:
            ValueError: If ``raised_at`` carries no timezone.
        """
        if self.raised_at.tzinfo is None:
            raise ValueError("Alert.raised_at must be timezone-aware UTC")

    @property
    def throttle_key(self) -> tuple[str, str]:
        """The identity a throttle deduplicates on.

        Returns:
            ``(code, key)``.
        """
        return self.code.value, self.key

    def to_line(self) -> str:
        """Render as one human-readable line.

        Returns:
            ``TIMESTAMP  SEVERITY  CODE  subject: detail``.
        """
        stamp = self.raised_at.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{stamp}  {self.severity.value:<8}  {self.code.value:<22}  "
            f"{self.subject}: {self.detail}"
        )

    def to_json(self) -> str:
        """Render as one JSON object.

        Returns:
            A single-line JSON document with no trailing newline.
        """
        return json.dumps(
            {
                "raised_at": self.raised_at.isoformat(),
                "severity": self.severity.value,
                "code": self.code.value,
                "subject": self.subject,
                "key": self.key,
                "detail": self.detail,
            },
            sort_keys=True,
        )


@runtime_checkable
class Notifier(Protocol):
    """Somewhere an alert can go.

    One method on purpose. Adding a channel means writing this method and
    nothing else, which is what makes the channel a configuration choice.
    """

    def emit(self, alert: Alert) -> None:
        """Deliver one alert.

        Args:
            alert: The alert.
        """
        ...


@dataclass(slots=True)
class NullNotifier:
    """Discards everything. For tests, and for a probe run that should be silent."""

    emitted: list[Alert] = field(default_factory=list)

    def emit(self, alert: Alert) -> None:
        """Record the alert and deliver it nowhere.

        Args:
            alert: The alert.
        """
        self.emitted.append(alert)


@dataclass(slots=True)
class StreamNotifier:
    """Writes one line per alert to a text stream, usually the terminal.

    Attributes:
        stream: Where to write.
        flush: Whether to flush after each line. True by default: a monitor
            whose alerts sit in a buffer until the process exits has delivered
            nothing at the moment they mattered.
    """

    stream: TextIO
    flush: bool = True

    def emit(self, alert: Alert) -> None:
        """Write the alert as one line.

        Args:
            alert: The alert.
        """
        self.stream.write(alert.to_line() + "\n")
        if self.flush:
            self.stream.flush()


@dataclass(slots=True)
class FileNotifier:
    """Appends one JSON object per line to a file.

    JSON lines rather than prose, because this file is the one durable record
    of what the monitor saw and when, and a record that has to be re-parsed out
    of formatted text is a record that will be re-parsed wrongly.

    The file is opened and closed per alert. That is slower than holding a
    handle and it is the right trade: alerts arrive at most a few times a
    minute, and a handle held open across a crash loses whatever was buffered.

    Attributes:
        path: File to append to. Parent directories are created.
    """

    path: Path

    def emit(self, alert: Alert) -> None:
        """Append the alert as one JSON line.

        Args:
            alert: The alert.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(alert.to_json() + "\n")


@dataclass(slots=True)
class MultiNotifier:
    """Fans one alert out to several channels.

    A channel that raises does not stop the others. A file that cannot be
    written must not silence the terminal, and the exception is re-raised only
    after every other channel has had the alert.

    Attributes:
        notifiers: The channels, in order.
    """

    notifiers: tuple[Notifier, ...]

    def emit(self, alert: Alert) -> None:
        """Deliver to every channel.

        Args:
            alert: The alert.

        Raises:
            Exception: The first exception raised by any channel, after every
                channel has been tried.
        """
        first: Exception | None = None
        for notifier in self.notifiers:
            try:
                notifier.emit(alert)
            except Exception as exc:
                first = first or exc
        if first is not None:
            raise first


@dataclass(slots=True)
class ThrottledNotifier:
    """Suppresses repeats of a standing condition inside a window.

    Attributes:
        inner: Where surviving alerts go.
        window: How long to suppress a repeat of the same ``(code, key)``.
        last_sent: Internal state — when each identity was last delivered, and
            at what severity.
    """

    inner: Notifier
    window: timedelta
    last_sent: dict[tuple[str, str], tuple[datetime, Severity]] = field(
        default_factory=dict
    )

    def emit(self, alert: Alert) -> None:
        """Deliver unless an equivalent alert is still inside the window.

        An alert whose severity is higher than the suppressed one always
        passes, and resets the window.

        Args:
            alert: The alert.
        """
        previous = self.last_sent.get(alert.throttle_key)
        if previous is not None:
            sent_at, severity = previous
            inside_window = alert.raised_at - sent_at < self.window
            escalated = SEVERITY_RANK[alert.severity] > SEVERITY_RANK[severity]
            if inside_window and not escalated:
                return
        self.last_sent[alert.throttle_key] = (alert.raised_at, alert.severity)
        self.inner.emit(alert)
