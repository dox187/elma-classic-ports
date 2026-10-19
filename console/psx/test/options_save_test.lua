-- Save changed game modes from Options and verify the card after a reboot.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "missing symbol: " .. name) end
local dbg, card = need("psx_debug"), need("psx_memcard_debug")
local state_ptr = need("State")
local rows_ptr, rows_count = need("_ZL6Hsorok"), need("_ZL5Hszam")
local log = assert(io.open(elma.args.log, "w"))
local function say(text) print(text); log:write(text, "\n"); log:flush() end
local function single()
    return elma.u32(elma.u32(state_ptr) + 90 * 688 + 50 * 116 + 44)
end
local function rows_have(prefix)
    local address, count = elma.u32(rows_ptr), elma.u32(rows_count)
    if address == 0 or count > 300 then return false end
    for row = 0, count - 1 do
        local matches = true
        for i = 1, #prefix do
            if elma.u8(address + row * 116 + i - 1) ~= prefix:byte(i) then matches = false; break end
        end
        if matches then return true end
    end
    return false
end
local function screen(name)
    return rows_have(name == "main" and "Main Menu" or "Options")
end
local stopped = false
local function finish(ok, message)
    if stopped then return end
    stopped = true
    say((ok and "PASS: " or "FAIL: ") .. message)
    PCSX.quit(ok and 0 or 1)
end
local steps, index, phase = {}, 1, "boot"
local deadline, pressed, chars, presents, released, saves = 6000
local function add(name, button, target, mode, saving)
    steps[#steps + 1] = {name=name, button=button, target=target, mode=mode, saving=saving}
end
local function begin(n)
    local s = steps[index]
    chars, presents = elma.u32(dbg+12), elma.u32(dbg+4)
    saves = elma.u32(card+4)
    elma.press(1, s.button)
    pressed, released, phase, deadline = n, false, "key", n+2400
end
elma.on_frame(function(n)
    if stopped then return end
    local ok, error = pcall(function()
        if elma.u32(dbg+36) ~= 0 then return finish(false, "runtime error during Options save") end
        if n > deadline then return finish(false, "timeout at " .. (steps[index] and steps[index].name or phase)) end
        if phase == "boot" then
            if elma.u32(dbg) ~= 0x454c4d41 or elma.u32(dbg+4) < 3 then return end
            if elma.u32(state_ptr) == 0 or elma.u32(card) ~= 0x4443524d then return end
            if elma.u32(card+16) ~= 0 then return finish(false, "private card failed to load") end
            local count = elma.u32(elma.u32(state_ptr)+90*688+50*116)
            if count < 1 then return finish(false, "saved-player fixture required") end
            local run = tonumber(elma.args.run)
            if run == 2 and single() ~= 0 then return finish(false, "Multiplayer did not survive reboot") end
            if run == 3 and single() ~= 1 then return finish(false, "Single Player did not survive reboot") end
            add("choose saved player", "CROSS", "main")
            local target = run == 1 and 0 or 1
            if run ~= 3 and single() ~= target then
                for i=1,3 do add("select Options "..i,"DOWN","main") end
                add("open Options","CROSS","options")
                local mode = target == 1 and "Single Player" or "Multiplayer"
                add("select "..mode,"CROSS","options",target)
                add("save "..mode,"CIRCLE","main",target,true)
            end
            begin(n)
        elseif phase == "key" then
            local s = steps[index]
            if not released and n >= pressed+6 then elma.release(1,s.button); released=true end
            if n < pressed+(s.saving and 300 or 90) or elma.u32(dbg+12) <= chars or
                elma.u32(dbg+4) < presents+4 or not screen(s.target) then return end
            if s.mode ~= nil and single() ~= s.mode then return finish(false,"wrong game mode after "..s.name) end
            if s.saving then
                if elma.u32(card+4) <= saves or elma.u32(card+12) ~= 0 then return end
                if elma.u32(card+8) ~= 0 then return finish(false,"card save failed after "..s.name) end
                say("OPTIONS "..s.name.."; card saved successfully")
            else say("OPTIONS "..s.name) end
            index=index+1
            if index > #steps then
                if elma.u32(dbg+44) ~= 0 then return finish(false,"development RAM enabled") end
                local messages = {"Multiplayer prepared on the private card",
                    "Multiplayer restored and Single Player saved successfully from Options",
                    "Single Player restored from the private card"}
                return finish(true,messages[tonumber(elma.args.run)])
            end
            begin(n)
        end
    end)
    if not ok then finish(false,"Lua error: "..tostring(error)) end
end)
