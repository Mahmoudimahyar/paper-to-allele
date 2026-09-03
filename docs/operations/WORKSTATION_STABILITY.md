# Workstation stability: the unclean shutdowns, and what the logs say

Two sessions of agent work were cut short by the machine powering off on
2026-09-03. The working hypothesis at the time was that the workload caused it.
**The Windows event log does not support that**, and this file records the
evidence so the question does not have to be re-opened from memory.

## What was measured (2026-09-03, from the System event log)

`Kernel-Power` event **41** — "the system has rebooted without cleanly shutting
down first" — appears **35 times**, the oldest retained on **2026-06-11**:

| period | unclean shutdowns | what was running |
|---|---:|---|
| 2026-06-11 … 2026-06-29 | 25 | none of this project's work existed |
| 2026-08-26 | 2 | before the OCR passes began |
| 2026-08-31 … 2026-09-03 | 6 | archive ingestion, OCR, GPU decode, model survey |

June alone, with none of this work in existence, produced five unclean
shutdowns on the 25th and five more on the 28th. The recent rate is **lower**
than the June rate, not higher.

## What kind of failure it is

| probe | result |
|---|---|
| `BugCheck` (event 1001) | **none** |
| `C:\Windows\Minidump` | **empty** |
| `C:\Windows\MEMORY.DMP` | absent |
| `WHEA-Logger` (machine-check hardware errors) | **no events** |
| display driver reset / TDR (event 4101) | **none** |

A driver fault, a kernel panic or a GPU hang leaves a bug-check and a dump. A
correctable hardware error leaves a WHEA record. **None of them is present**,
which means the kernel was never given the chance to write anything: the
machine either lost power or locked hard at a level below the operating system.

That signature points at power delivery (PSU under transient load, a cable, or
mains), thermal cut-out at the board level, or a memory/motherboard fault. It is
not a signature software can produce on its own, though a heavy workload will
surface a marginal supply or a cooling problem far more often than an idle
desktop will.

## What to check, in order of cost

1. **Temperatures under load** (HWiNFO64 or similar) — CPU package and GPU. A
   Ryzen 9 9900X and a GTX 1070 in one case will both climb during these runs.
2. **The power supply.** A GTX 1070 draws large transient spikes; an ageing or
   marginal PSU browns out under them and takes the board with it, silently.
   The June cluster with no such workload argues for a fault that is already
   there rather than one this work created.
3. **Memory** (`mdsched.exe`, or MemTest86 for a real pass).
4. **Mains power** — if other appliances on the circuit correlate, it is the
   wall, not the box.
5. Enable a kernel memory dump (`sysdm.cpl` → Advanced → Startup and Recovery)
   so that *if* a future stop is a software bug, it leaves something to read.
   Today it would leave nothing.

## How the agent workload was reduced anyway

Independently of cause, the heavy path was retired on 2026-09-03:

* The 11-agent OCR model survey — which installed eleven engine environments,
  downloaded ~22 GB of model weights, and was queued to run seven vision
  models on the GPU one after another — was **stopped and not resumed**. The
  survey was written up from the results already on disk, which cover every
  CPU-side engine.
* Remaining OCR work uses the CPU recognizers already in the lockfile.
* Long corpus passes (`ocr_pass.py`, `decode_pass.py`, `confirm_pass.py`) are
  resumable and idempotent by design: re-running the same command after a
  power loss skips what completed. Nothing in this project loses work to an
  abrupt shutdown except an unsaved review-page session, and that page now
  warns when its storage is unavailable.

## Cross-references

`docs/ingestion/OCR_MODEL_SURVEY_2026-09-03.md` records which engines were
measured and which were left untested because of this decision.
