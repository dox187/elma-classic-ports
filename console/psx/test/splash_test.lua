-- Capture actual startup video before resource initialization and the final
-- static splash. Breakpoint snapshots prove neither drawing helper allocates.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "missing symbol " .. name) end
local dbg, mem = need("psx_debug"), need("psx_mem_stats")
local intro, force = need("Pintro"), need("psx_video_force")
local done, frame, loads = false, 0, 0
local loading, captured, prepared, presented, presented_at
local callbacks = {}
local function finish(ok, reason)
    if done then return end
    done = true
    print((ok and "PASS: " or "FAIL: ") .. reason)
    PCSX.quit(ok and 0 or 1)
end
local function guard(fn)
    return function(...)
        if done then return true end
        local ok, err = pcall(fn, ...)
        if not ok then finish(false, tostring(err):sub(1, 800)) end
        return true
    end
end
local function bp(address, fn)
    callbacks[#callbacks + 1] = PCSX.addBreakpoint(address, "Exec", 4, "splash", guard(fn))
end
local function heap() return {elma.u32(mem + 12), elma.u32(mem + 16), elma.u32(mem + 32)} end
local function check(before)
    local after = heap()
    for i, value in ipairs(before) do assert(value == after[i], "splash helper allocated memory") end
end
local function on_return(fn)
    local address = tonumber(PCSX.getRegisters().GPR.n.ra)
    if address < 0 then address = address + 0x100000000 end
    local once = false
    bp(address, function()
        if once then return end
        once = true
        fn()
    end)
end
bp(need("_Z6ddinitv"), function() elma.write_u32(force, tonumber(elma.args.force)) end)
bp(need("FntLoad"), function()
    loads = loads + 1
    assert(loads == 1, "resident font was loaded again")
end)
bp(need("_Z9gv_noticeiiiiPKPKci"), function()
    if loading then return end
    local before = heap()
    on_return(function()
        check(before)
        assert(elma.u32(intro) == 0, "first Loading followed splash allocation")
        loading = true
        print("BOOT early Loading drawn without heap allocation")
    end)
end)
bp(need("_Z9initqopenv"), function()
    assert(loading, "resource initialization preceded Loading")
end)
bp(need("_Z18psx_splash_prepareP4pic8"), function()
    local before = heap()
    on_return(function()
        check(before)
        local picture = elma.u32(intro)
        assert(picture ~= 0 and elma.u32(picture + 8) == 512 and elma.u32(picture + 12) == 480,
               "incorrect composed splash dimensions")
        prepared = true
        print("BOOT splash composed in its existing allocation")
    end)
end)
bp(need("_Z8bltfrontP4pic8"), function()
    if not prepared or presented then return end
    on_return(function() presented, presented_at = true, frame end)
end)
elma.on_frame(guard(function(n)
    frame = n
    assert(elma.u32(dbg + 36) == 0, "game stopped with an error")
    assert(n < 12000, "startup timed out")
    if loading and not captured then
        assert(elma.u32(intro) == 0, "Loading capture was too late")
        elma.screenshot("loading.ppm")
        captured = true
    end
    if presented and n >= presented_at + 6 then
        assert(captured and loads == 1, "early screen or resident font was not verified")
        assert(elma.u32(dbg + 56) == tonumber(elma.args.force) - 1, "incorrect video region")
        elma.screenshot("splash.ppm")
        finish(true, "splash Loading, composition, resident font and video region")
    end
end))
