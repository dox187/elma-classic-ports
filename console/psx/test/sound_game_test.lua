-- Runs test/core_boot_test.lua (the game from the intro to Warm Up with gas)
-- and prints the sound stream counters now and then, to see that the real
-- game streams its sound without underruns. Started by sound_game_test.py.

local stats = elma.sym("spu_stats")
local steps = elma.sym("irq_steps")
local function dump(n)
    if not stats then return end
    local function u(o) return tonumber(elma.u32(stats + o)) end
    print(string.format("sound: frame %d blocks=%d irq_steps=%d underruns=%d resyncs=%d late_blocks=%d overflows=%d uploads=%d",
        n, u(0), tonumber(elma.u32(steps)), u(8), u(12), u(16), u(20), u(24)))
end
elma.on_frame(function(n)
    if n % 300 == 0 then dump(n) end
end)
dofile(elma.args.core_lua)
