-- PAL/NTSC test of the game on the PS1, run by test/video_test.py.
-- Forces the video mode (psx_video_force, read by ddinit; 1 NTSC, 2 PAL,
-- 0 the emulator's own), lets the menu run and compares, over the same
-- stretch of emulated CPU cycles: the vertical blanks (50 or 59.94 a second),
-- the game's stopper (mv_stopperido: 182 ticks a second whatever the mode).
-- Arguments: force=0|1|2, frames=N (frames of the measurement), shot=PATH.
-- See test/video_level_test.lua for the same in the game view.

local force = tonumber(elma.args.force or "0")
local frames = tonumber(elma.args.frames or "400")
local dbg = elma.sym("psx_debug")
local fv = elma.sym("psx_video_force")
if not dbg or not fv then
    print("FAIL: symbols psx_debug / psx_video_force not found")
    PCSX.quit(1)
end
local CPU_HZ = 33868800

-- psx_debug: see src/psx_platform.cpp (stopper_x1000 at +48, vblanks +52, pal +56)
local function snapshot()
    return {
        cycles = tonumber(PCSX.getCPUCycles()),
        stopper = elma.u32(dbg + 48) / 1000.0,
        vblanks = elma.u32(dbg + 52),
        pal = elma.u32(dbg + 56),
        presents = elma.u32(dbg + 4),
    }
end

-- psx_debug is refreshed at every present, so a measurement starts and ends
-- at a frame in which the present counter has just moved.
local first, started, last_presents
local boot_frame

-- An error in the handler would be printed again at every frame:
local function guarded(handler)
    return function(n)
        local ok, err = xpcall(handler, function(e) return tostring(e) .. "\n" .. debug.traceback("", 2):sub(1, 600) end, n)
        if not ok then
            print("LUA ERROR: " .. tostring(err))
            PCSX.quit(99)
        end
    end
end

elma.on_frame(guarded(function(n)
    -- The mode is chosen in ddinit: write the override while the program
    -- has started but not yet shown anything.
    if force ~= 0 and elma.u32(dbg) == 0x454C4D41 and elma.u32(dbg + 4) == 0 then
        elma.write_u32(fv, force)
    end
    if elma.u32(dbg + 36) > 0 then
        print("FAIL: the game stopped with an error")
        PCSX.quit(1)
    end
    local presents = elma.u32(dbg + 4)
    local moved = presents ~= last_presents
    last_presents = presents
    if not started and moved and elma.u32(dbg) == 0x454C4D41 and presents >= 3 then
        started = true
        boot_frame = n
        first = snapshot()
    end
    if started and n >= boot_frame + frames and moved then
        local last = snapshot()
        local seconds = (last.cycles - first.cycles) / CPU_HZ
        local vhz = (last.vblanks - first.vblanks) / seconds
        local shz = (last.stopper - first.stopper) / seconds
        print(string.format("MEASURE pal=%d seconds=%.3f vblank=%.3f Hz stopper=%.3f ticks/s presents=%d",
            last.pal, seconds, vhz, shz, last.presents - first.presents))
        if elma.args.shot then elma.screenshot(elma.args.shot) end
        local want_pal = (force == 2) and 1 or 0
        local ok = last.pal == want_pal and math.abs(shz - 182) < 0.2
        if force == 2 then ok = ok and math.abs(vhz - 50) < 0.3 end
        if force == 1 then ok = ok and math.abs(vhz - 59.94) < 0.3 end
        print(ok and "PASS" or "FAIL")
        PCSX.quit(ok and 0 or 1)
    end
end))
