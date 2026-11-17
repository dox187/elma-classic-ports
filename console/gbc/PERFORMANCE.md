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

**Scope change, 2026-11-17:** the 4 MiB variant is no longer a development
target. Continue optimization and validation on 8 MiB only. Compressed-format
experiments below remain historical evidence; do not continue their work.

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

The retained 0.90 compressed manifests/source tiles are frozen in
`build/v090-gen-4m`; current `build/gen` uses the 0.91 layout. Reproduce from
`console/gbc`, using the matching `--gen build/gen-8m` for the unchanged raw
8 MiB layout:

```sh
.venv/bin/python test/all_levels.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/v090-gen-4m --out build/baseline-starts-4m --idle-updates 12
.venv/bin/python test/freefall.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/v090-gen-4m --out build/baseline-freefall-4m
.venv/bin/python test/profile_play.py --rom build/elma-gbc-v0.90-4m.gbc --gen build/v090-gen-4m --out build/baseline-driving-4m --steps 300
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

## 01: batch synchronous tile acquisitions — retained

The detailed 8 MiB audit reproduces all 432 Freefall update costs exactly.
At step 351, `world_scroll` costs 171,892 cycles, including 35,640 dispatcher
cycles and 23,652 acquisition-bookkeeping cycles; just six DMA uploads total
5,408 cycles. Consecutive synchronous acquisitions repeat 736 dispatcher
cycles. Evidence: `build/v091-render-audit/{handoff,report}.json`.

Finish the remaining acquisitions in a synchronous subloop. Budgeted idle
preparation retains its per-unit checks, allocation order and cancellation.
`elma-gbc-v0.91-batch-8m.gbc` SHA-256:
`bacd344bcc6ae0a0e5b5272f87cc38679d87e2fb1cbbff0512745d5382047b97`.
Freefall misses fall **13 to 5**, peak **356,336 to 343,456 cycles**; the
54-start misses fall **6 to 4**. The 300-step Warm Up profile remains at zero.
Both raw/compressed native cache fixtures pass 3,031 views with no byte,
reference, save-guard or preparation-deadline failures.
Evidence: `build/v091-batch-{freefall-profile,starts-8m,drive-8m,cache-raw,cache-4m}`.

## 02: raw-fetch preparation allowance — retained, insufficient alone

Reserve 20 scanlines (18,240 cycles) instead of 35 for one raw chunk fragment.
The detailed route's largest fragment cost is 10,556 cycles. This change
allows useful fetch work nearer the deadline; compressed cold-work bounds
remain separate. Freefall still has five misses and the same 343,456 peak,
but step 66 falls from 299,532 to 287,712 cycles. Do not repeat this change
expecting it alone to finish the timing work. ROM:
`elma-gbc-v0.91-rawfetch-8m.gbc`; evidence:
`build/v091-rawfetch-freefall-profile/report.json`.

## 03: absent-ID insertion and DMA boundary wait — retained

Acquisition already knows the new pattern ID is absent. Insert at the lookup
bucket head without searching that absent ID again; preserve mapping contents
and allocation/reference semantics. The native acquisition fixture passes
2,809 cases against its C reference. Memory tests cover all 65,536 IDs,
64 colliding IDs, eviction/reinsertion, protected RAM and bank restoration.
Evidence: `build/v091-insert-{acquire,memory}/report.json`.

The DMA polling loop now accepts VBlank when leaving HBlank instead of waiting
through the entire blanking interval. Only one linked byte changes (`2` to
`3`), with the same 143-byte helper. A 4,112-call phase sweep per version has
zero byte/guard/bank/register/IRQ failures. Worst polling falls 9,444 to 672
cycles; the late-line-143 helper maximum including IRQs falls 11,532 to 2,220.
The independent poll/launch/transfer bound is **140 < 160 cycles**. Evidence:
`build/v091-dma-window/report.json` and `test/check_world_dma_window.py`.

Combined ROM `elma-gbc-v0.91-insert-dma-8m.gbc` SHA-256:
`f2bdd2d0b0ed49c6ef3cba0606a7b08661935e24e280017ee911cce22df61e07`.
Freefall still has five misses, peak **335,096 cycles**. The broad controller
benchmark below proves unchanged native gameplay; further work is needed.

## 04: smaller compressed work units — regression found; not accepted alone

An exact nine-layout size audit rejects 256-byte pattern blocks: even with
the old maps they exceed the bank limit by 71,102 span bytes. A 512-byte
pattern plus 32x8 map layout also fails by 19,528 bytes. Do not judge fit
using payload alone; bank-boundary padding and directories count too.

The selected layout uses **512-byte patterns and independent 512-byte map
planes**, keeping the original 32x16 map cells. It occupies banks **94–249**,
2,534,598 payload bytes, with 34,716 contiguous bytes left before bank 252.
Native maximum decode costs are **89,968 pattern / 91,996 map-plane cycles**,
versus 179,208 / 215,976 for the old indivisible units. Decoding all three map
planes still costs about 1.22% more in total; the gain requires yielding
between planes, not merely repacking bytes.

Runtime changes keep 32 half-KiB pattern slots in the same SRAM banks 2–3
and five maps in bank 1, with three validity bits per map. A partial fetch
advances its strip index only after all three planes have arrived; cancellation
discards that fragment's staging progress. No partial tile/attribute data is
published. All 11,514 packed streams pass native byte, directory, guard and
bank checks. Both new raw/compressed cache fixtures pass 3,031 views with zero
failures. Evidence: `build/v091-block-audit`, `build/v091-plane-format`,
`build/v091-planes-cache-{raw,4m}`.

The first complete-game integration regresses: 4 MiB starts have 17 misses
and Freefall 67, versus 13 and 54 in 0.90. Completing synchronous fetches in
one call reduces Freefall misses to 60, but that candidate also includes the
new segment iterator and coordinate cache key. It is not an isolated timing
measurement of fetch batching. A smaller maximum decoder cost is insufficient
evidence to retain a layout.

A read-only Freefall audit finds **zero cold decodes during budgeted idle
preparation** in both layouts: the 130-line reservation still prevents them.
Synchronous decoder work falls from 11,323,632 to 9,605,672 cycles, but repeated
cached-plane dispatch raises `fetch_strip` exclusive work from 2,599,028 to
5,525,092, and fetch-budget checks from 871,972 to 2,553,208. The next bounded
candidate gathers all three already-valid planes in one fragment operation,
under the existing 20-line warm guard. Cold work keeps its separate guard.

That warm-fragment candidate passes all 3,031 native cache views and all 216
controller cases / 27,447 exact physics steps. Freefall falls to **47 misses**.
The complete 4 MiB corpus improves **1,506 to 1,203 over-budget updates** from
0.90; passing cases improve 50 to 63, and the worst update falls 1,489,760 to
1,011,344 cycles. Retain the smaller units with the warm fast path, but the
cold reservation remains an unresolved scheduling limit. ROM
`elma-gbc-v0.91-warmplanes-4m.gbc`, SHA-256
`63c037a0ae53cdb7d6c4d3cad07668830b0acfba0644ad730cef77b0784d8154`;
evidence `build/v091-warmplanes-{cache,freefall,gameplay-4m}` and
`build/v091-baseline-gameplay-4m/report.json`.

## 05: exact native physics and rider frame selection — retained

`ph_step` moves only its arrays and damping workspace to fixed native storage.
Static RAM grows by 60 bytes, its stack frame shrinks 104 to 44 bytes and
bank-8 code shrinks by 96. All 1,727 native/HOST states match frozen 0.90.
Mean active-update savings are 988–1,002 cycles. A second layout also moved
long-lived scalars; it added 24 further bytes and cost 153–206 more cycles, so
it was rejected. Evidence: `build/v091-step-workspace/findings.json`.

Collision cache identity is `(cy << 8) | cx`; directory multiplication happens
only on a miss. The bank-9 segment-box iterator preserves record order and
every cursor/remaining-count result. Its fixture passes 13,784 cases and
42,439 native comparisons, including page crossings and 255 records. Paired
isolated iteration costs fall 46.23%; this is not the whole physics speedup.
Evidence, from repository root: `build/v091-segment-scan/report.json`.

The rider compression helper preserves both separately rounded products and
their thresholds, including overflow and subtraction borrows. All 15,000
native/frozen-C/model cases pass; bounded frame-preparation overhead falls
7,500 to 5,709 cycles with identical upload recorders. Code shrinks 260 bytes,
RAM is unchanged. Actual DMA and head publication remain covered by the
complete Freefall/54-start runs. Evidence, from repository root:
`build/v091-bike-prepare/report.json`.

Combined candidate ROM hashes:

| ROM | SHA-256 |
|---|---|
| `elma-gbc-v0.91-combined1-4m.gbc` | `50cc452d549c39bf01d93871e58db42320c5a970fdfee4b2578b1f5657bbce8a` |
| `elma-gbc-v0.91-combined1-8m.gbc` | `7b7988ac4ffeb7b24ec9bf3489508b22143593893941bd3f1cbebc55cc0e6a98` |

Both sizes pass all 216 reference cases / 27,447 exact native steps, with
matching inputs, physics, clocks and object results. The combined native/HOST
fixture also passes all 1,727 snapshots. Frontend, saves across ROM sizes,
volts, finish audio, source VRAM, head publication and packed graphics pass.
Timing remains a failed gate:

| Measurement | 0.90 8 MiB | Combined 8 MiB | Combined 4 MiB |
|---|---:|---:|---:|
| Corpus over-budget updates | 1,025 | 624 | 1,307 |
| Entirely passing cases / 216 | 72 | 105 | 52 |
| 54-start misses | 6 | 2 | 15 |
| Freefall misses | 13 | 5 | 56 |
| Warm Up 300-step profile misses | 0 | 0 | 4 |

Evidence: `build/v091-combined1-{gameplay-4m,gameplay-8m,trace,checks}`.
Further exact suspension/contact work and compressed scheduling are required;
these development artifacts are not a stable-30-FPS release.

## 06: two-wheel suspension orchestration — retained

Use a bank-8 helper for both wheels' anchor, spring and damping work. Keep
the existing arithmetic helpers, pre-volt angular velocity, full 32-bit linear
velocities and reaction-torque calculation. Native structure offsets are
compile-time checked; generic SDCC and HOST fixtures retain the C path.
The helper adds 18 net static bytes and 22 bank-8 bytes; the step frame shrinks
44 to 41 bytes. It saves 7,490–7,796 cycles per active reference update.

All 761 full-width/boundary vectors and 1,727 native/HOST snapshots pass.
The production integration also passes all 216 controller cases / 27,447
states in both sizes, and the generic 54-level fixture passes 53,416 HOST
queries and 27,164 native queries. Corpus misses improve to **460 / 1,053**
for 8 / 4 MiB; wholly passing cases become **126 / 72**. Still not stable.
Evidence: `build/v091-suspension`, `build/v091-suspension-trace`,
`build/v091-suspension-levels`, `build/v091-suspension-gameplay-{4m,8m}`.

| Candidate | SHA-256 |
|---|---|
| `elma-gbc-v0.91-suspension-4m.gbc` | `bb0bee62353578ea1a8993c44441540750900396e5e999809bedc76559d6ce00` |
| `elma-gbc-v0.91-suspension-8m.gbc` | `8a54b2d06c5f260d3c2d4d16f8401a1097e789e46441cc0cf5cbf6a1592ec6ab` |

## 07: contact projection glue — rejected for marginal integrated gain

The ABI0 helper regressed the actual contact loop despite a promising isolated
projection call. An ABI1 variant passes 11,442 vectors and 360 captured contact
groups, but saves only 146 cycles per Gravity Ride update, with 8 extra bytes
of shared workspace. Do not integrate the helper or repeat the isolated-call
claim as a whole-game gain. Larger rendering and physics costs remain.
Evidence: `build/v091-contact-projection`.

## 08: exact per-block ZX0 scheduling costs — retained

Replace the fixed 130-line cold-work reservation with each stream's measured
decoder cost, rounded up to 912-T-cycle scanlines, plus a separate 30-line
wrapper/cache/IRQ margin. A 12-line guard protects the metadata read itself.
One prefix byte precedes each stream; all nine ROM-bank bits remain available.
The source-hashed decoder model is checked by the packer and build. Updated
payload is 2,546,131 bytes in banks 94–250, within the 4 MiB profile.

All 11,514 production streams and 26 synthetic streams exactly match native
entry-through-return cycles, with zero undercounts. Additional checks cover
1,910 copy-loop lengths, changed decoder source and truncated streams. Packed
graphics remain byte-exact; the 3,031-view cache fixture passes with zero guard,
reference, bank or preparation-deadline errors. Old untimed 0.91 data are
retained in `build/v091-planes-gen-4m`; current `build/gen` includes the prefix.

The full 216-case / 27,447-state corpus remains identical to 0.90. The 4 MiB
over-budget count falls **1,053 to 959**, with 73 entirely passing cases.
Freefall improves from 47 misses before the suspension/cost changes to 40.
Its detailed profile now performs 23 cold decodes during idle preparation,
moving 1,245,592 decoder cycles outside active updates; previously none fit.
The largest remaining cold blocks still cannot fit many idle windows.

ROM `elma-gbc-v0.91-timed-zx0-4m.gbc`, SHA-256
`1d8822adb5bafae128e2f16128d8b8df1a673ad17144257a8bbbfce6f3a3a0f6`.
Evidence: `build/v091-timed-zx0-{cost,graphics,gameplay-4m,freefall}`,
`build/v091-cost-prefix-cache`, and
`build/v091-compressed-regression/v0.91-timed-zx0-4m`.

## 09: acquisition and raw upload bookkeeping — retained

The near-bank6 acquisition helper preserves both output/temporary slot lists,
attributes, allocation order and every counter without scratch RAM. It saves
116–128 cycles per item. The raw upload helper preserves the partial first ROM
bank, nine-bit bank value and physical slot-252 gap; DMA itself is unchanged.
Raw upload glue shrinks 28 bytes and adds no RAM. It is omitted from compressed
builds; native structure offsets are compile-time checked.

Focused fixtures pass 7,576 bookkeeping cases, 2,809 integrated acquisitions,
16,384 upload arguments and the worst update's 37 exact upload arguments.
The latter saves 5,816 isolated cycles; acquisition saves 4,992 for its 39
calls. Full-game timing is measured separately: all 216 cases / 27,447 states
still match 0.90 in both sizes. Corpus misses fall **460 to 444** in 8 MiB
and **959 to 950** in 4 MiB; entirely passing cases reach **131 / 76**.

Both cache fixtures pass 3,031 views. The compressed full observer passes;
the raw full instruction observer again stalls under PyBoy and is terminated.
The identical raw fixture passes native checks plus SRAM-guard and DMA-launch
observation, including 23,147 safe launches. This is an observer limitation,
not evidence of physical-cartridge timing. DMA polling was only 21.56% of the
worst raw update's upload helper cost; repeating a wait-loop optimization is
unlikely to close its remaining gap.

| Candidate | SHA-256 |
|---|---|
| `elma-gbc-v0.91-stream-glue-4m.gbc` | `0731029510f76f3ad8d9bc38f82be58dd3d19f6dab2cad327fbe3473243d0f56` |
| `elma-gbc-v0.91-stream-glue-8m.gbc` | `846e2477f85503f9dc603a3c230bfd02355497638d367a02e353715a3ef5a474` |

Evidence: `build/v091-acquire-bookkeeping`, `build/v091-raw-scroll-hotspot`,
`build/v091-stream-glue-cache-{4m,8m}`, and
`build/v091-stream-glue-gameplay-{4m,8m}`.

## 10: exact contact memoization — deferred for worst-frame regression

Two per-wheel entries store full coordinates and pure contact geometry before
pushout. Collision reset invalidates them. A native gate bypasses moving
wheels; HOST stays uncached. All 27,447 controller steps plus 1,727 trajectory
steps match the frozen 161-byte state, and 7,568 normal cases pass.

The candidate saves 1.44% of fixture physics time (2,260 cycles/update), mainly
settled neutral wheels. Moving bypass averages +361 cycles and reaches +608;
eligible misses reach +5,920. The heaviest moving updates regress slightly,
and the cache costs 59 RAM / 727 ROM bytes. Defer integration: this does not
address the remaining worst-frame deadline failures. Revisit only if a cheaper
gate or broader exact reuse changes the measured tradeoff.
Evidence: `build/v091-contact-memoization/{findings,timing-analysis}.json`.

## 11: proven-empty object regions — retained with fused clipping

After an empty coarse scan, retain an inclusive rectangle containing the
bike bounds but no eligible object coordinate. Reuse is exact only while the
new bounds remain inside and the apple count is unchanged. Level start
invalidates the proof; active object flags only clear between starts.
Collision radii, fractional positions, effect order and drawing stay intact.

The first implementation builds the rectangle in a second object pass. Its
1,226 native paired cases pass, including signed boundaries, ordered effects,
interrupts and 100 captured Haircut states. Haircut's object-check mean falls
42,855 to 19,968 cycles, but a cold 64-object scan regresses by up to 41,572.
The integrated 216-case corpus is still exact: raw misses **444 to 335**,
compressed **950 to 848**, with 140 / 81 wholly passing cases. Raw level7/brake
gains one new miss; the next candidate fuses clipping into the existing near
test to remove the duplicated walk before retaining the implementation.

| Intermediate candidate | SHA-256 |
|---|---|
| `elma-gbc-v0.91-empty-region-4m.gbc` | `3fdd95554afb65f1fea48ed25b43756ca199fa633f0b5383fecb6303fde92637` |
| `elma-gbc-v0.91-empty-region-8m.gbc` | `09b4ca57484f6d30c42c9209faf86faff9becb24a70b38e419bbc89ff9dec53a` |

Evidence: `build/v091-dense-objects` and
`build/v091-empty-region-gameplay-{4m,8m}`. These are development measurements;
the strict 30-FPS gate remains unmet.

The final helper clips the rectangle during the existing assembly near test,
removing the second pass. Cold 64-object scans improve 304–352 cycles over the
original; sampled boundary cases add at most 352. Dense-near scans improve
3,168 cycles on average. Haircut object checks average 18,970 cycles. The cache
uses 10 bytes; bank5 shrinks 260 bytes versus the second-pass candidate.

The reusable fixture passes 1,094 native paired scenes, 12,544 clipping cases,
729 saturating bound combinations, and the independent 4,096-bound fixture.
The optional captured Haircut run passes 1,226 paired scenes. Full raw gameplay
again matches all 216 cases / 27,447 states, with **340 misses / 140 passing
cases**, versus 444 / 131 before object caching. This is five more misses than
the second-pass intermediate despite better isolated costs; whole-loop timing
also includes IRQ/LCD phase and idle-preparation changes. Do not infer complete
frame timing from an isolated helper measurement.

Retained ROM `elma-gbc-v0.91-fused-empty-8m.gbc`, SHA-256
`77ee3c8061987acb5f138e9e40f68e4113d027be16ab3a213a1ec75dd24c39d1`.
Evidence: `build/v091-object-empty-clip`, `build/v091-fused-empty-native`,
`build/v091-fused-empty-gameplay-8m`, and `build/objects-bounds-check`.

## 12: resumable ZX0 — stopped after scope change

A private 323-byte decoder plus 38-byte bank wrapper can yield after at most
65 output bytes, using 14 HRAM bytes. The completed native run covers 11,514
production streams, six bank-300 mirrors and 90 cancellation/restart cases;
maximum wrapper cost is 17,048 cycles. Total decode work increases, so this
was only useful for moving compressed work into smaller idle windows.
The 4 MiB scope was dropped before integration. Production is unchanged;
no further compression work or tests should run. Final IRQ-stress output
was not reviewed after cancellation. Evidence: `build/v091-incremental-zx0`.

## 13: direct raw pattern lookup — retained

Use the raw build's spare SRAM banks1–3 for 12,288 direct ID-to-slot entries.
All 53 fitting courses use this path; level46 keeps the full-ID linked table.
The selected lookup module is separate from common far/mirror access. Each
operation restores SRAM0; the save region stays untouched. The fallback costs
32 extra cycles per API call. Raw code grows 172 ROM0 bytes and one RAM byte;
LCD-off direct initialization costs 246,304 cycles versus 168,336 linked.

All 49,829 native lookup checks, 2,809 direct and 2,809 fallback acquisitions,
and 3,031 cache views pass. The 39-acquisition/37-upload replay saves 20,156
cycles with LCD off and 18,196–20,044 with LCD on. The natural full-game corpus
stays exact across 216 cases / 27,447 states, with **333 misses / 141 wholly
passing cases**, versus 340 / 140 before this change. The isolated 13.2%
acquisition saving is not a 13.2% whole-game improvement.

The shared-memory split also passes the full 131,072-ID linked check,
327,680 clear checks, 202 far-copy and 340 gather checks. A reusable direct
lookup test is added. The cache fixture's explicit `--launch-observer` keeps
native byte/reference/deadline checks, SRAM guards and DMA-launch checks,
while omitting instruction hooks that can stall PyBoy with pending interrupts.
Reports identify this observation mode; they do not claim RAM-write or DMA
completion timing instrumentation when it is disabled.

ROM `elma-gbc-v0.91-direct-lookup-8m.gbc`, SHA-256
`b27d9cae71b78d112153eb1987c94252fe98b1610b8bef6169f61bfe1b4dba26`.
Evidence: `build/v091-raw-direct-lookup`,
`build/v091-direct-lookup-{native,cache,acquire,gameplay-8m}`, and
`build/playtest/world-memory-check`.

## 14: exact brake torque orchestration — retained

Replace only the two-wheel brake spring/angular damping loop with a near-bank8
helper. Brake-edge initialization, gas, reaction and volt order remain intact.
It preserves wrapping 32-bit angles, signed17 omega differences, clamping,
coefficient rounding and final saturation. No workspace is added; bank8 shrinks
276 bytes and the step's 41-byte stack frame is unchanged.

All 1,614 native boundary vectors, 1,727 full-state trajectory samples and 326
representative route states match their C/model/frozen0.90 oracles. Isolated
two-wheel savings are 4,044–4,212 cycles. Worst Gravity Ride physics improves
295,860 to 291,696; Bumpy Journey 303,380 to 299,220. Those physics calls still
exceed the whole-frame budget even before presentation.

The integrated raw ROM retains all 216 exact cases / 27,447 states. Full-corpus
misses improve **333 to 317**, with **148 entirely passing cases**. ROM
`elma-gbc-v0.91-brake-8m.gbc`, SHA-256
`501cc631a63acd54fc1055aa002c2f9d514fe12548a71c7f38f9979b63ea86f7`.
Evidence: `build/v091-brake-reaction`, `build/v091-brake-native`, and
`build/v091-brake-gameplay-8m`. `test/check_physics_brake.py` retains the
independent vector/model fixture using the selected generated constants.

## 15: fixed cache-reference retirement — retained

Use the production cache addresses directly in a near-bank6 helper, removing
generic pointer arguments and repeated stack traffic. Full 16-bit reference
counts, duplicates, zero references and the exact 1-to-0 bitmap transition
remain unchanged. The kernel moves from 104 ROM0 bytes to 88 bank6 bytes,
adds no RAM and uses four fewer transient stack bytes.

The native paired fixture passes 71,368 cases, including every 16-bit reference
value, all 444 slots, duplicate lists, zero/count255, timer interrupts and SRAM
guards. The private captured run adds 25 actual retirement calls and tests a
page-crossing mask table. The 39-entry update148 call improves 16,580 to 9,952
cycles; all captured calls together improve 219,536 to 137,584. The production
cache fixture passes 3,031 views with guards and DMA-launch observation.

All 216 gameplay cases / 27,447 states remain exact. Deadline misses fall
**317 to 304**, and **156 cases** now pass throughout. ROM
`elma-gbc-v0.91-retire-8m.gbc`, SHA-256
`a1ad063ffc9771834ab34230a819baf2bce60555f2eb03b1a83ef9a3a14b3ae6`.
Evidence: `build/v091-reference-retirement`, `build/v091-retire-native`,
`build/v091-retire-cache` and `build/v091-retire-gameplay-8m`.

## Controller benchmark and remaining physics work

`test/benchmark_gameplay.py` uses actual menu/buttons, deterministic per-step
inputs and natural death/finish. It records all 109 internal and 52 public
state bytes at physics return, plus clock/object state after each update.
The strict deadline is fixed and timing failures do not truncate the corpus.

```sh
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.90-8m.gbc --gen build/gen-8m --out build/v091-baseline-gameplay-8m --steps 180
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.91-retire-8m.gbc --gen build/gen-8m --out build/v091-retire-gameplay-8m --steps 180 --reference build/v091-baseline-gameplay-8m/report.json
```

All 216 cases (54 levels times neutral/gas/brake/seeded) and **27,447 native
steps** match the 0.90 reference exactly in the combined raw candidate.
Timing misses improve **1,025 to 304**; wholly passing cases improve **72 to
156 of 216** in the retirement candidate. This is still a failed 30-FPS gate.
Some physics calls alone exceed the frame budget: the brake candidate reaches
299,220 cycles in Bumpy Journey and 291,696 in Gravity Ride. Exact native
arithmetic/contact optimization is the next requirement.

PyBoy does not charge the GDMA CPU stall or fully reproduce early LY-153
wrapping. The benchmark additionally reports a 64-cycle-per-world-upload
margin estimate, but this does not simulate the shifted interrupt/LCD
schedule or establish physical-cartridge stability. Cache tests avoid hooks
directly replacing EI: with a pending IRQ, that PyBoy instrumentation can loop
without advancing emulated time. This was a test-observer failure; the
superseded raw-fetch fixture run was stopped and the current fixtures pass.
The gameplay observer also ignores a repeated first-instruction hook when an
IRQ returns to the same unreturned call and stack depth. This fixes the
spurious extra step in level 45/seeded; all 216 combined cases pass the exact
reference comparison with this observation fix.
