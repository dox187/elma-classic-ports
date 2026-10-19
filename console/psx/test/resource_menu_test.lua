-- Check actual rendered menu text and the loaded level's identity in 2 MB.
if jit then jit.off() end
local function need(name)
    return assert(elma.sym(name), "symbol not found: " .. name)
end
local dbg, top = need("psx_debug"), need("Ptop")
local rows_ptr, rows_count = need("_ZL6Hsorok"), need("_ZL5Hszam")
local slots = need("_ZL9Leiroszam")
local counts = need("_ZL11Palyaszamok")
local dialogs = need("psx_dialog_waits")
local scenario = elma.args.scenario
local collections = elma.args.collections == "1"
local wanted_stamp = tonumber(elma.args.stamp)
local quitting = false
local log = elma.args.log and assert(io.open(elma.args.log, "w"))
local function say(text)
    print(text)
    if log then log:write(text, "\n") log:flush() end
end

local function split(text, pattern)
    local result = {}
    for item in text:gmatch(pattern) do result[#result + 1] = item end
    return result
end
local wanted_rows = split(elma.args.rows or "", "[^|]+")
local wanted_counts = split(elma.args.counts, "[^,]+")
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
local function finish(ok, text)
    if quitting then return end
    quitting = true
    if elma.args.shots then elma.screenshot(elma.args.shots .. (ok and "pass" or "fail") .. ".ppm") end
    say((ok and "PASS: " or "FAIL: ") .. text)
    PCSX.quit(ok and 0 or 1)
end

local phase, step, started, deadline = "boot", 1, 0, 18000
local boot_steps = {"CROSS", "RIGHT", "CROSS"}
local button, pressed_at, wait_until, key_presents, key_chars, next_phase
local function press(name, n, afterwards, wait)
    button, pressed_at, next_phase = name, n, afterwards
    key_presents, key_chars = elma.u32(dbg + 4), elma.u32(dbg + 12)
    elma.press(1, name)
    wait_until = n + (wait or 75)
    phase = "key"
end
local path, path_index = {}, 1
local game_start, game_frame, bike_x
local dialog_seen, dialog_release = 0, nil

elma.on_frame(function(n)
    if quitting then return end
    local ok, err = xpcall(function()
        if n > deadline then return finish(false, "timeout in " .. phase) end
        if elma.u32(dbg + 36) > 0 then return finish(false, "runtime error in " .. phase) end
        if phase == "boot" then
            if elma.u32(dbg) == 0x454c4d41 and elma.u32(dbg + 4) >= 3 then
                press(boot_steps[step], n, "boot_next", 180)
            end
        elseif phase == "key" then
            if n >= pressed_at + 6 then elma.release(1, button) end
            if n >= wait_until and elma.u32(dbg + 12) > key_chars then
                phase = next_phase
            end
        elseif phase == "boot_next" then
            step = step + 1
            if step <= #boot_steps then
                press(boot_steps[step], n, "boot_next", 120)
            else
                phase = "main"
            end
        elseif phase == "main" then
            if has(menu_rows(), "Play") then press("CROSS", n, "play_menu", 120) end
        elseif phase == "play_menu" then
            local rows = menu_rows()
            if collections and not has(rows, "Select collection!") then return end
            if not collections and not has(rows, "Select Level!") then return end
            if elma.u32(slots) ~= tonumber(elma.args.slots) then
                return finish(false, "resource descriptor layout mismatch")
            end
            for i, value in ipairs(wanted_counts) do
                if elma.u32(counts + 4 * (i - 1)) ~= tonumber(value) then
                    return finish(false, "resource collection count mismatch")
                end
            end
            if collections then
                if #rows ~= #wanted_rows + 1 then return finish(false, "unexpected collection row count") end
                for i, prefix in ipairs(wanted_rows) do
                    if rows[i + 1]:sub(1, #prefix) ~= prefix then
                        return finish(false, "collection row mismatch: " .. rows[i + 1])
                    end
                end
            else
                if not has(rows, "External File") or not has(rows, "1 Warm Up") or has(rows, "Tutorial") then
                    return finish(false, "classic level menu mismatch")
                end
            end
            say("MENU " .. table.concat(rows, " | "))
            if elma.args.shots then elma.screenshot(elma.args.shots .. "menu.ppm") end
            if scenario == "collection" then
                -- A fresh collection starts its first level directly.
                path = split(elma.args.collection_steps, "[^,]+")
            else
                path = split(elma.args[scenario == "external" and "external_steps" or "internal_steps"], "[^,]+")
            end
            path_index, phase = 1, "path"
        elseif phase == "path" then
            if path_index == #path then
                press(path[path_index], n, "loading", 6)
            else
                press(path[path_index], n, "path_next", 120)
            end
        elseif phase == "path_next" then
            path_index = path_index + 1
            if scenario == "external" and path_index == #path then
                if not has(menu_rows(), "TEST.LEV") then return finish(false, "external file list not rendered") end
                say("MENU external file TEST.LEV")
            end
            phase = "path"
        elseif phase == "loading" then
            if dialog_release and n >= dialog_release then
                elma.release(1, "CROSS")
                dialog_release = nil
            end
            if not dialog_release and elma.u32(dialogs) > dialog_seen then
                dialog_seen = elma.u32(dialogs)
                elma.press(1, "CROSS")
                dialog_release = n + 6
            end
            if elma.u32(dbg + 8) >= 3 then
                local ptr = elma.u32(top)
                if ptr == 0 or elma.u32(ptr) ~= wanted_stamp then return finish(false, "wrong level loaded") end
                if elma.u32(dbg + 44) ~= 0 then return finish(false, "development RAM enabled") end
                say(string.format("LEVEL stamp=%08x retail2MB", wanted_stamp))
                game_start, game_frame = n, elma.u32(dbg + 8)
                bike_x = elma.u32(dbg + 16)
                elma.press(1, "UP")
                phase = "game"
            end
        elseif phase == "game" then
            if n >= game_start + 120 then
                elma.release(1, "UP")
                if elma.u32(dbg + 8) < game_frame + 30 or elma.u32(dbg + 16) == bike_x then
                    return finish(false, "level did not keep rendering and moving")
                end
                return finish(true, "resource menu and requested level verified")
            end
        end
    end, function(error) return tostring(error) .. "\n" .. debug.traceback("", 2):sub(1, 500) end)
    if not ok then return finish(false, "Lua error: " .. tostring(err)) end
end)
