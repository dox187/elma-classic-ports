-- Console root screens ignore Back; ordinary submenu cancellation still works.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "symbol not found: " .. name) end
local dbg, state_ptr = need("psx_debug"), need("State")
local rows_ptr, rows_count = need("_ZL6Hsorok"), need("_ZL5Hszam")
local card = need("psx_memcard_debug")
local log = elma.args.log and assert(io.open(elma.args.log, "w"))
local function say(text)
    print(text)
    if log then log:write(text, "\n"); log:flush() end
end
local function cstring(address, size)
    local chars = {}
    for i = 0, size - 1 do
        local value = elma.u8(address + i)
        if value == 0 then break end
        chars[#chars + 1] = string.char(value)
    end
    return table.concat(chars)
end
local function menu_rows()
    local address, count = elma.u32(rows_ptr), elma.u32(rows_count)
    if address == 0 or count > 300 then return {} end
    local rows = {}
    -- egyszovsor: text[102], padding[2], x, y, kozep (116 bytes on MIPS).
    for i = 0, count - 1 do rows[#rows + 1] = cstring(address + 116 * i, 102) end
    return rows
end
local function has(rows, prefix)
    for _, text in ipairs(rows) do
        if text:sub(1, #prefix) == prefix then return true end
    end
    return false
end
local function on_screen(kind, rows)
    if kind == "name" then return has(rows, "Please enter your name:") end
    if kind == "main" then return has(rows, "Main Menu") and has(rows, "Play") end
    if kind == "play" then return has(rows, "Select collection!") or has(rows, "Select Level!") end
    if kind == "options" then return has(rows, "Options") and has(rows, "Player A:") end
    if kind == "choose" then return has(rows, "Choose Player") and has(rows, "Create New Player") end
    return false
end
local function players()
    local state = elma.u32(state_ptr)
    -- state_s: 90 level times (688 bytes), then 50 players (116 bytes).
    return state ~= 0 and elma.u32(state + 90 * 688 + 50 * 116) or nil
end
local function animated_menus()
    local state = elma.u32(state_ptr)
    -- Player count, two 15-byte names, alignment, then eight int fields.
    return state ~= 0 and elma.u32(state + 90 * 688 + 50 * 116 + 68) or nil
end
local quitting = false
local function finish(ok, text)
    if quitting then return end
    quitting = true
    if ok and elma.args.capture then elma.screenshot(elma.args.capture) end
    if elma.args.shots then elma.screenshot(elma.args.shots .. (ok and "pass" or "fail") .. ".ppm") end
    say((ok and "PASS: " or "FAIL: ") .. text)
    PCSX.quit(ok and 0 or 1)
end

local fresh = elma.args.scenario == "fresh"
local steps = {}
local function step(name, button, screen, count, wait)
    local result = {name = name, button = button, screen = screen, players = count, wait = wait or 90}
    steps[#steps + 1] = result
    return result
end
step("intro", "CROSS", fresh and "name" or "choose", fresh and 0 or 1, 180).animated = fresh and 1 or 0
if fresh then
    step("first-name Circle ignored", "CIRCLE", "name", 0)
    step("first-name Select ignored", "SELECT", "name", 0)
    step("name first letter", "RIGHT", "name", 0)
    step("create first player", "CROSS", "main", 1)
else
    step("startup chooser Circle ignored", "CIRCLE", "choose", 1)
    step("startup chooser Select ignored", "SELECT", "choose", 1)
    step("choose saved player", "CROSS", "main", 1)
end
step("Main Menu Circle ignored", "CIRCLE", "main", 1)
step("Main Menu Select ignored", "SELECT", "main", 1)
if fresh then
    step("open Play submenu", "CROSS", "play", 1)
    step("Play submenu Circle returns", "CIRCLE", "main", 1)
    step("reopen Play submenu", "CROSS", "play", 1)
    step("Play submenu Select returns", "SELECT", "main", 1)
    for i = 1, 3 do step("select Options row " .. i, "DOWN", "main", 1) end
    step("open Options", "CROSS", "options", 1)
    step("select Player A", "DOWN", "options", 1)
    step("open Options player chooser", "CROSS", "choose", 1)
    step("Options chooser Circle returns", "CIRCLE", "options", 1)
    step("reopen Options player chooser", "CROSS", "choose", 1)
    step("Options chooser Select returns", "SELECT", "options", 1)
    for _, button in ipairs({"CIRCLE", "SELECT"}) do
        step("open chooser for new player", "CROSS", "choose", 1)
        step("select Create New Player", "UP", "choose", 1)
        step("open cancellable name prompt", "CROSS", "name", 1)
        step("new player " .. button .. " cancels", button, "options", 1)
    end
    for i = 1, 4 do step("select Animated Menus row " .. i, "DOWN", "options", 1) end
    step("turn Animated Menus off", "CROSS", "options", 1).animated = 0
    step("Options Back returns to Main Menu", "CIRCLE", "main", 1)
end

local index, phase, deadline = 1, "boot", 6000
local pressed_at, presents_before, chars_before, released
local saves_before_player
local function begin(n)
    local current = steps[index]
    if current.name == "create first player" then saves_before_player = elma.u32(card + 4) end
    presents_before, chars_before = elma.u32(dbg + 4), elma.u32(dbg + 12)
    elma.press(1, current.button)
    pressed_at, released, phase, deadline = n, false, "key", n + 1800
end
elma.on_frame(function(n)
    if quitting then return end
    local ok, err = xpcall(function()
        local rows = menu_rows()
        if has(rows, "Do you want to quit?") then return finish(false, "console opened the desktop quit dialog") end
        if elma.u32(dbg + 36) ~= 0 then return finish(false, "runtime error") end
        if n > deadline then return finish(false, "timeout at " .. steps[index].name .. ": " .. table.concat(rows, " | ")) end
        if phase == "boot" then
            if elma.u32(dbg) == 0x454c4d41 and elma.u32(dbg + 4) >= 3 then begin(n) end
        elseif phase == "key" then
            local current = steps[index]
            if not released and n >= pressed_at + 6 then
                elma.release(1, current.button)
                released = true
            end
            if n >= pressed_at + current.wait and elma.u32(dbg + 12) > chars_before and
                elma.u32(dbg + 4) >= presents_before + 4 and on_screen(current.screen, rows) then
                if players() ~= current.players then return finish(false, "wrong player count after " .. current.name) end
                if current.animated ~= nil and animated_menus() ~= current.animated then
                    return finish(false, "wrong Animated Menus setting after " .. current.name)
                end
                say("UI " .. current.name .. "; screen=" .. current.screen)
                index = index + 1
                if index > #steps then
                    if elma.u32(dbg + 44) ~= 0 then return finish(false, "development RAM enabled") end
                    if fresh and (elma.u32(card + 4) <= saves_before_player or elma.u32(card + 8) ~= 0) then
                        return finish(false, "private player card was not saved after creating the player")
                    end
                    return finish(true, fresh and "root Back ignored; submenu and new-player cancellation work" or
                        "saved player and menu setting restored; startup Back ignored and Main Menu remains active")
                end
                begin(n)
            elseif n >= pressed_at + 600 and elma.u32(dbg + 12) == chars_before then
                -- A transition or card transfer may have consumed the press.
                begin(n)
            end
        end
    end, function(error) return tostring(error) .. "\n" .. debug.traceback("", 2):sub(1, 500) end)
    if not ok then finish(false, "Lua error: " .. tostring(err)) end
end)
