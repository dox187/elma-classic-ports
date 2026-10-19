-- Boot test of the game core on the PS1, run by test/core_boot_test.py
-- (through test/pcsx.py, which provides `elma`). With PCdrv game data it
-- goes from the intro through the name entry and the menus to the first
-- internal level (Warm Up), gives gas and checks that the bike moves.
--
-- The game state comes from psx_debug in src/psx_platform.cpp.
-- Arguments: shots=DIR prefix of the screenshots (default: none).

local dbg = elma.sym("psx_debug")
if not dbg then
    print("FAIL: symbol psx_debug not found")
    PCSX.quit(1)
end

local function state()
    return {
        magic = elma.u32(dbg),
        presents = elma.u32(dbg + 4),
        game_frames = elma.u32(dbg + 8),
        menu_chars = elma.u32(dbg + 12),
        bike_x = elma.u32(dbg + 16),
        bike_y = elma.u32(dbg + 20),
        heap = elma.u32(dbg + 24),
        heap_max = elma.u32(dbg + 28),
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

-- Menu steps: the button to press, then wait until the game has taken the
-- key and drawn a few frames of the next screen.
local steps = {
    -- (The menu's intro animation, about 1.2 s, follows; the name entry
    -- drops keys pressed during it.)
    {name = "intro", button = "CROSS", wait = 150},
    {name = "name: first letter", button = "RIGHT"},
    {name = "name: enter", button = "CROSS"},
    {name = "main menu: Play", button = "CROSS"},
    {name = "collections: Original Levels", button = "DOWN"},
    {name = "collections: enter", button = "CROSS"},
    {name = "levels: Warm Up", button = "CROSS"},
}

local step = 0          -- 0: waiting for the first picture
local phase = "boot"
local deadline = 6000   -- frames (a disc boot is slower)
local press_frame, chars_before, presents_before
local game_start_x, gas_frame, gas_game_frames
local result

local function finish(ok, text)
    local s = state()
    print(string.format("%s: %s (presents=%d game_frames=%d heap=%d KB max=%d KB fps=%d.%02d errors=%d)",
        ok and "PASS" or "FAIL", text, s.presents, s.game_frames, math.floor(s.heap / 1024),
        math.floor(s.heap_max / 1024), math.floor(s.fps / 100), s.fps % 100, s.errors))
    shot(ok and "pass" or "fail")
    PCSX.quit(ok and 0 or 1)
end

elma.on_frame(function(n)
    local s = state()
    if s.errors > 0 then return finish(false, "the game stopped with an error") end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end

    if phase == "boot" then
        if s.magic == 0x454C4D41 and s.presents >= 3 then
            print(string.format("frame %d: first pictures shown", n))
            shot("intro")
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
        -- The last key starts the level: the loading screen stays without
        -- new frames, so only the key is waited for.
        local drawn = step == #steps or s.presents >= presents_before + 4
        local waited = n >= press_frame + (steps[step].wait or 0)
        if s.menu_chars > chars_before and drawn and waited then
            print(string.format("frame %d: %s done", n, steps[step].name))
            if step == #steps then
                phase = "loading"
                deadline = n + 6000
            else
                step = step + 1
                phase = "press"
                deadline = n + 3000
            end
        elseif n > press_frame + 600 and s.menu_chars == chars_before then
            -- The press was not seen (the game was busy); try again.
            phase = "press"
        end
    elseif phase == "loading" then
        if s.game_frames >= 3 then
            print(string.format("frame %d: level running, bike at %d,%d mm", n,
                signed(s.bike_x), signed(s.bike_y)))
            shot("level")
            game_start_x = signed(s.bike_x)
            elma.press(1, "UP")
            gas_frame = n
            gas_game_frames = s.game_frames
            phase = "gas"
            deadline = n + 3000
        end
    elseif phase == "gas" then
        local moved = math.abs(signed(s.bike_x) - game_start_x)
        -- Ten seconds of gas, also to measure the frame rate of the game:
        if n >= gas_frame + 600 then
            elma.release(1, "UP")
            shot("moving")
            local rate = (s.game_frames - gas_game_frames) * 60 / (n - gas_frame)
            if moved > 1000 then
                return finish(true, string.format(
                    "Warm Up runs, the bike moved %d mm with gas, %.2f game frames a second",
                    moved, rate))
            end
            return finish(false, string.format("the bike moved only %d mm with gas", moved))
        end
    end
end)
