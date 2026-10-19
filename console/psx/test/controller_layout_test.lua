-- The console sheet shows fixed pad actions and never edits saved controls.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "missing symbol: "..name) end
local dbg, card, state_ptr = need("psx_debug"), need("psx_memcard_debug"), need("State")
local rows_ptr, rows_count = need("_ZL6Hsorok"), need("_ZL5Hszam")
local log = assert(io.open(elma.args.log,"w"))
local function say(text) print(text); log:write(text,"\n"); log:flush() end
local function bytes(address, count)
    local result = {}
    for i=0,count-1 do result[#result+1]=string.char(elma.u8(address+i)) end
    return table.concat(result)
end
local function rows()
    local address, count = elma.u32(rows_ptr), elma.u32(rows_count)
    local out={}
    if address==0 or count>300 then return out end
    for i=0,count-1 do out[#out+1]=bytes(address+i*116,102):match("^[^%z]*") end
    return out
end
local function has(list,prefix)
    for _,text in ipairs(list) do if text:sub(1,#prefix)==prefix then return true end end
    return false
end
local expected={"Controller Layout","Pad 1: Player A; Pad 2: Player B",
    "Up / Cross","Throttle","Down / Circle","Brake","Left / Right","Rotate left / right",
    "Square / R1","Change direction","Triangle","Toggle navigator","L1","Toggle time",
    "L2","Both rotation keys","R2","Show / hide view","Select","Leave level",
    "Pad 1 menus: arrows; L1/R1 pages","Cross/Start: OK; Circle/Select: Back"}
local done=false
local function finish(ok,message)
    if done then return end
    done=true
    say((ok and "PASS: " or "FAIL: ")..message)
    PCSX.quit(ok and 0 or 1)
end
local steps,index,phase={},1,"boot"
local deadline,pressed,released,chars,presents=6000
local original, saves, controls
local function add(name,button,target)
    steps[#steps+1]={name=name,button=button,target=target}
end
local function begin(n)
    local step=steps[index]
    chars,presents=elma.u32(dbg+12),elma.u32(dbg+4)
    elma.press(1,step.button)
    pressed,released,phase,deadline=n,false,"key",n+2400
end
elma.on_frame(function(n)
    if done then return end
    local ok,error=pcall(function()
        if elma.u32(dbg+36)~=0 then return finish(false,"runtime error") end
        if n>deadline then return finish(false,"timeout at "..(steps[index] and steps[index].name or phase)) end
        local list=rows()
        for _,text in ipairs(list) do
            if text:find("Key code",1,true) or text:find("Customize",1,true) or
                text:find("Screen Size",1,true) or text:find("Screenshot",1,true) or
                text:find("Reset all controls",1,true) then return finish(false,"desktop control row: "..text) end
        end
        if phase=="boot" then
            if elma.u32(dbg)~=0x454c4d41 or elma.u32(dbg+4)<3 or elma.u32(state_ptr)==0 then return end
            if elma.u32(card)~=0x4443524d or elma.u32(card+16)~=0 then return end
            local state=elma.u32(state_ptr)
            controls=state+90*688+50*116+72
            original=bytes(controls,76)
            add("choose saved player","CROSS","Main Menu")
            for i=1,3 do add("select Options "..i,"DOWN","Main Menu") end
            add("open Options","CROSS","Options")
            local mode=elma.u32(state+90*688+50*116+44)
            for i=1,9+(mode==0 and 1 or 0) do add("select layout "..i,"DOWN","Options") end
            add("open controller sheet","CROSS","Controller Layout")
            add("direction does not rebind","RIGHT","Controller Layout")
            add("Cross closes sheet","CROSS","Options")
            add("reopen for Circle","CROSS","Controller Layout")
            add("Circle closes sheet","CIRCLE","Options")
            add("reopen for Select","CROSS","Controller Layout")
            add("Select closes sheet","SELECT","Options")
            add("Options returns","CIRCLE","Main Menu")
            add("select Help","DOWN","Main Menu")
            add("Help shows controller sheet","CROSS","Controller Layout")
            add("Start closes Help","START","Main Menu")
            saves=elma.u32(card+4)
            begin(n)
        elseif phase=="key" then
            local step=steps[index]
            if not released and n>=pressed+6 then elma.release(1,step.button);released=true end
            if n<pressed+90 or elma.u32(dbg+12)<=chars or elma.u32(dbg+4)<presents+4 or
                not has(list,step.target) then return end
            if step.target=="Controller Layout" then
                for _,text in ipairs(expected) do
                    if not has(list,text) then return finish(false,"missing pad action: "..text) end
                end
                if step.name=="open controller sheet" then elma.screenshot(elma.args.capture) end
            end
            if bytes(controls,76)~=original then return finish(false,"controller sheet edited bindings") end
            if elma.u32(card+4)~=saves or elma.u32(card+12)~=0 then return finish(false,"viewing layout triggered a save") end
            say("CONTROLS "..step.name)
            index=index+1
            if index>#steps then
                if elma.u32(dbg+44)~=0 then return finish(false,"development RAM enabled") end
                return finish(true,"pad layout and Help show console actions; bindings and card unchanged")
            end
            begin(n)
        end
    end)
    if not ok then finish(false,"Lua error: "..tostring(error)) end
end)
