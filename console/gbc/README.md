# Elasto Mania for Game Boy Color

Current development version: **0.96 — joint physics fidelity and stable-30-FPS work**,
recorded in [`VERSION`](VERSION). Development is in progress; no accepted 0.96
ROM exists yet. Latest playable diagnostic:
**[0.96 test38 — 8 MiB](build/elma-gbc-v0.96-test38-8m.gbc)**.
Four controller routes on each of the 54 courses averaged **29.44 updates/s**.
The 24 longer routes averaged **29.11**, and the neutral Freefall descent
averaged **29.80**. Compared with test37, late updates fell from 608 to 562
on the standard routes and from 281 to 267 on the longer routes. The largest
extended update rose from 491,852 to 510,320 T against the 280,896 T budget.
All 75,252 physics substeps and 25,112 published states matched test37.
[Timing and verification](PERFORMANCE.md#096-test38--combined-angular-torque-and-wheel-contact-products)

Earlier diagnostic ROMs remain available in their respective sections.
The retained **[0.96 test1 — 8 MiB](build/elma-gbc-v0.96-test1-8m.gbc)**
contains the earlier exact optimizations with the old narrow physics.
The **[0.94 speed test — 8 MiB](build/elma-gbc-v0.94-speed-test-8m.gbc)**
is the earlier drive-cutoff checkpoint.
The retained 0.93 checkpoint is
**[0.93 rebound test — 8 MiB](build/elma-gbc-v0.93-rebound-test-8m.gbc)**.
It fixes the measured rebound, but is too slow for release: Freefall averages
**13.43 physics updates/s** in the emulator. The older
`build/elma-gbc-v0.93-test1-8m.gbc` still has the measured 52.22% 4 m rebound
error. Existing 0.92 images below are
previous test builds. Stable 30 FPS and improved original-PC fidelity remain
requirements; neither input buffering nor a relaxed accuracy target is added.
Active development now targets the **8 MiB ROM only**. Work on the 4 MiB
compressed variant stopped on 2026-11-17; its existing releases and experiments
are retained for reference.
See the [performance experiment log](PERFORMANCE.md) for measured candidates
and rejected approaches. Development builds do not overwrite the 0.90 ROMs.

## Version milestones

| Version | Scope | Status |
|---|---|---|
| 0.93 | Measured rebound correction and existing braking improvements | Retained diagnostic checkpoint; 13.43 updates/s in Freefall |
| 0.94 | High-speed rolling, impacts, rotation and braking against PC; numeric saturation and overflow audit | 122-case audit complete; cutoff corrected, other limits remain |
| 0.95 | Reduce the corrected model's runtime cost toward stable 30 FPS | Work continues within 0.96; no separate release |
| 0.96 | Joint original-PC accuracy and full-game stable-30-FPS acceptance | In progress; both requirements remain mandatory |

The retained 0.93/0.94 and current 0.96 diagnostics still have a runtime-cost
limitation; the final joint acceptance target is 0.96. Version numbers do not imply that unpassed
accuracy or timing requirements have been waived. All new ROM filenames remain
versioned and directly inside `build/`.

Playable test: **[0.91 test1 — 8 MiB](build/elma-gbc-v0.91-test1-8m.gbc)**,
for MBC5 with 32 KiB cartridge RAM. Its SHA-256 is
`624e427940917c15d1d4960866f0368f61549b6f59292a41290c047b6c38a8b5`.

This build preserves all 27,447 native states in the 216-case controller
corpus. Deadline misses fall from 1,025 to 55, with 196 cases passing
throughout. Its separate functional run passes all 54 starts, complete
Freefall, menus, save profiles, volt controls and finish audio. Further graphics/physics
optimization and physical-cartridge timing checks remain; **0.91 is not yet a
stable 30-FPS release**.

The 0.91 test1 emulator corpus averages **29.84 updates/second**, against
the GBC two-display-frame target of **29.86**: approximately **0.09%** aggregate
slowdown. The slowest tested route averages **28.59**. The 196/216 fully passing
cases are a test pass rate, not the game's percentage speed. Local stalls
remain; these short routes do not establish full-course or cartridge timing.

## 0.96 test29 — suspension forces, rider pose and signed projections

The rider geometry shares exact planar records. Suspension forces retain
intermediate digits in registers, and the projection multiplier has shorter
paths for both signed coefficient lookup and general products. Standard
misses including DMA fell from 2,584 to 2,189. The longest extended update
took 527,472 T-cycles. [Timing and validation](PERFORMANCE.md#096-test29--combined-cartridge)

## 0.96 test28 — damping, terrain contacts and scrolling

The four-term damping moment and suspension braking use exact integer
shortcuts. Dense terrain queries reuse ordered candidate spans. Scrolling
can retain both completed rows and partially filled columns. Standard
deadline misses including DMA fell from 2,906 to 2,584. The slowest standard
update increased from 468,784 to 511,924 cycles.
[Timings and fidelity checks](PERFORMANCE.md#096-test28--combined-cartridge)

## 0.96 test27 — wheel projections, spring torque and rider limits

Sloped ground and compressed suspension use exact integer product tables.
The rider limit covers larger seat displacements directly. The standard
routes had 2,906 deadline misses including sprite DMA, down from 3,733.
On the longer routes the heaviest update took 555,172 T-cycles against
a 280,896-cycle budget. [Timings and physics comparisons](PERFORMANCE.md#096-test27--combined-cartridge)

## 0.96 test26 — wheel terrain, rider rotation and suspension forces

The renderer and physics kept the same recorded outputs on every tested
course. The wheel solver skips terrain segments proven irrelevant throughout
a 64-unit square and rejects exterior endpoints from a precomputed circle
boundary. The rider's forward and inverse rotations share multiplication
rows. Spring forces keep their exact wide fallback and body residuals.
The standard routes recorded 3,733 misses including sprite DMA, down from
4,569. [Full timings and validation](PERFORMANCE.md#096-test26--combined-cartridge)

## 0.96 test25 — suspension, terrain and movement

This build uses exact integer tables for partial movement, shallow slopes,
the seat constraint and square roots. It reuses the distance to a terrain
plane and combines matching suspension arms before accumulating their
damping torque. Standard deadline misses including sprite DMA fell from
6,918 to 4,569. The longest standard update took 531,188 cycles.
[Full timings and validation](PERFORMANCE.md#096-test25--combined-cartridge)

## 0.96 test24 — terrain contacts and exact integer multiplication

The wheel solver reuses the classification of a finite segment within a
64-unit region when its bounds prove that every point has the same outcome.
The cartridge uses one signed product implementation for terrain and wheel
arithmetic. A dedicated table covers squared distances, freeing the former
quarter-square banks for physics calculations. The worst standard update
took 529,156 CPU cycles against a budget of 280,896.
[Full timings and validation](PERFORMANCE.md#096-test24--combined-cartridge)

## 0.96 test23 — wheel impacts, suspension and sprite transfers

Braking, rolling and suspension use exact integer products and keep the
original rounding and residuals. Swept-head collision reuses proven terrain
clearance. The renderer uploads changed bike tiles in bounded DMA bursts.
The longest of the 216 standard routes' updates took 555,028 CPU cycles
against a budget of 280,896. Physical cartridge timing remains to be checked.
[Full timings and validation](PERFORMANCE.md#096-test23--combined-cartridge)

## 0.96 test22 — terrain queries and wheel motion

Both wheels use the same three original wheel images resident in VRAM.
Changing rotation phase updates their sprite tile indices. Wheel translation
carries its fractional remainder directly into the position update. Terrain
queries now search the three cached cells in registers and copy missed records
directly from ROM. Row and column scenery reads share a length-specific copy.
[Full timings and validation](PERFORMANCE.md#096-test22--combined-cartridge)

## 0.96 test21 — suspension, rider and wheel motion

The suspension can prepare one wheel at a time between input samples.
The body rotation, rider movement and wheel rolling calculations use shorter
paths for common inputs while retaining their rounding and residuals.
The controller benchmark now supports comparing the native bike, fractional
accumulators, wheel contacts and survival after each physics substep.
[Full timings and validation](PERFORMANCE.md#096-test21--combined-cartridge)

## 0.96 test20 — spring symmetry and terrain contacts

When the left and right springs exert opposite moments, the solver computes
their exact combined rounding remainder. The contact solver has a shorter
projection for two frequent terrain directions. The head collision check
uses its own radius to reject distant edges. The live HUD timer passed its
90-updates-in-180-display-frames check. Whole-game timing still misses
the two-frame budget on 11,440 of the 19,885 measured updates.
[Full timings and validation](PERFORMANCE.md#096-test20--combined-cartridge)

## 0.96 test19 — geometry, wheel rotation and torque

The pose lookup computes the head and suspension anchors with fewer register
loads. Free and rolling wheels share the same angular update. The suspension
uses shorter exact products for common lever lengths during throttle.
Missed deadlines fell from 11,874 to 11,461. The worst active update still
takes almost four display frames.
[Full timings and validation](PERFORMANCE.md#096-test19--combined-cartridge)

## 0.96 test18 — wheel contacts and position updates

For common pairs of terrain normals, a lookup can establish how a stationary
wheel responds to both contacts. More quarter-metre terrain cells have a
precomputed list of candidate edges. Near-horizontal contacts and full-step
position updates also take shorter arithmetic paths with the same rounding.
Across the 216 routes, 11,874 updates exceeded budget, down from 12,056.
[Full timings and validation](PERFORMANCE.md#096-test18--combined-cartridge)

## 0.96 test17 — partial-step movement and timer

The final substep uses the motion coefficient’s byte products directly for
all eight position axes. The HUD advances the clock once per completed
physics step and retains its fractional centiseconds. Eighteen controller
routes stayed within the two-display-frame budget on every update.
[Full timings and validation](PERFORMANCE.md#096-test17--combined-cartridge)

## 0.96 test16 — damping and scenery uploads

The solver uses shorter products for small relative wheel speeds and prepares
spring and damper products during spare display lines. Scrolling reuses the
selected tile lookup when installing a new pattern. Across 216 controller
routes, 12,514 of 19,885 updates exceeded two display frames.
[Full timings and validation](PERFORMANCE.md#096-test16--combined-cartridge)

## 0.96 test15 — terrain vertices, braking and camera

Wheel contact with a terrain vertex can look up the exact integer normal.
On shallow slopes the solver can often decide the sign of the impulse
directly. The brake, throttle and gravity paths use the same physics units
and cutoffs. The camera retains a projection already calculated during
scenery preparation. The worst complete update fell from 658,224 to
557,592 CPU cycles across the 216 controller routes.
[Full timings and validation](PERFORMANCE.md#096-test15--combined-cartridge)

## 0.96 test14 — suspension and display preparation

During spare display time the game can prepare the geometry and inputs for
the next suspension step. A reset, turn or menu transition discards that
work. The wheel and body updates share integer force calculations, and
the renderer converts all five bike positions together. Fourteen of 216
routes stayed within the two-frame budget throughout. The original-PC
landing, braking and seeded spin comparisons reproduce test13.
[Full timings and validation](PERFORMANCE.md#096-test14--combined-cartridge)

## 0.96 test13 — terrain and wheel updates

Both wheels consume suspension impulses directly in one visit to bank 9.
Precomputed terrain windows preserve the order of wheel contacts. Finer
clearance masks let head sweeps past empty quarter-metre squares skip
the exact edge scan. The rider, body and wheels retain the previous
movement and angular rounding. Eleven of 216 routes stayed within the
two-frame budget throughout.
[Full timings and collision checks](PERFORMANCE.md#096-test13--combined-cartridge)

## 0.96 test12 — suspension forces and contact geometry

The 8 MiB build combines spring and damping products, reuses the geometry
of ordered wheel contacts, and looks up common rolling and rider responses
with their original rounding. Eight of the 216 controller routes stayed
within the two-frame budget throughout. The 12,380 native physics states
matched the frozen test5 reference. All 45 PC landing and braking checks
passed and all 20 seeded spin comparisons reproduced test11.
[Full timings and arithmetic checks](PERFORMANCE.md#096-test12--combined-cartridge)

## 0.96 test11 — suspension, wheel contacts and rider movement

The 8 MiB cartridge uses precomputed wheel clearance on all 54 courses,
shares the angular-speed lookup across the four suspension arms and shortens
the grounded-wheel and rider movement paths. Scrolling reuses pinned graphics
slots for adjacent cells with the same pattern. All 19,885 controller updates
matched test10. Six of 216 routes stayed within the two-frame deadline
throughout. The mean active update fell from 409,130 to 368,361 SM83 T-cycles.
[Full cartridge timings and regression checks](PERFORMANCE.md#096-test11--combined-cartridge)

## 0.96 test10 — repeated wheel contacts and collision tables

The game reuses both ordered contacts when a wheel returns to the exact
same position. It reads precomputed head clearance from all 54 courses and
uses exact partial products for 80 frequent projection coefficients. All
19,885 controller updates matched test9 at both comparison points. The full
game averaged 409,130 active T-cycles per update. Five of the 216 routes
met the 280,896-cycle deadline throughout. Hardware timing is pending.
[Measurements and regression checks](PERFORMANCE.md#096-test10--combined-cartridge)

## 0.96 test9 — single wheel contact

A wheel touching one surface can accept a supporting impulse immediately
when its projection on the surface normal is zero or inward. This saves a
second projection of the wheel velocity. Across 19,885 gameplay updates,
mean active cost fell from 427,400 to 418,598 T-cycles. Five of 216 routes
stayed within the two-display-frame budget throughout. All compared gameplay
states matched test8 and all 12,380 native states matched the frozen test5
host model. Physical cartridge timing is pending. See the [performance log](PERFORMANCE.md#096-test9--single-contact-support).

## 0.96 test8 — grounded wheels, terrain vertices and rider motion

| Measured updates per real second in emulation | Test5 | Test6 | Test7 | Test8 |
| --- | ---: | ---: | ---: | ---: |
| Freefall, complete descent | 11.61 | 17.87 | 18.20 | **18.50** |
| All 54 levels, four short routes each | 10.99 | 15.75 | 16.83 | **17.34** |
| Shelf Life, gas followed by braking | 8.75 | 12.32 | 12.34 | **12.61** |

One simulated second now takes **1.61 real seconds in Freefall** and **1.72
seconds** across the controller routes. Three of the 216 routes met the
29.86 updates/s requirement throughout. The largest single frame cost
increased on Double Trouble. The detailed timing is in the
[performance log](PERFORMANCE.md#096-test8--grounded-contact-and-vertex-costs).

Against test5, all **19,885** gameplay updates and all **12,380** native
physics states matched. The native checks include both wheel support
normals, contact flags and accumulated motion fractions. The PC rebound,
braking and rotation regressions passed. Measurements use the double-speed
CGB emulator. Cartridge timing still needs a physical test.

[Download test8 for the 8 MiB cartridge](build/elma-gbc-v0.96-test8-8m.gbc) ·
SHA-256 `88ce9d247f301183bb5e92517e93412135b7f20b952fb9e6ce14a8466f93bbbf`.

## 0.96 test7 — wheel contacts, head collisions and damping torque

| Emulator measurement | Test5 | Test6 | Test7 |
| --- | ---: | ---: | ---: |
| Freefall descent, updates per real second | 11.61 | 17.87 | **18.20** |
| All 54 courses, four controller routes each, aggregate updates/s | 10.99 | 15.75 | **16.83** |
| Slowest route, Shelf Life with braking, updates/s | 8.75 | 12.32 | **12.34** |
| Complete active updates over 280,896 T-cycles on those routes | 19,878 | 19,266 | **18,750** |

These routes use identical inputs for up to 100 updates each. A simulated
game second takes **1.64 real seconds** on the complete Freefall run, or
**1.77** across the short routes. The wheel contact shortcut reuses a small
terrain region after repeated visits. The head collision shortcut skips
regions clear of terrain, and the damper preserves the full sum of both
wheels' torques before rounding.

All 12,380 native state comparisons passed. The 45 PC rebound and braking
checks and the 20 extreme Freefall spin tests retain their previous results.
All 54 courses started successfully. The stable-30 timing gate still fails
in the emulator. Physical Game Boy Color timing is unverified.

[Download test7 for the 8 MiB cartridge](build/elma-gbc-v0.96-test7-8m.gbc) ·
SHA-256 `3fb8c2c232f6e7c3bee4bda6eabb5d520670983e3bc24ed17113d3924166e15f`.

## 0.96 test6 — faster physics on GBC

| Emulator measurement | Test5 | Test6 |
| --- | ---: | ---: |
| Freefall, no input, measured updates per real second | 11.61 | **17.87** |
| Real seconds per simulated game second on this run | 2.57 | **1.67** |
| Freefall, mean / worst complete active update in CPU T-cycles | 671,566 / 938,636 | **425,960 / 663,348** |
| 12 controller runs on three courses, mean / worst complete active update | 705,610 / 966,868 | **462,809 / 685,588** |
| 46 native physics cases, mean / worst T-cycles | 537,506 / 1,030,792 | **321,678 / 657,704** |

A real-time update has **280,896 T-cycles** for input, physics, audio and graphics.
In Freefall, 296 measured intervals took three display frames, 126 took four,
and 11 took five. The game clock advances once per simulated update. Timing
above comes from emulation at the original double-speed CGB clock.

The ROM retains all three physics intervals per update. Precomputed exact
body geometry, fixed-point arithmetic and fewer repeated terrain and rider
calculations account for the gain. Across 168 native cases, every compared
228-byte state matches test5. The 45 rebound and braking cases passed the
existing gates, and the 122 speed cases agreed with the PC on survival.
All 54 courses passed the menu, start and rendering checks. The stable-30
timing gate remains open. Measurements and rejected experiments are in
[the performance log](PERFORMANCE.md#096-test6--integrated-physics-timing).

[Download the 8 MiB ROM](build/elma-gbc-v0.96-test6-8m.gbc) ·
SHA-256 `9a6a84b44140158c1ceed5803d5050cadf58fc2e91e62b38850833032e1654ce`.
Physical Game Boy Color timing awaits a cartridge test.

## 0.96 test5 — body rotation during Freefall

The wheel damper now uses both wheel-to-frame coordinates at their full Q18
resolution. The angular impulse retains the signed Q24 remainder from both
torque terms, and the next update uses that remainder in rotational velocity
and body angle. Rounding the summed spring moment also preserves a symmetric
landing on level ground.

The emulator tests open Freefall through the game menu. PC starts from the
ROM's pose and velocities. Time in the comparisons is measured in completed
physics updates. Each update advances both simulations by the same model
interval, regardless of the number of display frames it took.

| Freefall comparison | Result on the playable ROM |
|---|---|
| Left then right, and right then left, via controller | Both sequences survived 70 updates. Maximum body-angle error was 0.015° and 0.0424° respectively. Maximum position error across the wheels, frame, rider and head was 2.26 cm and 1.29 cm. |
| Inject ±120 rad/s at updates 240, 250, 260, 270 and 280 | All ten runs survived the following 25 updates in both models. Maximum position error was 2.26 mm. |
| Inject ±140 rad/s at those same five starting points | Both models stopped 21 updates later for negative rotation and 25 for positive rotation in all ten runs. Across these runs position error reached 7.31 mm through update 19. Near the crash, the peak reached 27.6 cm and the body-angle difference reached 15.75°. |
| The original update-260 comparison, −140 / +140 | Peak common-live position error fell from 1.56 / 0.84 m in test4 to 3.4 / 25.0 cm in test5. Each PC run starts from the matching ROM's own descent. |

The 45 rebound/braking cases pass their existing gates, including the 0.1%
flat-drop rebound and airtime checks. All 122 speed fixtures match final PC
survival. Eight injected extreme volt fixtures reach a numeric limit. The
SM83 matches the corresponding HOST calculation byte for byte in 9,210 default
and 3,170 high-speed states, including the angular remainder. All 54 starts
and complete no-input Freefall pass their functional checks. Freefall takes
4–7 display frames per update and averages 11.61 updates/s. Stable 30 FPS,
global 99.9% accuracy and physical-cartridge validation remain open.

[Playable test5 ROM](build/elma-gbc-v0.96-test5-8m.gbc) · 8,388,608 bytes ·
MBC5, 32 KiB RAM · SHA-256
`4e10759c014da913bf67f1547da74e0ca1bcdf00aa72df1de841e65183317db0`.

## 0.96 test4 — airborne damping and level exits

The suspension samples the nearest body-angle phase and uses four times the
previous coordinate resolution for damping while the rounded wheel levers
fit in Q12. Gas and brake keep their original reaction inputs. Each internal
step also checks the wheels, head and frame against the collision-grid and
camera bounds derived from the original course geometry.

On Freefall, the test sets the frame's angular velocity at game update 260.
The PC reference starts with the ROM's pose and velocities. At −140 rad/s
both now stop on update 21, and at +140 both stop on update 25. Test3 was
one update late and one early, respectively. Both ±120 runs survive all
25 updates. Through the common live updates at ±140 the largest position
errors are still 1.56 m and 0.84 m. Injecting −140 at update 240 exposes
another one-update mismatch (GBC 20, PC 21).

All 45 rebound/braking cases pass their 0.1% peak and airtime limits. All 122
speed cases agree on final survival. Two native suites match 9,209 and 3,170
HOST states byte for byte. The level-exit tests pass 1,008 boundary probes
and 16 trajectories against the desktop source. All 54 course starts and
the no-input Freefall pass their functional checks. Freefall takes 4–7 display
frames per update (12.85 updates/s). Hardware timing remains unverified.

[Playable test4 ROM](build/elma-gbc-v0.96-test4-8m.gbc) · 8,388,608 bytes ·
SHA-256 `83430fd97453fd313f341978b0defae3fe5709a761b0c0c0cd508e89ddc0dc98`.

## 0.96 test3 — airborne wheel extension

Test2 declared a crash if a wheel moved more than 3 m from the frame on
either axis. In four airborne fixtures, original PC physics also extends the
suspension past 3 m and continues. Test3 allows up to 8 m per wheel axis.
The extended PC reference reaches 7.081 m on its last live step in the
140 rad/s fixture. The rider has a separate 3 m limit.

All 122 speed fixtures now agree on final survival. Six extreme volt fixtures
reach arithmetic saturation on their terminal update (step 10 in both models). In a 120-update comparison
at ±120 rad/s both models survive. At ±140 rad/s both stop at update 23,
but late positions diverge by up to 3.16 m. In a separate rendered Freefall
test we set body rotation at update 260. Both ±120 cases survive 25 further
updates. At −140 the ROM stops after 22 updates and PC after 21. At +140
the counts are 24 and 25. The wheel sprites match the exported coordinates.
The Freefall test retains its strict death-step assertion and reports this
remaining difference.

Freefall without injected input still averages 13.54 updates/s in the emulator.
SHA-256 of test3 is `084930fcdd7ead078a0cdf3198870a5913d1525f8c738017ca291928cb3d9c0b`.

## 0.96 test2 — widened physics integrated into the ROM

The native SM83 core now stores angular velocity, saved volt velocity and wheel
brake torque as signed 32-bit values. Spring torque input also retains its full
width. The previous 16-bit clipping and volt wrap are removed without lowering
precision or changing the integration intervals. At 80 model m/s, wheel speed
now reaches **200.001461 rad/s**, versus PC **200.000058**, instead of clipping
near 142.8 rad/s. The audio API still receives its existing bounded speed range.

During strong wheel/body compression, the old reciprocal table underestimated
the reaction torque. Below its distance floor the ROM now computes the exact
integer quotient before applying the unchanged physical coefficient. Zero
separation retains the previous table fallback. Both ±60 m/s flat braking
impacts now survive, matching PC; all **18 impact survival outcomes** match in
the 122-case audit. Four synthetic ±120/±140 rad/s body-spin differences remain
because of GBC's 3 m stretch guard. This is not a claim of global 99.9% fidelity.

Validation of this implementation:

- **9,213 default states + 3,179 high-speed states**, each 224 bytes including
  motion/force residuals and audio events, match the corresponding HOST model
  exactly when executed as native SM83 code.
- All **45 PC rebound/braking cases** pass the 0.1% peak/airtime gates. The
  122-case audit records no numeric limit hits and all six drive-cutoff gates pass.
- Independent native checks cover **14,114 close-reaction quotients** and
  **1,592 full-width motion cases**, plus 1,500 brake and 1,200 wheel fixtures.
- Menu, volt controls, all 54 starts and complete no-input Freefall pass their
  functional/graphics checks. Player names, timer text, result panels, records,
  retry and battery reload pass; finish checks use an explicitly injected
  flower contact rather than claiming a player-controlled finish.
- The 216-case controller corpus completes **30,490 updates** without observer
  or functional errors; all 216 timing gates still fail.

**Timing still fails.** The native default mean is **481,028 T-cycles**, with a
maximum of **925,724 T**, before rendering, against the **280,896 T entire-frame
budget**. All-start/Freefall runs record **1,615 / 438 deadline misses**. Freefall
averages **13.5432 updates/s** (4–6 display frames per update), versus 13.5858 in
test1. The player/save suite completes its functional checks and still exits
with failure for the unchanged cadence/deadline requirements. No hardware pass
or stable-30-FPS release is claimed.

ROM: **[elma-gbc-v0.96-test2-8m.gbc](build/elma-gbc-v0.96-test2-8m.gbc)**,
**8,388,608 bytes**, MBC5 + 32 KiB RAM, header **1B/08/03**; banks **508–511 all FF**.
SHA-256: `b5e5d2baacd43bc8857d954811addf323c39f8477e02d0e40459f14734ad1e5a`.
The menu and splash show **0.96**. The versioned ROM is directly in `build/`.

Remaining work: reduce the corrected model's cost enough to meet 30 FPS with
rendering, investigate the four extreme-spin/stretch-guard discrepancies, and
validate on the physical cartridge. Accuracy and timing targets remain mandatory.

## 0.96 test1 — retained optimization checkpoint

Test1 combines three exact native optimizations: suspension force submissions
use bank8 register entries, Q24 v3 tables store short negative products directly,
and wide dot products seed their accumulator from the first product. No physical
coefficient, integration interval or input latency changes. The default 46-case
mean falls **491,599 → 478,295 T-cycles (2.706%)**; maximum **920,384 T** still
exceeds the **280,896 T whole-frame budget**. All **9,213** default and **3,186**
high-speed states match the frozen 0.94 HOST exactly, including residuals/audio.
Even the mean needs at least another **41.3% cost reduction before rendering**;
this checkpoint is still far from the final timing requirement.

Independent arithmetic tests pass **11,572 dot products**, **8,192 force
accumulations**, **48,958 production Q24 cases**, and **48,964 signed/extreme Q24
cases**, including fractions, saturation and physical bank restoration. Q24 v3
keeps banks 481–501; the builder rejects the old v2 format with this kernel.

The ROM passes menu/volt and all 54 start/Freefall functional checks, with no
observer errors. Strict timing gates still fail: **1,609 / 438 deadline misses**.
Freefall averages **13.59 updates/s**, versus **13.43** in 0.94, with 4–6 display
frames per update. These improvements do not establish stable 30 FPS. The
player/save cadence gate remains unresolved; no new hardware acceptance is claimed.

SHA-256: `0c81315309db968e42842319c095f94dd64e3d5c57ac0823441c1cc78f5163d6`.
Size **8,388,608 bytes**, header **1B/08/03**, unused banks **508–511 all FF**.
The menu and splash show **0.96**. This file is directly in `build/`.

Separate HOST research widens angular velocity, brake torque and spring input
without reducing precision. It removes the 80 m/s wheel-spin clipping but alone
increases survival mismatches from five to six. The additional cause is the
reaction lookup's minimum wheel/body distance: around 0.28 m it underestimates
torque reaction by **39–40%**. A localized direct reciprocal below the table floor
fixes both ±60 m/s flat braking impacts, retains all 45 strict rebound results,
and leaves four synthetic extreme-spin/stretch-guard mismatches. **Neither HOST
prototype is included in test1.** Test2 integrates and validates the widened native ABI and close-reaction arithmetic;
its runtime cost still exceeds the release budget. Applying only the
reciprocal correction to the old narrow model does not resolve its impact death.

See [`PERFORMANCE.md`](PERFORMANCE.md) for the measured experiments, rejected
partial changes, evidence paths and the remaining joint acceptance work.

## 0.94 high-speed audit

The scheduled profile previously stopped applying drive torque one raw angular
unit too early. Its threshold now rounds upward, preserving the original PC
`omega < 110` / `omega > -110` comparisons. At raw omega ±25241, the driven-wheel
peak now reaches **120.308544 rad/s**, versus PC **120.310253**, instead of
remaining at **109.997753**. Maximum peak error over the six cutoff fixtures is
**0.001421%**; the old threshold fails the same 0.1% regression gate.
This is a torque cutoff, not a hard limit on downhill or externally induced speed.

The audit covers **122 synthetic initial conditions**: ±40/44/55/57.12/60/80
model m/s with both facing directions and coast/gas/brake, fast impacts on
flat/±15° ground, and angular/brake/volt boundaries. Flat cases begin with zero
wheel spin and establish contact; they are not pre-settled rolling or completed
controller routes. Original PC equations run as native double, not Windows x87.
All **3,187 instrumented HOST states** match the untouched HOST. Separately,
the native core matches all **3,186 packed states × 214 bytes**. Native tests
cover the core only; the PC comparison also applies GBC's production 3 m
stretch guard, so these state counts describe different termination rules.

Remaining limitations are measured, not declared fixed:

| Path | Current limit | Measured consequence |
|---|---|---|
| Stored angular velocity | About ±142.8 rad/model-second | Rolling omega clips near 57.12 model m/s; translation continues |
| Brake relative angular velocity | ±71.3955 rad/model-second | Damping is weaker than PC beyond this range |
| Brake torque | −8192 to +8191.75 Nm | Further clipping under strong braking |
| Volt impulse | 16-bit addition can wrap | Extreme initial rotation can reverse the stored sign |
| Spring moment input | About ±2 m² | Large deformation clips the spring's body torque |

**74/122 cases** exercise at least one recorded clamp or wrap. Five survival
outcomes differ: one +60 m/s flat braking impact dies in the GBC core while PC
survives; four ±120/±140 rad/s body-spin fixtures trigger GBC's 3 m stretch guard
while PC survives. These counts do not establish how often normal gameplay
reaches those states. The 32-bit linear range itself is approximately
±93,091 model m/s; the lower angular and torque limits are the practical concern.
No artificial linear speed cap was added.

The 45 existing PC landing/braking fixtures still pass their rebound/airtime
and survival gates; the 46-case native regression retains **9,213 exact states**.
The new ROM passes menu/volt and all 54 start/Freefall functional checks.
Strict timing checks still fail (1,605/439 deadline misses); Freefall remains
**13.43 updates/s**. The player/save suite stops at its timer-cadence assertion,
so this build does not claim a new full save-suite pass. Hardware testing is
still required. This is a diagnostic checkpoint, not final 0.96 acceptance.

SHA-256: `b3727b3e8b31c03b1ae327c60e33a9d0b4370e208801b32d3b5986b4acbcb240`.
Size **8,388,608 bytes**, MBC5 + 32 KiB RAM; banks 508–511 remain all FF.
Both menu and splash show **0.94**. Run `make check-speed-limits` with the
resource paths from the build instructions to reproduce the PC audit and native seeded cases;
its gas-cutoff and native-equivalence gates do not waive the other findings.
See [`PERFORMANCE.md`](PERFORMANCE.md) for evidence paths and next work.

## 0.93 acceptance work

The current source reproduces the original PC integration schedule with three
unequal substeps per outer frame, Q24 coefficients and retained fractional
movement/force impulses. Controlled first-rebound peak errors are **0.089867% at
4 m** and **0.007095% at 8 m**; all 45 coast/gas/brake and slope survival outcomes
match PC. These results describe those measured cases, not global 99.9% fidelity.
The native SM83 port matches the frozen HOST model in **9,213 complete states**
across 46 cases, including fractional accumulators, controls and audio events.

Performance is still blocking release: the latest combined native kernels
cost **491,599 T-cycles per outer update on average**, before game
rendering, versus **280,896 T-cycles for the entire two-display-frame budget**.
Further optimizations are in progress. Internal `*-probe-*` ROMs are diagnostic
artifacts, not playable replacements. The named rebound test contains the
latest combined correction (SHA256
`d4838a7e747c246c38a931e28ce1197329b51218bdceb52056837dd09d2a8561`).
All 54 starts, Freefall and volt controls pass their functional checks; the
zero-overrun timing gates still fail. See [`PERFORMANCE.md`](PERFORMANCE.md)
for the experiment sequence and evidence.

Development ROM: **[0.93 test1 — 8 MiB](build/elma-gbc-v0.93-test1-8m.gbc)**.
The menu and splash both show 0.93. Grounded braking now follows the original
PC damping substeps with rolling inertia; free-wheel braking is unchanged.
All 27 controlled braking cases (flat/±15°, heights 1/4/8 m, speeds 0/4/8 model m/s)
match PC survival/death. Flat-braking position RMSE improves .19243→.10723 m,
velocity RMSE .39059→.20532 model m/s. These are remaining errors, not full
fidelity. All 1,471 native/HOST trajectory states match in 161 bytes.


The full 216-case controller corpus records 29,866 physics steps without
runtime correctness failures, averaging **29.70 updates/s**. There are 341
active deadline misses and 140/216 fully passing cases; stable 30 FPS remains
unfinished. Menu/save/control checks pass; all 54 starts and Freefall run,
but their strict timing gates fail with 2/3 misses. Test ROM SHA-256:
`50b02679e014668a032f34df0e1ee672ac0ab3e79dbe6956f1013e64ec294fe9`.

The 0.92 landing test is an improvement, not the required original-PC match.
Its stationary 4 m first rebound differs by **52.22%** (5.13 mm); first
airtime differs by **5.90%**. At 8 m the corresponding errors are **0.105%**
and **10.12%**. A matching peak alone therefore does not establish fidelity.

`test/fixtures/landing_pc_accuracy_bounds.json` records a strict 0.1%
relative diagnostic bound for both wheels' first rebound height and airtime in all
4/8 m, vx0/4/8 coast cases. Use it with `check_landing_response.py --bounds`.
The released test1 implementation fails all 24 checks. The scheduled rebound
test passes the 0.1% peak and actual-substep airtime gates in
`check_rebound_schedule.py` for both wheels at all six 4/8 m, vx0/4/8 coast
conditions. Its maximum airtime difference is floating-point timestamp noise.
The earlier broad landing
bounds remain a historical regression guard, not proof of 99.9% fidelity. Contact-time quantization must be distinguished
from trajectory error when interpreting the airtime diagnostic.
Braking must also retain the PC survivors on the ±15-degree drop fixtures.
Development test ROMs do not certify these unresolved accuracy requirements.

## 0.92 landing test

Playable **[0.92 landing test — 8 MiB](build/elma-gbc-v0.92-landing-test-8m.gbc)**
keeps the audio and save format of 0.92 and corrects excessive landing rebound.
The previous audio-only ROM remains available below.

The old exponential damper applied the free wheel's 10 kg response to the
supported body as well. The correction uses a 59.03 kg effective body-point
mass, including pitch, for its supported normal reaction. Spring stiffness,
physical damping and masses remain unchanged. Wheel impulses and airborne
motion retain their previous equations; no adhesive contact or speed clamp
is introduced. Two retained contact constraints correct both axes.

Original-PC comparison, stationary coast onto horizontal ground:

| Initial wheel-center height | Previous first rebound | Landing test | Original PC |
|---|---:|---:|---:|
| 4 m | 49.44 cm | 1.50 cm | 0.98 cm |
| 8 m | 120.05 cm | 17.73 cm | 17.71 cm |

At initial horizontal speed 8 model m/s, the same 4/8 m tests rebound
1.38/16.69 cm instead of 49.31/120.14 cm. The 27-case matrix covers all
1/4/8 m heights, 0/4/8 model m/s speeds and coast/gas/brake. It introduces
no new deaths relative to the old GBC model on horizontal ground. Two old
8 m gas failures disappear; the 8 m / 8 m/s held-gas case still fails while
PC survives. These are sampled HOST comparisons to the original native-double
PC equations, not cartridge measurements or a global fidelity percentage.

Remaining limitations: support is cached from the preceding step, and its
body-point mass uses upright rest geometry. In the added ±15-degree slope
matrix, 4 m / zero initial speed / held-brake cases fall over after roughly
7 seconds although PC and the old GBC model survive. Inclined gas/brake motion
needs more work. At 8 m stationary coast, first airtime is 1.005 seconds versus
PC 1.118 seconds, despite the similar peak height. This is an experimental
landing build, not a 99.9%-accurate physics release.

Validation: 1,471 native/HOST steps match in all 161 state bytes; 768
arithmetic boundary cases match in all 32 result bytes. The final assembly
also preserves all 29,410 recorded physics states of the C landing candidate
across 216 controller cases. Menus, saving, volt/finish controls and impact
sound checks pass. All 54 course starts and Freefall run, but their strict
timing gates still fail (2 and 3 misses respectively).

The final controller corpus averages **29.70 updates/s**, with **329 active
deadline misses and 142/216 fully passing cases**. This is slower than the
audio-only baseline's 29.82 updates/s; stable 30 FPS remains unfinished.
Hardware playtesting is still needed. ROM SHA-256:
`fc98be152f93cdc77a171e9ed3e5e002c38c77ce6e5ecde669ea96c4643b4136`.

Reproduce the horizontal bounds (both wheels, peak and airtime):

```sh
python3 console/gbc/test/check_landing_response.py \
  --gen console/gbc/build/gen-8m \
  --bounds console/gbc/test/fixtures/landing_response_bounds.json
```

The bounds allow up to 4 cm rebound at 4 m and 12–25 cm at 8 m, over all
three initial speeds. They protect this specific correction; they are not
an accuracy score. Optional `--baseline-source`/`--baseline-constants` compare
against a frozen source tree; `--slope-degrees` adds inclined diagnostics.
Full traces, contact windows and failures are written before assertions.

## 0.92 audio update

- Suspension creak requires a new supported wheel collision and sufficient
  incoming speed into the terrain. Acceleration, weight transfer and spring
  compression alone do not trigger it. The original `dorzsol.wav` contour
  plays once on CH2; takeoff mutes it and apples take priority. This correction
  stays in version 0.92.
- Idle CH1 volume fades over approximately 285 ms and rises over 67 ms.
- Every two or three cycles, occasionally shift its frequency by one percent;
  reset to the original frequency when the accumulated deviation reaches five
  percent. CH3's original engine cycle and pitch remain unchanged.
- CH1 throttle volume is reduced from 8 to 6 (25%). Idle peaks at 2 instead
  of 3, the closest integer hardware level to 2.25, and falls to zero.
- Accepted left/right volts use `ugras.wav`; turning uses `fordul.wav`.
  Both use CH4, shared with flower/finish, which takes priority.

The versioned 0.91 test1 image above remains available as the performance
baseline. The playable **[0.92 — 8 MiB ROM](build/elma-gbc-v0.92-8m.gbc)**
uses MBC5 and 32 KiB RAM. Audio remains a native pulse/noise approximation
of the original recordings. Physical GBC speaker balance still needs testing.

Validation: all seven functional checks pass, including all 54 level starts,
menus, saving, volt controls, finish audio and Freefall. All 27,447 physics
states still match the baseline. The corrected 0.92 averages **29.82 updates/s**;
77 updates exceed the deadline (0.91 test1: 55), with 189/216 cases passing
throughout. The added audio therefore has a small measured performance cost;
stable 30 FPS is still unfinished. Native PCM, channel priorities, idle drift,
clock wrap and watchdog tests pass. ROM SHA-256:
`03bad0ac2d625603b03b40cf509e333f33411da2feadfa63ff47af20bdb5fb96`.

In 0.90, the rider updates on every physics step and responds
to the body's rotation after a volt. Green scenery is slightly brighter.
This release uses the native fixed-point riding core; the much more precise
Q44/Q46 host experiments described below are separate research. Neither full
PC fidelity nor stable 30 FPS on every course is claimed.

The original-derived CH3 cycles, pitch curve and master gain are retained.
The two-channel engine has quieter, variable idle, no streaming interrupt and
finite hardware watchdogs. Collision sounds consume a reported impact once
per physics step; no extra terrain query or pose projection is used. This
affects sound only.

It includes the 0.74 splash: original logo above native CG Pixel 3x5 platform/
version text, `UNOFFICIAL FAN MADE PORT BY DOX187`, original copyright/author,
website and A/Start prompt. The 0.73 per-frame timer and frozen finish panel,
and 0.72 held volt controls are retained. Both playable filenames include the
version and live directly in `build/`; the previous versioned builds are retained.

The retained 0.90 release has two cartridge builds, both targeting **MBC5 +
32 KiB battery-backed RAM** with the same 54 courses, graphics and physics:

| Build | Scenery | Versioned test image |
|---|---|---|
| **4 MiB** (4,194,304 bytes) | Lossless ZX0 compression | `build/elma-gbc-v0.90-4m.gbc` |
| **8 MiB** (8,388,608 bytes) | Uncompressed, read directly from ROM | `build/elma-gbc-v0.90-8m.gbc` |

The 8 MiB build avoids decompression during scrolling. Both share the same
player/record save layout, compatible with 0.7. The 8 MiB build retains the
four physics-table banks at **477–480**, directly after the scenery, as in
`elma-gbc-v0.7-8m-bankfix.gbc` (previously 508–511). Its final 64 KiB
is unused. All graphics and table bytes are retained. **The same motorcycle
failure was subsequently reported with that 0.7 build on FlashMaster, so the
relocation has not resolved the issue.** Version 0.90 does not change this
bank layout; physical-cartridge verification remains outstanding.

The original 0.7 8 MiB image (`build/elma-gbc-v0.7-8m.gbc`) had an immediate
motorcycle physics failure on FlashMaster. Its full physical cartridge scan
passed banks 1–507 and first failed at **bank 508: expected CRC16 `65FD`, read
`FFF0`** (2026-11-16, source
ROM SHA-256 prefix `dbf763f7f55c`). `FFF0` is also the checksum of a full bank of
`FF` bytes; it suggests blank or incorrectly mapped data, but a CRC alone does
not prove every byte or identify the cause. The reported settings are MBC5,
8M ROM and 32K RAM. This confirms readable nonempty graphics banks above 255;
it does not establish why the final physics-table banks read incorrectly.
Erasing bank 508 to `FF` in the emulator also destabilizes the motorcycle.

Simulating an inaccessible upper ROM half (banks 256–511 reading the
corresponding lower banks) also reproduces a detached wheel on the first
physics step. However, that simulation reads CRC `6F29` at bank 508, different
from the physical `FFF0` result; simple upper-to-lower aliasing is not confirmed.

The 0.6 build required **128 KiB SRAM**. The
[FlashMaster guide](https://ae01.alicdn.com/kf/S2f62136b14a64022bb70b3d32150367f6.pdf)
lists RAM settings only through 32K. Running the same 0.6 ROM with emulated
32 KiB RAM reproduced corrupt Warm Up graphics; 128 KiB rendered correctly.
Version 0.7 replaces the large lookup and relocates the decoded caches and
saves to four RAM banks. Changing the ROM-size setting alone cannot fix the
old SRAM layout.

An early native Game Boy Color version built with
[GBDK-2020](https://gbdk.org/docs/api/index.html), C and SM83 assembly.
**All 54 registered internal levels are selectable:** ride, brake, volt, turn
around, collect apples and reach the flower. Original level geometry, LGR
artwork and an adaptation of the existing original-derived fixed-point
motorcycle physics form its basis.

## What works in 0.90

- Parallel **4 MiB compressed / 8 MiB raw ROMs** containing all 54 courses,
  with a compact graphics lookup and a shared 32 KiB cartridge RAM layout.

- An original-logo title screen with native platform/version, unofficial port
  credit, original copyright/author and website text. A fresh A/Start press
  continues to a separate main menu and Controls screen.
- A level selector with all **54 registered internal levels**, their original
  names and order, page navigation, pause/resume and explicit restart actions.
- Four persistent player profiles, editable ten-character names with a framed
  Game Boy keyboard, and best times for each player on all 54 courses.
- CH3 engine sound using separate original idle/load cycles, reinforced by a
  CH1 exhaust pulse for speaker audibility, with quieter,
  constant idle without throttle. Throttle raises the volume and uses the
  original wheel-speed/pitch curve. Apple, crash and finish sounds use
  original-derived native pulse/noise contours; menu clicks are included.
  Pausing silences the engine.
- Native **CG Pixel 3x5 Mono** text in the level selector and HUD, with a
  four-pixel character advance and no downscaling of the original PC font.
- Riding, acceleration, braking, volts and turning around, with suspension,
  rider movement, **32-bit linear velocities** and swept head collisions.
- Rider integration on every physics step, using the updated body rotation
  after a volt, with exact SM83 coordinate and movement helpers.
- Held left/right volt input with the original shared cooldown, rounded up to
  a physics step. Pause freezes the cooldown and restart clears it.
- Apple collection, gravity-changing apples, killers, crash detection, flower
  completion and advancing to the next course. The HUD shows remaining apples,
  a labelled elapsed time refreshed with every riding frame; A/Start retries
  after a crash. The frozen finish frame shows the measured time, previous
  best, record comparison and next/retry/menu controls.
- Original level geometry and LGR artwork, streamed terrain, independently
  positioned wheels and head, **red apples and white flower petals**.
- A modest brightness lift for green scenery while retaining its original
  artwork and the protected source sky colors.
- Head pattern buffering to prevent uploads from changing the head still on
  screen, and separate terrain/background reduction to avoid invented sky
  colors at terrain edges.
- A reproducible GBDK build and emulator checks for arithmetic, physics state,
  menu navigation, all 54 course starts, scrolling VRAM and protected colors.

## Remaining work and known limits

- **Finish stable 30 FPS.** Some complete-game updates still exceed the
  two-display-frame budget (about 29.86 updates per second). Continue assembly
  and scrolling optimization while preserving direct controls, the current
  physics model and no additional frame queue.
- **Verify complete rides on every course.** All 54 levels have been selected
  and started through actual menu input; this does not establish that every
  level can be completed. Extend contact, high-speed and long-route testing,
  and compare the riding behavior with the original game.
- **Measure frame timing on a real Game Boy Color.** Current timing figures
  come from emulation.
- **Add replay support and an editor.** These are unimplemented. Verify the
  new player and best-time saves on the physical cartridge.
- **Check the new audio on hardware and refine its timbre.** Two representative
  32-sample, 4-bit engine cycles and pulse/noise effects approximate the original
  recordings; they do not reproduce the full PCM, changing exhaust texture or
  start/rev transition. The added CH1 layer deliberately strengthens exhaust
  harmonics; its volume and character need another speaker listening test.
  Music is unimplemented.
- **Review further graphics and animation improvements.** Object animation
  currently uses its first frame; the sky has no parallax and foreground
  pictures do not occlude the rider. Crowded object sprites can flicker under
  the hardware scanline limit, as accepted for this version. Trees, flags and
  barrels are intentionally omitted from rendering.

The physics is adapted from the original-derived fixed-point core; it is not
trajectory-identical to the PC integrator. The detailed differences and
verification limits are described below.

## Planned after 0.90

- **0.91: target stable 30 FPS**, starting with the measured scenery-update
  spikes, while preserving the current physics results and direct controls.
  Check both ROM sizes, all 54 course starts, Freefall and moving views.
- Check the brighter bushes and green decorations on a real Game Boy Color.
- Bring the menu closer to the original game's layout, colors and functions,
  while retaining readable native pixel text on the 160x144 display.
- Verify the relocated **8 MiB** physics tables on FlashMaster, then verify
  scrolling and retained player saves with both ROM sizes, MBC5, 32K RAM and
  Save RAM enabled. Keep the confirmed original bank-508 failure as a regression.
- Continue measuring compressed graphics streaming, including first-use
  decoding and cache misses during fast scrolling. Keep all 54 levels and
  the current physics; discuss any necessary graphics or gameplay
  simplifications before choosing a compromise.

## Physics fidelity research

The intermediate 0.90 release includes the current native rider corrections.
The higher-precision solver remains research: its host results are not the
physics running in the playable ROMs. Version 0.91 targets the existing core's
complete-game timing; the PC-fidelity requirements below remain open.

Acceptance priorities, in the requested order:

1. At least **99.9%** of aligned samples must keep every measured part within
   **1 cm** position, **0.1 degree** angle and **0.01 m per real second** linear
   velocity of the PC reference, with matching collision, apple and finish
   events. Evaluate each case, including both wheel angles; easy cases must not
   hide a failing route.
2. Then evaluate **0.1% relative error**, with explicit absolute tolerances near
   zero. Preserve the direct controls and the 30 Hz gameplay budget.

Integrating the higher-precision solver requires both the fidelity target and
stable 30 FPS. Passing host comparisons alone does not establish a playable
console implementation. Preserve direct controls without an extra frame queue.

The comparison links the original PC physics equations with their actual
headers. Generated test-only copies observe resolved wheel-contact transitions;
their complete numeric state is checked bit for bit against uninstrumented
builds. It uses identical timed controls and the original **0.0055
maximum step plus remainder** schedule at each GBC sampling time. Its native
`double` reference is the project's PC SDL arithmetic profile, not a claim of
bit-identical Windows x87 behavior. Baselines are reconstructed from Git with
their own constants generator; reports include source/library hashes, full
trajectories, shared live windows and event mismatches.

From the repository root:

```sh
python3 console/gbc/test/compare_pc_physics.py \
  --res build-reg/elma.res --baseline-ref 17c1493
python3 console/gbc/test/score_pc_fidelity.py \
  console/gbc/build/pc-comparison-v090/report.json --run both --require-target
```

The current 40-case corpus covers six original courses and controlled
acceleration, braking, suspension, landing, air and volt fixtures, plus an
original-PC Warm Up run that collects the apple and reaches the flower. The rider
now updates each physics step and uses post-volt body rotation. Exact SM83
coordinate/movement helpers reduce the cost, and native/HOST state agreement
is checked. This intermediate correction leaves substantial whole-bike
errors; it does not meet the fidelity target. Further work must address
integration timing, brake/contact behavior and numerical precision.

The contact-enabled comparison observes both wheels' resolved contact counts,
transition order and enclosing frame intervals. All 40 cases have validated
contact coverage; both 0.84 and the current rider correction fail the primary
acceptance requirement in all 40 cases. This is an all-component threshold,
not a percentage estimate of how recognizable the game feels.

Separate arithmetic feasibility studies replay a longer 40-case corpus. Full
float32 arithmetic accepts 84.73% of its 10,203 live samples. The first checked
Q44 fixed variant accepted 92.17%: rounding a segment-length reciprocal tilted
the contact normal even on flat ground. Dividing each segment component directly
by its length fixes that particular bias. Together with the independently
verified rider-spring cancellation, the corrected Q44 variant passes all 40
cases and 10,203 live samples. All 817 ordered wheel-contact transitions also
match the original PC observation times, with instrumentation preserving the
complete underlying state bits.

An independent holdout adds four scripts on every internal course: neutral and
brake for 1,800 samples each, plus two seeded 900-sample control sequences.
Q44 passes 215 of these 216 cases. Q46 also passes 215, accepting 174,552 of
174,564 live samples overall (99.9931%). The remaining case, a minute at rest
on What the Heck, passes only 99.3333%: wheel velocity differs by up to
0.0121 m/s against the 0.01 m/s limit. Pooling easier cases cannot pass the
per-case requirement. Holdout object/terminal events match; its nonfatal contact
coverage has not yet been validated. Pure relative-error diagnostics also
remain separate from the primary absolute-tolerance result.

These studies use host trigonometry and do not establish a native GBC solver.
A separate byte-limb arithmetic ROM passes 2,050 integer-oracle checks, but a
dense 52-bit state product averages 6.80 ms and general wide division averages
34.70 ms in that C implementation. Those costs require substantial
specialization; they are not lower bounds for assembly or a full-game timing
result. The research corpus differs from the production-core comparison above,
and its scores cannot be substituted for that release gate. Versions 0.80
through 0.84 share the same production physics; their changes concern sound.

## Build and run

Requirements: Make, Bash, Python 3, a host C compiler for tests, curl and tar,
plus `elma.res` and `default.lgr` from your own copy of the game. The converters
use numpy and Pillow, and the emulator tests use PyBoy. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
make bootstrap
make 8m ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

The current kernel requires `ROM_MIB=8 PHYS_HZ=30 DAMPER=scheduled`.

The current checkout builds versioned **0.96 development ROMs**. They are not
accepted releases until their complete-game timing and regression checks pass.
The retained 0.90 images below are the last completed intermediate release.

The current default output is **`build/elma-gbc-v0.96-8m.gbc`**. The corrected
scheduled kernel is still too slow; use this development output for diagnostics.
The older versioned ROMs listed above retain their original behavior.
These are CGB-only MBC5 cartridges, not Game Boy
Advance programs; monochrome Game Boy hardware is unsupported. Both use header
type `0x1B` (MBC5+RAM+BATTERY), RAM code `0x03` (32 KiB), and ROM code `0x07`
(4 MiB) or `0x08` (8 MiB).

`make 8m` generates assets in `build/gen-8m`. The earlier 4 MiB and alternative
integration kernels remain in Git history; the current source rejects those
profiles. For an explicit output name, use e.g.
`make ROM_MIB=8 GAME_ROM=build/elma-gbc-v0.96-dev-8m.gbc game` with your resource
paths. Both Make and the standalone builder read `VERSION` for their default
playable filenames. Original rendered tiles are reused when their fingerprints
match; codec and bank-layout mismatches are rejected before linking. The current scheduled Q24
physics tables occupy banks **481–501**. The 8 MiB builder
rejects data in banks 508–511 and verifies that this tail remains unused.

On FlashMaster, select **MBC5**, **32K RAM**, the file's matching **4M or 8M ROM
size**, and enable **Save RAM**. The emulator's battery file or the cartridge's
save mechanism must preserve RAM across sessions. SRAM bank0 B800–BFFF holds
two checksummed save slots; the previous valid slot survives an interrupted
write. Versions 0.7 through 0.90 share saves across both ROM sizes; 0.6's 128 KiB
save files used a different location and are not loaded automatically.

For the reported 8 MiB hardware failure, build a separate cartridge diagnostic:

```sh
.venv/bin/python tools/cartridge_check.py --source build/elma-gbc-v0.84-8m.gbc --out build/elma-gbc-v0.84-8m-check.gbc --first-bank 477 --verify
```

Load the resulting `build/elma-gbc-v0.84-8m-check.gbc` with the same MBC5 / 8M / 32K settings.
It retains every byte of the game's switchable ROM banks and replaces only
ROM0 with a reader. It runs at double speed, first checking all bytes of banks
477–480 (about three seconds including boot in the emulator). **A** scans banks
1–511 (about 5–6 minutes of emulated hardware time); **B** repeats the quick check.
`FAIL` reports the bank and expected/read CRC16 values; `Matches bank 221`,
for example, suggests that bank 477 is reading its lower-half counterpart.
Record the displayed result before drawing a hardware conclusion. CRC16 is an
error detector, not a collision-proof comparison. The diagnostic itself never
enables or writes cartridge SRAM and is not a playable game build. The original
diagnostic is retained as `build/elma-gbc-v0.7-8m-check.gbc`; use `--first-bank
508` when rebuilding it from the original image.

| Button | Riding action |
|---|---|
| A | Gas |
| B | Brake |
| Left / Right | Volt left / right |
| Up | Turn around |
| Select | Open the pause menu; press again to resume |
| Start | Restart the current level, including after a crash or finish |

In Level Select, Up/Down select a course, Left/Right change page, and A/Start
launch it. On the title screen, a fresh A/Start press enters the main menu.
Choose Play, Level Select, Players or Controls; the pause menu offers Resume,
Restart, Level Select and Controls. B returns from a sub-screen, then resumes a paused
ride from the main menu. After finishing, A starts the next course;
after a crash, A or Start retries. After a crash or finish, B or Select opens
the main menu. These actions are shown on the result panel. After finishing,
Up toggles between the frozen gameplay frame and the detailed result screen.

The riding HUD shows apples remaining at the left and a labelled `TIME`
clock at the right. The display refreshes on every riding presentation
(nominally 29.86 Hz), using prebuilt digit-pair tiles so a normal update uploads
just one changed tile. The clock advances with simulated riding time, freezes
while paused or after a result, and resets on retry. Left/right can be held
to repeat volts. Both directions share the original `Ugroturelem = 0.4`
model-second cooldown, approximately **0.916 seconds** on the displayed clock.
The 30 Hz GBC profile waits **28 physics steps, approximately 0.938 seconds**:
the first step strictly beyond that threshold. An early held press fires when
eligible; releasing it before expiry does not queue a volt. Pause freezes the
cooldown and restart clears it. Missed frame deadlines can extend real elapsed
time, as they do for the rest of the simulation.

In Players, Up/Down chooses one of four profiles, A/Start selects it, Select
opens the name editor, and B returns. The editor accepts up to ten uppercase
letters, digits or spaces: arrows move around the large keyboard, A enters
the highlighted key, B deletes, Start saves, and Select cancels. Blank names
are rejected. Renaming keeps the profile’s records. Players can be changed
from the main menu outside a paused ride. Finishing a course saves a new best
time automatically; crashes and slower finishes leave existing records intact.

The finish panel and detailed screen show `TIME`, the previous best, and one
of `FIRST RECORD`, `NEW RECORD`, `BEST MATCHED` or `NO IMPROVEMENT`. Comparison
uses the current player's saved time for that course before replacing a record.
Matching or slower times leave that record intact. The bottom panel occupies
the final 24 screen pixels; scenery and sprites above it remain frozen. Its
extra text tiles reuse only world patterns absent from the visible area.
Returning from the detail screen, retrying or starting the next course rebuilds
the world cache before rendering gameplay again.

Audio uses the GBC wave, pulse and noise channels, serviced by the existing
main loop without a streaming interrupt. `tools/audio_assets.py` selects one
real cycle from each original `harl.wav` idle and `harl2.wav` load loop, limits
them to representable harmonics and quantizes each into CH3's 32 samples / 16
bytes. The cycle changes only at throttle edges, with the DAC off during the
bounded transfer. Steady pitch changes never rewrite wave RAM or retrigger it.

Without gas, the selected idle cycle plays at approximately **103 Hz, 50% wave
level**, independently of wheel speed or braking. With gas, the separate loaded
cycle starts at **57.3 Hz, 100% wave level**, reaching about **111 Hz at the normal
driven-wheel limit** and approaching 114.6 Hz at extreme speed. These preserve
the selected cycles' original duration; the full recordings are nonstationary
and have richer spectra. Their perceived pitch is not just these base rates.
The generated 512-entry table converts native angular velocity to original
radians/model-second before applying `2 - exp(-min(abs(omega)*0.025, 30))`.
Braking changes audio through the physical wheel speed, without a separate
artificial pitch division. The former 96–344 Hz idle-wave transposition is gone.

CH1 uses a **12.5% pulse, volume 3 at idle / 8 under throttle**. Sharing CH3's
period value puts it exactly at the second harmonic: about 206 Hz at idle and
115–229 Hz under throttle. CH3 itself is not transposed. The narrow pulse adds
exhaust harmonics while keeping its second-harmonic amplitude below the original
loaded cycle's fundamental. Its sweep and automatic volume envelope are off;
speed changes update the period without retriggering. Mode changes retrigger
once to apply the new volume. CH1's duty phase survives retriggering, so the
combined peak level can vary with relative phase. Each update refreshes both
channels' 250 ms length watchdogs; both DACs are silenced when the engine stops.

The 0.82 CH3 output levels roughly double engine amplitude while keeping idle
quieter than gas. The physical CGB's analog high-pass filter attenuates the low
engine cycles more than the high menu beep; raw emulator PCM alone misses this
balance difference. The native fixture additionally reports a relative-level
proxy using the [Pan Docs CGB capacitor model](https://gbdev.io/pandocs/Audio_details.html#obscure-behavior).
It does not model the built-in speaker or replace a hardware listening test.

The converter derives the apple pulse contour from `eves.wav`, and crash/finish
noise contours from `torik.wav` / `siker.wav`. It uses the original mixer's
11025 Hz rate, even where the WAV header differs. Four-VBlank control points
describe pitch/noise colour, loudness and hardware envelope; the source-based
durations are 38, 59 and 46 VBlanks respectively. These are native APU
approximations, not full PCM playback. Generated `audio-manifest.json` records
source hashes, cycle selection and effect measurements. Finite hardware lengths
stop sounds if servicing ceases; there is no background music.

Crash/finish now peak at volume 15; the menu remains at 8 and apple at 10, with
master level 6/8 on both outputs. Each noise control point retriggers the 15-bit
LFSR, whose startup requires 15 clocks. Candidate noise rates must start within
one VBlank, leaving most of each four-VBlank control interval audible. The old
128/146 Hz settings took longer than the entire interval and produced silent
crash sections. This constraint adjusts noise colour offline, with no additional
cartridge CPU cost; engine waveform, pitch and effect durations are preserved.

`make bootstrap` installs pinned GBDK **4.5.0**, with SHA-256 verification,
under ignored `.toolchain/`. It supports macOS arm64/x86_64 and Linux
aarch64/x86_64 and does not modify the shell profile. `GBDK_HOME=/path/to/gbdk`
selects an existing SDK. The Makefile supports macOS Make 3.81 and prefers
`.venv/bin/python`; override it with `PYTHON=/path/to/python` if needed.

Without explicit data paths, it looks for `../../elma.res` and
`../../lgr/default.lgr`. Keep the SDK, virtual environment, generated assets,
original game data and ROMs out of source commits; their working directories
are ignored by Git.

## Original data and graphics

The host converters reuse the existing readers and PC rendering models under
[`../snes/tools`](../snes/tools). All internal levels present in the resource
file are preserved in `build/gen/levels.json`, including original polygon,
object and picture records. Registered data supplies all 54 playable runtime
levels, in their original order and with their original names.

Collisions use the original non-grass polygon edges, subdivided for local
fixed-point contact queries and indexed by spatial cells. Dense cells receive
an additional subdivision without dropping edges. Collision queries use the
original geometry independently of the visual tile map. Source exports use
Q16.16 meters with y pointing upward.

The scenery reconstructs the PC graphics at 48 pixels per meter and reduces
them to a provisional **12 pixels per meter**, using seven four-color background
palettes. Foreground and background are reduced separately so terrain edges do
not invent a third sky color. Lossless horizontal/vertical flip deduplication
reduces storage; a **444-pattern cache** streams entering strips while retaining
all patterns still visible. Idle CPU time prepares the next offscreen row or
column, retaining the same 399 current cells until the camera enters the new
tile. Temporary references cover at most 438 cells; reversal discards the
prediction safely. This preparation adds no simulation or presentation frame.
The discontinued 0.91 development 4 MiB layout stores ZX0 blocks of 32 patterns
(512 bytes) and three independent 512-byte planes per 32x16 map chunk. Five
decoded map chunks use SRAM bank1; 32 decoded pattern blocks use banks2–3.
Preparation can stop between cold planes; a complete cached map gathers all
three planes together. Small courses that fit are preloaded with the LCD off.
Each compressed stream carries its exact native decode cost, rounded up to
double-speed scanlines. Idle preparation uses that cost plus a separate margin
for bank switching, cache work and interrupts. The build verifies the decoder
source hash before accepting these costs.
The retained 0.90 release uses 1,024-byte pattern and 1,536-byte map blocks.
The 8 MiB ROM
reads uncompressed patterns and maps directly, without these decoded caches.
It uses SRAM banks1–3 as a direct table for up to 12,288 pattern IDs. All but
one course fit; the larger Bowling course uses the linked bank0
lookup. Every lookup restores SRAM bank0, and the player save region is shared
with the retained earlier builds.

Both builds use this bank0 layout:

| Address | Purpose |
|---|---|
| A000–A7FF | 1,024 fallback lookup bucket heads |
| A800–AEEF | 444 fallback entries storing full pattern IDs and chain links |
| AEF0–AFFF | Reserved |
| B000–B7FF | 32x32 viewport slot mirror |
| B800–BFFF | Two persistent player/record save slots |

The lookup retains full IDs and resolves hash collisions without discarding
artwork. Background preparation stops between bounded work units. Cold block
decoding can extend level loading and scrolling updates, so the compressed
build still needs timing optimization. The remaining bank0 VRAM patterns hold
the killer sprites. Cartridge SRAM banks and VRAM banks are separate memories.

The build uses GBDK's `gbcompress --alg=zx0` and an optimized SM83 decoder.
ZX0 was created by Einar Saukas. Its decompressor license accompanies the port
in [`licenses/ZX0.txt`](licenses/ZX0.txt).
Every generated block is decoded on the host and compared byte-for-byte with
its source before packing. `test/check_graphics.py` also checks every block
through the native decoder, including SRAM guards and bank restoration.

Trees (`tree1`–`tree5`), flags and barrels are omitted from rendering. The original
picture records remain in the exported source data, as do the original polygons
and game objects. Grass, bushes and terrain texture/mask records are retained.
The sky is currently baked, without parallax or foreground-picture occlusion.

The menu retains the original background texture and helmet cursor. Text uses
[CG Pixel 3x5 Mono](fonts/README.md) at its native pixel size, with two characters
per tile. The HUD uploads only character pairs that changed. The
motorcycle and rider are rendered from the original LGR parts at **32
angles, three rider-compression poses and two facing directions**. The wheels
and head follow their independent physical positions; changed patterns are
uploaded through CGB DMA. The head updates every physics step with half-pixel
animation phases and separate front/back patterns so an upload cannot alter
the head still displayed at the previous position. This discrete animation is
an approximation of the original articulation. Global 8×16 sprite mode leaves
13 OAM entries for the bike and 26 for course objects. The riding VRAM layout is:

| VRAM allocation | Pattern indices |
|---|---|
| Background, bank 0 | 0–251 |
| Killers, bank 0 | 252–255 |
| Background, bank 1 | 0–191 |
| Bike body, wheels and head buffers, bank 1 | 192–219 |
| HUD text cells, bank 1 | 220–239 |
| Reserved, bank 1 | 240–247 |
| Apple and flower, bank 1 | 248–255 |

**Apples must be red and flower petals must be white.** They retain their
original outlines with dedicated object palettes, protected from scenery palette
fitting. Their first animation frames are used for now. Objects remain separate
sprites. Crowded areas cycle their sprite priority and can flicker at the
hardware's ten-sprites-per-scanline limit.

## Physics and the 30 FPS profile

The riding engine adapts the complete fixed-point C core of the existing NES
version, itself derived from `LEPTET.CPP`, `BEALLIT.CPP` and the original contact
code. It includes the body and both wheels, suspension, motor/brake reactions,
rolling contacts, rider movement and swept head-collision death. Linear
velocities retain 32-bit precision for fast courses such as Freefall. The GBC adaptation
uses banked code, cell-indexed collision data, SM83 arithmetic and exact lookup
tables; the tables accelerate products without approximating their results.

The **exponential damper** profile integrates the isolated suspension damper's
velocity impulse over the longer update interval. It retains the suspension
spring coefficient, physical damping coefficient and masses, applying the
corresponding reaction to the body. It is not an exact solution of the complete
coupled motorcycle and is numerically different from the PC integrator. Fixed
point, coarser stepping and the inherited discrete brake/contact solver also
mean PC trajectory equivalence is not claimed.

The original clock is **182 ticks per second scaled by `0.0024`** to obtain
target simulation time. Its solver uses a **`0.0055` step cap with a shorter
final step**, not a fixed 182 Hz physics rate. The GBC profile advances the same
game-time scale at nominal 30 updates per second, synchronized to every other
display frame (about 29.86 Hz on the GBC clock).

Historical `PHYS_HZ=60 DAMPER=explicit` comparisons do not establish a complete
60 FPS game and require the corresponding historical sources. The standalone
`physics-probe.gbc` is an older suspension diagnostic, not the riding solver or
a measure of full-game performance.

## Verification

```sh
make check-scheduled ELMA_RES=/path/to/elma.res ELMA_LGR=/path/to/lgr/default.lgr
```

`make check-scheduled` runs exact native/HOST state comparison, original-PC
rebound and braking trajectories, audio/control tests and complete-game checks.
It retains zero allowed deadline misses; current timing/cadence failures block
release. Each native run keeps an immutable source snapshot. The older
`make check` sequence below targets the historical one-step kernel and has not
been fully migrated to scheduled units.

The historical `make check` builds the playable and diagnostic ROMs, checks conversion, ROM
metadata, actual scrolling VRAM, protected object colors and the diagnostic
arithmetic. Native SM83 tests check the production multiplication, coefficient,
division, square-root, coordinate-bound and video helpers against independent
references, including lookup-table bytes and ROM-bank restoration.

The controller-only regression exercises controls, braking, pause,
head-collision death and restart, then attempts an apple/flower route.
It verifies actual tile, attribute and pattern VRAM across
map/chunk boundaries. It defaults to **zero allowed deadline misses** and does
not inject completion or object state into game RAM. Its default Warm Up
controller currently needs retuning: it also fails on the retained 0.72 ROM.
The 0.73 result checks below use an explicit contact fixture and do not claim
a new controller-completed course.

The native trajectory fixture compares all 109 internal and 52 public state
bytes after each call against the HOST implementation and a frozen reference.
It covers a Warm Up completion, fast Freefall and braking. This establishes
that arithmetic optimizations preserve the selected fixed-point model; it is
not a comparison against the PC integrator. Separate real-ROM checks select
all 54 courses through buttons and verify starts, object metadata, HUD, actual
VRAM, scenery palettes and moving head buffers. A diagnostic run with an
explicitly relaxed deadline budget is marked as failing the performance target.

Separate title and audio fixtures verify the complete splash framebuffer,
fresh button presses, audible PCM output, pitch changes, finite effects,
pause muting and ROM-bank restoration. The complete-ROM frontend check covers
title-to-menu navigation, Controls, course selection, pause/resume and restart.
The 0.74 splash fixture also checks all six native footer rows against the
source BDF glyphs, including the version, DOX187 credit and original copyright.

For 0.90, both complete ROMs pass frontend, held-volt, finish-audio and
player/record checks, including save reload in both directions between sizes.
The clock check verifies 1,890 exact presentations, minute rollover and one
LCD update every two display frames. All 54 course starts and the complete
433-step no-input Freefall pass their functional checks: source scenery,
object colors, moving head buffers, 32-bit velocities and camera tracking.
The strict timing assertions still fail, as recorded below. These are the
baseline for 0.91, not a stable-30-FPS claim.

| 0.90 deadline misses | 4 MiB ZX0 | 8 MiB raw |
|---|---:|---:|
| 54 course starts, 12 idle updates each | 13 | 6 |
| No-input Freefall | 54 | 13 |
| 300-step Warm Up driving profile | 4 | 0 |

The 4 MiB native decoder independently checks all 4,800 unique scenery blocks
(6,034,992 decoded bytes), with zero byte, guard or bank-restoration failures.
The splash pixel check also passes. Reports are under
`build/v090-release-checks` and `build/splash-v090-release`; the two versioned
ROMs remain directly in `build`. Physical-cartridge testing is still needed.

For 0.84, the native fixture verifies CH1 volume 3 at idle and volume 8 under
load, including the emitted pulse PCM. Pitch, duty, original CH3 cycles,
watchdogs and effect checks pass; the maximum audio update remains 2,844 cycles.
Both complete ROMs pass frontend checks covering the new levels, throttle/coast,
pause/resume and version text. The new balance still needs a hardware audition.

For 0.83, the unchanged CH3 cycle shapes and pitch curve pass independently
with CH1 temporarily excluded from the fixture mixer. The isolated CH1 PCM
has **12.48% duty** and exactly twice the CH3 rate within measurement precision.
Both channels trigger only on starts/mode changes, survive 30 Hz servicing and
stop on pause/finish or after a 15-VBlank watchdog timeout. The CGB filter
proxy measures **8.98 dB more idle, 11.28 dB more low-gas and 10.00 dB more
fast-gas output** than 0.82; this is not a physical speaker measurement.
Engine-only updates take **816–1,132 cycles**, with a **2,844-cycle** maximum
including a mode switch and effect. Both complete ROMs pass frontend and
finish-audio checks; the 0.83 splash also passes its pixel check. The 300-step
controller profiles retain **four deadline misses for 4 MiB, zero for 8 MiB**.

For 0.82, unnormalized native PCM measured engine RMS increases of **5.85 dB
under throttle / 6.20 dB at idle**, crash **4.04 dB** and finish **3.38 dB**;
menu/apple levels are unchanged. The CGB HPF proxy estimates **7.40 dB** more
crash output after removing silent slow-LFSR intervals. Noise control-point
checks at both 30 and 60 Hz catch the previously silent sections.
The original engine cycles/pitches, finite effects and IRQ/bank checks still
pass. The largest audio update remains **2,552 cycles**. Both complete ROMs
passed frontend and finish-audio checks, and the 0.82 splash text passed its
pixel check. The 300-step controller profiles exactly match 0.81's measured
costs: **four deadline misses for 4 MiB, zero for 8 MiB**. Physical hardware
volume balance remains to be checked; the filter proxy omits speaker response.

For 0.81, all 65,536 speed arguments were checked against the original formula
with independently converted physics units; the maximum lookup plus hardware
rounding error was below **0.607 Hz**. Native PCM checks cover both cycle shapes,
source playback rates, speed boundaries, rapid throttle changes, effect/engine
overlap, muting, watchdog, IRQs and ROM-bank restoration. Every observed wave-RAM
write occurs with the DAC off. Steady engine updates take **596–924 cycles**;
the largest update including a throttle transition and an effect is **2,552
cycles**. Both complete ROMs passed frontend, finish-audio and splash checks.
The 300-step driving profile retains **four deadline misses for 4 MiB and zero
for 8 MiB**, as in 0.80. These results do not establish physical-cartridge sound
quality or stable 30 FPS on every course.

For 0.80, the same splash check passed with the new version label. The native
audio fixture captured 48 kHz PCM at both 30 and 60 Hz service rates. It verified
the engine waveform (0.9957 correlation to the quantized cycle), continuous
87.93 Hz idle, throttle/coast changes, only one trigger during continuous
running, no active wave-RAM writes, effect durations/priority, skipped updates,
timer wrap, the hardware watchdog and bank/IRQ preservation. The largest
measured `audio_update` was **1,240 cycles**, including simultaneous engine and
apple sound, versus 4,084 in the previous fixture; engine-only calls took
620–788 cycles. These are emulator measurements, not a listening comparison.

Both complete 0.80 ROMs passed frontend, player/record and cross-size save
reload checks. `test/check_finish_audio.py` also verifies audible onset, body
and tail after the frozen panel is visible, engine muting, and a finite stop.
It uses the explicit flower-contact fixture described below. A 300-step
controller-only driving profile retained the 0.74 deadline-miss counts:
**zero for 8 MiB, four for 4 MiB**. Real-cartridge audio quality and stable
30 FPS across all courses remain to be verified.

Both 0.72 ROMs passed the frontend check with continuous quiet idle PCM, throttle
volume and return to idle while coasting. The native audio fixture measured
87.93 Hz idle over 1.205 seconds and verified uninterrupted PCM between 30 Hz
updates, no-gas braking, throttle return, mute/resume, effects and bank restoration.
`test/check_volt_input.py` drives Freefall through actual controller input and
observes accepted physics commands without writing guest state. Both ROMs passed
held repeats in both directions, the shared 28-step cooldown, early held/released
input, pause and restart. These checks do not establish physical-cartridge behavior.

`test/check_save.py` compiles the production save module for the SM83 and
tests battery-file reboots, player/course isolation, faster-time replacement,
invalid requests, interrupted writes, CRC rejection and generation rollover.
It also checks that the graphics SRAM banks remain untouched. The 32 KiB run
passed 47 fresh boots, including 12 interrupted-write cases.

`test/check_players.py` drives the real name keyboard, selection, timer, pause,
crash and A retry through buttons, then reloads the battery file in a fresh
emulator. Its finish check supplies an unlocked-flower contact to exercise the
normal result/save path; it does not claim a controller-completed course.
For 0.73, both sizes passed all four finish comparisons, frozen scenery/sprite
preservation, result/detail toggling, next/retry/menu controls, and save reload
in both directions between ROM sizes. Each clock run checked 1,890 exact
presentations including minute rollover, with 90 actual LCD changes in 180
display frames and no idle deadline misses. A 300-step driving profile retained
the 0.72 deadline-miss counts: zero for 8 MiB and four for 4 MiB. The stable
30 FPS target across all courses and physical-cartridge save test remain outstanding.
The 32 KiB native cache fixtures each passed 3,031 verified views for raw and
compressed graphics. All 2,048 save bytes survived, requested RAM banks stayed
within 0–3, and bank3 cache eviction/reload was checked through address BFFF.

Both complete 0.7 ROMs passed all 54 course starts and the frontend/player
checks under a 32 KiB RAM configuration. Battery saves loaded in both
directions between the two ROM sizes. These are emulator results, not a
physical FlashMaster test or proof that every course can be completed.

| 0.7 diagnostic | 4 MiB ZX0 | 8 MiB raw |
|---|---:|---:|
| Longest course load, display frames | 75 | 21 |
| Deadline misses across 54 course starts | 13 | 4 |
| Deadline misses in no-input Freefall | 52 | 10 |

The relocated 8 MiB build passed 648 native coefficient vectors, all 54 course
starts and Freefall with the same 4/10 deadline-miss counts. Byte comparisons
confirm that banks 1–476 and all moved physics tables are unchanged; ROM0 only
changes the coefficient bank immediate and global checksum. The cartridge
diagnostic passed all 511 switchable banks and rejected a simulated alias.
The physical report for `elma-gbc-8m.gbc` still describes the same failure;
that file is byte-identical to `elma-gbc-v0.7-8m-bankfix.gbc`.

A separate rebuild of all 517 sources without cached objects produced the
same SHA-256 (`1eb65d4be66b785bdbb81147ddcb64f373268b2bcb57d8c195664d501f877049`).
Independent checks matched 453 generated byte arrays to their linked ROM
offsets and verified headers, checksums, coefficient descriptors and ROM-bank
bounds. These checks found no static packing/linking defect; they do not rule
out a runtime banking or SRAM problem on hardware. The standalone cartridge
reader replaces ROM0 and never exercises the game's SRAM-dependent runtime.

The 8 MiB build is faster in the emulator. Both still miss the strict stable-30-FPS
target; the diagnostic runs explicitly allow deadline misses while verifying
graphics and physics. All 4,800 unique compressed
graphics blocks decoded exactly with SRAM guards on the 32 KiB fixture, and
both coefficient placements passed 648 native vectors plus exhaustive host
checks without bank-restoration failures.

Results, ROM hashes, timing traces and screenshots are written under
`build/playtest/`; conversion and diagnostic results use
`build/verification.json`. Emulator results do not establish complete PC
trajectory parity.

`build/elma-gbc-viewer.gbc` remains as a graphics inspection ROM: D-pad pans,
A pans faster, B mirrors the illustration, Select hides/shows it and Start
returns to the start. Its static `VIEW` scene is separate from the playable ROM.

Toolchain references are the
[GBDK coding guidelines](https://gbdk.org/docs/api/docs_coding_guidelines.html)
and [Pan Docs](https://gbdev.io/pandocs/).
