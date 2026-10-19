-- PAL/NTSC test in the game view, run with test/pcsx.py like video_test.lua:
-- forces the video mode (psx_video_force), walks to Warm Up with the pad,
-- leaves the bike idle for `frames` frames and compares, over the same
-- emulated CPU cycles, the vertical blanks, the frames of the game view and
-- the game's stopper (182 ticks a second in both modes).
-- Arguments: internal_steps=BUTTON,..., force=1|2, frames=N, shot=PATH.

-- LuaJIT traces of the emulator's frame callbacks can overflow its stack.
if jit then jit.off() end
local logfile = elma.args.log and assert(io.open(elma.args.log, "w"))
local function say(text)
    print(text)
    if logfile then logfile:write(text, "\n"); logfile:flush() end
end
local force = tonumber(elma.args.force or "0")
local frames = tonumber(elma.args.frames or "480")
local dbg = elma.sym("psx_debug")
local fv = elma.sym("psx_video_force")
if not dbg or not fv then print("FAIL: symbols not found") return PCSX.quit(1) end
local CPU_HZ = 33868800

local function snapshot()
    return {cycles = tonumber(PCSX.getCPUCycles()), stopper = elma.u32(dbg + 48) / 1000.0,
            vblanks = elma.u32(dbg + 52), pal = elma.u32(dbg + 56), game = elma.u32(dbg + 8),
            presents = elma.u32(dbg + 4)}
end

local steps = {"CROSS", "RIGHT", "CROSS", "CROSS"}
for button in assert(elma.args.internal_steps, "internal_steps must come from the resource layout"):gmatch("[^,]+") do
    steps[#steps + 1] = button
end
local step, phase = 0, "boot"
local press_frame, chars_before, presents_before, first
local last_game, moved_frame, game_advanced_at
local quitting = false

-- An error in the handler would be printed again at every frame:
local function guarded(handler)
    return function(n)
        if quitting then return end
        local ok, err = xpcall(handler, function(e) return tostring(e) .. "\n" .. debug.traceback("", 2):sub(1, 600) end, n)
        if not ok then
            say("LUA ERROR: " .. tostring(err))
            quitting = true
            PCSX.quit(99)
        end
    end
end

elma.on_frame(guarded(function(n)
    if n > 18000 then
        quitting = true
        say("FAIL: game video measurement timed out in " .. phase)
        return PCSX.quit(1)
    end
    if force ~= 0 and elma.u32(dbg) == 0x454C4D41 and elma.u32(dbg + 4) == 0 then
        elma.write_u32(fv, force)
    end
    if elma.u32(dbg + 36) > 0 then
        quitting = true
        print("FAIL: the game stopped with an error")
        return PCSX.quit(1)
    end
    local presents, menu_chars, game = elma.u32(dbg + 4), elma.u32(dbg + 12), elma.u32(dbg + 8)
    if game ~= last_game then game_advanced_at = n end
    if phase == "boot" then
        if elma.u32(dbg) == 0x454C4D41 and presents >= 3 then step, phase = 1, "press" end
    elseif phase == "press" then
        chars_before, presents_before = menu_chars, presents
        elma.press(1, steps[step])
        press_frame, phase = n, "release"
    elseif phase == "release" then
        if n >= press_frame + 6 then elma.release(1, steps[step]) phase = "taken" end
    elseif phase == "taken" then
        local drawn = step == #steps or presents >= presents_before + 4
        local waited = step ~= 1 or n >= press_frame + 150
        if menu_chars > chars_before and drawn and waited then
            say(string.format("VIDEO frame %d: menu step %d taken", n, step))
            if step == #steps then phase = "loading" else step = step + 1 phase = "press" end
        elseif n > press_frame + 600 and menu_chars == chars_before then
            phase = "press"
        end
    elseif phase == "loading" then
        if game >= 3 then
            say(string.format("VIDEO frame %d: game running", n))
            -- Gas alone can kill the bike before a measurement ends. Idle
            -- physics keeps the real game loop and clock running throughout.
            phase, last_game = "wait_move", game
        end
    elseif phase == "wait_move" then
        -- measure from a frame in which the game view has just moved on
        if game ~= last_game then first = snapshot() moved_frame = n phase = "run" end
    elseif phase == "run" then
        if n > game_advanced_at + 120 then
            quitting = true
            say("FAIL: game stopped advancing during the video measurement")
            return PCSX.quit(1)
        end
        if n >= moved_frame + frames and game ~= last_game then
            local last = snapshot()
            local seconds = (last.cycles - first.cycles) / CPU_HZ
            local vhz = (last.vblanks - first.vblanks) / seconds
            local ghz = (last.game - first.game) / seconds
            local shz = (last.stopper - first.stopper) / seconds
            say(string.format("MEASURE pal=%d seconds=%.2f vblank=%.2f Hz game view=%.2f frames/s stopper=%.3f ticks/s",
                last.pal, seconds, vhz, ghz, shz))
            if elma.args.shot then elma.screenshot(elma.args.shot) end
            local want_pal = force == 2 and 1 or 0
            local want_hz = want_pal == 1 and 50 or 59.94
            local ok = last.pal == want_pal and math.abs(shz - 182) < 0.4
                and math.abs(vhz - want_hz) < 0.4 and ghz > 0.5 * vhz
            say(ok and "PASS" or "FAIL")
            quitting = true
            PCSX.quit(ok and 0 or 1)
        end
    end
    last_game = game
end))
