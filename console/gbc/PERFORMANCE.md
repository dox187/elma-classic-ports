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
