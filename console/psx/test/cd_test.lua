-- Disc test, run by test/pcsx.py (the prelude provides `elma`): waits until
-- cdtest has finished (cdtest_state.done), then checks the counters.
--   --arg frames=N       give up after N frames (default 20000)
--   --arg min_levels=N   LEV/ must have at least N entries (default 1)
local MAX_FRAMES = tonumber(elma.args.frames or "20000")
local MIN_LEVELS = tonumber(elma.args.min_levels or "1")
local MAGIC = 0x43445354

local state = elma.sym("cdtest_state")
if not state then
    print("FAIL: symbol cdtest_state not found")
    PCSX.quit(1)
end

local names = {"magic", "done", "pass", "fail", "track", "base", "track_base",
               "mount_frames", "list_frames", "lev_count", "files_ok",
               "bytes_read", "verify_frames", "t1_ok", "backend_ok", "toc_base2", "mount_err", "probe_lba"}

local function read_state()
    local s = {}
    for i, n in ipairs(names) do s[n] = elma.u32(state + (i - 1) * 4) end
    return s
end

local done_frame = nil
elma.on_frame(function(n)
    local s = read_state()
    if n % 1000 == 0 then
        print(string.format("frame %d: magic=%08x done=%d pass=%d fail=%d files=%d bytes=%d",
            n, s.magic, s.done, s.pass, s.fail, s.files_ok, s.bytes_read))
    end
    if s.done == 1 and not done_frame then
        done_frame = n
        local ok = s.magic == MAGIC and s.fail == 0 and s.pass > 0
            and s.track == 2 and s.lev_count >= MIN_LEVELS and s.t1_ok == 1
            and s.backend_ok == 1
        print(string.format("RESULT frame=%d track=%d base=%d toc_base=%d lev=%d files=%d "
            .. "bytes=%d pass=%d fail=%d mount_frames=%d list_frames=%d verify_frames=%d "
            .. "t1_ok=%d backend_ok=%d toc2=%d mount_err=%d probe_lba=%d",
            n, s.track, s.base, s.track_base, s.lev_count, s.files_ok, s.bytes_read,
            s.pass, s.fail, s.mount_frames, s.list_frames, s.verify_frames, s.t1_ok,
            s.backend_ok, s.toc_base2 >= 0x80000000 and -1 or s.toc_base2,
            s.mount_err >= 0x80000000 and s.mount_err - 4294967296 or s.mount_err, s.probe_lba))
        print(ok and "PASS" or "FAIL")
        PCSX.quit(ok and 0 or 1)
    elseif n >= MAX_FRAMES then
        print(string.format("FAIL: timeout after %d frames (magic=%08x pass=%d fail=%d)",
            n, s.magic, s.pass, s.fail))
        PCSX.quit(2)
    end
end)
