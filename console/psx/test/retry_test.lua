-- The shared memory harness enters Warm Up and supplies gas. This observer
-- waits for a genuine physics death, then owns only post-game input.
local dbg = assert(elma.sym("psx_debug"))
local trans = assert(elma.sym("psx_transition_debug"))
local card = assert(elma.sym("psx_memcard_debug"))
local bank = assert(elma.sym("Wavbank"))
local rec1, rec2 = assert(elma.sym("Prec1")), assert(elma.sym("Prec2"))
local rubrikak = assert(elma.sym("Rubrikak"))
local menu_ptr, menu_count = assert(elma.sym("_ZL6Hsorok")), assert(elma.sym("_ZL5Hszam"))
local phase, since, done = "ride", 0, false
local frames_before, presents_before, chars_before, saves_before
local exit_vblank, first_ready
local checked_recorders, checked_best_times = false, false

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
local function cstring(address, size)
    local text = {}
    for i = 0, size - 1 do
        local c = elma.u8(address + i)
        if c == 0 then break end
        text[#text + 1] = string.char(c)
    end
    return table.concat(text)
end
local function check_recorders()
    for _, symbol in ipairs({rec1, rec2}) do
        local object = elma.u32(symbol)
        assert(object ~= 0 and elma.u32(object - 8) == 20,
               "recorder is not a 20-byte metadata object")
        assert(cstring(object + 4, 16) == "QWQUU001.LEV", "recorder lost the level name")
    end
    checked_recorders = true
end
local function check_choices()
    local rows, count = elma.u32(rubrikak), u(24)
    assert(count == 3, "internal post-game selector must have three choices")
    assert(cstring(rows, 42) == "Play again", "missing restart")
    local next = cstring(rows + 42, 42)
    assert(next == "Play next" or next == "Skip level", "missing next/skip")
    assert(cstring(rows + 84, 42) == "Best times", "obsolete replay/save choice remains")
end
local function best_times_visible()
    local rows, count = elma.u32(menu_ptr), elma.u32(menu_count)
    if rows == 0 or count > 300 then return false end
    local title, time = false, false
    for i = 0, count - 1 do
        local text = cstring(rows + i * 116, 102)
        title = title or text:sub(1, 3) == "1: "
        time = time or text == "00:12:34"
    end
    return title and time
end

elma.on_frame(function(n)
    if done then return end
    local ok, err = xpcall(function()
        assert(elma.u32(dbg + 36) == 0, "game error")
        local frames, presents = elma.u32(dbg + 8), elma.u32(dbg + 4)
        if phase == "ride" then
            if frames >= 10 then
                if not checked_recorders then check_recorders() end
                elma.press(1, "CROSS")
            end
            if u(0) > 0 then
                assert(frames >= 30, "no real ride before death")
                phase, since = "ready", n
            end
        elseif phase == "ready" then
            if u(32) == 1 then
                local delta = u(8) - u(4)
                local hz = elma.u32(dbg + 56) == 1 and 50 or 59.94
                print(string.format("RETRY death-to-ready %d vblanks %.3fs", delta, delta / hz))
                -- The shared mixer plays the original sample count at 11025 Hz,
                -- regardless of its WAV header rate. Include the queued SPU
                -- tail and one IRQ granularity margin after the complete cue.
                local wave = elma.u32(bank + 2 * 4) -- WAV_TORES
                assert(wave ~= 0, "death sample was not loaded")
                local limit = math.ceil((elma.u32(wave + 4) / 11025 + 0.35) * hz)
                assert(delta <= limit, "death-to-selector exceeds the complete cue and queue margin")
                assert(u(28) == 0, "wrong initial selector row")
                check_choices()
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
                    phase, since = "best-select", n
                end
            end
        elseif phase == "save" then
            assert(u(32) == 1 and u(8) == first_ready, "save left the compact selector")
            if elma.u32(card + 4) > saves_before and elma.u32(card + 12) == 0 then
                assert(elma.u32(card + 8) == 0, "memory-card save failed")
                print("RETRY compact card save OK")
                image("retry-saved", 320, 240)
                phase, since = "best-select", n
            end
        elseif phase == "best-select" then
            if n == since + 1 then
                -- A fresh player has no times. Seed only this private guest's
                -- first single-player table so the real viewer must open.
                local state = elma.u32(assert(elma.sym("State")))
                elma.write_u32(state, 1)
                elma.write_u32(state + 4, 1234)
                elma.write_u32(state + 44, 0x54534554) -- TEST
                elma.write_u32(state + 48, 0)
            end
            if n == since + 8 then elma.press(1, "UP") end
            if n == since + 14 then elma.release(1, "UP") end
            if n == since + 22 then
                assert(u(28) == 2, "Best times was not selectable")
                presents_before = presents
                elma.press(1, "CROSS")
            end
            if n >= since + 28 then
                elma.release(1, "CROSS")
                phase, since = "best-times", n
            end
        elseif phase == "best-times" then
            if best_times_visible() and presents >= presents_before + 3 and n >= since + 30 then
                checked_best_times = true
                image("retry-best-times", 640, 480)
                elma.press(1, "CIRCLE")
                phase, since = "best-return", n
            end
        elseif phase == "best-return" then
            if n >= since + 6 then elma.release(1, "CIRCLE") end
            if u(32) == 1 and n >= since + 18 then
                check_choices()
                assert(u(28) == 2, "Best times return lost the selected row")
                elma.press(1, "DOWN")
                phase, since = "restart-select", n
            end
        elseif phase == "restart-select" then
            if n >= since + 6 then elma.release(1, "DOWN") end
            if n >= since + 14 then
                assert(u(28) == 0, "restart row did not wrap from Best times")
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
                check_recorders()
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
                assert(checked_recorders and checked_best_times, "missing no-recording/Best times checks")
                done = true
                print("PASS: retry transitions, held gas, restart progress, Best times and 20-byte recorders")
                PCSX.quit(0)
            end
        end
        assert(n - since < (phase == "ride" and 16000 or 6000), "timeout in " .. phase)
    end, debug.traceback)
    if not ok then fail(tostring(err):sub(1, 900)) end
end)
dofile(elma.args.memory_lua)
