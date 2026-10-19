-- External level menu on a disc image, run by test/ext_menu_test.py.
-- Walks from the intro (name entry) to Play, collections, External Levels with
-- the pad, measures how long the list takes to appear, and then (scenario
-- "lgr") starts the only level on the disc, which names an LGR that is not
-- on the disc: the "LGR file not found" dialog must be answered with the pad
-- and the level must start. Arguments: scenario=list|lgr, shots=PREFIX.

-- The emulator's output is long and the harness keeps only its beginning and
-- end, so the test's own messages also go to a file (arg log=PATH).
local logfile = elma.args.log and io.open(elma.args.log, "a")
local function say(text)
    print(text)
    if logfile then logfile:write(text, "\n") logfile:flush() end
end

local scenario = elma.args.scenario or "list"
local dbg = elma.sym("psx_debug")
if not dbg then say("FAIL: symbol psx_debug not found") PCSX.quit(1) end
local shots = elma.args.shots
local function shot(name) if shots then elma.screenshot(shots .. name .. ".ppm") end end
local CPU_HZ = 33868800

local function dbg_state()
    return {magic = elma.u32(dbg), presents = elma.u32(dbg + 4), game_frames = elma.u32(dbg + 8),
            menu_chars = elma.u32(dbg + 12), errors = elma.u32(dbg + 36)}
end
local function now_seconds() return tonumber(PCSX.getCPUCycles()) / CPU_HZ end

local ffi = require("ffi")
-- True when the first row of the external list ("PA26LE01.LEV", yellow text
-- from x=200 to 435) is on the display: in the collections menu that part of
-- the row is empty (the first entry, "Tutorial", ends at x=295).
local function list_visible()
    local ss = PCSX.GPU.takeScreenShot()
    if ss.width ~= 640 or ss.height ~= 480 then return false end
    local data = tostring(ss.data)
    local bpp = (#data >= ss.width * ss.height * 3) and 3 or 2
    local yellow = 0
    for y = 94, 112, 2 do
        for x = 380, 430, 2 do
            local o = (y * ss.width + x) * bpp
            local r, g, b
            if bpp == 3 then
                r, g, b = data:byte(o + 1), data:byte(o + 2), data:byte(o + 3)
            else
                local v = data:byte(o + 1) + data:byte(o + 2) * 256
                r, g, b = (v % 32) * 8, (math.floor(v / 32) % 32) * 8, (math.floor(v / 1024) % 32) * 8
            end
            if r > 180 and g > 180 and b < 110 then yellow = yellow + 1 end
        end
    end
    return yellow >= 12
end

local steps = {
    {name = "intro", button = "CROSS"},
    {name = "name: first letter", button = "RIGHT"},
    {name = "name: enter", button = "CROSS"},
    {name = "main menu: Play", button = "CROSS"},
    {name = "collections: row 2", button = "DOWN"},
    {name = "collections: row 3", button = "DOWN"},
    {name = "collections: row 4", button = "DOWN"},
    {name = "collections: row 5", button = "DOWN"},
    {name = "collections: row 6, External Levels", button = "DOWN"},
}
local step, phase = 0, "boot"
local settled_at
local deadline = 9000
local press_frame, chars_before, presents_before
local t_press, last_present_time, last_presents, max_gap, gap_at, list_time
local shown_at, title0, title1, changed_at
local answers = 0

local function finish(ok, text)
    say(string.format("%s: %s", ok and "PASS" or "FAIL", text))
    shot(ok and "pass" or "fail")
    PCSX.quit(ok and 0 or 1)
end

-- An error in the handler would be printed again at every frame:
local function guarded(handler)
    return function(n)
        local ok, err = xpcall(handler, function(e) return tostring(e) .. "\n" .. debug.traceback("", 2):sub(1, 600) end, n)
        if not ok then
            say("LUA ERROR: " .. tostring(err))
            PCSX.quit(99)
        end
    end
end

elma.on_frame(guarded(function(n)
    local s = dbg_state()
    if s.errors > 0 then return finish(false, "the game stopped with an error") end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end

    if phase == "boot" then
        if s.magic == 0x454C4D41 and s.presents >= 3 then
            say(string.format("frame %d: first pictures shown", n))
            step = 1
            phase = "press"
            deadline = n + 3000
        end
    elseif phase == "press" then
        chars_before, presents_before = s.menu_chars, s.presents
        elma.press(1, steps[step].button)
        press_frame = n
        phase = "release"
    elseif phase == "release" then
        if n >= press_frame + 6 then
            elma.release(1, steps[step].button)
            phase = "taken"
        end
    elseif phase == "taken" then
        local drawn = s.presents >= presents_before + 4
        if s.menu_chars > chars_before and drawn then
            say(string.format("frame %d: %s done", n, steps[step].name))
            settled_at = n + 120
            phase = "settle"
        elseif n > press_frame + 600 and s.menu_chars == chars_before then
            phase = "press"
        end
    elseif phase == "settle" then
        -- the next screen may still be loading: wait until frames are drawn
        -- steadily again and two more seconds have passed
        if n >= settled_at and s.presents >= presents_before + 8 then
            if step == #steps then
                shot("collections")
                -- Enter on the last row: the list is built
                chars_before, presents_before = s.menu_chars, s.presents
                elma.press(1, "CROSS")
                t_press = now_seconds()
                press_frame = n
                last_present_time, last_presents = t_press, s.presents
                max_gap, gap_at = 0, 0
                phase = "ext_release"
                deadline = n + 12000
            else
                step = step + 1
                phase = "press"
                deadline = n + 3000
            end
        elseif n >= settled_at then
            presents_before = math.min(presents_before, s.presents - 8)
        end
    elseif phase == "ext_release" then
        if n >= press_frame + 6 then
            elma.release(1, "CROSS")
            phase = "ext_wait"
        end
    elseif phase == "ext_wait" then
        local t = now_seconds()
        if s.presents ~= last_presents then
            local gap = t - last_present_time
            if gap > max_gap then max_gap, gap_at = gap, t - t_press end
            last_present_time, last_presents = t, s.presents
        end
        if n % 3 == 0 and list_visible() then
            shown_at = t - t_press
            shot("list")
            say(string.format("TIMING: Enter on External Levels until the list is on the screen: %.2f s (longest gap between pictures %.2f s at %.2f s)",
                shown_at, max_gap, gap_at))
            if scenario == "list" then
                return finish(true, string.format("the external list appears after %.2f s", shown_at))
            end
            -- scenario lgr: one level on the disc; Enter starts it
            chars_before, presents_before = s.menu_chars, s.presents
            elma.press(1, "CROSS")
            press_frame = n
            shown_at = nil
            phase = "lvl_release"
            deadline = n + 9000
        end
    elseif phase == "lvl_release" then
        if n >= press_frame + 6 then
            elma.release(1, "CROSS")
            phase = "lvl_wait"
            press_frame = n
        end
    elseif phase == "lvl_wait" then
        if s.game_frames >= 3 then
            shot("level")
            return finish(true, "the level started after " .. answers .. " answer(s) with the pad")
        end
        -- The level loads (the dialog comes while it does); a picture that
        -- stays is answered with Enter, a few times at most.
        if n >= press_frame + 900 and answers < 3 then
            shot("dialog" .. answers)
            say(string.format("frame %d: the level has not started: answering with Enter (the dialog is in dialog%d)",
                n, answers))
            answers = answers + 1
            elma.press(1, "CROSS")
            press_frame = n
            phase = "dialog_release"
        end
    elseif phase == "dialog_release" then
        if n >= press_frame + 6 then
            elma.release(1, "CROSS")
            phase = "lvl_wait"
            press_frame = n
        end
    end
end))
