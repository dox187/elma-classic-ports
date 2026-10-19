-- Memory card test, run by test/pcsx.py (the prelude provides `elma`).
-- Waits for mctest to boot, sets the operation, waits until it is done and
-- prints one RESULT line with the state words (parsed by test/mc_test.py).
--   --arg op=1|2|3  --arg kind=0|1|2  --arg crc=N --arg len=N  --arg frames=N
-- --arg nocard=1 ejects the card of slot 1 before the program starts.
if elma.args.nocard == "1" then PCSX.settings.emulator.Mcd1Inserted = false end
local MAX_FRAMES = tonumber(elma.args.frames or "3000")
local state = elma.sym("mctest_state")
if not state then
    print("FAIL: symbol mctest_state not found")
    PCSX.quit(1)
end
local names = {"magic", "op", "kind", "expect_crc", "expect_len", "done",
               "init_status", "status", "status2", "data_ok", "crc", "len",
               "blocks", "frames", "ticks", "comp_bytes"}
local function word(n) return state + (n - 1) * 4 end
local started = false
elma.on_frame(function(n)
    if not started and elma.u32(state) == 0x4D435354 and n >= 20 then
        started = true
        elma.write_u32(word(3), tonumber(elma.args.kind or "0"))
        elma.write_u32(word(4), tonumber(elma.args.crc or "0"))
        elma.write_u32(word(5), tonumber(elma.args.len or "0"))
        elma.write_u32(word(2), tonumber(elma.args.op or "3"))
    end
    local done = elma.u32(word(6)) == 1
    if done or n >= MAX_FRAMES then
        local parts = {}
        for i, nm in ipairs(names) do
            parts[#parts + 1] = string.format("%s=%d", nm, elma.u32(word(i)))
        end
        print("RESULT done=" .. tostring(done) .. " " .. table.concat(parts, " "))
        PCSX.quit(done and 0 or 2)
    end
end)
