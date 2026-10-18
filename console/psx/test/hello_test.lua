-- Hello smoke test, run by test/pcsx.py (the prelude provides `elma`).
-- Passes when the magic value is set, the frame counter advances, and an
-- injected pad press shows up in the program's pad state.

local FRAMES = tonumber(elma.args.frames or "150")
local MAGIC = 0x454C4D41

local state = elma.sym("hello_state")
if not state then
    print("FAIL: symbol hello_state not found")
    PCSX.quit(1)
end

local first_frames = nil
local pad_seen = false

elma.on_frame(function(n)
    if n == 30 then
        first_frames = elma.u32(state + 4)
        elma.press(1, "CROSS")
    elseif n > 30 and n < FRAMES and not pad_seen and elma.u32(state + 8) == 0x4000 then
        -- PAD_CROSS is bit 14
        pad_seen = true
        elma.release(1, "CROSS")
    elseif n == FRAMES then
        local magic = elma.u32(state)
        local frames = elma.u32(state + 4)
        print(string.format("magic=%08x frames=%d first=%s pad_seen=%s",
            magic, frames, tostring(first_frames), tostring(pad_seen)))
        elma.screenshot(elma.args.shot or "hello.ppm")
        local ok = magic == MAGIC and first_frames ~= nil and frames > first_frames
            and frames > first_frames + 20
        if elma.args.need_pad ~= "0" and not pad_seen then ok = false end
        print(ok and "PASS" or "FAIL")
        PCSX.quit(ok and 0 or 1)
    end
end)
