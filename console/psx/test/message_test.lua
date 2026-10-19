-- Two real core warnings per load, interleaved with memory-card notices,
-- followed by game -> menu -> game. Breakpoints verify one font upload,
-- no heap change while drawing any notice, and intact heap block links.
if jit then jit.off() end
local logfile = elma.args.log and assert(io.open(elma.args.log, "w"))
local function say(text)
    print(text)
    if logfile then logfile:write(text, "\n"); logfile:flush() end
end
local function need(name)
    local address = elma.sym(name)
    assert(address, "missing symbol " .. name)
    return address
end
local dbg = need("psx_debug")
local mem = need("psx_mem_stats")
local free_list = need("free_list")
local mcd = need("psx_memcard_debug")
local video = need("psx_video_force")
local font_loads, notices, warnings, heap_checks = 0, 0, 0, 0
local glyph_checks = 0
local warning_ready, ready_frame = 0, 0
local notice_heap, active_return
local frame, quit = 0, false
local breakpoints, return_breakpoints = {}, {}
local function finish(ok, reason)
    if quit then return end
    quit = true
    say(string.format("%s: %s (font uploads=%d notices=%d warnings=%d heap checks=%d glyph checks=%d)",
        ok and "PASS" or "FAIL", reason, font_loads, notices, warnings, heap_checks, glyph_checks))
    if elma.args.shots then elma.screenshot(elma.args.shots .. (ok and "pass" or "fail") .. ".ppm") end
    PCSX.quit(ok and 0 or 1)
end
local function guard(fn)
    return function(...)
        if quit then return true end
        local ok, err = pcall(fn, ...)
        if not ok then finish(false, tostring(err)) end
        return true
    end
end
local function bp(address, fn)
    breakpoints[#breakpoints + 1] = PCSX.addBreakpoint(address, "Exec", 4, "messages", guard(fn))
end
local function heap_snapshot()
    return {elma.u32(mem + 12), elma.u32(mem + 16), elma.u32(mem + 28),
            elma.u32(mem + 32), elma.u32(mem + 36)}
end
local function check_heap()
    local start, limit, top = elma.u32(mem + 4), elma.u32(mem + 8), elma.u32(mem + 12)
    assert(start <= top and top <= limit, "heap extent outside RAM")
    local address, prev, allocated, blocks, free = start, 0, 0, 0, {}
    while address < top do
        local flags = elma.u32(address)
        local size = bit.band(flags, 0xfffffffe)
        assert(size >= 16 and size % 8 == 0 and address + size <= top, "invalid heap block")
        assert(elma.u32(address + 4) == prev, "damaged previous-block link")
        if bit.band(flags, 1) == 1 then allocated = allocated + size; blocks = blocks + 1
        else free[address] = true end
        address, prev = address + size, size
    end
    assert(allocated == elma.u32(mem + 16), string.format("heap byte counter differs: %d / %d",
        allocated, elma.u32(mem + 16)))
    assert(blocks == elma.u32(mem + 32), "heap block counter differs")
    local node, previous, seen = elma.u32(free_list), 0, {}
    while node ~= 0 do
        assert(free[node] and not seen[node], "damaged or cyclic free list")
        assert(elma.u32(node + 12) == previous, "damaged free-list back link")
        seen[node] = true
        previous, node = node, elma.u32(node + 8)
    end
    for address in pairs(free) do assert(seen[address], "free block absent from list") end
    heap_checks = heap_checks + 1
end
local function check_warning_glyph()
    -- The title starts with E. Compare its 8x8 screen pixels to the font's
    -- actual packed 4-bit glyph and CLUT at its reserved VRAM location.
    -- This detects incorrect page-relative UVs even before an LGR loads.
    local raw = tostring(PCSX.GPU.getVRAM())
    -- Redux exposes a 1024-row backing store even for the 512-row GPU.
    assert(#raw >= 1024 * 512 * 2 and #raw % 2048 == 0, "unexpected VRAM format")
    local function word(x, y)
        local at = (y * 1024 + x) * 2
        return raw:byte(at + 1) + 256 * raw:byte(at + 2)
    end
    local clut = elma.u16(need("_font_clut"))
    local cx, cy = bit.band(clut, 63) * 16, bit.rshift(clut, 6)
    local lit = 0
    for y = 0, 7 do
        for x = 0, 7 do
            local u = 32 + x -- E = character 69, font cell (4,2)
            local packed = word(960 + math.floor(u / 4), 448 + 16 + y)
            local index = bit.band(bit.rshift(packed, (u % 4) * 4), 15)
            local want = bit.band(word(cx + index, cy), 0x7fff)
            local got = bit.band(word(32 + x, 32 + y), 0x7fff)
            assert(got == want, "warning glyph pixels differ from the reserved font")
            if want ~= 0 then lit = lit + 1 end
        end
    end
    assert(lit > 8, "warning glyph has no visible pixels")
    glyph_checks = glyph_checks + 1
end
bp(need("FntLoad"), function()
    font_loads = font_loads + 1
    assert(font_loads == 1, "debug font loaded again")
end)
bp(need("_Z9gv_noticeiiiiPKPKci"), function()
    check_heap()
    notices = notices + 1
    notice_heap = heap_snapshot()
    active_return = tonumber(PCSX.getRegisters().GPR.n.ra)
    if active_return < 0 then active_return = active_return + 0x100000000 end
    local ra = active_return
    if not return_breakpoints[ra] then
        return_breakpoints[ra] = true
        bp(ra, function()
            if active_return ~= ra then return end
            local after = heap_snapshot()
            for i, v in ipairs(notice_heap) do assert(v == after[i], "notice changed the heap") end
            check_heap()
            if warnings > glyph_checks then
                check_warning_glyph()
                warning_ready, ready_frame = warnings, frame
            end
            say(string.format("MESSAGE notice %d drawn; glyph checks=%d", notices, glyph_checks))
            active_return = nil
        end)
    end
end)
local warning_pending, answered, answer_frame, answer_down = 0, 0, 0, false
bp(need("_ZN12_GLOBAL__N_114message_screenEPKcPcS2_S2_b"), function()
    warnings = warnings + 1
    warning_pending = warning_pending + 1
    say(string.format("MESSAGE warning %d at frame %d", warnings, frame))
end)

local keys = {"CROSS", "RIGHT", "CROSS", "CROSS"}
for button in assert(elma.args.external_steps, "external_steps must come from the resource layout"):gmatch("[^,]+") do
    keys[#keys + 1] = button
end
local phase, index, deadline = "boot", 1, 9000
local pressed, chars_before, presents_before, game_before, play_at, left_at
local plays = 0
local reload_keys, reload_index = {"CIRCLE", "DOWN", "CROSS"}, 1
elma.on_frame(guard(function(n)
    frame = n
    local presents, game = elma.u32(dbg + 4), elma.u32(dbg + 8)
    assert(elma.u32(dbg + 36) == 0, "game stopped with an internal error")
    assert(n < deadline, "timeout in " .. phase)
    if presents == 0 and elma.u32(dbg) == 0x454c4d41 then
        elma.write_u32(video, tonumber(elma.args.force))
    end
    if answer_down and n >= answer_frame + 6 then
        elma.release(1, "CROSS")
        answer_down = false
        answer_frame = n
    elseif warning_ready > answered and not answer_down and n >= answer_frame + 24 and n >= ready_frame + 12 then
        if elma.args.shots then elma.screenshot(elma.args.shots .. "warning" .. warning_pending .. ".ppm") end
        elma.press(1, "CROSS")
        answered = answered + 1
        answer_frame, answer_down = n, true
    end
    if phase == "boot" then
        if presents >= 3 then phase = "press" end
    elseif phase == "press" then
        chars_before, presents_before = elma.u32(dbg + 12), presents
        elma.press(1, keys[index])
        pressed, phase = n, "release"
    elseif phase == "release" then
        if n >= pressed + 6 then elma.release(1, keys[index]); phase = "taken" end
    elseif phase == "taken" then
        if elma.u32(dbg + 12) > chars_before and n >= pressed + (index == 1 and 150 or 60) and
            (index == #keys or presents >= presents_before + 4) then
            if index == #keys then phase = "loading"; game_before = 0
            else index = index + 1; phase = "press" end
        elseif n > pressed + 600 and elma.u32(dbg + 12) == chars_before then phase = "press" end
    elseif phase == "loading" then
        if game >= game_before + 10 then
            plays = plays + 1
            assert(warnings >= plays * 2, "expected both core warnings on every load")
            say(string.format("MESSAGE game %d running after %d warnings", plays, warnings))
            play_at, phase = n, "play"
        end
    elseif phase == "play" and n >= play_at + 60 then
        if plays == 2 then
            assert(font_loads == 1 and notices >= warnings + 1 and glyph_checks >= 4,
                   "missing shared card notice/font/glyph check")
            assert(elma.u32(mcd + 4) >= 1, "memory-card save was not exercised")
            assert(elma.u32(dbg + 56) == (tonumber(elma.args.force) == 2 and 1 or 0), "wrong video mode")
            return finish(true, "repeated warnings and card notices preserve heap and resume game")
        end
        elma.press(1, "SELECT")
        left_at, presents_before, phase = n, presents, "leave"
    elseif phase == "leave" then
        if n == left_at + 6 then elma.release(1, "SELECT") end
        if n >= left_at + 240 and presents >= presents_before + 4 then
            check_heap()
            game_before = game
            -- Play again reuses the parsed level. Return to the list and
            -- choose the second file so both real warnings run once more.
            elma.press(1, reload_keys[reload_index])
            pressed, phase = n, "again_release"
        end
    elseif phase == "again_release" and n >= pressed + 6 then
        elma.release(1, reload_keys[reload_index])
        phase = "again_settle"
    elseif phase == "again_settle" and n >= pressed + 90 then
        if reload_index == #reload_keys then
            phase, deadline = "loading", n + 9000
        else
            reload_index = reload_index + 1
            elma.press(1, reload_keys[reload_index])
            pressed, phase = n, "again_release"
        end
    end
end))
