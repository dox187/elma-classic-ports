-- Edit physical pad bindings, save them, then reboot and exercise the mapping.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name), "missing symbol: "..name) end
local dbg, card, state_ptr = need("psx_debug"), need("psx_memcard_debug"), need("State")
local recorder_ready = need("Prec2")
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
local STATE_CONTROLS=90*688+50*116+72
local offsets={0,4,12,8,16,20,24,28}
local defaults={0x4010,0x2040,0x0180,0x0120,0x8800,0x1000,0x0400,0x0200}
local function binding(player,action)
    return elma.u32(elma.u32(state_ptr)+STATE_CONTROLS+player*32+offsets[action])
end
local function key(player,mask) return 0x50580000+player*0x10000+mask end
local function expect_binding(player,action,mask)
    assert(binding(player,action)==key(player,mask),
        string.format("pad%d action%d: got %08x expected %08x",player+1,action,
            binding(player,action),key(player,mask)))
end
local function expect_defaults()
    for player=0,1 do for action,mask in ipairs(defaults) do expect_binding(player,action,mask) end end
end
local function expect_custom()
    for player=0,1 do
        for action,mask in ipairs(defaults) do
            if action==1 then mask=player==0 and 0x1000 or 0x0008 end
            if player==0 and action==6 then mask=0 end
            expect_binding(player,action,mask)
        end
    end
end
local function signed(value) return value>=0x80000000 and value-0x100000000 or value end
local done=false
local function finish(ok,message)
    if done then return end
    done=true
    say((ok and "PASS: " or "FAIL: ")..message)
    PCSX.quit(ok and 0 or 1)
end
local run=tonumber(elma.args.run)
local steps,index,phase={},1,"boot"
local deadline,pressed,released,chars,presents=6000
local saves, controls_before_help
local function add(name,button,target,check,wait)
    steps[#steps+1]={name=name,button=button,target=target,check=check,wait=wait or 30}
end
local function down(count,target)
    for i=1,count do add("move down", "DOWN",target) end
end
local function begin(n)
    local step=steps[index]
    chars,presents=elma.u32(dbg+12),elma.u32(dbg+4)
    elma.press(1,step.button)
    pressed,released,phase,deadline=n,false,"key",n+3000
end
local function build_steps()
    add("dismiss splash","CROSS","Choose Player",nil,180)
    add("choose saved player","CROSS","Main Menu")
    if run==1 then
        down(3,"Main Menu")
        add("open Options","CROSS","Options")
        -- The gameplay check on the next boot uses player A alone.
        local single=elma.u32(elma.u32(state_ptr)+90*688+50*116+44)
        if single==0 then add("choose Single Player","CROSS","Options") end
        down(9,"Options")
        add("open Customize Controls","CROSS","Customize Controls",function(list)
            assert(has(list,"Reset all controls to default"),"missing reset action")
            assert(has(list,"Customize Player A") and has(list,"Customize Player B"),"missing player editors")
        end)
        add("reset both pads","CROSS","Customize Controls",expect_defaults)
        down(1,"Customize Controls")
        add("edit Player A","CROSS","Customize Player A (Pad 1)")
        add("choose throttle button","CROSS","Throttle: choose button",function(list)
            for _,name in ipairs({"Unassigned","Up","Down","Left","Right","Cross","Circle","Square","Triangle","L1","R1"}) do
                assert(has(list,name),"missing physical choice: "..name)
            end
        end)
        down(8,"Throttle: choose button")
        add("assign Triangle to A throttle","CROSS","Customize Player A (Pad 1)",function(list)
            expect_binding(0,1,0x1000);expect_binding(0,6,0)
            for action,mask in ipairs(defaults) do expect_binding(1,action,mask) end
            assert(has(list,"Triangle") and has(list,"Unassigned"),"mapping names not updated")
            elma.screenshot(elma.args.capture:gsub("%.ppm$", "-editor.ppm"))
        end)
        add("reopen button picker","CROSS","Throttle: choose button")
        add("cancel picker with Circle","CIRCLE","Customize Player A (Pad 1)",function() expect_binding(0,1,0x1000) end)
        down(1,"Customize Player A (Pad 1)")
        add("choose brake button","CROSS","Brake: choose button")
        add("clear A brake","CROSS","Customize Player A (Pad 1)",function() expect_binding(0,2,0) end)
        add("leave Player A","CIRCLE","Customize Controls")
        add("select reset","UP","Customize Controls")
        add("reset restores aliases and cleared actions","CROSS","Customize Controls",expect_defaults)
        down(1,"Customize Controls")
        add("edit A after reset","CROSS","Customize Player A (Pad 1)")
        add("choose A throttle after reset","CROSS","Throttle: choose button")
        down(8,"Throttle: choose button")
        add("set final A Triangle binding","CROSS","Customize Player A (Pad 1)")
        add("leave final A editor","CIRCLE","Customize Controls")
        down(1,"Customize Controls")
        add("edit Player B using pad 1","CROSS","Customize Player B (Pad 2)")
        add("choose B throttle","CROSS","Throttle: choose button")
        down(13,"Throttle: choose button")
        add("assign Start to B throttle","CROSS","Customize Player B (Pad 2)",function() expect_custom() end)
        add("leave Player B","SELECT","Customize Controls")
        add("leave control editor","CIRCLE","Options",function()
            expect_custom();assert(elma.u32(card+4)==saves,"control editor saved before Options Back")
        end)
        add("save on Options Back","CIRCLE","Main Menu",function()
            if elma.u32(card+4)<=saves or elma.u32(card+12)~=0 then return false end
            assert(elma.u32(card+8)==0,"card save failed")
            controls_before_help=bytes(elma.u32(state_ptr)+STATE_CONTROLS,64)
            saves=elma.u32(card+4)
            say("CONTROLS card save MC_OK")
        end,90)
        down(1,"Main Menu")
        add("Help shows current A bindings","CROSS","Controller Layout: Player A (Pad 1)",function(list)
            assert(has(list,"Triangle") and has(list,"Unassigned"),"Help has stale A bindings")
            elma.screenshot(elma.args.capture)
        end)
        add("Help switches to current B bindings","RIGHT","Controller Layout: Player B (Pad 2)",function(list)
            assert(has(list,"Start"),"Help has stale B binding")
        end)
        add("Start closes read-only Help","START","Main Menu",function()
            assert(bytes(elma.u32(state_ptr)+STATE_CONTROLS,64)==controls_before_help,"Help edited controls")
            assert(elma.u32(card+4)==saves and elma.u32(card+12)==0,"Help triggered a save")
        end)
    else
        add("open Play","CROSS",elma.args.collections=="1" and "Select collection!" or "Select Level!")
        local route={}
        for button in elma.args.internal_steps:gmatch("[^,]+") do route[#route+1]=button end
        for i=1,#route-1 do
            add("open internal levels",route[i],i==#route-1 and "Select Level!" or "Select collection!")
        end
        -- The cloned player's last selection can be any level.
        for i=1,6 do add("first level page","L1","Select Level!") end
        if elma.args.collections~="1" then down(1,"Select Level!") end
        add("start Warm Up","CROSS",nil,nil,0)
    end
end
local old_x,game_frames,game_started
elma.on_frame(function(n)
    if done then return end
    local ok,error=pcall(function()
        if elma.u32(dbg+36)~=0 then return finish(false,"runtime error") end
        if n>deadline then return finish(false,"timeout at "..(steps[index] and steps[index].name or phase)) end
        local list=rows()
        for _,text in ipairs(list) do
            if text:find("Key code",1,true) or text:find("Screen Size",1,true) or
                text:find("Screenshot",1,true) then return finish(false,"desktop control row: "..text) end
        end
        if phase=="boot" then
            if elma.u32(dbg)~=0x454c4d41 or elma.u32(dbg+4)<3 or
                elma.u32(state_ptr)==0 or elma.u32(recorder_ready)==0 then return end
            if elma.u32(card)~=0x4443524d or elma.u32(card+16)~=0 then return end
            if run==2 then expect_custom();say("CONTROLS reboot restored both physical pad bindings") end
            saves=elma.u32(card+4)
            build_steps();begin(n)
        elseif phase=="key" then
            local step=steps[index]
            if not released and n>=pressed+6 then elma.release(1,step.button);released=true end
            if n<pressed+step.wait or elma.u32(dbg+12)<=chars or
                (step.target and (elma.u32(dbg+4)<presents+4 or not has(list,step.target))) then return end
            if step.check and step.check(list)==false then return end
            if step.name~="move down" and step.name~="first level page" then say("CONTROLS "..step.name) end
            index=index+1
            if index>#steps then
                assert(elma.u32(dbg+44)==0,"development RAM enabled")
                if run==1 then return finish(true,"both pad editors, assignment conflicts, reset, cancel, card save and read-only Help") end
                phase,deadline="loading",n+6000
            else begin(n) end
        elseif phase=="loading" then
            if elma.u32(dbg+8)<3 then return end
            expect_custom()
            old_x=signed(elma.u32(dbg+16));game_frames=elma.u32(dbg+8)
            elma.press(1,"CROSS")
            phase,game_started,deadline="old-gas",n,n+3000
        elseif phase=="old-gas" then
            if n<game_started+90 then return end
            elma.release(1,"CROSS")
            assert(math.abs(signed(elma.u32(dbg+16))-old_x)<250,"old Cross binding still drives player A")
            say("CONTROLS former Cross binding does not accelerate")
            old_x=signed(elma.u32(dbg+16));elma.press(2,"START")
            phase,game_started="pad2-isolation",n
        elseif phase=="pad2-isolation" then
            if n<game_started+90 then return end
            elma.release(2,"START")
            assert(math.abs(signed(elma.u32(dbg+16))-old_x)<250,"pad 2 accelerated player A")
            say("CONTROLS pad 2 Start does not accelerate player A")
            old_x=signed(elma.u32(dbg+16));game_frames=elma.u32(dbg+8)
            elma.press(1,"TRIANGLE")
            phase,game_started="mapped-gas",n
        elseif phase=="mapped-gas" then
            if n<game_started+120 then return end
            elma.release(1,"TRIANGLE")
            local moved=math.abs(signed(elma.u32(dbg+16))-old_x)
            assert(elma.u32(dbg+8)>game_frames+30,"gameplay did not keep rendering")
            assert(moved>1000,"mapped Triangle moved bike only "..moved.." mm")
            elma.screenshot(elma.args.capture)
            return finish(true,"saved Triangle throttle moved bike "..moved.." mm; old Cross and pad 2 isolated")
        end
    end)
    if not ok then finish(false,"Lua error: "..tostring(error)) end
end)
