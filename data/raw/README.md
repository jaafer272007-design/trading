# `data/raw/` — the irreplaceable bytes

Exactly what MetaTrader handed over, written by `scripts/mt5_export.py` on the
Windows machine that hosts the terminal. Server timestamps untouched, MT5's own
columns in MT5's own order, no conversion of any kind.

**These files are committed.** Everything derived from them is not.

## Why

`DATA_CONTRACT.md` §8 makes a result void if its snapshot no longer exists. The
two stages differ in whether they *can* be made to exist again:

| stage | if lost | committed |
|---|---|---|
| **raw** | Unrecoverable. A broker can revise history, prune it, or close the account. These bytes exist because we have them and for no other reason. | **yes** |
| **derived** | A pure function of raw + `calendar/gold_fxpro.yaml` + `src/data/`, all committed. Rebuild and compare the manifest hash. | no |

So `data/snapshots/` is gitignored. Committing it would store the same
information twice.

## What is in here

Three files per export:

| file | what it is |
|---|---|
| `<SYMBOL>-<TF>-<first>-<last>.csv` | the bars, `time` = **server wall-clock as a Unix epoch, not UTC** |
| `<same>.csv.sha256` | hash written on the exporting machine, travelling with the file |
| `<same>.meta.json` | provenance: account server, terminal build, symbol digits. Login masked. |

## Adding one

1. Run the exporter on Windows.
2. Copy the three files here. Do not open the CSV in an editor on the way — a
   text-mode round trip rewrites line endings and breaks the hash.
3. Add a `RawExport` entry to `src/data/raw.py` with the hash, row count and
   span **transcribed from the export run's own output**, not copied from the
   sidecar. The sidecar travels with the file; a transport that mangles one
   mangles the other, and the pair stays consistent while being wrong. The
   registry is the independent record, and the hand step is the point.
4. `uv run pytest tests/data/test_raw_exports.py`.

`.gitattributes` marks these paths `-text` so git performs no end-of-line
conversion in either direction. Without it, a clone with `core.autocrlf=true`
rewrites the file on checkout and the guard fires on a machine difference — the
worst possible failure for a check whose job is detecting data corruption.

## Never

- Edit a file in place. §8 makes snapshots immutable; a correction is a new
  export under a new name.
- Update a hash in `src/data/raw.py` to silence a failing guard. Establish
  first whether the bytes changed in transit or the broker revised history.
  Those need opposite responses.
