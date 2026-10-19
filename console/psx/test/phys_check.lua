-- Reads the result of build/physcheck.exe (test/phys_check.c) from RAM when
-- it is done and prints it as the host version does. Run by
-- test/phys_test.py --ps1 through test/pcsx.py.
local res = elma.sym("phys_check_result")
if not res then
    print("FAIL: symbol phys_check_result not found")
    PCSX.quit(1)
end
elma.on_frame(function(n)
    if elma.u32(res) == 0x50485953 then
        local function s32(v) if v >= 0x80000000 then return v - 0x100000000 end return v end
        print(string.format("physcheck: sum %08x steps %d events %d body %d %d mm",
            elma.u32(res + 4), elma.u32(res + 8), elma.u32(res + 12),
            s32(elma.u32(res + 16)), s32(elma.u32(res + 20))))
        PCSX.quit(0)
    elseif n > 3000 then
        print("FAIL: physcheck did not finish")
        PCSX.quit(1)
    end
end)
