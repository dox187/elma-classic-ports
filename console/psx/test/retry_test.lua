-- The shared memory harness enters Warm Up and supplies gas. This observer
-- waits for a genuine physics death, then owns only post-game input.
local dbg = assert(elma.sym("psx_debug"))
local trans = assert(elma.sym("psx_transition_debug"))
local card = assert(elma.sym("psx_memcard_debug"))
local phase, since, done = "ride", 0, false
local frames_before, presents_before, chars_before, saves_before
local exit_vblank, first_ready

local function u(offset) return elma.u32(trans + offset) end
local function fail(message)
    if done then return end
    done = true
    print("FAIL: retry transitions: " .. message)
    PCSX.quit(1)
end
local function image(name, w, h)
    local shot = PCSX.GPU.takeScreenShot()
    assert(shot.width == w and shot.height == h,
           string.format("wrong display %dx%d for %s", shot.width, shot.height, name))
    elma.screenshot(name .. ".ppm")
end
local function release()
    for _, key in ipairs({"UP", "CROSS", "SELECT", "CIRCLE"}) do elma.release(1, key) end
end

elma.on_frame(function(n)
    if done then return end
    local ok, err = xpcall(function()
        assert(elma.u32(dbg + 36) == 0, "game error")
        local frames, presents = elma.u32(dbg + 8), elma.u32(dbg + 4)
        if phase == "ride" then
            if frames >= 10 then elma.press(1, "CROSS") end
            if u(0) > 0 then
                assert(frames >= 30, "no real ride before death")
                phase, since = "ready", n
            end
        elseif phase == "ready" then
            if u(32) == 1 then
                local delta = u(8) - u(4)
                local hz = elma.u32(dbg + 56) == 1 and 50 or 59.94
                print(string.format("RETRY death-to-ready %d vblanks %.3fs", delta, delta / hz))
                assert(delta <= 60, "death-to-selector exceeds one second")
                assert(u(28) == 0 and u(24) >= 4, "wrong initial selector row")
                image("retry-ready", 320, 240)
                first_ready = u(8)
                phase, since = "held", n
            end
        elseif phase == "held" then
            assert(u(32) == 1 and u(28) == 0, "held gas selected or moved a menu row")
            if n >= since + 90 then
                release()
                if elma.args.quick_card_save == "1" then
                    saves_before = elma.u32(card + 4)
                    elma.write_u32(card + 12, 1)
                    phase, since = "save", n
                else
                    phase, since = "confirm", n
                end
            end
        elseif phase == "save" then
            assert(u(32) == 1 and u(8) == first_ready, "save left the compact selector")
            if elma.u32(card + 4) > saves_before and elma.u32(card + 12) == 0 then
                assert(elma.u32(card + 8) == 0, "memory-card save failed")
                print("RETRY compact card save OK")
                image("retry-saved", 320, 240)
                phase, since = "confirm", n
            end
        elseif phase == "confirm" then
            if n == since + 8 then
                frames_before = frames
                elma.press(1, "CROSS")
            elseif n >= since + 14 then
                elma.release(1, "CROSS")
                phase, since = "resumed", n
            end
        elseif phase == "resumed" then
            if u(16) ~= 0 and frames >= frames_before + 10 then
                local delta = u(16) - u(12)
                local hz = elma.u32(dbg + 56) == 1 and 50 or 59.94
                print(string.format("RETRY select-to-first-frame %d vblanks %.3fs", delta, delta / hz))
                assert(u(20) == 0 and u(32) == 0, "Play again was not selected")
                assert(delta <= 60, "retained-level retry exceeds one second")
                image("retry-running", 320, 240)
                phase, since = "leave", n
            end
        elseif phase == "leave" then
            if n == since + 20 then elma.press(1, "SELECT") end
            if n == since + 26 then elma.release(1, "SELECT") end
            if u(32) == 1 then
                release()
                phase, since = "back", n
            end
        elseif phase == "back" then
            if n == since + 12 then elma.press(1, "CIRCLE") end
            if n >= since + 18 then
                elma.release(1, "CIRCLE")
                if u(32) == 0 then
                    assert(u(20) == 0xffffffff, "Back was not selected")
                    exit_vblank, presents_before = u(12), presents
                    phase, since = "menu", n
                end
            end
        elseif phase == "menu" then
            if presents >= presents_before + 3 then
                image("retry-level-menu", 640, 480)
                print(string.format("RETRY back-to-level-menu %d vblanks", elma.u32(dbg + 52) - exit_vblank))
                chars_before = elma.u32(dbg + 12)
                elma.press(1, "UP")
                phase, since = "menu-input", n
            end
        elseif phase == "menu-input" then
            if n >= since + 6 then elma.release(1, "UP") end
            if n >= since + 12 and elma.u32(dbg + 12) > chars_before then
                done = true
                print("PASS: retry transitions, held gas, replay progress and usable level menu")
                PCSX.quit(0)
            end
        end
        assert(n - since < (phase == "ride" and 16000 or 6000), "timeout in " .. phase)
    end, debug.traceback)
    if not ok then fail(tostring(err):sub(1, 900)) end
end)
dofile(elma.args.memory_lua)
