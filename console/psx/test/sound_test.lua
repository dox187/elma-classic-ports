-- Checks the result of soundtest.exe (soundtest/main.cpp), which streams a
-- known signal through the SPU and verifies everything inside the PS1. This
-- script waits for the program to finish, cross-checks playback progress
-- independently from the emulator frame count, compares the encoder CRC with
-- the host build (--arg crc=XXXXXXXX) and reports PASS/FAIL.

local state = elma.sym("sound_state")
assert(state, "sound_state not found in the map file")

local MAGIC = 0x534e4421
local F = { magic = 0, done = 4, fail_mask = 8, frame = 12, irq_steps = 16,
    underruns = 20, resyncs = 24, overflows = 28, uploads = 32, readbacks = 36,
    readback_bad = 40, decode_checks = 44, decode_min_ratio = 48,
    speed_per_mille = 52, crc = 56, hang_calls = 60, hang_cycles_avg = 64,
    hang_cycles_max = 68, enc_cycles_signal = 72, enc_cycles_noise = 76,
    enc_cycles_silence = 80, mixed_samples = 84, hang_cycles_a = 88, dma_cycles_1 = 92, dma_cycles_40 = 96, irq_cycles = 100, mixer_cycles_a = 104, dbg0 = 108, dbg1 = 112, dbg2 = 116, dbg3 = 120 }
local function field(name) return tonumber(elma.u32(state + F[name])) end

local CPU_HZ = 33868800
local BLOCK_CYCLES = CPU_HZ * 550 / 11025 -- CPU cycles per 550 samples

local timeline = {} -- {emulated frame, program frame, irq steps}
local function on_frame(n)
    if field("magic") == MAGIC and field("hang_calls") > 0 and #timeline < 2 then
        if n % 100 == 0 then
            timeline[#timeline + 1] = { n, field("frame"), field("irq_steps"),
                tonumber(PCSX.getCPUCycles()) }
        end
    end
    if field("done") == 1 then
        local ok = true
        local function check(cond, text)
            if not cond then print("FAIL: " .. text); ok = false end
        end
        check(field("magic") == MAGIC, "magic")
        check(field("fail_mask") == 0, string.format("fail_mask=0x%x (1 readback, 2 decode, 4 speed, 8 underrun, 0x10 reset, 0x20 stall, 0x40 crc, 0x80 silence)", field("fail_mask")))
        check(field("readbacks") >= 8, "too few SPU RAM readbacks")
        check(field("readback_bad") == 0, "SPU RAM differs from the encoded data")
        check(field("decode_checks") >= 4, "too few decode checks")
        check(field("overflows") == 0, "ring overflow")
        check(field("resyncs") >= 1 and field("resyncs") <= 3, "resyncs=" .. field("resyncs") .. " (the deliberate stall and the restart after nullazhangot)")
        -- None in the steady phases, exactly one from the deliberate stall.
        check(field("underruns") == 1, "underruns=" .. field("underruns") .. " (expected 1, the deliberate stall)")
        if elma.args.crc then
            local want = tonumber(elma.args.crc, 16)
            check(field("crc") == want, string.format("encoder crc %08x, host %08x", field("crc"), want))
        end
        -- Independent progress check: the SPU IRQ steps counted by the
        -- program against the emulated CPU cycle counter.
        if #timeline == 2 then
            local dc = timeline[2][4] - timeline[1][4]
            local ds = timeline[2][3] - timeline[1][3]
            local expected = dc / CPU_HZ * 11025 / 140
            print(string.format("sound: playback %d steps in %.2f s, expected %.1f (%.1f%%)",
                ds, dc / CPU_HZ, expected, 100 * ds / expected))
            check(math.abs(ds / expected - 1) < 0.05, "playback speed differs from 11025 Hz")
        else
            check(false, "no progress samples")
        end
        local avg, max = field("hang_cycles_avg"), field("hang_cycles_max")
        print(string.format("sound: SPU DMA %d cycles for 16 bytes, %d for up to 640 bytes", field("dma_cycles_1"), field("dma_cycles_40")))
        print(string.format("sound: SPU IRQ handler %d cycles per interrupt", field("irq_cycles") / math.max(1, field("irq_steps"))))
        print(string.format("sound: mixed %d samples in %d hang calls", field("mixed_samples"), field("hang_calls")))
        print(string.format("sound: dbg %x %x %x %x", field("dbg0"), field("dbg1"), field("dbg2"), field("dbg3")))
        print(string.format("sound: readbacks=%d bad=%d decode_checks=%d min signal/error=%d (%.1f dB)",
            field("readbacks"), field("readback_bad"), field("decode_checks"),
            field("decode_min_ratio"), 10 * math.log(field("decode_min_ratio")) / math.log(10)))
        print(string.format("sound: irq_steps=%d underruns=%d resyncs=%d overflows=%d uploads=%d speed=%d/1000",
            field("irq_steps"), field("underruns"), field("resyncs"), field("overflows"),
            field("uploads"), field("speed_per_mille")))
        local gross, mixer = field("hang_cycles_a"), field("mixer_cycles_a")
        print(string.format("sound: hang() per call, steady phase: %d cycles with the test mixer, %d without (%.2f%% of the CPU at 60 calls/s: encoder, DMA, bookkeeping), max %d",
            gross, gross - mixer, 100 * (gross - mixer) * 60 / CPU_HZ, max))
        print(string.format("sound: encoder per 550 samples: signal %d, noise %d, silence %d cycles (%.2f%%, %.2f%%, %.2f%% of the CPU at 11025 Hz)",
            field("enc_cycles_signal"), field("enc_cycles_noise"), field("enc_cycles_silence"),
            100 * field("enc_cycles_signal") / BLOCK_CYCLES, 100 * field("enc_cycles_noise") / BLOCK_CYCLES,
            100 * field("enc_cycles_silence") / BLOCK_CYCLES))
        print(ok and "PASS" or "FAIL")
        PCSX.quit(ok and 0 or 1)
    end
end

elma.on_frame(function(n)
    local ok, err = pcall(on_frame, n)
    if not ok then
        print("LUA ERROR: " .. tostring(err))
        PCSX.quit(99)
    end
end)
