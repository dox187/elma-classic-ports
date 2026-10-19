-- Cycles of the physics on the PS1, run by test/phys_cycles.py (through
-- test/pcsx.py, which provides `elma`). Goes from the intro through the name
-- entry to an internal level (all levels are unlocked in the player's
-- state for this), plays it with a fixed input and counts the emulated CPU
-- cycles (PCSX.getCPUCycles) between execution breakpoints:
--   leptet entry -> vizsgalat entry          one leptet (step of the bike)
--   vizsgalat entry -> kiszamolsurlodast     vizsgalat (head, objects)
--   belsoresz entry -> next belsoresz entry  a whole step of the game loop
--                                            (only within one frame)
-- and the parts of the step around the physics:
--   belsoresz entry -> leptet entry          the volt keys (pre)
--   kiszamolsurlodast -> recorder::store     the engine sound values (sound)
--   recorder::store -> next belsoresz entry  recorder, objects, loop (rest)
-- Arguments: level=N (internal level, from 0), seconds=S of play,
-- input=gas|mixed, shots=PREFIX (screenshots), probes=SYM,SYM,... (the
-- cycles inside these functions, from their entry to the return, a step).

local dbg = elma.sym("psx_debug")
local state_ptr = elma.sym("State")
local function need(name)
    local a = elma.sym(name)
    if not a then
        print("FAIL: symbol " .. name .. " not found")
        PCSX.quit(1)
    end
    return a
end
local a_leptet = need("_Z6leptetP7motorstddiiii")
local a_vizsgalat = need("_Z9vizsgalatP7motorst")
local a_surl = need("_Z17kiszamolsurlodastv")
local a_belso = need("_ZL9belsoreszP7motorstP13jatekosopciokP8valtozokP8recorderPlPidd")
local a_frame = need("_Z11kirajzol320dP8valtozokS0_iiii")
local a_store = need("_ZN8recorder5storeEP7motorstdP8hanginfo")

local level = tonumber(elma.args.level or "0")
local seconds = tonumber(elma.args.seconds or "20")
local input = elma.args.input or "mixed"

local function state()
    return {
        magic = elma.u32(dbg),
        presents = elma.u32(dbg + 4),
        game_frames = elma.u32(dbg + 8),
        menu_chars = elma.u32(dbg + 12),
        bike_x = elma.u32(dbg + 16),
        bike_y = elma.u32(dbg + 20),
        fps = elma.u32(dbg + 32),
        errors = elma.u32(dbg + 36),
    }
end

local function signed(v)
    if v >= 0x80000000 then return v - 0x100000000 end
    return v
end

local shots = elma.args.shots
local function shot(name)
    if shots then elma.screenshot(shots .. name .. ".ppm") end
end

-- state_s (STATE.H): palyakidejei[90] of 688 bytes, then jatekosok[50] of
-- 116 bytes (sikerespalyakszama at 108, jelenlegipalya at 112), then
-- jatekosokszama.
local function unlock()
    local s = elma.u32(state_ptr)
    local players = elma.u32(s + 61920 + 50 * 116)
    for i = 0, players - 1 do
        local p = s + 61920 + i * 116
        elma.write_u32(p + 108, 53)
        elma.write_u32(p + 112, level)
    end
    return players
end

-- Statistics:
local function stats()
    return {n = 0, sum = 0, max = 0, min = math.huge}
end
local st_leptet, st_vizs, st_step = stats(), stats(), stats()
local st_pre, st_sound, st_rest = stats(), stats(), stats()
local t_surl, t_store
local function add(s, v)
    s.n = s.n + 1
    s.sum = s.sum + v
    if v > s.max then s.max = v end
    if v < s.min then s.min = v end
end
local measuring = false
local t_leptet, t_vizs, t_belso
local steps_in_frame, frames = 0, 0
local function cycles() return tonumber(PCSX.getCPUCycles()) end

local bps = {}
local function bp(addr, fn)
    bps[#bps + 1] = PCSX.addBreakpoint(bit.band(addr, 0xffffffff), "Exec", 4, "phys",
        function() fn(); return true end)
end
bp(a_belso, function()
    local c = cycles()
    if measuring and t_belso then add(st_step, c - t_belso) end
    if measuring and t_store then add(st_rest, c - t_store) end
    t_store = nil
    t_belso = c
    steps_in_frame = steps_in_frame + 1
end)
bp(a_leptet, function()
    t_leptet = cycles()
    if measuring and t_belso then add(st_pre, t_leptet - t_belso) end
end)
bp(a_vizsgalat, function()
    local c = cycles()
    if measuring and t_leptet then add(st_leptet, c - t_leptet) end
    t_vizs = c
end)
bp(a_surl, function()
    local c = cycles()
    if measuring and t_vizs then add(st_vizs, c - t_vizs) end
    t_vizs = nil
    t_surl = c
end)
bp(a_store, function()
    local c = cycles()
    -- The first store of the step (a death stores once more):
    if t_surl then
        if measuring then add(st_sound, c - t_surl) end
        t_surl = nil
        t_store = c
    end
end)
-- Probes: the entry and, at each call, the return address (ra):
local probe_stats = {}
local probe_names = {}
for name in string.gmatch(elma.args.probes or "", "[^,]+") do
    local a = elma.sym(name)
    if not a then
        print("FAIL: probe symbol " .. name .. " not found")
        PCSX.quit(1)
    end
    local st = stats()
    probe_stats[name] = st
    probe_names[#probe_names + 1] = name
    local pending = {}     -- return address -> start cycles
    local returns = {}
    bp(a, function()
        local ra = tonumber(PCSX.getRegisters().GPR.n.ra)
        pending[ra] = cycles()
        if not returns[ra] then
            returns[ra] = true
            bp(ra, function()
                local t0 = pending[ra]
                if t0 then
                    if measuring then add(st, cycles() - t0) end
                    pending[ra] = nil
                end
            end)
        end
    end)
end

bp(a_frame, function()
    t_belso = nil
    t_store = nil
    if measuring then frames = frames + 1 end
end)

local steps = {
    {name = "intro", button = "CROSS"},
    {name = "name: first letter", button = "RIGHT"},
    {name = "name: enter", button = "CROSS"},
    {name = "main menu: Play", button = "CROSS"},
    {name = "collections: Original Levels", button = "DOWN"},
    {name = "collections: enter", button = "CROSS"},
    {name = "levels: start", button = "CROSS"},
}

local step = 0
local phase = "boot"
local deadline = 6000
local press_frame, chars_before, presents_before
local play_frame, play_game_frames, held = nil, nil, {}

local function finish(ok, text)
    for _, b in ipairs(bps) do b:remove() end
    local function line(name, s)
        if s.n == 0 then return string.format("%s: none", name) end
        return string.format("%s: n=%d avg=%d min=%d max=%d cycles", name, s.n,
            math.floor(s.sum / s.n), s.min, s.max)
    end
    print("CYCLES " .. line("leptet", st_leptet))
    print("CYCLES " .. line("vizsgalat", st_vizs))
    print("CYCLES " .. line("step", st_step))
    print("CYCLES " .. line("  pre", st_pre))
    print("CYCLES " .. line("  sound", st_sound))
    print("CYCLES " .. line("  rest", st_rest))
    for _, name in ipairs(probe_names) do
        local st = probe_stats[name]
        print(string.format("CYCLES probe %s: %d calls, %d cycles a call, %d a step", name, st.n,
            st.n > 0 and math.floor(st.sum / st.n) or 0,
            st_leptet.n > 0 and math.floor(st.sum / st_leptet.n) or 0))
    end
    local s = state()
    print(string.format("%s: %s (level %d, %d frames measured, fps=%d.%02d)",
        ok and "PASS" or "FAIL", text, level, frames, math.floor(s.fps / 100), s.fps % 100))
    shot(ok and "pass" or "fail")
    PCSX.quit(ok and 0 or 1)
end

-- The keys held at a time t (seconds of emulated play):
local function keys_at(t)
    local k = {UP = true}
    if input == "mixed" then
        local p = t % 6
        if p > 2.0 and p < 2.15 then k.LEFT = true end
        if p > 4.0 and p < 4.15 then k.RIGHT = true end
        if p > 5.0 and p < 5.6 then k.UP = nil; k.DOWN = true end
    end
    return k
end

local function set_keys(k)
    for _, name in ipairs({"UP", "DOWN", "LEFT", "RIGHT"}) do
        if k[name] and not held[name] then elma.press(1, name) end
        if not k[name] and held[name] then elma.release(1, name) end
        held[name] = k[name]
    end
end

elma.on_frame(function(n)
    local s = state()
    if s.errors > 0 then return finish(false, "the game stopped with an error") end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end

    if phase == "boot" then
        if s.magic == 0x454C4D41 and s.presents >= 3 then
            step = 1
            phase = "press"
            deadline = n + 3000
        end
    elseif phase == "press" then
        local st = steps[step]
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
        local drawn = step == #steps or s.presents >= presents_before + 4
        if s.menu_chars > chars_before and drawn then
            print(string.format("frame %d: %s done", n, steps[step].name))
            if steps[step].name == "name: enter" then
                print(string.format("frame %d: %d players unlocked", n, unlock()))
            end
            if step == #steps then
                phase = "loading"
                deadline = n + 8000
            else
                step = step + 1
                phase = "press"
                deadline = n + 3000
            end
        elseif n > press_frame + 600 and s.menu_chars == chars_before then
            phase = "press"
        end
    elseif phase == "loading" then
        if s.game_frames >= 3 then
            print(string.format("frame %d: level running, bike at %d,%d mm", n,
                signed(s.bike_x), signed(s.bike_y)))
            shot("start")
            play_frame = n
            play_game_frames = s.game_frames
            measuring = true
            phase = "play"
            deadline = n + seconds * 60 + 600
        end
    elseif phase == "play" then
        local t = (n - play_frame) / 60
        set_keys(keys_at(t))
        if t >= seconds then
            set_keys({})
            local rate = (s.game_frames - play_game_frames) * 60 / (n - play_frame)
            return finish(true, string.format("played %d s, bike at %d,%d mm, %.2f game frames a second",
                seconds, signed(s.bike_x), signed(s.bike_y), rate))
        end
    end
end)
