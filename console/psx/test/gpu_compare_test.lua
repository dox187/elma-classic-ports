-- Screenshots of the game view for test/gpu_compare_test.py (run through
-- test/pcsx.py, which provides `elma`). Goes from the intro through the
-- menus into a level, stops the game's clock and takes screenshots of the
-- same state: from the GPU renderer, and in the comparison build
-- (ELMA_PSX_GPU_COMPARE) from the software renderer too. Then gas for a
-- while, and the same again.
--
-- Arguments:
--   path=B1,B2,...  buttons after "Play" in the main menu (pad names)
--   levels=N        make N internal levels selectable (gpu_test_levels)
--   soft=1          also the software renderer's pictures
--   gas=F           frames of gas between the two states (default 150)
--   shots=P         prefix of the screenshot files (default "")
--   fps=1           measure the frame rate of the view for 10 seconds
--   menu=1          only measure the main menu's frame rate (10 seconds)
-- Prints "state NAME cam_x cam_y view_x view_y" for every state, so the
-- comparison can align the two renderers' pictures.

local dbg = elma.sym("psx_debug")
local stats = elma.sym("gpu_draw_stats")
local freeze = elma.sym("gpu_test_freeze")
local soft = elma.sym("gpu_render_soft")
local unlock = elma.sym("gpu_test_levels")
if not dbg or not stats or not freeze then
    print("FAIL: debug symbols not found")
    PCSX.quit(1)
end

local function signed(v)
    if v >= 0x80000000 then return v - 0x100000000 end
    return v
end

local function presents() return elma.u32(dbg + 4) end
local function game_frames() return elma.u32(dbg + 8) end
local function menu_chars() return elma.u32(dbg + 12) end
local function errors() return elma.u32(dbg + 36) end

local prefix = elma.args.shots or ""
local want_soft = elma.args.soft == "1"
local gas_frames = tonumber(elma.args.gas or "150")

-- The menu steps: intro, the name, "Play", then the given path.
local steps = {"CROSS", "RIGHT", "CROSS", "CROSS"}
for b in string.gmatch(elma.args.path or "DOWN,CROSS,CROSS", "[^,]+") do steps[#steps + 1] = b end

local phase = "boot"
local loading_presents, loading_release, loading_still = nil, nil, 0
local step = 0
local wait_until = 0
local press_frame, chars_before, presents_before
local deadline = 9000
local captures = {}
local state_index = 0

local function finish(ok, text)
    if not ok then elma.screenshot(prefix .. "fail.ppm") end
    print(string.format("%s: %s (presents=%d game_frames=%d errors=%d)", ok and "PASS" or "FAIL", text,
        presents(), game_frames(), errors()))
    PCSX.quit(ok and 0 or 1)
end

-- A capture: name, then optional soft picture.
local function begin_state(n, name)
    state_index = state_index + 1
    captures = {name = name, stage = "gpu", at = n + 12}
    elma.write_u32(freeze, 1)
end

elma.on_frame(function(n)
    if errors() > 0 then return finish(false, "the game stopped with an error") end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end

    if phase == "boot" then
        if presents() >= 3 then
            -- (Only once the program runs: it clears its variables first.)
            if unlock and elma.args.levels then elma.write_u32(unlock, tonumber(elma.args.levels)) end
            phase = "press"
            step = 1
            deadline = n + 4000
        end
    elseif phase == "press" then
        if n < wait_until then return end
        chars_before, presents_before = menu_chars(), presents()
        elma.press(1, steps[step])
        press_frame = n
        phase = "release"
    elseif phase == "release" then
        if n >= press_frame + 4 then
            elma.release(1, steps[step])
            phase = "taken"
        end
    elseif phase == "taken" then
        -- The key was taken and the next screen drawn a few times (the last
        -- key starts the level: no new frames while it loads).
        -- (A menu drops keys pressed before it starts, so the next one
        -- waits until this one has drawn a while.)
        local drawn = step == #steps or (presents() >= presents_before + 12 and n >= press_frame + 45)
        if (menu_chars() > chars_before or (step == #steps and game_frames() > 0)) and drawn then
            if elma.args.menu == "1" and step == 3 then
                -- In the main menu, with its balls:
                phase = "menufps"
                captures = {n0 = n + 120, p0 = nil}
                return
            end
            print(string.format("frame %d: step %d (%s) taken", n, step, steps[step]))
            if step == #steps then
                phase = "loading"
                deadline = n + 9000
            else
                step = step + 1
                phase = "press"
            end
        elseif step < #steps and n > press_frame + 600 and menu_chars() == chars_before then
            -- The press was not seen (the game was busy); again. (Not the
            -- last one: a big level loads for longer than that.)
            phase = "press"
        end
    elseif phase == "loading" then
        if elma.args.trace == "1" and n % 600 == 0 then
            -- Where the program is while it loads (args trace=1):
            local r = PCSX.getRegisters()
            print(string.format("loading: pc %08x ra %08x", r.pc, r.GPR.n.ra))
        end
        -- A message while loading (e.g. the level's LGR is missing, so the
        -- default one is used): the menu draws but the level does not run;
        -- answered with CROSS.
        -- (A dialog may also wait without drawing: then nothing changes for
        -- long, the presents neither.)
        if game_frames() == 0 and n % 300 == 0 then
            local still = loading_presents and presents() == loading_presents
            loading_still = still and (loading_still or 0) + 1 or 0
            if loading_presents and (presents() > loading_presents + 5 or loading_still >= 4) then
                loading_still = 0
                print(string.format("frame %d: a message while loading, CROSS", n))
                elma.press(1, "CROSS")
                loading_release = n + 4
            end
            loading_presents = presents()
        end
        if loading_release and n >= loading_release then
            elma.release(1, "CROSS")
            loading_release = nil
        end
        if game_frames() >= 3 then
            print(string.format("frame %d: level running", n))
            begin_state(n, "start")
            phase = "capture"
            deadline = n + 3000
        end
    elseif phase == "capture" then
        local c = captures
        if n < c.at then return end
        if c.stage == "gpu" then
            print(string.format("state %s %d %d %d %d", c.name, signed(elma.u32(stats + 32)),
                signed(elma.u32(stats + 36)), signed(elma.u32(stats + 24)), signed(elma.u32(stats + 28))))
            elma.screenshot(prefix .. c.name .. "_gpu.ppm")
            if state_index == 1 then
                -- The raw VRAM (the harness's elma.vram picture assumes
                -- another format):
                local f = io.open(prefix .. "vram.raw", "wb")
                f:write(tostring(PCSX.GPU.getVRAM()))
                f:close()
            end
            if want_soft and soft then
                elma.write_u32(soft, 1)
                c.stage = "soft"
                c.at = n + 12
                c.presents = presents()
            else
                c.stage = "done"
            end
        elseif c.stage == "soft" then
            -- The software picture is sent to the single display buffer in
            -- pieces: right after a whole one (a present) has arrived.
            if presents() < c.presents + 2 then return end
            if c.last_seen ~= presents() then
                c.last_seen = presents()
                return
            end
            elma.screenshot(prefix .. c.name .. "_soft.ppm")
            elma.write_u32(soft, 0)
            c.stage = "done"
            c.at = n + 6
        elseif c.stage == "done" then
            elma.write_u32(freeze, 0)
            if state_index == 1 then
                elma.press(1, "UP")
                phase = "gas"
                wait_until = n + gas_frames
            elseif elma.args.fps == "1" then
                phase = "fps"
                c.frames0 = game_frames()
                c.n0 = n
            else
                return finish(true, "pictures taken")
            end
        end
    elseif phase == "gas" then
        if n >= wait_until then
            elma.release(1, "UP")
            begin_state(n, "moving")
            phase = "capture"
        end
    elseif phase == "menufps" then
        local c = captures
        if n == c.n0 then c.p0 = presents() end
        if c.p0 and n >= c.n0 + 600 then
            print(string.format("menu frames a second: %.2f", (presents() - c.p0) * 60 / (n - c.n0)))
            elma.screenshot(prefix .. "menu.ppm")
            return finish(true, "menu measured")
        end
    elseif phase == "fps" then
        -- The longest time between two game frames, in display frames:
        local f = game_frames()
        if f ~= captures.last_frames then
            if captures.last_n and n - captures.last_n > (captures.worst or 0) then captures.worst = n - captures.last_n end
            captures.last_frames = f
            captures.last_n = n
            -- The statistics of the frame just completed, summed up:
            local c = captures
            c.sum = c.sum or {}
            for i = 0, 10 do c.sum[i] = (c.sum[i] or 0) + elma.u32(stats + 52 + 4 * i) end
            c.sum_built = (c.sum_built or 0) + elma.u32(stats + 20)
            c.max_built = math.max(c.max_built or 0, elma.u32(stats + 20))
            c.nsum = (c.nsum or 0) + 1
        end
        -- (Measured until the game leaves the view, e.g. when the bike dies.)
        local left = captures.last_n and n - captures.last_n > 60
        if n >= captures.n0 + 600 or left then
            local until_n = left and captures.last_n or n
            local rate = (captures.last_frames - captures.frames0) * 60 / math.max(1, until_n - captures.n0)
            if left then print(string.format("view left after %d vblanks", until_n - captures.n0)) end
            print(string.format("view worst gap between frames: %d vblanks", captures.worst or 0))
            print(string.format("view frames a second: %.2f; last frame: built in %.2f ms, %d command words, " ..
                "%d trapezoids, %d pictures, %d near; GPU fill %d textured, %d flat, %d blended pixels", rate,
                elma.u32(stats + 20) / 4233.6, elma.u32(stats + 4), elma.u32(stats + 8), elma.u32(stats + 12),
                elma.u32(stats + 16), elma.u32(stats + 40), elma.u32(stats + 44), elma.u32(stats + 48)))
            local names = {"collect", "ground", "far-ground", "sky", "far-sky", "objects", "bikes", "near", "map", "sound"}
            local parts = {}
            local c = captures
            for i = 0, 9 do parts[#parts + 1] = string.format("%s %.2f", names[i + 1], c.sum[i] / c.nsum / 4233.6) end
            print(string.format("view frames built in %.2f ms on average, at most %.2f ms (%d frames)",
                c.sum_built / c.nsum / 4233.6, c.max_built / 4233.6, c.nsum))
            print("view parts (ms, average): " .. table.concat(parts, ", "))
            print(string.format("view trapezoids looked at %.1f a frame", c.sum[10] / c.nsum))
            print(string.format("view command words at most %d", elma.u32(stats + 100)))
            return finish(true, "pictures taken")
        end
    end
end)
