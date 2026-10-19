-- Retail disc menu timing and optional exact partial/full repaint comparison.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "missing symbol " .. name) end
local dbg, card = need("psx_debug"), need("psx_memcard_debug")
local video, prof = need("psx_video_force"), need("gv_prof")
local rows_ptr, rows_count = need("_ZL6Hsorok"), need("_ZL5Hszam")
local compare = elma.args.compare == "1"
local enabled = compare and need("gpu_menu_compare_enable")
local compared = compare and need("gpu_menu_compare_frames")
local errors = compare and need("gpu_menu_compare_errors")
local timed = compare and need("gpu_menu_timed_frames")
local fast = compare and need("gpu_menu_cached_ticks")
local slow = compare and need("gpu_menu_uncached_ticks")
local force = tonumber(elma.args.force)
local frames = tonumber(elma.args.frames)
local compare_frames = tonumber(elma.args.compare_frames)
local log = assert(io.open(elma.args.log, "w"))
local function say(text) print(text); log:write(text, "\n"); log:flush() end
local function seconds() return tonumber(PCSX.getCPUCycles()) / 33868800 end
local function has(text)
    local address, count = elma.u32(rows_ptr), elma.u32(rows_count)
    if address == 0 or count > 300 then return false end
    for row = 0, count - 1 do
        local chars = {}
        for i = 0, 101 do
            local c = elma.u8(address + row*116 + i)
            if c == 0 then break end
            chars[#chars+1] = string.char(c)
        end
        if table.concat(chars) == text then return true end
    end
    return false
end
local quitting = false
local function finish(ok, text)
    if quitting then return end
    quitting = true
    say((ok and "PASS: " or "FAIL: ") .. text)
    PCSX.quit(ok and 0 or 1)
end
local function snapshot(n)
    return {time=seconds(), frame=n, presents=elma.u32(dbg+4),
            stopper=elma.u32(dbg+48)/1000, vblanks=elma.u32(dbg+52),
            upload=elma.u32(prof+16), physics=elma.u32(prof+20), draw=elma.u32(prof+24)}
end
local phase, button, pressed, next_phase = "boot", nil, 0, nil
local function press(key, n, next)
    button, pressed, next_phase, phase = key, n, next, "release"
    elma.press(1,key)
end
local first, last, histogram, start_frame = nil, nil, {}, nil
local previous_presents = 0
elma.on_frame(function(n)
    if quitting then return end
    local ok, err = xpcall(function()
        if n > 18000 then return finish(false,"timeout in " .. phase) end
        if elma.u32(dbg+36) ~= 0 then return finish(false,"runtime error") end
        if compare and elma.u32(errors) ~= 0 then return finish(false,"partial/full menu pixels differ") end
        local presents = elma.u32(dbg+4)
        local moved = presents ~= previous_presents
        previous_presents = presents
        if presents == 0 and elma.u32(dbg) == 0x454c4d41 then elma.write_u32(video,force) end
        if phase == "boot" and presents >= 3 then
            say(string.format("MENU first usable intro %.3f emulated seconds",seconds()))
            press("CROSS",n,"name")
        elseif phase == "release" and n >= pressed+6 then
            elma.release(1,button); phase=next_phase
        elseif phase == "name" and n >= pressed+180 and has("Please enter your name:") then
            press("RIGHT",n,"letter")
        elseif phase == "letter" and n >= pressed+90 then
            press("CROSS",n,"main")
        elseif phase == "main" and moved and has("Main Menu") and n >= pressed+300 then
            if elma.u32(card+4) == 0 or elma.u32(card+8) ~= 0 then return end
            if elma.u32(dbg+44) ~= 0 then return finish(false,"development RAM enabled") end
            say("MENU first player saved to private card")
            first=snapshot(n); last=first; start_frame=n; phase="measure"
            if compare then elma.write_u32(enabled,1) end
        elseif phase == "measure" then
            if presents ~= last.presents then
                local gap=n-last.frame
                histogram[gap]=(histogram[gap] or 0)+1
                last=snapshot(n)
            end
            if moved and n >= start_frame+frames and presents ~= first.presents and
                (not compare or elma.u32(compared) >= compare_frames) then
                local now=snapshot(n)
                local dt, count=now.time-first.time, now.presents-first.presents
                local hz=(now.vblanks-first.vblanks)/dt
                local clock=(now.stopper-first.stopper)/dt
                say(string.format("MENU %.3f presents/s; VBlank %.3f Hz; draw %.3f ms, upload %.3f ms, balls %.3f ms",
                    count/dt,hz,(now.draw-first.draw)*1000/4233600/count,
                    (now.upload-first.upload)*1000/4233600/count,(now.physics-first.physics)*1000/4233600/count))
                local gaps={}
                for gap=1,120 do if histogram[gap] then gaps[#gaps+1]=gap..":"..histogram[gap] end end
                say("CADENCE VBlank gaps "..table.concat(gaps,", "))
                if math.abs(hz-(force==2 and 50 or 59.94)) > 0.4 or math.abs(clock-182) > 0.4 then
                    return finish(false,"video or stopwatch rate differs")
                end
                if compare then
                    local count=elma.u32(timed)
                    if count < compare_frames/2 then return finish(false,"too few cached frame comparisons") end
                    say(string.format("PARITY %d frames, zero errors; same-geometry partial draw cached %.3f ms / uncached %.3f ms",
                        elma.u32(compared),elma.u32(fast)*1000/4233600/count,elma.u32(slow)*1000/4233600/count))
                elseif count/dt < 20 then return finish(false,"menu presents below 20 per second") end
                return finish(true,compare and "exact menu repaint comparison" or "retail disc menu timing and first-player save")
            end
        end
    end,function(e) return tostring(e).."\n"..debug.traceback("",2):sub(1,500) end)
    if not ok then finish(false,err) end
end)
