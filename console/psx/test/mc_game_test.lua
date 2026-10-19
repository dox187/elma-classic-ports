-- Memory card test of the game on the PS1, run by test/mc_game_test.py (two
-- runs on the same card image). Arguments: run=1|2, shots=PREFIX.
--
-- Run 1 (fresh card): enters a name and saves it in the menu, starts Warm Up
-- with the clock held, marks the state as saved during the level, and checks
-- that the card write waits until Select returns to the menu. Back at Main
-- Menu keeps the game running. An optional physics script finishes the level.
-- Run 2 (the same card, a new emulator): the player, and the best time when
-- a finish script was used, must return from the card without name entry.

-- The emulator's output is long and the harness keeps only its beginning and
-- end, so the test's own messages also go to a file (arg log=PATH).
local logfile = elma.args.log and io.open(elma.args.log, "a")
local function say(text)
    print(text)
    if logfile then logfile:write(text, "\n") logfile:flush() end
end

if jit then jit.off() end -- (a trace of the frame handler overflowed the stack once)
local run = tonumber(elma.args.run or "1")
local dbg = elma.sym("psx_debug")
local mcd = elma.sym("psx_memcard_debug")
local state_ptr = elma.sym("State")
local key_count = elma.sym("_ZN12_GLOBAL__N_19key_countE")
local freeze = elma.sym("gpu_test_freeze")
local clock_add = elma.sym("gpu_test_clock_add")
local rows_ptr, rows_count = elma.sym("_ZL6Hsorok"), elma.sym("_ZL5Hszam")
for name, v in pairs({psx_debug = dbg, psx_memcard_debug = mcd, State = state_ptr,
                      key_count = key_count, gpu_test_freeze = freeze,
                      gpu_test_clock_add = clock_add, menu_rows = rows_ptr, menu_count = rows_count}) do
    if not v then say("FAIL: symbol " .. name .. " not found") PCSX.quit(1) end
end
local shots = elma.args.shots
local function shot(name) if shots then elma.screenshot(shots .. name .. ".ppm") end end

local WANT_TIME = tonumber(elma.args.want_time or "0")
local SCRIPT = elma.args.script or ""

local function dbg_state()
    return {magic = elma.u32(dbg), presents = elma.u32(dbg + 4), game_frames = elma.u32(dbg + 8),
            menu_chars = elma.u32(dbg + 12), errors = elma.u32(dbg + 36)}
end
local function mc()
    local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end
    return {magic = elma.u32(mcd), saves = elma.u32(mcd + 4), last = s32(elma.u32(mcd + 8)),
            dirty = elma.u32(mcd + 12), boot = s32(elma.u32(mcd + 16))}
end
local function state_obj() return elma.u32(state_ptr) end
-- state_s: palyakidejei[0].singleidok = {int32 idokszama, int32 idok[10], ...}
local function best_times()
    local s = state_obj()
    if s == 0 then return nil end
    return elma.u32(s), elma.u32(s + 4)
end
local function players()
    local s = state_obj()
    if s == 0 then return nil end
    -- palyakidejei: 90 * 2 * (4 + 40 + 2 * 150) bytes, then jatekosok[50] of 16+92+8 bytes
    return elma.u32(s + 90 * 2 * 344 + 50 * 116)
end
local function menu_has(prefix)
    local address, count = elma.u32(rows_ptr), elma.u32(rows_count)
    if address == 0 or count > 300 then return false end
    for row = 0, count - 1 do
        local matches = true
        for i = 1, #prefix do
            if elma.u8(address + 116 * row + i - 1) ~= prefix:byte(i) then matches = false break end
        end
        if matches then return true end
    end
    return false
end

-- The free list of the heap (src/mem/psx_mem.c): a cycle means the heap is damaged.
local fl_sym = elma.sym("free_list")
local function free_list_ok()
    local node, cnt = elma.u32(fl_sym), 0
    while node ~= 0 and cnt < 4000 do
        node = elma.u32(node + 8)
        cnt = cnt + 1
    end
    return node == 0, cnt
end
local heap_bad_reported = false
local quitting = false
local function finish(ok, text)
    if ok and elma.u32(dbg + 44) ~= 0 then ok, text = false, "development RAM enabled" end
    quitting = true
    local m = mc()
    say(string.format("%s: %s (card saves=%d last status=%d boot status=%d)", ok and "PASS" or "FAIL",
        text, m.saves, m.last, m.boot))
    shot(ok and "pass" or "fail")
    PCSX.quit(ok and 0 or 1)
end

-- ---- script of the finish: items of keys and a number of steps ------------
local DIK = {G = 0xC8, B = 0xD0, L = 0xCB, R = 0xCD, T = 0x39}
local steps_keys = {}  -- per step: set of keys
do
    local step = 0
    local turn_at = {}
    for item in SCRIPT:gmatch("%S+") do
        local keys, n = item:match("^([GBRLTN]*)(%d*)$")
        n = tonumber(n) or 1
        for i = 0, n - 1 do
            local set = {}
            for k in keys:gmatch(".") do
                if k ~= "N" and k ~= "T" then set[DIK[k]] = true end
            end
            steps_keys[#steps_keys + 1] = set
        end
        -- The game turns the bike after the steps of a frame (kulsoresz in
        -- LEJATSZO.CPP), the host test before the first step of the item
        -- (after the first step in the first item): the key is held in the
        -- step before the item (in its first step, for the first item).
        if keys:find("T") then turn_at[#turn_at + 1] = step > 0 and step - 1 or 0 end
        step = step + n
    end
    for _, s in ipairs(turn_at) do steps_keys[s + 1][DIK.T] = true end
end
-- game seconds per clock tick: 0.0024 * 182 / 4233600; one script step is 0.0055 s
local TICKS_PER_STEP = 0.0055 / (0.0024 * 182 / 4233600)

local ffi = require("ffi")
local ram = PCSX.getMemPtr()
local ram_mask = elma.ram8 and 0x7fffff or 0x1fffff
local function write_u8(address, value)
    ffi.cast("uint8_t*", ram + bit.band(address, ram_mask))[0] = value
end

-- The keys of the player that the pad would press (key_count of the platform
-- layer): set is a table code -> true.
local function set_keys(set)
    for _, code in pairs(DIK) do write_u8(key_count + code, set[code] and 1 or 0) end
end

-- ---- menu walk (as test/core_boot_test.lua) -----------------------------------
local steps
if run == 1 then
    steps = {
        {name = "intro", button = "CROSS"},
        {name = "name: first letter", button = "RIGHT"},
        {name = "name: enter", button = "CROSS", after = "first_save"},
        {name = "main menu: Play", button = "CROSS"},
    }
    for button in assert(elma.args.internal_steps, "internal_steps is required"):gmatch("[^,]+") do
        steps[#steps + 1] = {name = "levels route: " .. button, button = button}
    end
    steps[#steps].before = "freeze"
else
    steps = {{name = "intro", button = "CROSS"}}
end

local phase = "boot"
local step = 0
local deadline = 6000
local press_frame, chars_before, presents_before
local script_step, advance_frames, gf_at_advance
local saves_in_level, saves_before_level, finish_frame, last_gf, last_gf_frame
local quiet_since
local back_buttons, back_index, back_presents, back_chars
local saves_before_player, saves_before_second
local stall, last_gf_seen = 0, -1

-- An error in the handler would be printed again at every frame:
local depth = 0
local function guarded(handler)
    return function(n)
        if quitting then return end
        depth = depth + 1
        if depth > 1 then say("NESTED handler call, depth " .. depth .. " at frame " .. n) end
        local ok, err = xpcall(handler, function(e) return tostring(e) .. "\n" .. debug.traceback("", 2):sub(1, 600) end, n)
        if not ok then
            say("LUA ERROR: " .. tostring(err))
            quitting = true
            PCSX.quit(99)
        end
        depth = depth - 1
    end
end

elma.on_frame(guarded(function(n)
    local s = dbg_state()
    local m = mc()
    if s.errors > 0 then return finish(false, "the game stopped with an error") end
    if menu_has("Do you want to quit?") then return finish(false, "console opened the desktop quit dialog") end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end
    if n % 30 == 0 and not heap_bad_reported then
        local ok, cnt = free_list_ok()
        if not ok then
            heap_bad_reported = true
            say(string.format("HEAP free list damaged by frame %d in phase %s (saves=%d)", n, phase, m.saves))
        end
    end

    if phase == "boot" then
        if s.magic == 0x454C4D41 and s.presents >= 3 and m.magic == 0x4443524D then
            say(string.format("frame %d: booted, card load status %d", n, m.boot))
            shot("boot")
            step = 1
            phase = "press"
            deadline = n + 3000
        end
    elseif phase == "press" then
        local st = steps[step]
        if st.after == "first_save" then saves_before_player = m.saves end
        if st.before == "freeze" then
            -- Warm Up starts with the game's clock held: nothing moves until
            -- the script moves it
            if not elma.args.nofreeze then
                elma.write_u32(freeze, 1)
                elma.write_u32(clock_add, 0)
            end
        end
        chars_before, presents_before = s.menu_chars, s.presents
        elma.press(1, st.button)
        press_frame = n
        phase = "release"
    elseif phase == "release" then
        if n >= press_frame + 6 then
            elma.release(1, steps[step].button)
            phase = "taken"
        end
    elseif phase == "taken" then
        local st = steps[step]
        local drawn = step == #steps or s.presents >= presents_before + 4
        if s.menu_chars > chars_before and drawn then
            say(string.format("frame %d: %s done", n, st.name))
            if st.after == "first_save" then
                phase = "first_save"
                deadline = n + 1500
                return
            end
            if step == #steps then
                if run == 1 then
                    phase = "loading"
                    deadline = n + 6000
                else
                    phase = "check_loaded"
                    deadline = n + 1500
                end
            else
                step = step + 1
                phase = "press"
                deadline = n + 3000
            end
        elseif n > press_frame + 600 and s.menu_chars == chars_before then
            phase = "press"
        end
    elseif phase == "first_save" then
        -- Require a save after submitting the new name, not an earlier write.
        if m.saves > saves_before_player then
            if m.last ~= 0 then return finish(false, "first save failed with status " .. m.last) end
            if players() ~= 1 then return finish(false, "first player was not created") end
            say(string.format("frame %d: new player saved to the card (status %d)", n, m.last))
            shot("first_save")
            if elma.args.second then
                -- a second save in the menu, no level in between
                saves_before_second = m.saves
                elma.write_u32(mcd + 12, 1)
                phase = "second_save"
                deadline = n + 1500
                return
            end
            step = step + 1
            phase = "press"
            deadline = n + 3000
        end
    elseif phase == "second_save" then
        if m.saves > saves_before_second then return finish(m.last == 0, "second save in the menu, status " .. m.last) end
    elseif phase == "loading" then
        if s.game_frames >= 3 then
            say(string.format("frame %d: level running (clock held)", n))
            saves_before_level = m.saves
            if not elma.args.nodirty then elma.write_u32(mcd + 12, 1) end -- the core saved the state during the level
            quiet_since = n
            phase = "in_level_quiet"
            deadline = n + 3000
        end
    elseif phase == "in_level_quiet" then
        if m.saves ~= saves_before_level then
            return finish(false, "the card was written while the level was running")
        end
        if n >= quiet_since + 240 then
            say(string.format("frame %d: no card write in 240 frames of the level (dirty=%d)", n, m.dirty))
            if #steps_keys == 0 then
                -- no script: leave the level with Select; the card must be written in the menu
                elma.write_u32(freeze, 0)
                elma.press(1, "SELECT")
                press_frame = n
                phase = "leave_level"
                deadline = n + 3000
                return
            end
            script_step = 0
            gf_at_advance = nil
            phase = "script"
            deadline = n + 40000
        end
    elseif phase == "leave_level" then
        if n % 15 == 0 and (leave_dbg or 0) < 30 then
            leave_dbg = (leave_dbg or 0) + 1
            local r = PCSX.getRegisters()
            say(string.format("LEAVE frame %d pc=%08x ra=%08x sp=%08x saves=%d dirty=%d heap=%d/%d", n, r.pc, r.GPR.n.ra, r.GPR.n.sp, m.saves, m.dirty, elma.u32(dbg+24), elma.u32(dbg+28)))
            shot("leave" .. leave_dbg)
        end
        if n >= press_frame + 6 then elma.release(1, "SELECT") end
        if (m.saves > saves_before_level) or (elma.args.nodirty and n >= press_frame + 600) then
            say(string.format("frame %d: card written after leaving the level (status %d)", n, m.last))
            shot("saved")
            if m.last ~= 0 then return finish(false, "save after the level failed: " .. m.last) end
            -- Return through the level menus. Back at the root must keep
            -- the game running; run 2 verifies the card after a power reset.
            back_buttons = {"CIRCLE", "CIRCLE", "CIRCLE", "CIRCLE", "SELECT"}
            back_index = 0
            back_presents, back_chars = s.presents, s.menu_chars
            phase = "back_press"
            deadline = n + 6000
        end
    elseif phase == "back_press" then
        -- one button at a time, every 150 frames
        if n >= (press_frame or 0) + 150 then
            if back_index > 0 then shot("back" .. back_index) end
            back_index = back_index + 1
            if back_index > #back_buttons then
                phase = "back_wait"
            else
                elma.press(1, back_buttons[back_index])
                press_frame = n
                phase = "back_release"
            end
        end
    elseif phase == "back_release" then
        if n >= press_frame + 6 then
            elma.release(1, back_buttons[back_index])
            phase = "back_press"
        end
    elseif phase == "back_wait" then
        if menu_has("Main Menu") and menu_has("Play") and
            s.presents > back_presents + 4 and s.menu_chars > back_chars then
            return finish(true, "card deferred until the menu; root Back kept Main Menu running")
        end
    elseif phase == "script" then
        -- one physics step at a time: keys first, then the clock; the next step
        -- only after a few more frames (the picture of a frame comes a frame late)
        if gf_at_advance == nil or s.game_frames >= gf_at_advance + 4 then
            script_step = script_step + 1
            if script_step > #steps_keys then
                phase = "script_done"
                finish_frame = n
                say(string.format("frame %d: script played (%d steps)", n, #steps_keys))
                return
            end
            if script_step <= 3 then say("script step " .. script_step .. " keys set next") end
            if script_step % 20 == 1 and script_step < 520 then
                local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end
                say(string.format("POS step %d bike %d,%d mm", script_step - 1, s32(elma.u32(dbg + 16)), s32(elma.u32(dbg + 20))))
            end
            set_keys(steps_keys[script_step])
            if script_step <= 3 then say("script step " .. script_step .. " keys done") end
            -- a little ahead (3 ticks), so that every step is a whole 0.0055 s
            elma.write_u32(clock_add, math.floor(script_step * TICKS_PER_STEP + 0.5) + 3)
            gf_at_advance = s.game_frames
            if script_step <= 3 then say("script step " .. script_step .. " clock done") end
        end
        if m.saves ~= saves_before_level then
            return finish(false, "the card was written during the script, in the level")
        end
        if gf_at_advance and s.game_frames == last_gf_seen then
            stall = stall + 1
            if stall % 300 == 100 and stall < 1000 then
                local r = PCSX.getRegisters()
                shot("stall" .. stall)
                say(string.format("STALL frame %d step %d game_frames %d presents %d pc=%08x ra=%08x", n, script_step,
                    s.game_frames, s.presents, r.pc, r.GPR.n.ra))
            end
        else
            stall = 0
        end
        last_gf_seen = s.game_frames
        if s.game_frames > 0 and script_step % 200 == 0 and n % 50 == 0 then
            say(string.format("  step %d/%d", script_step, #steps_keys))
        end
    elseif phase == "script_done" then
        -- the level has ended by itself (finished); give the clock back
        set_keys({})
        elma.write_u32(freeze, 0)
        shot("script_done")
        phase = "after_level"
        deadline = n + 3000
    elseif phase == "after_level" then
        local count, time = best_times()
        if m.saves > saves_before_level then
            local count2, time2 = best_times()
            say(string.format("frame %d: card written after the level (status %d), best times %s, first %s",
                n, m.last, tostring(count2), tostring(time2)))
            shot("saved")
            if m.last ~= 0 then return finish(false, "save after the level failed: " .. m.last) end
            if count2 ~= 1 or time2 ~= WANT_TIME then
                return finish(false, string.format("best time is %s (%s), wanted 1 (%d)",
                    tostring(time2), tostring(count2), WANT_TIME))
            end
            return finish(true, string.format("Warm Up finished in %d, saved to the card in the menu", time2))
        end
    elseif phase == "check_loaded" then
        if state_obj() ~= 0 then
            local count, time = best_times()
            local np = players()
            say(string.format("frame %d: state read back: %d player(s), best time entries %d", n, np or -1, count or -1))
            shot("loaded")
            if m.boot ~= 0 then return finish(false, "card load status " .. m.boot) end
            if WANT_TIME > 0 then
                if count ~= 1 or time ~= WANT_TIME then
                    return finish(false, string.format("best time is %s (%s), wanted 1 (%d)", tostring(time), tostring(count), WANT_TIME))
                end
                return finish(true, string.format("the best time %d came back from the card", time))
            end
            if np ~= 1 then return finish(false, "the player entered in run 1 did not come back") end
            return finish(true, "the player entered in run 1 came back from the card (no name entry in run 2)")
        end
    end
end))
