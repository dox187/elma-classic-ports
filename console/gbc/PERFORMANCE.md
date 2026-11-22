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

## 16: native contact candidate loop — retained

Move candidate iteration, endpoint selection and contact-record writes into a
bank9 kernel. Keep the existing ordered box iterator, projection, multiply,
normalization and contact merge formulas. An initial scalar-workspace variant
saved only 222 cycles/update and was rejected. The retained kernel adds 17 RAM
bytes and reduces bank9 by 383 bytes. Merge invokes a C helper, so a reduced
maximum stack depth is not claimed.

All 7,038 adversarial boundary groups preserve all 20 contact bytes, count and
final segment cursor. Normalization passes 7,568 cases. The captured Gravity
Ride replay saves 1,624–8,976 cycles/update (mean 4,741), with no regressions.
Complete native/HOST trajectories preserve 1,727 states of 161 bytes, including
wide freefall and interrupts. Their previous physics peaks improve by
3,908–5,396 cycles; none of those fixture steps regresses.

The integrated 216-case / 27,447-state corpus stays exact. Misses improve
**304 to 271**, with **157 wholly passing cases**. ROM
`elma-gbc-v0.91-contact-loop-8m.gbc`, SHA-256
`523254912ce7d8a68436ad17e91f5edca5cbd96cb2e0d8f03ebc5652d3f50957`.
Evidence: `build/v091-contact-loop`, `build/v091-contact-loop-native`,
`build/v091-contact-loop-integrated-trace` and
`build/v091-contact-loop-gameplay-8m`. The reusable boundary fixture keeps the
original C collector as an independent frozen reference.

## 17: combined raw map-plane reads — retained

Read the low/high/attribute planes under one nine-bit ROM-bank selection;
specialize unit stride and hoist raw tile extents. The helper adds 107 ROM0
bytes, while bank6 shrinks 152 bytes; no static RAM is added. The C fetch frame
grows from 19 to 25 bytes. Count zero remains a no-op.

The native fixture passes 12,048 cases with interrupts off and on, covering
clipping, partial reads, count/offset combinations, banks255/256/500/511 and
the last ROM-window byte. Its private captured extension adds 58 real calls;
all improve, totaling 57,104 saved cycles. Double Trouble/gas update148's two
fetches improve 25,324 to 20,964. Short synthetic reads starting outside the
extent can regress by up to 420 cycles; in-bounds synthetic reads do not.
All 3,031 cache views, save guards and preparation deadlines pass.

The integrated corpus remains exact across all 216 cases / 27,447 states.
Misses improve **271 to 262**, with **163 entirely passing cases**. Frontend,
profiles/saves, finish audio and volt checks pass. The 54-course visual/start
suite and complete Freefall run pass their functional checks but each reports
one timing overrun, so their strict performance gate remains failed.

ROM `elma-gbc-v0.91-strip-8m.gbc`, SHA-256
`6047c799d8d99d7ab64254c3a101a07b1317cbaae86f66c62b806d2fa076d863`.
Evidence: `build/v091-raw-strip-fetch`, `build/v091-strip-native`,
`build/v091-strip-cache`, `build/v091-strip-gameplay-8m` and
`build/v091-strip-checks`.

## 18: use existing post-overrun idle time and fix the first wait — retained

After an overrun the main loop already waits for the next VBlank. Permit
bounded offscreen preparation in that existing tail, supplying `now-1` to the
unchanged two-frame preparation deadline. Keep the original normal-case
condition/call and original update-start timestamp. No queued input or extra
presentation frame is introduced; all active work still counts against the
strict budget. Double Trouble/gas update148 improves from 473,160 to 387,960
cycles in the fast-tail candidate; its upload count drops from 37 to 3.

The initial ternary gate added common-case overhead and exposed a pre-existing
wait race: VBlank could arrive between reading `sys_time` and calling `vsync`,
whose entry clears its event flag. The original inner wait then skipped a
frame. A conditional first-frame helper checks the timestamp/pending interrupt
atomically and sleeps only while the first VBlank has not arrived. Its NOP
absorbs the IME-off HALT duplicate-fetch case. The profiler observes helper
entry at the same first-idle boundary as the previous inner `vsync`.

The native wait fixture passes 2,772 LCD-phase/counter-wrap/timer-IRQ cases;
already-passed deadlines return within 1,264 cycles including ISR work.
Actual waits remain below one frame. The scenery fixture passes 374 phase/wrap
cases / 748 views, including 142 conflicting preparations, with no byte,
reference, save-guard or preparation-deadline failures. A full-ROM audit sees
11 post-overrun preparation calls and no supplied-deadline crossings.
Combined footprint is +73 ROM0 bytes with no static RAM increase.

All 216 gameplay cases / 27,447 states remain exact. The final candidate has
**233 active deadline misses / 224 stretched input intervals / 163 wholly
passing cases**, versus 262 / 253 / 163 before scheduling. The final wait fix
removes one stretched input interval from the fast-tail candidate. These are
still failed 30-FPS results, including several physics-only overruns.

ROM `elma-gbc-v0.91-wait-8m.gbc`, SHA-256
`dac9fca460ab16e00547ab9428c8d56c60ec0245ee36611e511ff1573f3aa43b`.
Evidence: `build/v091-scroll-schedule`, `build/v091-wait-native` and
`build/v091-wait-gameplay-8m`. Intermediate ROM hashes are retained in their
`v091-idle-{tail,fast}-gameplay-8m` reports.

## 19: exact wheel response orchestration — retained

Near-bank9 support, rolling and free-wheel kernels use the existing exact
projection, coefficient and move helpers. Contact collection, pushout and
support ordering stay unchanged. Preserve full 32-bit saturation/wrap and the
signed17 free-wheel angular sum. No static RAM is added; bank9 shrinks 499
bytes and the wheel caller's stack frame falls from 28 to 6 bytes.

The reusable fixture passes 1,356 boundary/random vectors against C and
independent wide-integer formulas; the private captured extension adds 233.
All 1,727 trajectory and 326 route states match the 161-byte frozen reference.
The private generic level fixture also passes 53,416 HOST / 27,164 native
queries. All measured active fixture calls save at least 2,000 cycles.
Gravity Ride's previous physics peak improves 284,296 to 278,880 and Bumpy
Journey's 295,500 to 291,196; the latter still exceeds the entire budget.

All 216 integrated gameplay cases / 27,447 states remain exact. Misses improve
**233 to 194**, stretched input intervals **224 to 184**, and wholly passing
cases **163 to 168**. ROM `elma-gbc-v0.91-wheel-8m.gbc`, SHA-256
`39ee7456a302a22c3196f1637ff9c97b0d62bb1d126781a2cd95dd7dbf02d3dc`.
Evidence: `build/v091-wheel-response`, `build/v091-wheel-native`,
`build/v091-wheel-integrated-trace` and `build/v091-wheel-gameplay-8m`.

## 20: cache small ordered object candidate sets — retained

Extend the empty-rectangle proof with up to four coarse-near original object
IDs. While the bike bounds stay inside the proof, omitted objects remain
excluded; retained candidates still receive the original coarse and exact
touch checks in original order. A warm apple hit switches to the full remaining
ID suffix so a later flower can unlock in the same call. Reset, apple-key
changes and list overflow invalidate the cache. Keep coarse checks because
wrapping exact-touch deltas alone can collide across signed coordinate limits.

The native fixture passes 1,118 paired scenes, 12,544 clipping cases and 729
bound combinations; the captured extension passes 1,250 scenes. Tests cover
warm signed extremes, last-apple/flower order, multiple gravity effects,
active clearing and list overflow. Haircut's 100-step object-check mean falls
18,970 to 7,622 cycles. Cold far scans save 8 cycles; cold dense-near scans add
1,252 on average, with a sampled cold maximum regression of 2,012. This is an
explicit measured tradeoff, not a universal cold-path improvement. The cache
adds 5 RAM / 420 bank5 bytes; tested stack watermark is 49 bytes below API
entry versus 47 for the original pre-cache oracle.

All 216 full-game cases / 27,447 states remain exact. Misses improve
**194 to 155**, stretched input intervals **184 to 144**, and wholly passing
cases **168 to 171**. ROM `elma-gbc-v0.91-object-cache-8m.gbc`, SHA-256
`024a57594fc99940f4052d913f322cdde1e28d94ef194e151d585973ebe16c28`.
Evidence: `build/v091-object-candidates`, `build/v091-object-cache-native`
and `build/v091-object-cache-gameplay-8m`.

## 21: rejected head-rejection order and unconditional diagonal lookahead

Moving the exact capsule AABB rejection before its infinite-line rejection
passes 8,192 independent geometry vectors and 326 exact route states. Gravity
Ride costs are unchanged. Bumpy Journey saves 490 cycles on average but its
previous worst physics frame regresses 291,196 to 291,860, with another sampled
regression of 3,044. Reject: it worsens the limiting case. Production remains
unchanged. Evidence: `build/v091-head-reject-order/findings.json`.

Always predicting both fine-motion axes also loses. Explicit byte-patched-ROM
screening preserves 1,635 states in 12 focused cases, but misses rise 26 to 28
and stretched intervals 24 to 26. Double Trouble update148 grows 387,960 to
440,916 cycles, with 3 to 21 uploads: column-first work starves the useful row
before target changes cancel it. Native cache/phase fixtures remain correct.
Reject without source integration or a complete candidate build. Evidence:
`build/v091-prepare-diagonal/handoff.json`, including patched-byte provenance.

## 22: exact rider response orchestration — retained

Move the rider acceleration orchestration into a near-bank8 kernel while
keeping the existing rider limit, vector, rounded coefficient and move helpers.
The HOST and generic native paths retain their C implementation. No static RAM
is added and bank8 shrinks 302 bytes. The C caller frame drops from 36 to 4
bytes; the new helper uses 16 local and 16 argument bytes, so this is not a
claim about maximum total stack depth.

All 1,640 paired boundary/random cases match both frozen C and an independent
integer oracle; the private extension adds 326 captured calls. The isolated
kernel saves 2,636 cycles per vector. Complete trajectories preserve all
1,727 states of 161 bytes, including interrupts and wide freefall. Active
fixture updates save 2,196–3,324 cycles; previous Gravity Ride and Bumpy peaks
improve 278,880 to 276,668 and 291,196 to 288,984 respectively.

All 216 integrated cases / 27,447 states remain exact. Misses improve
**155 to 137**, stretched input intervals **144 to 129**, and wholly passing
cases **171 to 175**. Changed LCD/preparation phase still makes individual
presentation peaks non-monotonic; Double Trouble/gas update148 reaches
437,440 cycles. The complete 30-FPS gate remains failed.

ROM `elma-gbc-v0.91-rider-8m.gbc`, SHA-256
`82efafb66125e0fbeccec642d1497590a6167ac63f791d174599d0362461f640`.
Evidence: `build/v091-rider-response`, `build/v091-rider-native`,
`build/v091-rider-integrated-trace` and `build/v091-rider-gameplay-8m`.

## 23: reuse exact head-sweep cross products — retained

Fuse the infinite-line rejection into the capsule predicate without changing
its position before AABB rejection. Reuse its exact cross products for segment
intersection and endpoint-distance checks; pass relative coordinates to the
distance helper. Bounded edge/path pieces retain the original signed arithmetic
and strict radius comparisons. Bank4 shrinks 119 bytes with no static RAM
increase. The capsule local frame grows 32 to 54 bytes while the removed
line-rejection frame used 27; maximum total stack depth was not measured.

All 8,211 native geometry vectors, including 19 real captures, pass the
independent oracle. All 1,727 trajectory and 326 route states remain exact.
Gravity Ride's previous physics peak improves 276,668 to 274,788; Bumpy's
288,984 to 269,920. Two non-peak Bumpy updates regress by 3,580 and 204 cycles.
These tradeoffs are retained because the limiting peak and complete corpus
improve. The previous rejected AABB-first ordering is not used.

All 216 integrated cases / 27,447 states remain exact. Misses improve
**137 to 129**, stretched input intervals **129 to 123**, and wholly passing
cases **175 to 177**. Every physics call in this corpus is now below the full
two-frame budget (maximum 275,800), but presentation and other loop work still
cause whole-update failures. This is not a stable 30-FPS release.

ROM `elma-gbc-v0.91-head-8m.gbc`, SHA-256
`e86923362def284df7493aa1a1b8156f017cc5d1eb076261dc0364298639ba53`.
Evidence: `build/v091-head-sweep-kernel` and `build/v091-head-gameplay-8m`.
The separate functional suite passes all 54 starts (12 idle updates each),
433 observed Freefall steps, frontend, player/save, finish audio, volt and
300-step driving checks. Starts and Freefall now report zero overruns.
Evidence: `build/v091-head-checks`.

## 24: retain the acquisition stage between budgeted items — retained

Keep the original outer budget guard for the first item, fetch and publication;
subsequent raw acquisitions check the same 20-line guard inside the stage loop.
This avoids repeating stage dispatch while retaining every bounded work unit.
The first variant added fetch-path discrimination and deferred a fragment at a
scanline threshold, regressing Double Trouble/neutral by 8,232 cycles. Reject
that variant; the retained version leaves the fetch guard unchanged.

Independent native validation passes 3,031 cache views and 374 phase/wrap cases
/ 748 views, including 142 conflicting cancellations, with no visible-byte,
reference, mirror, save-guard or preparation-deadline failures. The focused
controller audit passes 3,270 visible/cache inspections. Footprint is +45 bank6
bytes, zero static RAM or ROM0 increase.

The isolated rider-baseline corpus improves 137 to 130 misses, 129 to 122
stretched input intervals and 175 to 177 passing cases, with none lost. Its
weighted mean saves 1,399 cycles/update. Timing is not monotonic: Sink/seeded
update106 grows 273,540 to 362,328 after preparation-phase changes, and
Twin Peaks/brake gains one miss. These remain failed cases.

Combined with the head-sweep change, all 216 cases / 27,447 states remain exact.
Misses improve **129 to 124**, cadence violations **123 to 117**, and wholly
passing cases **177 to 178**. The strict 30-FPS gate remains failed.
ROM `elma-gbc-v0.91-dispatch-8m.gbc`, SHA-256
`49a2e1bd7685ff26f3a8cfc13c37a0b0af223f17e0aa672938ac71d329ac9627`.
Evidence: `build/v091-prepare-dispatch` (both variants, native/captured checks,
private hash-exact relink and full-corpus comparison) and
`build/v091-dispatch-gameplay-8m`.

## 25: remove paired VRAM-copy stack traffic — retained

Read the attribute and tile bytes directly through BC/DE inside the existing
fresh-STAT write window; advance both pointers after the final write. Remove
two push/pop pairs per cell. Every caller supplies stable ROM/WRAM data, and
the accepted LCD modes, attribute-before-tile order, wrap logic and interrupt
handling remain unchanged. Fixed work saves 56 cycles/cell and bank6 shrinks
256 bytes with no static RAM increase.

The strict linked-instruction assertion proves 92 fast T-cycles from the start
of the final STAT read through both writes, down from 100 and below the
following mode2 minimum of 160. The expanded native fixture passes 2,486 cases
plus 32 interrupt stress calls and observes 84,064 writes: every count0–32,
wrap start, both orientations, source-page carries, ROM/WRAM sources, all entry
LCD modes, registers, banks and guards. The original reusable fixture and all
3,031 independent cache views also pass. Per-strip phase differences can add
32 cycles in isolated cases; mean and observed worst improve. Physical hardware
has not been tested.

All 216 integrated cases / 27,447 states remain exact. Misses improve
**124 to 119**, cadence violations **117 to 112**, and wholly passing cases
**178 to 180**, with none lost. The whole-update 30-FPS gate remains failed.
ROM `elma-gbc-v0.91-video-8m.gbc`, SHA-256
`0058d193c2b567ffbd9dd1d973fbbb836f927be2adfa6c75c6048e450c2821f6`.
Evidence: `build/v091-strip-pair`, `build/v091-video-native` and
`build/v091-video-gameplay-8m`.
The combined video candidate also passes the seven separate functional checks,
including all54 starts and complete Freefall with zero overruns. Evidence:
`build/v091-video-checks`.

## 26: cache exact repeated contact normals — retained

Use a single pure-result entry keyed by all eight supplied dx/dy/d2 bytes.
Cache only nx/ny/length; preserve the destination's tx/ty. Repeated calls may
target different contacts, and level/reset/gravity changes need no invalidation.
Table misses retain the original stack; deep misses alone forward arguments.
The initial general wrapper cost 300 more cycles on every table miss and is
superseded. The retained helper adds 111 bank9 / 15 WRAM bytes, with unchanged
table-path stack depth and 12 additional bytes on deep misses.

The independent integer fixture passes 23,586 calls, including warm hits,
changed/revisited d2 bytes, signed boundaries, reciprocal-index wrapping and
different guarded destinations. Another 1,289 captured/signed native-parity
calls pass. All 1,727 trajectory and 326 route states remain exact. On the
captured Gravity Ride workload, 198/412 calls hit and the mean falls from
4,440 to 3,107 cycles; warm hits cost 808. Cold calls add 708–1,156, so this is
not a universal per-call improvement.

All 216 combined cases / 27,447 states remain exact. Misses improve
**119 to 114**, cadence violations **112 to 107**, and passing cases **180 to
181**. Animal Farm/brake and Steppes/neutral become passing; Gravity Ride/seeded
gains one miss on its first cold update (279,552 to 289,012 including existing
post-overrun preparation). This explicit regression remains to be removed.
The maximum physics call falls 275,800 to 270,932; the 30-FPS gate remains failed.

ROM `elma-gbc-v0.91-normal-8m.gbc`, SHA-256
`50d36d5f0d7bcb6a1d151928c098032fda8e356e05322a55b4509ce47b9412f7`.
Evidence: `build/v091-normal-cache`, `build/v091-normal-gameplay-8m` and the
read-only first-update breakdown in `build/v091-preparation-margin`.

## 27: head-pose orchestration and fixed-size normal-cache loops — retained

The bank8 head helper extracts the required 16 angle bits directly and retains
the existing sine and four rounded coefficient kernels. It refreshes both
cosine/sine caches during initialization, turns and completed steps. Native
validation covers all 65,536 phases with both turn states, varying discarded
angle bits, 16 coordinate boundaries and an independent integer oracle:
131,072 cases, all 109 Bike bytes, caches, guards and banks remain correct.
Direct head calls save 1,252–1,264 cycles; isolated active updates save at least
1,124. Bank8 shrinks 110 bytes, static RAM is unchanged and measured head-path
stack depth falls 30 to 24 bytes.

Separately unroll the fixed eight-byte normal-cache comparison/key copy and
six-byte result transfers. Keep every byte access and comparison, removing
only loop counters/branches. Warm hits improve 808 to 576 cycles; a cold copy
and result store save 232 before any partial-key comparison saving. The
23,586-call independent normal fixture remains exact, with guards/banks intact.

All 1,727 integrated trajectory states and all 216 full-game cases / 27,447
states remain exact. Misses improve **114 to 106**, cadence violations **107
to 100**, passing cases **181 to 182**, with none lost. Gravity Ride/seeded's
first cold update improves 289,012 to 281,108 but still exceeds 280,896.
ROM `elma-gbc-v0.91-pose-8m.gbc`, SHA-256
`695dcecaeae4b9312ec04bad386b537062979970b51b2639e6c46dc45dd36dd2`.
Evidence: `build/v091-head-pose`, `build/v091-normal-unroll`,
`build/v091-pose-integrated-trace` and `build/v091-pose-gameplay-8m`.

## 28: fixed scenery slots — prototype deferred

An offline conflict graph assigns nonconflicting pattern IDs to the same
physical slot. Independent shifted-grid verification proves all distinct IDs
within a 22x20 old/new viewport union differ in slot, including padded ID0.
Thirty of 54 courses fit 444 slots; other courses retain the current cache.
The prototype keeps reference/free-bit/save invariants and uses a proved live
reference shortcut. It passes 3,031 native views, 324 cancellations, 13,159 live
invariant checks, 3,108 static / 2,809 fallback metadata cases, and all 216 real-ROM
physics/visible-source comparisons.

Against the frozen dispatch build, misses improve 124 to 122 and cadence 117
to 115, but passing cases stay 178. Bumpy/brake and Sink/gas each gain one miss.
The prototype adds 67,734 table bytes, 216 directory bytes, 305 code bytes and 1
WRAM byte, using only previously unused banks 481–485. Defer production
integration: the current implementation has a small, uneven gain and needs
a reproducible asset-generation/build path. Do not regenerate or retest the
same coloring expecting a different result without a new runtime hypothesis.
Evidence: `build/v091-static-slot-audit` and `build/v091-static-slots`.

A separate coordinate-modulo22x20 model plus four common fixed patterns raises
uploads from 13,907 to 17,902 even before speculative preparation. It only models
incoming cells, not native cycles. Do not confuse it with the pattern conflict
graph prototype. Evidence: `build/v091-coordinate-slots/model.json`.

## 29: share the projection of equal contacts — retained

If both contacts have identical nx/ny/length, their projected tx/ty are also
identical. Compute that point once and copy it to the second contact, then
perform the original final normalization. That normalization is not assumed
idempotent. A compile-time assertion retains the positive merge-radius proof;
all20 contact bytes and the return count remain exact.

Paired native validation passes 2,322 direct merge vectors, 7,038 frozen-C
contact groups, 1,727 trajectory and 326 route states. Read-only real-game
captures preserve 686 steps including clock/object results. Equal contacts
occur in118/174 captured merges; Gravity Ride's mean merge saving is3,284
cycles. Unequal captures add80, with a synthetic maximum addition of292.
Footprint is +262 bank9 bytes, no static RAM and the same20-byte local frame.

All216 integrated cases /27,447 states remain exact. Misses improve **106
to98**, cadence violations **100 to93**, and passing cases remain **182**,
with none lost. The largest physics call is269,780; complete updates still
miss the strict deadline.
ROM `elma-gbc-v0.91-merge-8m.gbc`, SHA-256
`5b73b360180f1706d437ef170fa8670b030822ee3233714fb229811b4e613b06`.
Evidence: `build/v091-equal-contacts` and `build/v091-merge-gameplay-8m`.

## 30: wheel torque reaction orchestration — retained

A bank 8 helper performs the existing two-wheel torque reaction with eight
stack-local bytes. It keeps the reciprocal index, truncating product,
C_REACT coefficient, rounded products and wrapping accumulations unchanged.
Zero torque skips the vector loads. The generic/HOST implementation remains
in C. The native reciprocal table is exported with a size assertion.

All 2,718 paired vectors pass, including 326 captured states, 676 accumulator
wraps, 691 zero-torque wheels and 512 occurrences each of the minimum and
maximum signed torque. All 1,727 trajectory plus 326 route states remain
exact, and the generic fixture passes all 54 levels. Matched active updates
save 404–3,884 cycles. Code shrinks by 176 bank 8 bytes with no static RAM;
the measured route stack maximum remains 237 bytes, while the main trajectory
maximum rises from 223 to 229 bytes. The ph_step local frame remains 41 bytes.

The integrated 216-case / 27,447-state controller corpus is exact. Misses
improve **98 to 84**, cadence violations **93 to 78**, and wholly passing
cases **182 to 188**, with none lost. Gravity Ride/seeded's cold first update
now passes. The maximum physics call is 267,008 cycles; complete updates still
exceed the strict deadline.
ROM `elma-gbc-v0.91-torque-8m.gbc`, SHA-256
`18676431c092322508463df5cd7c5541f422d81305afc5e1d46836a93d7a7bf4`.
Evidence: `build/v091-torque-reaction` and `build/v091-torque-gameplay-8m`.

## 31: exact wheel pushout orchestration — retained

Native bank 9 assembly replaces pushout's C bookkeeping and retains the
existing mulq14/dotq14 kernels. The signed 16-bit correction narrows before
its positive test. A displacement shifted by eight bits leaves the position's
low byte unchanged; update the upper three bytes with the original carries.
On the positive branch, length plus the narrowed correction is exactly 405
modulo 65,536. The first contact's length is written before reading the optional
second contact, including when both pointers are equal. Layout and radius
assertions protect those identities; HOST and PHYSICS_PUSHOUT_C retain C.

All 11,361 paired native calls pass against C and an independent integer oracle,
including 241 captures, boundary values, optional/equal contacts, guard bytes
and ROM/RAM banks. The length identity also passes all 65,536 input values.
Every paired call saves 224–2,076 cycles. Code shrinks by 311 bank 9 bytes with
no static RAM; measured helper stack depth falls from 50 to 34 bytes. All
1,727 trajectory and 326 route states remain exact. Those isolated updates
never regress, although one full-game physics call moves by +864 cycles with
the changed interrupt phase.

On top of the torque candidate, all 216 cases / 27,447 states remain exact.
Misses improve **84 to 82**, cadence violations **78 to 74**, with **188**
wholly passing cases and none lost. Maximum physics cost is 266,512 cycles.
All seven separate functional checks pass: menus, profiles/saves, finish audio,
volt input, 54 starts, the complete 433-step Freefall and a 300-step profile.
The starts and Freefall have zero overruns and retain source-graphics checks.
ROM `elma-gbc-v0.91-pushout-8m.gbc`, SHA-256
`af69add17a6a1472bc57357b76c7d9acf6da4c34fb81ee5b1791164d22f713c8`.
Evidence: `build/v091-pushout`, `build/v091-pushout-gameplay-8m` and
`build/v091-pushout-checks`.

## 32: larger normal cache — model deferred

Replay the frozen read-only normalization keys from four difficult routes
through one-, two-, four- and eight-entry LRU models. Gravity Ride gains only
2 hits with two entries (198 to 200 of 412); Bumpy Journey, Sink and Downhill
gain none. Four and eight entries give Gravity Ride 209 and 214 hits, still
none extra on the other three routes. This model excludes additional lookup,
replacement and storage costs. Defer a larger native cache: the measured reuse
does not justify assuming a net gain, particularly on cold calls already
near the deadline. No production code changed for this model.
Evidence: `build/v091-normal-cache-model/model.json`.

## 33: current rendering bottlenecks — read-only profile

Six difficult controller routes reproduce all 935 update cycles and states
exactly against the frozen merge ROM. Inclusive timings must distinguish
mandatory presentation/physics from preparation performed in the existing
tail after an overrun. The strict update measurement continues to include both.

Double Trouble/gas update 148 spends 197,420 cycles in physics and 214,336
in presentation, with only 5,848 in its preparation tail. Of 39 synchronous
acquisitions, 18 hit and 21 upload. Acquisition bookkeeping alone costs 51,824
cycles, versus 21,156 in the upload helper. Across all 935 updates, acquisition
bookkeeping averages 4,098 and reaches 53,380. This motivates fused acquisition
orchestration rather than another DMA wait-loop adjustment.

The same update cancels a completed column at x=7, y=17..35 because the target
changes from (63,142) to (63,144). Eighteen cells at y=18..35 remain useful.
Cancelling costs 5,720 cycles; fetching/acquiring/publishing those cells again
costs 44,764. All 21 new uploads belong to the incoming row. Retaining the
overlapping column is a different hypothesis from always predicting diagonals.
Across the six routes, 101 cancellations discard 1,132 references.

Ordered object visibility filtering, excluding OAM publication, averages
5,378 cycles and reaches 32,512 on Haircut. The existing clipping prototype
is therefore worth integrating and measuring in the current game.
Evidence: `build/v091-scroll-profile/findings.json` and
`build/v091-scroll-profile/double-trouble-cancellation.json`.

## 34: ordered object visibility clipping — retained

Integrate the previously isolated 120-byte bank 5 clipping helper. It returns
the same active object IDs in ascending order, using the exact unsigned tests
`uint16(object.x-camera.x+7)<175` and the corresponding Y test `<151`.
It preserves every signed/wrapping boundary and only writes the returned ID
prefix. The existing camera/apple cache, sprite phase and OAM publication stay
unchanged. Layout assertions protect object stride/count offsets, and the
original C scan remains available with OBJECTS_VISIBLE_C_REFERENCE.

The reusable native check passes 2,835 scenes, all 131,072 X/Y coordinate
deltas, counts 0..64, mixed active flags and 256 IRQ-enabled calls. C and the
independent oracle agree on ordered IDs; output/global/bank/IRQ guards pass.
A 51-object distant scan falls from a mean 30,355.5 to 13,204.5 cycles.
The linked bank 5 size decreases by 36 bytes; there is no added static RAM.

All 216 full-game cases / 27,447 states remain exact. Deadline misses improve
**82 to 67**, cadence violations **74 to 59**, and passing cases **188 to 191**,
with none lost. Haircut/neutral falls from seven misses to three.
ROM `elma-gbc-v0.91-visible-8m.gbc`, SHA-256
`5084a17bc7f41db19cc3614e4d0d89a9cc26e5283bb1fe2fe2d1057d18c3a5ab`.
Evidence: `build/objects-visible-prototype`, `build/v091-visible-check` and
`build/v091-visible-gameplay-8m`.

## 35: rider-limit coordinate glue — exact, deferred

Two bank 8 helpers preserve wrapped/saturated local coordinates and moved
rider restoration. Seat and ellipse math stay in C. All 3,212 native/oracle
vectors pass, including 326 captures, 744 ellipse projections, 490 wrapped
subtractions and 288 wrapped restorations. The 1,727 trajectory / 326 route
states and generic 54-level fixture remain exact. Isolated active updates save
380–1,528 cycles, bank 8 shrinks 131 bytes and static RAM is unchanged. The C
frame grows four bytes; the measured hard-route stack maximum stays 237.

The whole game nevertheless regresses after the visibility optimization:
misses 67 to 70, cadence 59 to 62, with 191 passing cases unchanged. Mandatory
presentation costs move because different partial strips finish in preceding
idle windows. A second comparison with fused acquisition has 66 misses with
this glue versus 65 without it (58 versus 57 cadence violations), both with
192 passing cases. Keep the current C glue; preserve the exact candidate and
vectors for later scheduling comparisons rather than assume a local saving
guarantees smoother gameplay.
Evidence: `build/v091-rider-limit`, `build/v091-limit-public-vectors`,
`build/v091-limit-gameplay-8m`, `build/v091-acquire-gameplay-8m` and
`build/v091-acquire-nolimit-gameplay-8m`.

## 36: fused raw acquisition bookkeeping — retained

Raw prepare_acquire keeps the pattern ID and selected slot on the same stack
through lookup, upload and insertion. It avoids rebuilding arguments across
two helper boundaries. Allocation order, reference/free-bit transitions,
lookup entries, output slots/attributes and pending references remain exact.
Per-item budget guards stay unchanged, as do the generic acquisition helper
and compressed path. No shared scratch is added.

All 2,809 direct, 2,809 linked, 756 boundary and 39 captured native pairs pass.
The captured Double Trouble acquisitions save 8,252 cycles with identical
cache/output arrays and all four SRAM banks after every call. The public cache
fixture passes 3,031 views and six focused controller routes pass 1,870
source/cache inspections. Bank 6 grows 233 bytes, static RAM is unchanged.
Maximum wrapper stack at existing helper entries falls 14 to 10 bytes; at
upload entry it falls 14 to 6, excluding unchanged callee/IRQ stack usage.

After visibility clipping, with the retained C rider-limit glue, all 216 cases
/ 27,447 states remain exact. Misses improve **67 to 65**, cadence violations
**59 to 57**, and wholly passing cases **191 to 192**. A complete source build
reproduces the cached-object comparison image exactly.
ROM `elma-gbc-v0.91-acquire-nolimit-8m.gbc`, SHA-256
`0d7db587dfde503418bbf828eed7fab1160d36cd99a61d6fc5bbe56ab84de772`.
Evidence: `build/v091-acquire-fused` and
`build/v091-acquire-nolimit-gameplay-8m`.

## 37: retain a completed column for a diagonal target — retained

When a completed horizontal-only preparation gains exactly one vertical tile,
keep its 18 useful column references and hidden published cells. Retire the
excluded endpoint, append the outgoing 20-cell row, then run the original
21-cell incoming row stages. Exact coarse old/target matches, direction,
counts and READY state are required. Budgeted callers retain the existing
21-line setup reservation; rejected calls make no changes. The predictor and
partial/nonmatching preparations keep their existing behavior.

The first prototype paid helper setup on every mismatch and regressed total
cycles. A cheap outer READY check removes that common-path overhead. Against
the pushout snapshot, the retained variant saves 857,220 aggregate cycles;
Double Trouble/gas update 148 improves 431,984 to 378,772. The largest other
update regression is 12,760 cycles and remains below the deadline. Bank 6
grows 533 bytes, with no static RAM or ROM0 growth.

The integrated fused-acquisition build passes the 3,031-view cache fixture and
the extended 3,199-view fixture, including 36 four-direction cases, 192 guard
checks, late-budget rejection, exact references/free bits/source pixels and
save guards. The private paired fixture also compares 36 complete cache and
lookup checkpoints with the original cancellation path. All 216 gameplay
cases / 27,447 states remain exact; misses/cadence/passing cases remain
**65 / 57 / 192**, with none lost. The worst Double Trouble/gas update falls
to 404,696 in this combination; timing is not monotonic across combinations.
ROM `elma-gbc-v0.91-column-8m.gbc`, SHA-256
`e5a871916072416519a45ba94aafb41c869c92416b60ccc246b2c8e7712cf6a6`.
Evidence: `build/v091-retain-column`, `build/v091-column-cache`,
`build/v091-column-extended-cache` and `build/v091-column-gameplay-8m`.

## 38: reference-free fixed scenery slots — positive private prototype

A new hypothesis extends section 28's verified fixed-slot mappings: eligible
levels need no reference/free-bit/retirement maintenance because the mapping
proves all old/pending viewport IDs have distinct slots. It still compares
cached IDs and uploads changed patterns. Dynamic fallback levels retain the
existing cache. This is a distinct runtime experiment, not a rerun of the
lookup-only prototype.

All 357,874,164 map-position pairs pass revalidation. The native fixture passes
3,031 views, 13,082 pending-cell source/slot checks, 324 cancellations, 79 fine
scroll checks and 3,061 save guards. Static acquisition leaves references and
free bits untouched; 2,809 dynamic metadata cases still match. Against the
frozen pushout build, the 216-case corpus is exact and improves misses 82 to
72, cadence 74 to 64, passes 188 to 190, with none lost. Aggregate active cost
improves 0.373%; fallback levels pay a small dispatch cost.

Cost is 67,734 table bytes, 216 directory bytes, 328 bank 6 bytes and one WRAM
byte, only in unused banks 481–485. Production integration remains pending:
deterministic generation/build dependencies, merging the new acquisition path
and its mode-aware cache oracle. Preserve this validated prototype while the
current test ROM retains the existing asset format.
Evidence: `build/v091-static-norefs/handoff.json` and its runtime patch.

## 39: full-width Q14 multiplication and playable test1 — retained

Wide signed32-by-signed16 Q14 products now use two existing exact 16-bit
multiplications, a complete signed 48-bit accumulator, the original +8192
rounding and saturated 32-bit extraction. The unsigned low-half correction
preserves all input bits. Narrow Q14 dispatch is unchanged; other wide shifts
retain C with a 28-cycle dispatch addition. No static RAM is added.

All 4,768 paired calls pass against the frozen public/native-C implementations
and an independent integer oracle: 4,512 vectors include 234 captured calls,
plus 256 calls with timer interrupts enabled. Captured wide calls save
5,900–6,976 cycles, mean 6,222.5. The kernel uses six local stack bytes; measured
depth is 18 versus 58 for C. All 1,727 trajectory plus 326 hard-route states
match frozen 0.90. Their total stack peaks stay 225 / 237 bytes. Individual
timings can move with interrupt phase; two isolated updates add 16 cycles.

The helper adds 168 ROM0 bytes. Integration exposed a separate footprint
mistake: retained-column memmove had pulled 175 library bytes into ROM0.
Together they put the end of startup at 0x406d and the test image failed before
splash. Replace that one fixed 36-byte forward overlap copy with a bank 6
helper. The complete fixed bank now ends at 0x3fbe, leaving 66 bytes. The build
tool validates CODE, HOME, initializer and startup areas, including cached
builds, plus each switchable bank's bounds. Seven layout regression cases
include the observed overflow and a one-byte startup overrun. The failed image
was never delivered; its diagnostic reports remain in the overflow folders.

The final combined **test1** passes all 216 cases / 27,447 exact states.
Misses improve **65 to 55**, cadence violations **57 to 49**, and passing
cases **192 to 196**, with none lost. Maximum physics cost is 265,148 cycles.
All seven functional checks pass, including 54 starts and 433-step Freefall.
The extended cache fixture verifies 3,199 views, 36 diagonal cases and 192
guard cases against the final fixed-copy implementation. Stable 30 FPS remains
unmet, and physical cartridge timing has not been verified.

Observed input intervals are 27,182 at two display frames and 49 at three.
Across 27,231 intervals, 7,655,960,960 double-speed T-cycles give 29.8369
updates/second against the two-frame target of 29.86375, a 0.0899% aggregate
slowdown. The slowest tested case, level 11/brake, averages 28.5862. These are
short emulator routes, not full-course or hardware guarantees. The fraction
of wholly passing cases must not be interpreted as the game's speed.

Playable ROM: `build/elma-gbc-v0.91-test1-8m.gbc`, 8,388,608 bytes,
SHA-256 `624e427940917c15d1d4960866f0368f61549b6f59292a41290c047b6c38a8b5`.
Evidence: `build/v091-mulq-wide`, `build/v091-test1-gameplay-8m`,
`build/v091-test1-checks`, `build/v091-test1-extended-cache` and
`build/v091-test1-overflow.json`.

## 40: 0.92 riding audio — bounded added cost

Retain 0.91 test1 as the performance baseline. Version 0.92 adds source-derived
creak/volt/turn effects, a 17-down/4-up VBlank CH1 idle envelope and bounded
pitch walk, and reduces CH1 load volume from 8 to 6 (idle peak 3 to 2).
CH3 source cycles/pitch and all native physics results remain unchanged.

The first two-wheel projection implementation regressed the full corpus from
55 to 142 deadline misses and 196 to 174 passing cases. Preserve its evidence
in `build/v092-gameplay-8m-initial` and `build/v092-checks-initial`; do not reuse
that implementation. Quantize relative positions before projection, alternate
wheel observations, use small-coefficient shift/add products and cardinal
shortcuts, and skip inaudible compression checks during higher-priority audio.
Volt and turn observation still runs on every audio update. Idle phase/pitch
advancement uses elapsed VBlanks with bounded work, no interrupt or catch-up
loop. Mute CH1's DAC before changing its software volume to avoid transient
envelope artifacts on active hardware.

Final 216 cases / 27,447 native states match the original reference exactly.
There are **74 active misses, 68 cadence violations and 192 passing cases**;
average cadence is **29.8265 updates/s** versus test1's 29.8369. This is a
documented audio cost, not a completed stable-30-FPS release. All seven
functional checks pass, including 54 starts with no reported overrun.

The idle helper passes 10,797 assertions at 268–736 T. Native PCM tests measure
5,512 T maximum steady live audio, 2,488 T inactive, and 6,996 T transitions.
The separate 32-orientation/compression fixture reaches 9,336 T; its 10,000 T
ceiling rejects the initial implementation. PCM tests cover all seven effects,
channel priorities, 30/60 Hz service, bank/IRQ restoration, CH3 waveform
correlation, idle drift and the 15-VBlank hardware watchdog. Actual cartridge
timing and speaker balance still require hardware testing. ROM0 retains its
66 free bytes; no physics/control loop changes are involved.

ROM: `build/elma-gbc-v0.92-8m.gbc`, 8,388,608 bytes, SHA-256
`091d004160dd86213cbcbfc88a0395499ba073ed39dbf031f724c2b8e4f6324d`.
Evidence: `build/v092-gameplay-8m`, `build/v092-checks`,
`build/v092-audio-check`, `build/v092-effects/test`, `build/audio-idle-check`.

## 41: 0.92 creak trigger correction

Hardware feedback: the original 0.92 creaked almost continuously, including
in flight. Its pose-only proxy treated small spring oscillations as audible
impacts, then played a full-strength contour repeatedly. Publish each wheel's
existing contact-query result in two separate observation bytes; no extra
collision query or change to native physics is required. Audio now requires
that wheel's contact plus >=10/64 m compression and >=4/64 m inward travel,
with a stronger strength threshold. Latch both wheels on a sound onset to
avoid a second delayed sound for the same landing; each wheel re-arms only
below 6/64 m compression. Stop the creak when neither wheel contacts terrain.

Focused native fixtures reject repeated small grounded motion and large
in-flight oscillations, allow landing/new impact after release, reject repeated
compression without release and verify takeoff mutes the contour. Existing
32-orientation, channel/PCM, priority, watchdog, pause and wrap checks pass.
All seven game checks and 54 starts pass. The full 216-case corpus retains all
27,447 exact states; 82 active misses / 79 cadence violations / 188 passing
cases, average 29.8205 updates/s. This replaces the previous 0.92 image while
retaining version 0.92. Stable 30 FPS remains unfinished.

ROM SHA-256: `92243b18d66a5471d054377f98e164fef91e7130b3d66e0a6e470d6f3c328aec`.
Evidence: `build/v092-creakfix-effects`, `build/v092-creakfix-audio`,
`build/v092-creakfix-checks`, `build/v092-creakfix-gameplay`.

## 42: 0.92 collision-driven creak instead of suspension proxy

Further hardware feedback: grounded throttle/weight transfer still crossed the
compression threshold. Remove that detector entirely. The existing collision
solver now reports a new supported wheel contact only when incoming velocity
along a contact normal is below -2 model m/s, before the response changes it.
Tangential speed and spring compression do not count. Two event bytes are
separate from native Bike state. Audio observes each completed physics step
once; repeated service calls cannot replay the event. Takeoff still mutes the
creak, and gas does not suppress a real landing sound.

Remove the two-wheel pose history, projections and hysteresis. Normal velocity
is evaluated only at new supported contacts, using the existing exact dot
product. All 216 cases / 27,447 native states match the reference; 77 active
misses / 77 cadence violations / 189 passing cases, average 29.8216 updates/s.
All seven functional checks and 54 starts pass. Native PCM regression passes
with maximum observed audio service cost 4,296 T in its fixture. Stable 30 FPS
and physical-speaker verification remain outstanding.

The production-physics synthetic-floor regression matches 240 native/host
steps. After 120 settling steps, 60 gas steps travel 2.5873 m with zero impact
events, zero creaks and zero isolated CH2 PCM. A one-meter drop with gas held
produces impacts at steps 28 and 34 and audible CH2 PCM (peak-to-peak 12).
The event-consumer fixture rejects arbitrary grounded compression in all 32
orientations, consumes each step once (including wrap), and preserves volt,
turn, priority and pause behavior; its maximum audio service is 5,860 T.

The previous 0.92 file is replaced in place, keeping the version. ROM SHA-256:
`03bad0ac2d625603b03b40cf509e333f33411da2feadfa63ff47af20bdb5fb96`.
Evidence: `build/v092-impactfix-gameplay`, `build/v092-impactfix-checks`,
`build/v092-impactfix-audio`, `build/impact-audio-check`,
`build/riding-audio-check`.

## Controller benchmark and remaining physics work

`test/benchmark_gameplay.py` uses actual menu/buttons, deterministic per-step
inputs and natural death/finish. It records all 109 internal and 52 public
state bytes at physics return, plus clock/object state after each update.
The strict deadline is fixed and timing failures do not truncate the corpus.
Consecutive riding input samples must also be exactly two display frames
apart. The report records their frame histogram and cycle intervals separately
from active computation: an idle-wait race can skip a VBlank even when the
active computation fits. Old reports remain unchanged; their stored traces
allow this additional cadence check to be reproduced.

```sh
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.90-8m.gbc --gen build/gen-8m --out build/v091-baseline-gameplay-8m --steps 180
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.91-test1-8m.gbc --gen build/gen-8m --out build/v091-test1-gameplay-8m --steps 180 --reference build/v091-baseline-gameplay-8m/report.json
```

All 216 cases (54 levels times neutral/gas/brake/seeded) and **27,447 native
steps** match the 0.90 reference exactly in the combined raw candidate.
Timing misses improve **1,025 to 55**; wholly passing cases improve **72 to
196 of 216** in playable test1. This is still a failed 30-FPS gate.
Some physics calls still leave too little time for the
rest of the update. Exact native arithmetic and presentation optimization
remain necessary.

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


## 2026-11-18 — supported-normal landing response (0.92 landing test)

The excessive rebound is a model discrepancy, not lookup rounding: the old
free-wheel exponential factor .525334 was applied to the grounded body's
reaction. Its normal effective mass at the upright rest pose is
`1/(1/200 + .85*.85/60.5) = 59.0293 kg`. The associated exponential impulse
ratio is .885729. The extra relative normal response quantizes to 176/256;
body force and torque are corrected while original wheel impulses remain.
Support comes from the previous resolved wheel contacts, reset in `ph_init`.
Two constraints use a full-vector correction. Air remains unchanged.

Rejected research directions, retained under ignored `build/landing-solver`
at the repository root:

- Increasing normal damping without maintaining the original free-wheel
  impulse changed release behavior; a contact-force guard reintroduced gas
  and brake failures in the 8 m matrix.
- Applying the same exponential scaling to spring and damper improved coast
  but produced failures under flat acceleration.
- An explicit body ratio of 1.0 prevented some deaths but under-rebounded:
  roughly 3.45 cm versus PC 17.71 cm from 8 m.
- Frozen .885729 body-only correction without a force guard best preserved
  the horizontal 27-case behavior. It resolves two old 8 m held-gas deaths
  without introducing a new horizontal-matrix death. The 8 m/vx8/gas PC
  survivor still fails. No global matching claim is made.

The production comparison uses per-wheel contact/release/recontact clocks,
plus a two-second impact window so early micro-hops cannot hide later bounce.
For stationary 4/8 m coast, peaks change from 49.44/120.05 cm to
1.50/17.73 cm; PC gives .98/17.71 cm. At vx8, peaks become 1.38/16.69 cm.
The original-PC 40-case corpus reduces drop body position RMSE from .26159 m
to .02789 m; flat acceleration .09524→.08865 m and braking .36234→.19243 m.
Air-coast RMSE remains .03536 m. Reference math is native double; contact
substep timing is measured directly rather than rounded to render samples.

Additional ±15/±30-degree slope diagnostics found limitations: h4/vx0/held
brake at ±15 degrees now dies after about 7 seconds, although PC and baseline
survive. Several other deaths newly observed relative to GBC also occur in
PC. These are recorded separately from the successful horizontal regression.
Support latency and pose-dependent effective mass remain work for a later
physics pass; do not repeat the rejected blanket coefficient/guard sweeps.

The old Warm Up feedback controller died after the physics change. The test
retains its angle/velocity feedback and real apple/flower contact checks,
using supported-model threshold .5 and anticipation .01 (legacy .4/.025 is
still available). It earns apple step 298 and flower step 550; legacy still
finishes the frozen old model at 806. Native/HOST comparison covers 1,471
steps × 161 state bytes, including Freefall, braking and reset/gravity/turn
transitions. There is no input delay or state injection in that route.

The first bank8 C implementation incurred 450 active deadline misses across
216 controller cases. Its first exact assembly replacement reduced this to 354. A generated
256-byte low-product residue table then replaces two FRIC_W multiplications
with one rounded delta product plus its exact carry (fallback for other
exponents or signed overflow). The final result is 329 misses, 142/216 passing
cases and 29.6974 updates/s, with all 29,410 C-candidate physics states
unchanged. The generator verifies 131,072 residue pairs; the native helper
passes 768 synthetic cases including INT32 boundaries. The explicit profile
also links successfully; its correction stays disabled. ROM0 has 51 bytes
free. All 54 starts and Freefall complete their functional checks, but timing
gates report 2 and 3 misses. Other frontend/save/control checks pass. The
production-physics audio fixture still reports zero creaks during flat
acceleration, with collision sounds at the actual drop impacts. This does not satisfy stable
30 FPS. The old audio-only 0.92 ROM remains untouched; the landing candidate
is delivered as `build/elma-gbc-v0.92-landing-test-8m.gbc`.

Evidence: `build/v092-landing-check`, `build/v092-landing-pc`,
`build/v092-landing-slope-*`, `build/v092-landing-native-opt`,
`build/v092-landing-gameplay-final`, `build/v092-landing-functional-final`,
`build/v092-landing-native-final`, `build/landing-math-delta-check2` and
`build/v092-landing-impact-final`.

Final test ROM SHA-256: `fc98be152f93cdc77a171e9ed3e5e002c38c77ce6e5ecde669ea96c4643b4136`.


## 2026-11-18 — 0.93 braking and accuracy work

The 0.92 landing test does not meet the requested accuracy: stationary 4 m
peak error is 52.2248% (5.133 mm), despite its improvement over the earlier
49 cm bounce. Its first airtime error is 5.8976%; at 8 m the peak error is
.1049% and airtime error 10.1151%. The new relative-error report and strict
0.1% diagnostic bounds expose all 24 mismatches. Airtime is observed at
different contact time resolutions, so this diagnostic is not a global
trajectory fidelity score.

Braking uses the original 1000 Nm/rad spring. The old 30 Hz code reduced the
100 Nms/rad angular damper to 35 for free-wheel stability, even while rolling.
The supported wheel's inertia is .32 + 10*.3975^2 = 1.9000625 kg m^2. Its new
equivalent damper follows the PC scheduler's .0055+.0055+remainder decay
product over a frame, giving 76.8389 Nms/rad before fixed-point quantization.
Free-wheel damping remains unchanged. One new table coefficient is required.

All 27 brake fixtures across 0/±15-degree surfaces, 1/4/8 m heights and
0/4/8 model m/s initial speeds now match PC survival/death. This includes the
previous h4/vx0 incline regressions. In the 40-case original-PC corpus, flat
braking body position RMSE drops .192430→.107225 m and velocity RMSE
.390585→.205318 model m/s. This is improvement, not exact braking equivalence.
Gas, coast drop and air-coast trajectories remain unchanged. Native/HOST
comparison passes 1,471 states × 161 bytes.

Rejected bounded experiments (do not repeat without a new hypothesis):
- Pose-dependent supported effective mass worsens 4/8 m peaks to 1.530/17.855 cm
  and makes the incline braking failures earlier.
- A common-mode mass substitution suppresses the 4 m bounce and gives 10.372 cm
  at 8 m. This is not a complete coupled-mode integrator.
- Unquantized physical coefficient products worsen peaks to 1.638/18.118 cm;
  coefficient precision is not the remaining root cause.
- Continuous exponential rolling brake damping fixes the 4 m incline cases
  but introduces an 8 m downhill survivor failure; the PC discrete decay fixes it.
- Three equal 90 Hz explicit substeps improve 4 m peak to 1.060 cm (7.83% error)
  but give 16.740 cm at 8 m (5.49% error) and retain an 8 m uphill brake failure.
  This is HOST research, not a stable 30 FPS native implementation.

Evidence: repository-root `build/brake-pc-damp/report.json`,
`build/contact-substeps/report.json`; GBC `build/v093-brake-native`,
`build/v093-brake-pc`, `build/rebound-precision/RESULTS.md` and
`build/landing-accuracy-baseline`. The rebound discrepancy remains open;
0.93 test builds must not be described as a completed 99.9%-fidelity release.

0.93 test1 final controller validation: 216 cases / 29,866 steps; no runtime
correctness errors. Average 29.6955 updates/s, 341 active misses, 140 fully
passing cases. Frontend/save/volt/finish checks pass. All 54 starts and Freefall
reach their functional checks, but timing gates record 2/3 misses. ROM:
`build/elma-gbc-v0.93-test1-8m.gbc`, SHA-256 `50b02679e014668a032f34df0e1ee672ac0ab3e79dbe6956f1013e64ec294fe9`.
Evidence: `build/v093-gameplay`, `build/v093-functional`.

The PC self-comparison confirms that three equal substeps also change the
reference engine itself: 4 m rebound .879 cm instead of .983 cm, 8 m 16.796 cm
instead of 17.713 cm. Next integration research must preserve the actual
.0055+.0055+remainder schedule, not merely triple PHYS_HZ. The private 90 Hz
native cost probe fails HOST state equivalence, so its timings cannot prove
feasibility or infeasibility of a correct port. Evidence:
repository-root `build/contact-substeps/pc-schedule-report.json`.

Correction to the 90 Hz diagnostic: its reported native/HOST mismatch was
a test-layout error. HOST structs contain alignment padding; native 109 bytes
must be compared to explicitly packed fields. Replaying all 720 steps with
field packing matches exactly. The existing 376,292 T mean three-call result
is valid for that isolated 4 m coast case, but is not an optimized lower bound
or a full-game performance claim. The unequal PC scheduler remains necessary.


## 2026-11-18 — collision seams and faithful scheduled rebound model

Artificial subdivision endpoints were incorrectly treated as real polygon
corners. A radial cap near a split merged with the flat-line normal and
injected vertical velocity into horizontal travel. Length flags now mark
internal endpoints; radial caps are skipped there, and half-open ownership
prevents double normalization exactly at a join. Records remain 18 bytes.
Validation: 288 packed flat-join / 2 real-corner cases, 7038 native contact cases,
8192 native head-sweep vectors. Original corners remain active. Geometry assets
must be regenerated; stale formats are rejected by the game builder.

Frozen baselines now retain their own geometry packer as well as their own
constants generator. Current flagged geometry must never be fed to historical
cores; this otherwise invalidates the PC comparison silently.

The canonical scheduled HOST model uses .0055+.0055+remainder game-second
steps, explicit original forces, separate linear/angular units, fine physical
rest anchors and contact projection, direct tangential rolling velocity and
retained fractional position/body impulses. Linear VS 23068.672 removes force
quantization; angular units remain separate. All coefficients and fractional
accumulators are now integer Q24, not HOST floating-point shortcuts.

Independent 45-case validation passes: both wheels at all vx 0/4/8 coast drops
from 4/8 m meet 0.1% peak error, and all 45 survival/death outcomes match PC. At 4 m,
frame-sampled error is 0.089867%; comparing actual internal-substep peaks gives
0.046035%. At 8 m these are 0.007095% and0.007713%. Separate holdouts 2/3/5/6/10 m
also pass (2/3 m no hop). This fixes the measured rebound in HOST; native-port
correctness, controls, audio event aggregation and full-game 30 FPS are still
pending. It is not evidence that the old 0.93 test1 ROM is fixed.

Evidence: root `build/pc-schedule-q24` (frozen source/driver/profile/manifest),
GBC `build/rebound-q24-independent/results/report.json`,
`build/rebound-seam-verified/report.json`. The new PC substep observer is checked
bit-identical to its unobserved control. Frame-only contact timing cannot
support a 0.1% airtime claim; the observer now compares the actual substeps.

The first actual SM83 port now matches 720 canonical microsteps, including
all 109 bike bytes, 32 position-residual bytes and 16 body-force-residual bytes.
The first generic implementation averaged 2.965 million T-cycles per microstep;
banked Q24 products reduce that to 567,918, still far above the playable budget.
These are isolated physics measurements, not full-game FPS. Further exact
arithmetic optimization is in progress; no replacement test ROM is released.
Evidence: root `build/faithful-native/{c64-report,q24-report,profile}.json`.

The scheduled constants now have a reproducible generator. Its 32 coefficient
pairs match the frozen canonical model; legacy profiles remain byte-identical.
Frame time and stored linear/angular velocity units are separate metadata.
The three-substep runtime preserves a single accepted volt impulse and combines
impact audio observations. Volts expire at the first microstep strictly after
0.1 model seconds (21 intervals), while the outer held-key cooldown is unchanged.
The audio pitch table uses the angular unit time rather than the outer frame
time. The native APU fixture passes with a maximum physical-range pitch error
of 0.410 Hz; evidence: GBC `build/v093-scheduled-audio`.

### Exact native scheduled integration and optimization checkpoints

The native port now matches the frozen canonical HOST model in 9,213 states
over 46 cases / 9,167 outer steps. Each comparison includes the packed 109-byte
bike, exported pose, all 48 residual bytes, schedule phase and wheel audio
observations (214 bytes total). HOST structure padding is never compared.
The fixture ignores duplicate PyBoy return hooks caused by IRQ re-entry only
after verifying the step identifier; skipped step identifiers still fail.

Mean isolated outer-step SM83 T-cycles on this same corpus:

| Exact implementation | Mean T-cycles | Maximum T-cycles |
|---|---:|---:|
| First faithful native kernel | 1,276,345 | 2,151,216 |
| Split whole/fraction body-force sums | 1,184,110 | 2,122,564 |
| Exact wide-vector assembly | 938,516 | 1,581,548 |
| Static local arrays / cached angle | 933,221 | 1,576,100 |
| Q24 v2 table kernel | 804,817 | 1,344,344 |
| Native rider/motion and body-force orchestration | 646,466 | 1,178,936 |
| Native wheel response and narrow exact division | 631,541 | 1,169,012 |
| Native head/brake and suspension orchestration | 579,802 | 1,100,700 |

All listed stages preserve every compared state. These are physics costs,
not full-game FPS; the entire 30-Hz update/render budget is 280,896 T-cycles.
The port remains too slow for release. The old test1 ROM is not fixed by
these source changes and no new playable ROM has been released.

Evidence: repository-root `build/scheduled-native-validation/` subdirectories
`split-force`, `split-force-wide`, `static-locals`, `q24-v2`, `q24-rider-force`,
`q24-rider-force-wheel`, `q24-suspension-integrated`.
Current production HOST PC acceptance: GBC
`build/v093-scheduled-pc-acceptance/report.json` (all 45 cases pass).
The native full-game held-volt fixture passes (`build/v093-scheduled-volts`).
Frontend audio cadence and player timer cadence checks currently fail in the
slow full-game probe; standalone APU/motion tests pass. These gameplay failures
must be retested after the runtime cost is reduced, not waived.

Arithmetic-specific evidence: 41,410 Q24 quotient/fraction/mapper vectors;
52,954 wide-product/dot/torque oracle cases plus 4,112 static edge cases;
8,564 rider/motion vectors; 8,192 full-width and 8,192 interleaved native body
force cases plus 100,000 HOST interleaved cases. Q24 v2 occupies banks 481–501;
508–511 remain unused because of the verified FlashMaster read failure.
The table format and constants hash are checked by the builder.

Precision study, not integrated: nine variants across 45 independent and 45
holdout cases retained all 810 survival outcomes. A 14-bit normalized coefficient
mantissa passed the sampled peak gates; 12/16/20-bit mantissas and fixed Q16
failed at least one gate. Native speed benefit is unmeasured, so this does not
justify replacing the current exact Q24 implementation. Evidence:
repository-root `build/scheduled-precision-budget/experiment-report.json`.

### Further exact kernels and rejected velocity-unit reduction

Exact Q10/Q14 wide reductions and zero/unit-axis paths, plus the shared packed
circle integrator, reduce the 46-case mean to 528,884 T (maximum 991,888), with
all 9,213 states unchanged. The wide-math oracle passes 115,025 cases per
implementation and 4,112 IRQ-enabled vectors; circle motion passes 3,970
independent packed-state cases. Evidence: root
`build/scheduled-native-validation/q24-axis-circle`,
`build/scheduled-wide-physical-fastpaths`, `build/scheduled-circle-integration`.

A narrow-displacement spring-torque path retains the complete 48-bit products
and keeps the full-width fallback. It saves 10,362 T/outer on the full corpus;
92,206 independent vectors pass. The mean is 518,521 T, but the worst sampled
step grows by 840 T due to dispatch overhead. Evidence:
`build/scheduled-spring-fastpaths`. Q24 narrow dispatch retains v2 tables and
all quotient/fraction/saturation side effects; its 61,787-case oracle passes,
and it saves 17,093 T/outer on its paired full-state corpus. These independent
savings require a combined integration run before reporting a combined cost.

Linear velocity-unit alternatives .176/.088/.044 were tested against the
unchanged .352 reference, preserving .022 angular units and original intervals.
The two smallest fail rebound gates. .176 passes the 90 PC cases but improves
native mean cost only 1.03%; one braking case's velocity RMSE grows 39.4%
(.005086 to .007090 m/model-second), and two gas deaths shift one frame earlier.
Rejected: keep .352, with no accuracy trade for that small speed gain. Evidence:
root `build/scheduled-velocity-precision-feasibility/experiment-report.json`.

The acceptance harness now records complete trajectory error as well as peaks
and explicitly gates first airtime at 0.1%. All 45 cases pass the existing peak
and new airtime gates; coast 4/8 m at vx0/4/8 retains PC contact release and
recontact times (floating-point timestamp noise only). Body trajectory RMSE
for the nine flat held-brake cases improves from .193283 to .019711 m, velocity
.397715 to .029972 m/model-second against baseline b2c314b. The ±15-degree
braking position errors remain .133864/.053708 m respectively; this is not a
global 99.9% trajectory match. Values pool squared errors over common live
samples, with each model seeded into its matching PC reference. Evidence: GBC
`build/v093-rebound-airtime-acceptance/report.json` and
`build/v093-scheduled-pc-acceptance/braking-trajectory-errors.json`.

Full-game spring probe SHA256
`2e4fdd6f7f6f936cfa95d4a684e3efbd04d94b8ff7e9919e1d88c957d0e39224`
passes functional checks for all 54 starts and Freefall (435 updates, maximum
speed component 51.780 model m/s). No observer errors or graphical invariants
fail. Timing gates correctly FAIL: 1,596/439 overruns in the respective runs.
Freefall advances every 4–7 display frames instead of two. This probe is not
a completed release. Evidence: GBC `build/v093-scheduled-all-starts/run.json`
and `build/v093-scheduled-freefall/run.json`. The Freefall speed report now
uses stored velocity units, independently of the outer frame interval.

### Combined diagnostic checkpoint

Bank9 contact filtering proves unambiguous far/near distances without a full
fine projection, retains exact arithmetic in the boundary band and compacts
the packed contact list. 29,040 native/C/Python cases and an exhaustive
65,536-length shortcut proof pass; every full-corpus case improves. Evidence:
root `build/scheduled-contact-staging`.

The final combined narrow Q24, spring and contact-filter run passes all 46
cases / 9,213 states against the frozen canonical HOST. Mean cost is
**491,599 T/outer**, maximum **942,896**; the complete frame budget remains
280,896. Evidence: root
`build/scheduled-native-validation/q24-final-integrated/report.json`.

Latest diagnostic: GBC `build/elma-gbc-v0.93-rebound-test-8m.gbc`, SHA256
`d4838a7e747c246c38a931e28ce1197329b51218bdceb52056837dd09d2a8561`.
8,388,608 bytes, MBC5+RAM+battery, 32 KiB RAM, banks 508–511 all FF.
All 54 starts and Freefall retain their functional/graphics checks with zero
observer errors; held/released volt controls pass. Timing gates fail with
1,605 and 439 overruns respectively. Freefall's 434 measured entry intervals
average **13.43 updates/s**, range 4–7 display frames per update. The all-start
interval stream includes level loading and is not a gameplay FPS statistic.
Evidence: GBC `build/v093-rebound-{all-starts,freefall,volts}`.
This is a slow rebound-corrected diagnostic, not a completed 0.93 release or
a stable-30-FPS build. Do not confuse it with the old test1 ROM.

## 2026-11-18 — 0.94 speed and numeric-limit audit

Version milestones are separated: 0.93 retains rebound correction, 0.94 covers
high-speed PC comparison and numeric-limit diagnosis, 0.95 addresses runtime
cost, and 0.96 is joint fidelity/full-game stable-30 acceptance. This experiment
changes no integration interval or velocity unit and adds no input buffering.

**Accepted correction:** use `ceil(110*WS)` for the scheduled torque cutoff,
25242 instead of 25241. A strict integer comparison then retains the last
representable value below the original PC 110 rad/s threshold. Both facing
signs are tested. At raw ±25241, the old GBC wheel peak was 109.997753 rad/s
against PC 120.310253; corrected GBC reaches 120.308544. Six boundary cases
have at most 0.001421% peak error and pass a 0.1% gate. The retained old report
fails precisely the two ±25241 unbraked cases (negative control). Brake still
overrides gas. Legacy profiles retain their original integer constant.

**Audit:** `test/check_speed_limits.py` freezes the sources, builds unchanged
and instrumented HOST copies, and uses the original PC integrator with equal
quantized initial states. It observes eleven clipping/wrapping sites and
checks every packed field against the unchanged HOST. The first 86-case run
included only opposing-throttle flat fixtures; review caught this coverage gap.
The final 122-case matrix tests both facing directions at signed 40/44/55/
57.12/60/80 model m/s, coast/gas/brake, flat/±15° high-speed impacts and angular,
brake and volt boundaries. These are synthetic seeds with initially zero wheel
spin/contact history, not completed routes. PC runs native double, not x87.

Final evidence under `console/gbc/build/`:

- `v094-speed-audit-baseline`: retained old-cutoff negative control (86 cases).
- `v094-speed-audit-final`: 122 PC comparisons, 3,187 exact instrumented/control
  states; all six gas-cutoff gates pass. Sources/constants/library hashes and
  complete traces are retained. 74 cases encounter a clamp/wrap.
- `v094-native-speed-final`: the exported 122 cases, 3,186 exact 214-byte states,
  3,064 raw core steps, zero differences; mean 492,324.72 T, max 997,540 T.
- `v094-native-regression`: original 46 cases, 9,213 exact states; unchanged mean
  491,599.008 T and max 942,896 T. The corpus-specific means are not directly
  comparable performance improvements.
- `v094-rebound-gates`: all 45 existing PC cases pass; first rebound and actual
  contact-airtime retain their strict 0.1% limits.

Measured events in the final synthetic matrix:

| Instrumented operation | Cases with a limit | Clipped/wrapped operations |
|---|---:|---:|
| Body omega | 5 | 19 |
| Free-wheel omega | 1 | 20 |
| Rolling omega | 40 | 4,465 |
| Brake relative omega | 38 | 454 |
| Brake torque | 28 | 402 |
| Spring moment input | 10 | 178 |
| Volt start addition | 5 | 5 |
| Volt release / residual addition | 0 | 0 |
| Q24 / wide signed32 result | 0 | 0 |

These are events within this matrix, not normal-play incidence rates. Release
and residual volt arithmetic remain vulnerable even though this matrix did not
trigger their wrap. Ordinary signed32 additions are not all covered by the two
result-saturation counters; zero counters do not prove general overflow safety.

**Unresolved behavior:** int16 omega spans approximately −142.799666 to
+142.795308 rad/model-second. Rolling first clips at about 57.119023 model m/s,
without clamping translation. Relative brake omega clips at ±71.395475 rad/s;
final torque at −8192/+8191.75 Nm. Spring moment clips at about ±2 m²; volt
addition can wrap at initial positive omega raw 30014 (negative −30015).
The 32-bit linear endpoints near ±93,091 model m/s do not solve these earlier
limits. Widening angular storage alone would leave brake/spring clamps intact.
No lowering of precision or extra saturation was accepted to conceal them.

There are five survival mismatches: +60 m/s flat braking impact is a GBC core
death with PC survival; four ±120/±140 rad/s body-spin fixtures hit the separate
GBC 3 m stretch guard with PC survival. This guard exists in production
`play.c`; original PC has no matching stretch death. The audit labels the cause
explicitly. Native verification invokes raw `physics_step`, without that runtime
guard or normal input cooldown, and therefore establishes core equality only.
It must not be cited as native gameplay-termination parity. The audited volt
inputs are single pulses, so cooldown does not change these fixture inputs.

**Built diagnostic:** `build/elma-gbc-v0.94-speed-test-8m.gbc`, SHA-256
`b3727b3e8b31c03b1ae327c60e33a9d0b4370e208801b32d3b5986b4acbcb240`.
8,388,608 bytes, header 1B/08/03, forbidden tail banks 508–511 all FF, splash
and menu 0.94. `v094-frontend` and `v094-volts` pass. `v094-all-starts` and
`v094-freefall` pass functional/graphics checks with no observer errors, but
strict timing still fails with 1,605/439 overruns. Freefall remains 13.43
updates/s (4–7 display frames/update), maximum component 51.78005 model m/s.
`v094-players.log` records the timer-cadence assertion failure; later save-suite
checks did not execute. No full save-suite or hardware acceptance is claimed.

Reproduce with `make check-speed-limits` and the usual resource paths. This
creates a fresh evidence directory, enforces the repaired gas cutoff, then
checks the exported seed matrix against native code. Numeric-limit findings
remain findings even when these two gates pass. Next fidelity work must address
angular/torque range and the distinct impact failure; 0.95 optimizations must
preserve exact state regressions and 0.96 must still meet both final requirements.

## 2026-11-18 — 0.96 exact native checkpoint and wider-physics research

User moved ongoing work to 0.96. Both original-PC fidelity and full-game stable
30 FPS remain required; no completed release is claimed. 0.95 performance work
continues here rather than being packaged as a separate release.

### Integrated exact changes

1. Suspension submits signed40 force units and the complete Q24 fraction using
   bank8 register entries. This removes stack packing/reloads without changing
   sums or residuals. Alone: 491,599.008→480,467.366 T on the default corpus;
   every case improves, bank8 shrinks 245 bytes, bank0/RAM unchanged.
2. Q24 v3 omits redundant sign bytes of short quotients and uses the available
   pages for direct −255..−1 products. Alone: 489,573.935 T; bank0 kernel grows
   40 bytes, table payload grows 31,488 bytes within the same banks481–501.
   Builder requires v3; table and assembly must migrate together.
3. Wide dot products initialize the signed56 accumulator with the first full
   signed48 product instead of zero-filling then adding. Alone: 491,452.456 T,
   maximum 936,848 T. Small mean saving, useful on wide projections; no narrowing.

Combined default46: **478,294.9296 T mean**, **920,384 T max**, all **9,213 states**
exact against frozen 0.94 HOST. This is **2.706%** mean cost reduction, still far
above the 280,896 T entire-frame budget. Combined speed122: **480,030.0601 T mean**,
**973,196 T max**, all **3,186 states** exact. Individual savings are not summed
as a substitute for these integrated measurements.

Evidence in repository-root `build/`:
`v096-suspension-speed`, `v096-q24-speed`, `v096-accumulator-seed`, and
`v096-integrated/{native,speed}`. Full-width mathematical oracles pass:
11,572 signed32 dot cases, 8,192 force accumulator vectors, 48,958 production
Q24 cases, and 48,964 synthetic signed Q24 cases. The signed generator explicitly
asserts INT32_MIN, zero and INT32_MAX coefficients are included. An initial
signed test changed only unused coefficients at those three special positions;
that inadequate coverage was corrected before acceptance. Evidence:
`v096-accumulator-seed/oracle`, GBC `build/v096-force-registers`, root
`v096-q24-integrated-oracle` and `v096-q24-integrated-signed-final`.
Durable tests `check_physics_dot32.py`, `check_force_registers.py` and
`check_q24.py` are included in `make check-scheduled`.

Full ROM: GBC `build/elma-gbc-v0.96-test1-8m.gbc`, SHA-256
`0c81315309db968e42842319c095f94dd64e3d5c57ac0823441c1cc78f5163d6`.
8,388,608 bytes, MBC5/8MiB/32KiB header1B/08/03, banks508–511 all FF.
Menu/splash show0.96. Menu and volt checks pass; all54 starts and Freefall pass
functional/graphics checks, with no observer errors. Timing correctly fails:
1,609/438 deadline misses (all starts/Freefall). Freefall intervals are
4frames×285, 5frames×126, 6frames×23 → **13.5858 updates/s**, versus13.43 before.
The all-start stream includes loading and is not an FPS statistic; its deadline
count does not improve in this run. Player/save timer-cadence remains unresolved;
these runs do not claim a complete save-suite or physical-cartridge pass.
Evidence: GBC `build/v096-test1-{frontend,volts,all-starts,freefall}`.

### HOST-only widening and impact diagnosis

`build/v096-wide-physics` freezes the old and proposed source, ctypes ABI,
constants, patch and full PC traces. Int32 omega/saved volt omega, wheel torque,
brake delta and spring input preserve old physical precision and schedule.
All122 frozen baseline traces exactly reproduce 0.94. Of122 cases,74 change;
all six gas-cutoff gates and all45 strict rebound cases pass. +80m/s coast wheel
peak improves from clipped142.799666 to200.001461rad/s (PC200.000058).
All11 observed intermediate ranges fit int32 in this matrix, with3,074 exact
probe/control states. Raw wheel omega reaches−47,387/+47,420, torque
−94,312/+94,206 and spring input−51,053/+51,045. Separate volt release/residual
checks retain both signs of35,514/34,826 without int16 wrapping.

**Do not integrate widening alone:** survival mismatches worsen5→6; −60m/s flat
braking impact newly dies, while the old +60 impact and four extreme-spin
stretch-guard mismatches remain. Native migration is substantial: circle22→24
bytes, Bike109→119, suspension40→44, packed verification214→224. All assembly
loads/stores, offsets, coefficient return widths, torque ABIs and observers must
change together. The prototype deliberately rejects native compilation.

`build/v096-impact-cause` identifies the additional error: reaction table clamps
wheel/body distance to about0.359m; original PC uses actual1/d². At frame15,
substep42, front separation is0.278m (+60) /0.281m (−60), and the old reaction
is low by40.0%/38.7%. HOST fallback for table index<16 computes
`trunc(tq * 2^22 / (kx*kx + ky*ky))` before the unchanged C_REACT coefficient.
With the wide model, both impact signs now survive; survival mismatches6→4.
Only four of122 trajectories change. All45 strict rebound result JSONs are
identical to prior wide results. Common-live-prefix body position RMSE improves
+60: .038743→.001236m; −60: .125231→.009357m. This is a local measured improvement,
not global99.9% fidelity. Full-reciprocal-everywhere also leaves4 mismatches but
changes73 cases; retain the smaller localized candidate for further validation.

Root `build/v096-narrow-recip` tests the fallback without widening: it retains
all five old survival mismatches, including +60impact. That partial change is
not integrated. Four extreme-spin mismatches are the separate production3m
stretch guard, absent in original PC; removing it requires checking rendering,
geometry and numerical bounds, not merely changing the expected test result.
Native reciprocal calculation and its near-zero/saturation contract remain
research prerequisites; neither HOST correction is in the test1 ROM.

A standalone native close-reaction helper is now implemented and retained as
`test/fixtures/reaction_division.s`, with `test/check_close_reaction.py`. It is
**not linked into test1**. ABI0 takes signed32 torque and unsigned32 distance²,
computes the complete54-bit numerator divided with truncation toward zero,
and saturates only the final signed32 result. The mathematical kernel defines
zero divisor→0; eventual gameplay integration must preserve the previous
zero-distance fallback instead of calling it for zero separation.
The14,114-case independent oracle passes arithmetic, stack/argument preservation
and mapper checks. Size243bytes in bank8, zero ROM0/static RAM, eight extra peak
stack bytes. Captured impact inputs cost18,244/18,260 T-cycles; range344–20,932 T.
Evidence: root `build/v096-reaction-division` (proof, ABI and original results),
`build/v096-close-reaction-retained` (relocated durable fixture). This establishes
the primitive only, not native widened-physics or full-game correctness.


## 2026-11-18 — 0.96 test2 native widening and compression correction

The combined correction is now linked into the playable 8 MiB ROM. This
supersedes the preceding HOST-only integration status; retained test1 remains
unchanged. The former division fixture is promoted to
`src/physics_reaction_division.s`, and its independent oracle tests that exact
production file. Widening alone and narrow-only reciprocal remain rejected.

Native migration covers circle24/Bike119/workspace44, full-width brake and free/
rolling torque ABIs, saved volt omega, body/spring updates, all affected assembly
loads/stores and full 224-byte state verification. Audio narrows only at its
existing bounded API. A ROM constant publishes the private physics state size
for controller observers; older ROMs retain the old-size fallback.

The first widened speed run exposed a real native/HOST mismatch at
`volt--32760`, outer step10, in the rider/head position. The seat-relative
subtractions still used SDCC's 16-bit integer promotion while HOST used32 bits.
Explicit signed32 inputs fix it without changing the HOST trajectory. The
final46-case suite matches **9,213 states**, mean **481,027.6073 T**, maximum
**925,724 T**. The122-case native suite matches **3,179 states**, mean
**485,619.6847 T**, maximum **1,068,264 T**. No discrepancies are waived.
These are equality against the matching integer HOST, not original-PC identity.

Original-PC audit: **3,173 instrumented/control HOST states** match, no numeric
range hits in this matrix, all six cutoff gates pass, all18 impact survival
results match. The ±60m/s flat braking impact deaths are resolved; four
±120/±140rad/s body-spin outcomes still differ due to the production3m stretch
guard. All45 strict rebound/braking fixtures pass 0.1% peak/airtime gates. At
+80m/s coast, wheel peak is200.001461rad/s versus PC200.000058. Original PC runs
native double, not Windows x87; these fixtures do not prove global99.9% fidelity.

Durable low-level regression gates now include 14,114 exact production close
quotients, 1,592 full-width motion cases, 1,500 independent brake fixtures and
1,200 wheel fixtures (2,400 native free/roll calls). Guard, mapper and state
checks pass. Wheel parity deliberately shares arithmetic primitives with its
C reference and initializes motion residuals to zero; the complete native
state suites cover evolving residuals. The standalone reaction bridge also
passed3,863 threshold/zero/torque cases during integration.

Full ROM SHA-256:
`b5e5d2baacd43bc8857d954811addf323c39f8477e02d0e40459f14734ad1e5a`.
Path: GBC `build/elma-gbc-v0.96-test2-8m.gbc`, directly in build/, version0.96
on menu/splash,8,388,608bytes, header1B/08/03, tailbanks508–511 allFF.
ROM0 has451bytes free. No physical-cartridge acceptance is claimed.

Menu and volt tests pass. All54 starts and full no-input Freefall pass functional
and graphics checks with zero observer errors. Strict timing remains failed:
1,615/438 deadline misses. Freefall has4frames×282,5frames×126,6frames×26,
**13.5432 updates/s**, slightly below test1's13.5858. The player/save test now
continues functional checks after recording cadence failures and exits nonzero
at the end. Names, exact clock text/minute rollover, first/slower/tied/improved
records, frozen result panels, retry, isolation and battery reload pass. Finish
uses the existing explicit flower-contact fixture. Timing fails36 publications/
35 visible changes in180 display frames,5-frame intervals and1,770 idle misses;
none of the original timing thresholds was relaxed.

The controller benchmark needed its own scheduled-profile migration: its old
single-ph_step observer rejected the second microstep. It now observes nested
core calls and validates all three inputs, with the volt bits present only on
the first microstep, including early death and duplicate IRQ hook handling.
The final controller-only216-case corpus completes **30,490 outer steps**, zero
observer/correctness errors,119-byte private states. All216 timing cases fail;
30,468 updates exceed the unchanged budget, worst1,101,180T in level40 gas.
This is functional ROM coverage, not a completed-all-levels or PC-parity claim.

Evidence (repository-root paths):
- `build/v096-wide-integrated/{native2,speed2,rebound2,close,move,wheel-regression,brake-regression}`
- `console/gbc/build/v096-wide-speed-audit/report.json`
- `build/v096-test2/{frontend,volt,all-levels,freefall,gameplay-scheduled}`
- `console/gbc/build/v096-test2/players/report.json`

Next acceptance work remains substantial: reduce the full corrected model's
runtime cost, resolve the four extreme-spin/guard discrepancies with geometry
and numerical validation, then validate cartridge timing. Stable30FPS and
accuracy remain simultaneous requirements. Test2 is an integrated diagnostic,
not a final0.96 release.

## 0.96 test3 airborne spin comparison

The 3 m wheel-axis guard caused all four premature test2 deaths. A 4 m
candidate recovered the first 12 steps but still killed the +140 rad/s
controlled case a step early. The original PC model reaches 7.081 m on
its final live step, motivating the 8 m wheel envelope in test3. The
rider limit stays at 3 m. The production change only affects the runtime
coordinate guard.

The extended controlled tests match survival through 120 updates at ±120
and death on update 23 at ±140. Late ±140 poses still diverge. The distinct
full-ROM test seeds rotation during a moving Freefall descent and compares
with the original PC engine seeded from the actual ROM state. Both pass the
old cutoff and publish the wheel sprites correctly. The strict death-step
check still reports a one-update difference in each ±140 case.

Local evidence under GBC build includes `v096-test2/spin-baseline/report.json`,
`v096-test3-spin-guard-pc/report.json`, and `v096-test3/spin-final/report.json`.
Ordinary Freefall still takes 4–6 display frames per update. On the existing
test2 controller corpus, physics occupied 90.9% of active update cycles
(weighted across 30,490 updates). The three substeps per update run the
suspension, contacts and rider dynamics on each substep.

## 0.96 test4 rotation accuracy

Freefall test3 at update 260 shows angular drift while both wheels are airborne.
For ±140 rad/s, Q10 lever rounding contributes roughly 0.006 rad/s of error
in the first internal update. The suspension amplifies it on subsequent
updates. Whole-step saturation and out-of-level queries occur later.
In a replay of a frozen pose, rounding the body phase alone matched both PC
death updates. In the rebuilt game that change still missed both. Q12 levers
and nearest-phase sampling together pass the original four Freefall cases.
The same build fails the −140 case starting at update 240 by one update.
The strict test accepts an alternative `--seed-step` for independent repeats.

The original desktop reference checks each wheel before movement, the head
after movement and the frame against the camera brush. Encoding these limits
in each level descriptor passes 1,008 PC probes and 16 exit trajectories.
The 8 m wheel guard still applies after the complete update.

The complete test4 ROM passes the 45 rebound/braking cases, all 122 final
survival outcomes and all 54 start checks. Freefall averages 12.845 updates/s
(204 four-frame intervals, 179 five-frame, 50 six-frame and one seven-frame).
The 54 starts and full descent miss 1,591 and 439 deadlines, respectively.
Reports are under `build/v096-test4/{spin-final,spin240-final,level-exits-final,speed-final,rebound-final,native-final,native-speed-final,all-final,ff-final}`
relative to this directory.

## 0.96 test5 rotation and rebound

Across Freefall injections at five different updates, changing the sine
lookup or carrying the torque remainder without feeding it back into motion
left inconsistent death timing in HOST replays. Full Q18 wheel levers plus
fractional angular velocity in both body-point velocity and phase integration
matched the ten PC ±140 outcomes. The SM83 implementation retains the full
four-product damping sum through cancellation, then shifts and saturates once.

The first integrated candidate introduced a 0.56% peak rebound error on a
symmetric 4 m drop. Rounding the summed spring moment before the torque
coefficient removed the spurious pitch. Both wheels now differ from the
PC's 9.82939 mm peak by 0.00883 mm. The full 45-case rebound/brake suite
passes the prior criteria. The eight synthetic extreme volt cases which
saturate are listed in the speed audit.

Test5 ROM SHA-256 is
`4e10759c014da913bf67f1547da74e0ca1bcdf00aa72df1de841e65183317db0`.
All 20 seeded Freefall comparisons pass their strict survival and death-step
checks. The controller runs observed one impulse in each direction, at
relative updates 5 and 41. During the 70-update windows their maximum angular
errors were 0.0148° (left/right) and 0.0424° (right/left). The five extreme
start poses give a worst near-terminal angular error of 15.75°. Remaining
trajectory divergence and full-game cycle cost are independent acceptance
items. No-input Freefall recorded 29 four-frame intervals, 323 five-frame,
73 six-frame and 9 seven-frame intervals, averaging 11.614 updates/s.
The 54 starts and full descent missed 1,590 and 439 display deadlines.

Reproduce both controller routes, the five injection points, high-speed
survival and native arithmetic parity with `make check-speed-limits` and
the matching resources. Test5 reports are under
`build/v096-test5/{controller,spin-240,spin-250,spin-260,spin-270,spin-280,speed-verified,rebound-final,native-final,native-speed-final,level-exits-final,levels,freefall}`.

## 0.96 test6 rider constraint projection, isolated against test5

The native rider limit skips both Q14 dot products when the world-space
rider displacement falls inside a 101 × 101 box centered near body-local
(0,416). The exact sine and cosine high bytes select the box. On a miss,
the helper reuses its wrapped, byte-shifted and saturated deltas to compute
both original dots. The 46-case test5 corpus takes the shortcut on 23,175 of
27,478 substeps (84.3%). The change adds 39 linked bytes in bank 8 and
uses stack temporaries.

The integer proof checks both turns and all 65,536 interpolated phases. Linear
seat and side bounds and a convex upper bound on the rounded ellipse radius
cover every point in each box. The minimum seat clearance is five units.
A separate native fixture passes 38,500 cases, including 21,867 wrapped
coordinate differences and 3,494 cases with at least one saturated delta.

| Frozen native suite | Compared states | Test5 mean T | Fused mean T | Test5 maximum T | Fused maximum T |
| --- | ---: | ---: | ---: | ---: | ---: |
| 46 scheduled cases | 9,210 | 537,506 | 525,848 | 1,030,792 | 1,030,148 |
| 122 speed cases | 3,170 | 545,234 | 534,592 | 1,125,796 | 1,124,860 |

Every compared state matches the frozen test5 HOST. A separate guard that
recomputed the deltas on a miss raised the two maxima by 2,012 and 1,632 T
respectively. Retaining the fused version removes that extra work.
Evidence is in `build/test6-rider-opt/{final,final-speed,final-proof,vectors}`.

## 0.96 test6 — integrated physics timing

The comparison uses the shipped test5 and test6 ROMs, identical simulation
steps and controller inputs. The 8 MiB test6 SHA-256 is
`9a6a84b44140158c1ceed5803d5050cadf58fc2e91e62b38850833032e1654ce`.
The hardware deadline is 280,896 SM83 T-cycles per complete active update.

| Check | Frozen test5 | Test6 |
| --- | ---: | ---: |
| Freefall physics updates/s from display intervals | 11.614 | 17.873 |
| Freefall complete active update, mean / worst T | 671,566 / 938,636 | 425,960 / 663,348 |
| Freefall active updates over budget | 439 of 439 | 439 of 439 |
| 12 controller routes, active updates over budget | 1,934 of 1,934 | 1,933 of 1,934 |
| 46 native physics cases, mean / maximum T | 537,506 / 1,030,792 | 321,678 / 657,704 |
| 122 native speed cases, mean / maximum T | 545,234 / 1,125,796 | 320,999 / 734,384 |

The strict real-ROM tests report timing failures. Their functional checks
pass for all 54 course starts, the complete Freefall descent and all 1,934
updates in the four controller scenarios on Warm Up, Twin Peaks and Freefall.
The native comparison matched 12,380 complete 228-byte states against the HOST
compiled from test5. The 20 raw-seeded Freefall comparisons and both
controller-only PC rotation tests reproduce the test5 results.

The following measurements isolate changes on different frozen checkpoints.
The integrated results above account for overlap.

| Experiment retained | Evidence |
| --- | --- |
| Keep Q24 input bytes and partial products in registers, use HRAM for the exact fraction | Mean saving of 13,205 T per update on the test5 native corpus. Production and signed synthetic arithmetic checked quotient, fraction, saturation and mapper restoration. |
| Combine suspension forces directly and reuse byte multiplication rows | 51,068 T mean saving on the same corpus before sharing the pose lookup. The four-term damping moment keeps the full-width fallback. |
| Cache empty head sweeps and extract terrain grid coordinates directly | Complete Freefall physics entry-to-export cost fell by 35,547 T on average in isolation. |
| Reuse exact phase geometry for head, rider and suspension | Lookup generation checks every signed Q14 input. An independent native oracle checks all 65,536 phases, both facings, all anchors and head coordinates. A first C-only lookup took 8,376 T per call in the head fixture. The retained assembly path averages 4,042 T and also supplies the rider and wheel terms. |
| Fast scheduled movement and body rotation | Full intervals add the fractional velocity nibble directly. The remainder interval combines byte quotients before its single floor operation. The body-point velocity keeps the whole signed residual through rounding and saturation. |
| Fuse body impulse bookkeeping and Q14 projections | The impulse helper saved 22,340 T per update on the 20-case mixed-control fixture. The projections saved 12,997 T on a subsequent matched 46-case checkpoint. |
| Reshape the integer product and division tables | Separating the two bytes of 8×8 products into pages saved 5,506 T mean and 24,540 T worst on the matched intermediate physics fixture. The accumulator's signed division by 20 now uses a bytewise quotient/remainder table in bank 15. |
| Take the free-wheel path as soon as contact is ruled out | Isolated mean saving of 8,878 T. The before/after native fixtures matched all 238 bytes including both landing flags and all four normal components. |

Full-game reports and state traces are under `build/v096-test6/`. The
`freefall` report measures hardware-frame spacing, and `fullfall` and
`controller` measure active work and compare gameplay traces. The native
fixtures exclude rendering and VBlank waits. The 8 MiB cartridge keeps
mapper 1B/08/03 and leaves banks 508–511 erased.

## 0.96 test7 — complete controller and timing comparison

The same four button sequences (neutral, gas, gas followed by braking, and
seeded mixed controls) ran on all 54 levels using each shipped cartridge.
Each route ends at death, finish or 100 updates. All three ROMs completed
19,885 updates. Aggregate updates/s uses the sum of the measured intervals
between input samples divided by their total elapsed emulated display time.
The denominator excludes setup and the unobserved interval after a route ends.

| Same controller routes | Test5 | Test6 | Test7 |
| --- | ---: | ---: | ---: |
| Aggregate updates/s | 10.989 | 15.748 | 16.830 |
| Mean complete active update (T) | 708,762 | 468,659 | 442,663 |
| Maximum complete active update (T) | 1,108,276 | 788,320 | 796,636 |
| Active updates above the 280,896 T deadline | 19,878 | 19,266 | 18,750 |
| Entire routes meeting the 30 Hz gate | 0/216 | 1/216 | 1/216 |

Test7 improved mean active work against test6 on 213/216 routes. Its largest
single update was Sink, seeded controls, update 78. Of its 796,636 T,
631,908 T went to physics. The slower Shelf Life braking route averaged
12.345 updates/s. The complete no-input Freefall run recorded 318 input
intervals of three display frames, 108 of four and seven of five, averaging
18.200 updates/s. All 439 complete active updates exceeded the deadline.

| Isolated experiment against test6 | Outcome |
| --- | --- |
| Cache wheel contacts in 256-unit squares | Waiting for five consecutive visits reduced the cost of classifying squares a fast wheel leaves immediately. A square with multiple possible surfaces or a possible endpoint keeps the full iterator. The adopted version saved 9,236 T on average over 1,934 controller updates. It added 1,194 T to the mean of the synthetic high-speed suite and raised the individual peak on seeded Warm Up by 18,144 T. |
| Reuse empty head sweeps inside nonempty terrain leaves | Inspect every wheel-expanded bounding box before marking a 1 m tile clear. A sweep can use the result only when both endpoints lie inside. Alone this saved 6,401 T per update on the complete Freefall run. All 8,192 native capsule checks and 17 queries at tile and cell boundaries passed. |
| Combine four damping products while retaining their fractional bits | Accumulate signed24 inputs directly. A wider operand transfers the current signed sum to the full nine-byte accumulator and resumes at that operand. Restarting from the first product made some wide calls 6,004 T slower. The retained code saves 26.4% on the mean cost of the moment in the standard native suite. Its dedicated cartridge passed 7,336 integer and bank-restoration checks. |

Together these changes reduced native physics from 321,678 to 303,770 T
on average in the 46 ordinary scenarios and from 320,999 to 310,270 T in
the 122 speed scenarios. The maxima were 651,832 and 728,012 T. All 12,380
packed 228-byte states matched the frozen test5 HOST. Independent PC checks
passed all 45 rebound/braking scenarios and reproduced all 20 previous
extreme Freefall spin comparisons. All 54 normal starts passed their
functional checks.

Reproduce from this directory using the generated 8 MiB assets and the
matching ROM and symbols in `build/`:

```sh
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.96-test5-8m.gbc --gen build/gen-v096-test4-8m --steps 100 --out build/v096-test6/baseline-catalog
.venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.96-test7-8m.gbc --gen build/gen-v096-test4-8m --steps 100 --out build/v096-test7/catalog --reference build/v096-test6/baseline-catalog
.venv/bin/python test/freefall.py --rom build/elma-gbc-v0.96-test7-8m.gbc --gen build/gen-v096-test4-8m --out build/v096-test7/freefall
```

The timing tests return a failing exit status for deadline misses and write
their reports and traces. Test7 SHA-256 is
`3fb8c2c232f6e7c3bee4bda6eabb5d520670983e3bc24ed17113d3924166e15f`.
The public ROM reproduced byte for byte on relink. Its last four banks are
erased, and its header declares MBC5 with battery, 8 MiB ROM and 32 KiB RAM.

## 0.96 test8 — grounded contact and vertex costs

The real test7 cartridge identified different costs on different routes.
Shelf Life braking spent 299,304 T per update processing its two wheels.
On Haircut update 98, the head sweep alone spent 249,564 T. All six
candidate capsule tests there projected beyond the endpoint of a terrain
edge. Test8 preserves contact order and the strict wheel and head radii.

| Matched workload | Test7 | Test8 |
| --- | ---: | ---: |
| 216 routes, aggregate updates/s | 16.830 | 17.341 |
| 216 routes, mean / maximum active T | 442,663 / 796,636 | 427,400 / 817,412 |
| Complete active updates exceeding the deadline | 18,750 / 19,885 | 18,698 / 19,885 |
| Complete Freefall descent, updates/s | 18.200 | 18.499 |
| Complete Freefall active T, mean / maximum | 420,767 / 647,724 | 413,750 / 622,208 |
| Shelf Life braking, mean active T | 609,394 | 574,897 |
| Haircut neutral, update 98, active T | 792,684 | 664,924 |
| Sink seeded, peak active T | 796,636 | 691,012 |

The mean active time improved on 215/216 routes. Bumpy Journey neutral
took an additional 2,590 T per update on average. The highest active cost
moved to Double Trouble with gas on update 71. On that same update physics
fell from 533,632 to 498,028 T. Scrolling rose from 11,840 to 150,500 T and
background preparation rose from 81,328 to 108,076 T. The earlier and
later images had identical physics, camera and game-clock traces in that
comparison. The two-display-frame budget remains 280,896 T.

| Physics change | Verification |
| --- | --- |
| Reuse fine contact distances when checking wheel penetration | 832 of 853 observed pushout calls on the Shelf Life braking route left the wheel untouched. The resolver can prove some pushes unnecessary and computes both filters against the original center. A real first push updates the wheel and its other contact before recomputing the second push. An independent oracle passed 10,448 inputs including reject, reorder, signed extremes and sequential pushes. |
| Compute distance to one terrain vertex in its outward quadrant | When the entire swept path projects beyond one endpoint, test that vertex directly. The general segment path handles all other configurations. The final isolated cartridge passed 12,455 circle/segment vectors, including 167 calls captured from the real route and exact tangencies. The combined cartridge spent 145,920 T on the Haircut head check at update 98. |
| Compute the rider's exact signed16 spring and damper products from byte tables | A low-byte remainder rank and a high-byte threshold encode the carry into the rounded integer. The tables use 7,168 bytes in bank 2. Wider inputs still use Q24. A cartridge fixture tested 262,176 results against the full multiplier, including every signed16 value for both coefficients in both phases, wide endpoints and bank restoration. |

Each of the 19,885 controller updates matched the frozen test5 at physics
return and at the end of the update. The native fixture additionally
compared both landing flags and all four support normal components. All
12,380 states of 238 bytes matched the test5 HOST. The 46 ordinary fixtures
averaged 295,006 T with a maximum of 625,892 T. The 122 speed fixtures
averaged 304,273 T with a maximum of 713,128 T. All 45 PC rebound and braking checks passed.
All 20 seeded Freefall spin comparisons reproduced the test5 results.
All 54 course starts and the player/save smoke tests passed their functional
checks. Freefall's measured input intervals comprise 335 three-frame, 97
four-frame and one five-frame interval. Physical cartridge timing is pending.

The 8 MiB ROM SHA-256 is
`88ce9d247f301183bb5e92517e93412135b7f20b952fb9e6ce14a8466f93bbbf`.
Rebuild and benchmark using the test7 commands above with the test8 ROM
and output directory. The catalog report includes the aggregate input rate
and the ratio of elapsed display time to target game time. The full timing,
fidelity and arithmetic reports are under `build/v096-test8/`, including
`catalog`, `route-cost`, `spike-test7`, `spike-test8`,
`native-with-support`, `native-speed-with-support` and `rider-signed`.

### Test8 optimization experiments

The 54-level controller catalog spends a weighted mean of 373,181 SM83
T-cycles in `physics_step` and 427,400 T in the whole active update before
the GDMA timing correction (427,427 T with it). The two-display-frame budget
is 280,896 T. These experiments used the test8 cartridge identified above.

**Terrain classification at build time.** Read-only hooks on levels 1, 7,
27, 39, 44 and 45 with neutral, gas, brake and seeded controls captured
2,185 completed updates. The timed routes reproduced their reference states
and cadence. At 1 m resolution the following original calls could be
replaced by an exact lookup or a shorter geometric test. The last column
is the original cost divided by all 2,185 updates. It is an upper bound
before lookup, bank changes, remaining arithmetic and misses.

| Test8 path | Eligible calls | Gross T/update |
| --- | ---: | ---: |
| Head sweep after a cache miss, all tiles in the swept bounds proven clear | 1,048 / 1,647 | 5,006 |
| Wheel segment scan, tile proven empty or limited to the interior of one edge | 1,165 empty + 1,437 single-edge / 7,237 | 5,055 |

The head mask uses the minimum distance from a closed tile to each finite
terrain segment and the solver's 244-unit radius. Keep the original enlarged
radius path for sweeps over 8 m. Wheel classification must respect rounded
Q14 projections, endpoint ownership and segment order. Ambiguous tiles use
the original scan. Each level's plain head mask fits in one 4 KiB bank
(maximum 3,256 bytes). The 54 levels share 1,636 distinct 16-bit head masks.
Per-level dictionaries combining head and wheel classifications need 78,800
bytes of patterns, plus indexing. Banked WRAM is an option for per-level
data, but the current stack descends from $E000 and `Bike` spans $D000.
Any switch must preserve the stack, interrupt handlers and live solver data.
Test8 has ten unused 16 KiB ROM banks below bank 508 (477–480 and 502–507).
The tile generator, classification inputs and per-path cycle counts are in
`build/v096-test8/optimization-audit/terrain/`.

**Repeated wheel queries.** On Shelf Life with braking, the same wheel
returned to exactly the previous Q18 center on 250 of 600 wheel calls. Both
queries accepted two contacts without moving the center. All 20 bytes of
the ordered contacts matched on every repeat. The repeated work before the
resolver cost 60,212 T per update across the 100 updates. Haircut neutral
had 25 such calls in 99 updates (6,730 T/update), Double Trouble gas had
none. A per-wheel cache would have to retain both center fractions and
ordered post-filter contacts, invalidate on level change or reset, and still
compute support, friction, braking and impact from the current motion.
The complete spring displacement and relative-speed inputs never repeated
on consecutive intervals in the six-route sample. The capture and per-route
counts are in `build/v096-test8/optimization-audit/repeat/verifylog`.

**Exact table for common terrain normals.** A separate ROM trained on all
54 neutral routes selected 80 frequent signed Q14 projection coefficients.
Tables indexed by the high and low bytes reconstruct each signed16 product
exactly. All other
operands fall back to the test8 multiplier. The model reproduced all
5,242,880 table products. A native check verified 18,886 raw results and
restoration of the caller's bank. Initializing the directory at boot saved
8,721 T per complete update across the catalog (2.04%) and raised cadence
to 17.67 updates/s. All 19,885 gameplay updates matched test8 at both state
boundaries. Shelf Life braking saved 20,931 T per update. Four additional
individual updates missed the deadline, and three routes met it throughout.
The prototype requires 125,760 additional linked ROM bytes and 825 bytes
of WRAM including alignment. Only 38 bytes of fixed ROM and 766 bytes
between static data and the initial stack remain. The stack high-water mark
still needs measuring. This experiment is independent of test9. The output
directory `build/v096-test8-numeric-audit/` contains `boot-summary.json`,
`product.py`, `fastdir.py` and `bootdir/native-raw.log`.

### 0.96 test9 — single-contact support

In test8, 1,929 of 1,979 single-contact tests on six controller routes could
accept the wheel from the sign of the projected impulse. Their baseline
velocity projections used 9,556 T per update across those 549 updates.
Test9 checks that impulse first for single contacts. For two contacts it
keeps the original test order and removes the exact incoming normal
velocity when required. No lookup data or extra persistent state is needed.

| Matched workload | Test8 | Test9 |
| --- | ---: | ---: |
| All 216 routes, aggregate updates/s | 17.341 | 17.655 |
| Mean active update / mean physics T | 427,400 / 373,181 | 418,598 / 364,301 |
| Highest active update T | 817,412 | 690,936 |
| Active updates over budget / 19,885 | 18,698 | 18,695 |
| Routes within budget throughout / 216 | 3 | 5 |
| Freefall input sampling, updates/s | 18.499 | 18.673 |

The mean active cost fell on 209 of 216 routes. The maximum includes
scrolling and display scheduling. All 19,885 controller updates matched
test8 after physics and after the whole update. All 12,380 packed 238-byte
states in the ordinary and extended-speed fixtures matched the frozen test5
host model. The 45 PC rebound and braking checks passed. The 20 seeded spin
cases reproduced the test8 comparisons. A separate raw-ROM oracle checked
1,984 support inputs including the −231 boundary, outward and inward
impulses, signed extremes, both removal modes, memory guards and stack
cleanup. Freefall still misses its deadline on all 439 active updates.

The benchmark cartridge and the playable test9 have the same SHA-256,
`5a4256efbc0a1cc7de019efc9d0ba5b5001b9ee9c2f5e816aaa0abb3d37aad04`.
The benchmark reports are in `build/v096-test8/optimization-audit/` under
`support-catalog`, `native`, `native-speed`, `fullfall`, `freefall`, `rebound`
and `spin-240` through `spin-280`. The isolated test used `support_oracle.py`.

### 0.96 test10 — combined cartridge

The production ROM includes per-wheel reuse of ordered contacts at an exact
Q18 center, conservative 1 m head clearance for all 54 courses, and ROM-only
partial products for 80 common signed coefficients. The projection tables
support both 16-bit and 32-bit components. No directory is copied to WRAM.
The raw scenery build also omits the ZX0 decoder and its banking wrapper.
The linked cartridge has 195 bytes of free fixed ROM and leaves banks
508–511 empty for FlashMaster. Seven controller routes left at least 1,261
bytes between static data and the observed stack watermark.

| Full-game PyBoy workload | Test9 | Test10 |
| --- | ---: | ---: |
| Aggregate updates/s on 216 routes | 17.655 | 18.061 |
| Freefall input samples/s, full descent | 18.673 | 18.768 |
| Mean whole active update / physics T-cycles | 418,598 / 364,301 | 409,130 / 355,098 |
| Maximum active T-cycles | 690,936 | 690,444 |
| Active updates over budget / 19,885 | 18,695 | 18,692 |
| Entire routes within deadline / 216 | 5 | 5 |

All 19,885 physics and presentation snapshots matched test9 at each of the
two update boundaries. The ordinary and extended-speed native fixtures
matched the frozen test5 host for 12,380 states. On the linked cartridge,
48,816 head sweeps matched test9 across all 54 courses, including border
crossings and tangencies. All 420,944 predicted tiles matched the geometry
oracle. All 26,635 native mask queries and bank restorations passed. The
projection checks covered 5,242,880 signed16 products, 10,704 native vectors
and 48 VBlank interruptions inside the high-bank reader. The 45 PC landing
and braking checks passed, and all 20 seeded spins reproduced test9's PC
comparisons. The player and save functional checks passed.

The ROM SHA-256 is `4292c81fe0d77059560940a3144d6bdfb9d2922dc639d5865f16487cdea39738`.
Rebuild with `tools/build.py --gen build/gen-v096-test4-8m --rom-mib 8
--out build/elma-gbc-v0.96-test10-8m.gbc` using the project's Python
environment. Reports are in `build/v096-test10/`.
