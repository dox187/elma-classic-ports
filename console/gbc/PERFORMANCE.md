# GBC 0.91 performance experiments

Goal: keep complete active gameplay updates within **280,896 CPU T-cycles**
at CGB double speed, one update per two display frames (about 29.86 Hz).
Preserve the 0.90 native physics results, visible source graphics, saves and
direct controls. Do not add a frame queue, lower physics frequency or relax
the deadline to turn a failed result into a pass.

For each candidate, record the hypothesis, actual implementation, reproduction
command, ROM/source hash, before/after costs, correctness checks and decision.
Revisit a rejected candidate only when new evidence changes its assumptions.
Host high-precision physics research is documented separately in the README;
it is not the physics running in these ROMs.

## Frozen 0.90 baseline — 2026-11-17

Release commit: `7efd2a1`. ROMs remain directly in `build`:

| ROM | SHA-256 |
|---|---|
| `elma-gbc-v0.90-4m.gbc` | `cc49dfec355bb91c22ed9cf70311233552e29db8db9fa91cf66c3150d88ddfad` |
| `elma-gbc-v0.90-8m.gbc` | `34bdf3d6928ace5f9927ddad86091be61fc02d667397e74799b4fb3891d0b28c` |

| Strict deadline misses | 4 MiB ZX0 | 8 MiB raw |
|---|---:|---:|
| All 54 starts, 12 idle updates per course | 13 | 6 |
| Complete no-input Freefall, 433 observed steps | 54 | 13 |
| 300-step Warm Up driving profile | 4 | 0 |

All three runs retain their normal controller input. The start/Freefall
functional checks pass in both sizes, but their strict timing assertions fail.
Frontend, players, clock/results, cross-size save reload, held volts, finish
audio and the 4,800-block native compressed-graphics check pass.
Evidence: `build/v090-release-checks/{4m,8m}/`.

Reproduce from `console/gbc`, using the matching `--gen build/gen-8m` for 8 MiB:

```sh
.venv/bin/python test/all_levels.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/gen --out build/baseline-starts-4m --idle-updates 12
.venv/bin/python test/freefall.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/gen --out build/baseline-freefall-4m
.venv/bin/python test/profile_play.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/gen --out build/baseline-driving-4m --steps 300
```

The retained pre-release rider probe has identical native gameplay code but
older scenery colors. Its detailed Freefall profile contains 432 complete
active updates, 13 over budget. The worst is **356,336 cycles**: physics
144,256; presentation 201,764; other loop work 10,316. Optimizing physics
alone misses the main cost on that frame. Evidence:
`build/v090-freefall-cost/{report,updates}.json`.

## Prior candidate reviewed: preparation bookkeeping assembly

The existing `build/prepare-acquire-prototype` passes 15,152 native metadata
cases. Ordinary acquisition bookkeeping averages 687 cycles versus 795 for
its C reference; its cached path averages 475 versus 487. This can help but
cannot by itself close a 75,440-cycle worst-update gap. Do not treat the
isolated metadata test as a complete-game timing result. The next experiment
must locate the synchronous scrolling cost before integrating this helper.

## Next measurement

Separate `world_scroll` strip fetching, tile acquisition/uploads, publication
and preparation overhead in the retained 8 MiB ROM. Extend controller-only
coverage to moving views on all courses and compare exact native state bytes
at identical physics steps before accepting rendering changes.
