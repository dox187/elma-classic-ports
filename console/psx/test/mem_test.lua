-- Memory test of the game on the PS1, run by test/mem_test.py (through
-- test/pcsx.py, which provides `elma`). Goes from the intro through the name
-- entry and the menus to a level (an internal one, all of them unlocked in
-- the player's state, or the only file of LEV\), gives gas and reports for
-- each phase (boot, menu, load, play):
--   the high-water of the heap: its extent (from the start of the heap to
--   the end of the highest block, what the RAM must hold, gaps included)
--   and the bytes allocated (blocks only),
--   the biggest live allocations of the C++ operator new by calling place
--   (the table of src/psx_platform.cpp) at the frame of the phase with the
--   most bytes in blocks,
-- and at the end the deepest stack use (the stack is painted at boot).
-- Arguments: level=N (internal level, from 0) or external=1, play=FRAMES of
-- gas (default 600), sites=N places listed per phase (default all),
-- shots=1 (screenshots at the start of the level and at the end),
-- after=again,next (then the phases "again": the same level once more, and
-- "next": the next level, each played like the first).
-- With src/mem/psx_mem.c the high-water of a phase is exact (and the free
-- bytes inside the extent are known); else it is sampled once a frame.
-- Output lines: "MEM <phase> ...", "SITE <phase> <addr> <bytes> <blocks>",
-- "STACK ...", "RAMFILES <bytes in the RAM file store>", then PASS or FAIL.

local function need(name)
    local a = elma.sym(name)
    if not a then
        print("FAIL: symbol " .. name .. " not found")
        PCSX.quit(1)
    end
    return a
end
local dbg = need("psx_debug")
local state_ptr = need("State")
-- The heap: the statistics of src/mem/psx_mem.c if it is linked in, else
-- the variables of the SDK's malloc.
local mem_stats = elma.sym("psx_mem_stats")
local heap_start, heap_end, heap_alloc
if not mem_stats then
    heap_start = need("_heap_start")
    heap_end = need("_heap_end")
    heap_alloc = need("_heap_alloc")
end
local sites = elma.sym("_ZN12_GLOBAL__N_111alloc_sitesE")
local SITE_COUNT = 256

local level = tonumber(elma.args.level or "0")
local external = elma.args.external == "1"
local play_frames = tonumber(elma.args.play or "600")
local site_lines = tonumber(elma.args.sites or "256")
local shots = elma.args.shots

local function state()
    return {
        magic = elma.u32(dbg),
        presents = elma.u32(dbg + 4),
        game_frames = elma.u32(dbg + 8),
        menu_chars = elma.u32(dbg + 12),
        bike_x = elma.u32(dbg + 16),
        errors = elma.u32(dbg + 36),
    }
end

local function signed(v)
    if v >= 0x80000000 then return v - 0x100000000 end
    return v
end

-- extent, allocated (and with psx_mem.c the free bytes inside the extent)
local function heap()
    if mem_stats then
        -- psx_mem_stats_t (src/mem/psx_mem.h): magic, start, limit, top,
        -- allocated, allocated_max, top_max, free, blocks, failed,
        -- peak_allocated, peak_free, peak_largest_free
        return elma.u32(mem_stats + 12) - elma.u32(mem_stats + 4), elma.u32(mem_stats + 16),
            elma.u32(mem_stats + 28)
    end
    return elma.u32(heap_end) - elma.u32(heap_start), elma.u32(heap_alloc)
end

local function read_sites()
    local list = {}
    if not sites then return list end
    for i = 0, SITE_COUNT - 1 do
        local a = sites + i * 12
        local bytes = elma.u32(a + 4)
        if bytes > 0 then
            list[#list + 1] = {caller = elma.u32(a), bytes = bytes, blocks = elma.u32(a + 8)}
        end
    end
    table.sort(list, function(x, y) return x.bytes > y.bytes end)
    return list
end

-- Phases and their high-water:
local phases = {}
local order = {}
local current
-- psx_mem.c keeps the exact high-water of the phase: its *_max fields are
-- reset when a phase begins and read when it ends.
local function close_phase()
    if not current or not mem_stats then return end
    current.extent = elma.u32(mem_stats + 24) - elma.u32(mem_stats + 4)
    current.alloc = elma.u32(mem_stats + 20)
    current.alloc_at = elma.u32(mem_stats + 40)
    current.free = elma.u32(mem_stats + 44)
    current.largest = elma.u32(mem_stats + 48)
end
local function enter(name, n)
    close_phase()
    current = {name = name, extent = 0, alloc = 0, sites = {}, start = n}
    phases[name] = current
    order[#order + 1] = name
    if mem_stats then
        elma.write_u32(mem_stats + 24, elma.u32(mem_stats + 12))
        elma.write_u32(mem_stats + 20, elma.u32(mem_stats + 16))
        elma.write_u32(mem_stats + 40, elma.u32(mem_stats + 16))
        elma.write_u32(mem_stats + 44, elma.u32(mem_stats + 28))
        elma.write_u32(mem_stats + 48, 0)
    end
end
-- Each frame: the highest extent seen, and the calling places at the frame
-- with the most bytes in blocks (sites_alloc).
local function sample(n)
    if not current then return end
    local extent, alloc, free = heap()
    if extent > (current.sampled or 0) then
        current.sampled = extent
        current.extent = math.max(current.extent, extent)
        current.alloc_at = alloc
        current.free = free
    end
    if alloc > current.alloc then current.alloc = alloc end
    if alloc > (current.sites_alloc or 0) then
        current.sites_alloc = alloc
        current.frame = n
        current.sites = read_sites()
    end
end

-- The stack: painted below the stack pointer once the game runs, and the
-- deepest overwritten word found at the end.
local PAINT = 0x5354434B
local stack_bottom, stack_top, painted_to
local function paint()
    local sp = tonumber(PCSX.getRegisters().GPR.n.sp)
    sp = bit.band(sp, 0xffffffff)
    if sp < 0 then sp = sp + 0x100000000 end
    if sp >= 0x807f0000 and sp < 0x80800000 then
        stack_top, stack_bottom = 0x807ffff0, 0x807f0000
    elseif sp >= 0x801f0000 and sp < 0x80200000 then
        stack_top, stack_bottom = 0x80200000, 0x801f0000
    else
        print(string.format("STACK not painted (sp %08x)", sp))
        return
    end
    painted_to = sp - 256
    for a = stack_bottom, painted_to - 4, 4 do elma.write_u32(a, PAINT) end
end
local function stack_report()
    if not painted_to then return end
    local a = stack_bottom
    while a < painted_to and elma.u32(a) == PAINT do a = a + 4 end
    print(string.format("STACK used %d bytes of %d (deepest %08x)", stack_top - a,
        stack_top - stack_bottom, a))
end

local function report()
    close_phase()
    for _, name in ipairs(order) do
        local p = phases[name]
        print(string.format("MEM %s extent_max=%d alloc_max=%d alloc_at_peak=%d free_at_peak=%s largest_free=%s sites_alloc=%d frame=%s",
            name, p.extent, p.alloc, p.alloc_at or 0, tostring(p.free or "-"),
            tostring(p.largest or "-"), p.sites_alloc or 0, tostring(p.frame or "-")))
        for i = 1, math.min(site_lines, #p.sites) do
            local s = p.sites[i]
            print(string.format("SITE %s %08x %d %d", name, s.caller, s.bytes, s.blocks))
        end
    end
    stack_report()
    print(string.format("RAMFILES %d", elma.u32(dbg + 40)))
end

local function finish(ok, text)
    if shots then elma.screenshot("end.ppm") end
    report()
    local s = state()
    print(string.format("%s: %s (presents=%d game_frames=%d errors=%d)", ok and "PASS" or "FAIL",
        text, s.presents, s.game_frames, s.errors))
    PCSX.quit(ok and 0 or 1)
end

-- state_s (STATE.H): palyakidejei[90] of 688 bytes, then jatekosok[50] of
-- 116 bytes (sikerespalyakszama at 108, jelenlegipalya at 112), then
-- jatekosokszama.
local function unlock()
    local s = elma.u32(state_ptr)
    local players = elma.u32(s + 61920 + 50 * 116)
    for i = 0, players - 1 do
        local p = s + 61920 + i * 116
        elma.write_u32(p + 108, 53)
        elma.write_u32(p + 112, level)
    end
end

local steps = {
    {name = "intro", button = "CROSS"},
    {name = "name: first letter", button = "RIGHT"},
    {name = "name: enter", button = "CROSS"},
    {name = "main menu: Play", button = "CROSS"},
    {name = "collections: Original Levels", button = "DOWN"},
}
if external then
    -- The collections: Original Levels, External Levels:
    steps[#steps + 1] = {name = "collections: External Levels", button = "DOWN"}
    steps[#steps + 1] = {name = "collections: enter", button = "CROSS"}
    steps[#steps + 1] = {name = "external file: start", button = "CROSS"}
else
    steps[#steps + 1] = {name = "collections: enter", button = "CROSS"}
    steps[#steps + 1] = {name = "levels: start", button = "CROSS"}
end

local step = 0
local phase = "boot"
local deadline = 6000
local press_frame, chars_before, presents_before
local gas_frame, start_x
-- After the first game (after=again,next): leave it and play the same level
-- again, then the next one, through the menu after a game.
local after = {}
for name in string.gmatch(elma.args.after or "", "[^,]+") do after[#after + 1] = name end
local played = {}
local menu_keys, frames_before

elma.on_frame(function(n)
    local s = state()
    sample(n)
    if s.errors > 0 then return finish(false, "the game stopped with an error in phase " .. phase) end
    if n > deadline then return finish(false, "timeout in phase " .. phase) end

    if phase == "boot" then
        if not current then enter("boot", n) end
        if s.magic == 0x454C4D41 and s.presents >= 3 then
            paint()
            enter("menu", n)
            step = 1
            phase = "press"
            deadline = n + 3000
        end
    elseif phase == "press" then
        chars_before, presents_before = s.menu_chars, s.presents
        elma.press(1, steps[step].button)
        press_frame = n
        phase = "release"
    elseif phase == "release" then
        if n >= press_frame + 6 then
            elma.release(1, steps[step].button)
            phase = "taken"
        end
    elseif phase == "taken" then
        -- A fast menu takes the key long before the next one is ready for
        -- keys (it empties the key buffer when it starts): wait a second.
        local drawn = step == #steps or (s.presents >= presents_before + 4 and n >= press_frame + 60)
        if s.menu_chars > chars_before and drawn then
            if steps[step].name == "name: enter" then unlock() end
            if step == #steps then
                enter("load", n)
                phase = "loading"
                deadline = n + 8000
            else
                step = step + 1
                phase = "press"
                deadline = n + 3000
            end
        elseif n > press_frame + 600 and s.menu_chars == chars_before then
            phase = "press"
        end
    elseif phase == "loading" then
        if s.game_frames >= 3 then
            print(string.format("frame %d: level running after %d frames of loading", n,
                n - current.start))
            enter("play", n)
            if shots then elma.screenshot("level.ppm") end
            start_x = signed(s.bike_x)
            elma.press(1, "UP")
            gas_frame = n
            phase = "play"
            deadline = n + play_frames + 600
        end
    elseif phase == "play" then
        if n >= gas_frame + play_frames then
            elma.release(1, "UP")
            local moved = math.abs(signed(s.bike_x) - start_x)
            played[#played + 1] = string.format("%s: %d mm", current.name, moved)
            if not after or #after == 0 then
                return finish(true, string.format("the level ran %d frames, the bike moved: %s",
                    play_frames, table.concat(played, ", ")))
            end
            -- Leave the game; the menu after it comes up.
            elma.press(1, "SELECT")
            press_frame = n
            phase = "leave"
            deadline = n + 3000
        end
    elseif phase == "leave" then
        if n == press_frame + 6 then elma.release(1, "SELECT") end
        if n >= press_frame + 240 then
            -- The menu after a game: Play again, Play next, ...
            local name = table.remove(after, 1)
            if name == "next" then
                menu_keys = {"DOWN", "CROSS"}
            else
                menu_keys = {"CROSS"}
            end
            enter(name, n)
            frames_before = s.game_frames
            phase = "menu_keys"
            press_frame = n
        end
    elseif phase == "menu_keys" then
        local k = menu_keys[1]
        if n == press_frame + 1 then elma.press(1, k) end
        if n == press_frame + 7 then elma.release(1, k) end
        if n >= press_frame + 90 then
            table.remove(menu_keys, 1)
            press_frame = n
            if #menu_keys == 0 then
                phase = "again_loading"
                deadline = n + 8000
            end
        end
    elseif phase == "again_loading" then
        if s.game_frames >= frames_before + 3 then
            start_x = signed(s.bike_x)
            elma.press(1, "UP")
            gas_frame = n
            phase = "play"
            deadline = n + play_frames + 600
        end
    end
end)
