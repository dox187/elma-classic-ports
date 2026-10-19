-- Marks state changes in an actual SDL disk-backend capture. The ordinary
-- memory harness drives a ride, the menu after it, and Play again.
local dbg = assert(elma.sym("psx_debug"))
local state = assert(elma.sym("State"))
local mute = assert(elma.sym("Mute"))
local first_active, last_mute, last_sound
local toggle_phase = 0
local failed = false
local card = elma.args.card_save == "1" and assert(elma.sym("psx_memcard_debug"))
local saves_before, save_requested
print("sound output: SPU settings", PCSX.settings.spu.Volume, PCSX.settings.spu.Mute)

elma.on_frame(function(n)
    if failed then return end
    local ok, err = pcall(function()
        if elma.u32(dbg + 8) < 3 then return end
        local m = elma.u32(mute)
        local sound = elma.u32(state) + 67756
        local s = elma.u32(sound)
        if not first_active then first_active = n end
        -- Also exercise the sound option while the core's Mute is false.
        if toggle_phase == 0 and n >= first_active + 45 then
            elma.write_u32(sound, 0)
            s, toggle_phase = 0, 1
        elseif toggle_phase == 1 and n >= first_active + 75 then
            elma.write_u32(sound, 1)
            s, toggle_phase = 1, 2
        end
        if card and not save_requested and n >= first_active + 90 then
            saves_before = elma.u32(card + 4)
            -- The core defers state writes made during a ride until the
            -- menu. Re-save the existing state through that normal path.
            elma.write_u32(card + 12, 1)
            save_requested = true
        end
        if card and last_mute == 1 and m == 0 then
            assert(save_requested and elma.u32(card + 4) > saves_before,
                   "memory card was not saved between rides")
            assert(elma.u32(card + 8) == 0, "memory card save failed")
            print("AUDIO_CARD resumed after save", elma.u32(card + 4))
        end
        if m ~= last_mute or s ~= last_sound then
            local f = assert(io.open(elma.args.capture_path, "rb"))
            local bytes = f:seek("end")
            f:close()
            print(string.format("AUDIO_MARK mute=%d sound=%d bytes=%d", m, s, bytes))
            last_mute, last_sound = m, s
        end
    end)
    if not ok then
        failed = true
        print("FAIL: audio capture marker: " .. tostring(err))
        PCSX.quit(99)
    end
end)
dofile(elma.args.memory_lua)
