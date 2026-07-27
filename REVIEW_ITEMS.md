# Open Review Items

A **review item** is a claim this project has made about the world that has not been
checked against a source outside this project.

It is not a bug and not a hypothesis. It is a declaration standing on internal evidence
alone, with a named owner who has to go and look at something external, and a condition
that is blocked until they do.

```
Registered ....... 1
Open ............. 1   R-001
Closed ........... 0
```

Nothing is ever deleted from this file. A closed item keeps its entry with the date and
the source that closed it — the record of *what was checked* is what makes the conclusion
worth anything a year later. Same rule as `HYPOTHESES.md` §2.3.

---

## The distinction this file enforces

> **Re-deriving a declaration from the data it describes is not a review.**

`scripts/report_session_eras.py` re-measures the session eras from the H1 export and
exits non-zero if they stop agreeing with `calendar/gold_fxpro.yaml`. That is worth
having and it is not a review. It establishes **still agrees with the feed** — the same
feed the declaration came from — and says nothing about **agrees with reality**.

A calendar derived from a feed and then validated against that feed is circular. That is
already the stated argument for why the clock rule is frozen rather than re-derived
(`src/data/calendar.py`), and it applies unchanged here.

Only a source outside this project closes an item: a broker's own announcements, an
exchange's published schedule, a regulator's notice. **Another measurement of the same
data is not one.**

---

## Enforcement

The register lives twice, deliberately:

| | where | what it carries |
|---|---|---|
| prose | this file | the reasoning, the evidence, what would settle it |
| code | `src/data/review.py` | the identifiers, owners, and blocking conditions |

`tests/test_review_items.py` checks the two against each other, so an item cannot be
closed in one and left open in the other. A blocking condition written only in prose is
a blocking condition nobody enforces — the same reason the feature registry is checked
against the filesystem rather than trusted.

---

## R-001 — `session.eras` has not been reviewed against an external source

- **Raised:** 2026-07-27
- **Owner:** jaafer272007-design
- **Status:** OPEN

### The claim

`calendar/gold_fxpro.yaml` declares three session eras:

| era start | daily break | note |
|---|---|---|
| 2015-09-11 | yes | one-hour break at 17:00 New York |
| 2017-10-07 | **no** | continuous 24h session |
| 2022-10-21 | yes | one-hour break at 17:00 New York, as before |

### What the evidence currently is

`[MEASURED]` `scripts/report_session_eras.py` over
`data/raw/GOLD-H1-20080311-20260727.csv`, in-window days only, counting bars per server
day — no conversion and no convention:

```
Mon-Thu days carrying 24 bars (no break) :   936
Mon-Thu days carrying 23 bars (a break)  : 1,079
                    (excluding 152 days in US/EU DST mismatch windows)
```

The two populations do not interleave. Each boundary falls on a single weekend and is
pinned to the day: the last 23-bar day before the middle era is Fri 2017-10-06 and the
first 24-bar day is Mon 2017-10-09; the last 24-bar day is Thu 2022-10-20 and the first
23-bar day is Fri 2022-10-21.

That evidence is internally strong and **entirely internal**. It says the feed behaves
this way. It does not say the broker announced a session change, and it cannot rule out
that the middle era is an artefact of how this particular demo server built its bars.

### What would close it

FxPro's own published session-hours announcements or client notices covering **2017-10**
and **2022-10**.

Failing that, any independent record of GOLD/XAUUSD session hours over that span from a
source that is not this feed — a second broker's schedule, an exchange notice, a
contemporaneous archived page.

Closing it means recording here: the date, the source consulted, what it said, and
whether it agreed. **A source that is silent about 2017 does not close this** — it
establishes that the question is unanswered, which is where it already is.

### What it blocks

> **No session-relative feature may be registered while R-001 is open.**

A session-relative feature is one that reads the session open, the session close,
position within the session, or bars remaining until the daily break. Two reasons, and
the second is the one that makes this blocking rather than advisory:

1. Such a feature measures a different quantity on either side of 2017-10-07, because
   the session it is relative to is a different session.
2. The boundary dates themselves rest on unreviewed evidence, so a feature that encodes
   them inherits an unreviewed claim into the evaluation path — and once it is in a
   design matrix, nothing downstream can see that it got there.

Nothing currently registered is session-relative. The four shipped features — `ATR`,
`LogReturn`, `RealizedVol`, `RangePosition` — all declare `session_relative = False`, and
`tests/test_causality.py` refuses a registry entry that declares `True` while this item
is open.

### What it does *not* block

The H-006 era **term** (see `HYPOTHESES.md` H-006, amended 2026-07-27). The term records
that the eras exist and lets their effect be measured; it is not a session-relative
feature and does not depend on the boundary dates being externally confirmed. If the
review moves a boundary, the term is recomputed — which is exactly the property a term
has and a baked-in feature does not.

Ingestion, conversion, the gap census, and the post-conversion invariants are also
unblocked. None of them uses the era declaration: the gap census reads the break hour
from the calendar's `daily_break_hour`, which is independently evidenced by the DST
mismatch analysis, and the invariants are anchored to New York rather than to the eras.
