-- Real physics endings, original mixer progress, IRQ playback and disk PCM.
if jit then jit.off() end
local function need(name) return assert(elma.sym(name),"missing symbol "..name) end
local dbg,trans,state=need("psx_debug"),need("psx_transition_debug"),need("State")
local vblanks=need("_ZN12_GLOBAL__N_112vblank_countE")
local top,rec=need("Ptop"),need("Prec2")
local mute,bank=need("Mute"),need("Wavbank")
local voices,positions,playing=need("_ZL6Pwavok"),need("_ZL7Kovhang"),need("_ZL6Ezmegy")
local wav_count=need("_ZL7Wavszam")
local irq,wblock,pending=need("irq_steps"),need("wblock"),need("pending_count")
local outcome=need("Aerintetteviragot")
local rowptr,rowcount=need("_ZL6Hsorok"),need("_ZL5Hszam")
local log=assert(io.open(elma.args.log,"w"))
local function say(text) print(text);log:write(text,"\n");log:flush() end
local function rows()
    local out,p,n={},elma.u32(rowptr),elma.u32(rowcount)
    if p==0 or n>300 then return out end
    for row=0,n-1 do
        local text={}
        for i=0,101 do local c=elma.u8(p+row*116+i);if c==0 then break end;text[#text+1]=string.char(c) end
        out[#out+1]=table.concat(text)
    end
    return out
end
local function has(list,prefix)
    for _,text in ipairs(list) do if text:sub(1,#prefix)==prefix then return true end end
    return false
end
local function audio_bytes()
    local file=io.open(elma.args.capture,"rb")
    if not file then return 0 end
    local size=file:seek("end");file:close();return size
end
local function release()
    for _,button in ipairs({"CROSS","RIGHT","SELECT","DOWN","UP"}) do elma.release(1,button) end
end
local enabled=elma.args.sound=="1"
local names={"death","success"}
local phase,deadline,case,seen="boot",9000,1,0
local steps,index,pressed,chars,presents={},1,0,0,0
local finish_vblank,end_block,start_bytes,ready_bytes,ready_at,size,muted_at
local done=false
local function finish(ok,message)
    if done then return end;done=true;release()
    say((ok and "PASS: " or "FAIL: ")..message)
    PCSX.quit(ok and 0 or 1)
end
local function add(name,button,target,wait,check)
    steps[#steps+1]={name=name,button=button,target=target,wait=wait or 30,check=check}
end
local function begin(n)
    local step=steps[index]
    chars,presents=elma.u32(dbg+12),elma.u32(dbg+4)
    elma.press(1,step.button);pressed,phase,deadline=n,"key",n+3000
end
local function boot_steps()
    add("dismiss splash","CROSS","Please enter your name:",180)
    add("name letter","RIGHT","Please enter your name:")
    add("create private player","CROSS","Main Menu",90,function()
        -- Make both private fixture slots selectable without altering user data.
        elma.write_u32(elma.u32(state)+61920+108,2)
    end)
    add("open Play","CROSS",elma.args.collections=="1" and "Select collection!" or "Select Level!")
    local route={};for button in elma.args.path:gmatch("[^,]+") do route[#route+1]=button end
    for i,button in ipairs(route) do
        local target
        if i<#route then target=i==#route-1 and "Select Level!" or "Select collection!" end
        add("start fixture route",button,target,0)
    end
end
elma.on_frame(function(n)
    if done then return end
    local ok,error=pcall(function()
        assert(elma.u32(dbg+36)==0,"runtime error")
        assert(n<=deadline,"timeout in "..phase)
        local list=rows()
        local count=elma.u32(trans)
        if count>seen then
            seen=count;release();phase,deadline="effect",n+3000
            finish_vblank=elma.u32(trans+4);start_bytes=audio_bytes();muted_at=nil
            assert(elma.u32(elma.u32(top))==0x46530000+case,"wrong fixture loaded")
            assert(elma.u32(outcome)==(case==2 and 1 or 0),"wrong physics ending")
            size=tonumber(case==1 and elma.args.death_samples or elma.args.success_samples)
            if enabled then
                local wave=elma.u32(bank+(case==1 and 2 or 3)*4)
                assert(wave~=0,"finish sample not loaded");size=elma.u32(wave+4)
                local position
                for i=0,4 do
                    if elma.u32(playing+i*4)~=0 and elma.u32(voices+i*4)==wave then position=elma.u32(positions+i*4) end
                end
                assert(position and position<size,"finish cue was not queued")
                -- Project the original mixer's remaining sample count onto the
                -- independent absolute SPU stream coordinates at this VBlank.
                end_block=math.ceil((elma.u32(wblock)*28+elma.u32(pending)+size-position)/28)
            end
            say("FINISH started "..names[case].." sound="..tostring(enabled).." samples="..size)
        end
        if phase=="boot" then
            if elma.u32(dbg)~=0x454c4d41 or elma.u32(rec)==0 or elma.u32(state)==0 then return end
            assert(elma.u32(dbg+44)==0,"development RAM enabled")
            elma.write_u32(elma.u32(state)+67756,enabled and 1 or 0)
            boot_steps();begin(n)
        elseif phase=="key" then
            local step=steps[index]
            if n>=pressed+6 then elma.release(1,step.button) else return end
            if n<pressed+step.wait or elma.u32(dbg+12)<=chars then return end
            if step.target and (not has(list,step.target) or elma.u32(dbg+4)<presents+4) then return end
            if step.check then step.check() end
            index=index+1
            if index>#steps then phase,deadline="playing",n+3000 else begin(n) end
        elseif phase=="playing" then
            elma.press(1,"UP")
        elseif phase=="effect" then
            if elma.u32(mute)==1 and not muted_at then
                muted_at=elma.u32(vblanks)
                if enabled then
                    assert(elma.u32(wav_count)==0,"mixer effects were cut off")
                    assert(elma.u32(irq)*5-1>=end_block,"SPU tail was cut off before playback")
                else assert(muted_at-finish_vblank<=3,"sound-off ending added a delay") end
            end
            if elma.u32(trans+32)~=1 then return end
            assert(muted_at,"selector appeared before mute observation")
            assert(elma.u32(trans+24)>=2 and elma.u32(trans+24)<=3,"obsolete post-game actions")
            ready_at,ready_bytes=elma.u32(vblanks),audio_bytes()
            say(string.format("FINISH ready %s wait=%d fields finish_to_mute=%d played=%d target=%d",
                names[case],elma.u32(trans+8)-finish_vblank,muted_at-finish_vblank,
                elma.u32(irq)*5-1,end_block or 0))
            phase,pressed,deadline="settle",n,n+3000
        elseif phase=="settle" then
            if n<pressed+90 then return end
            say(string.format("FINISH_AUDIO %s samples=%d start=%d ready=%d end=%d",names[case],size,
                start_bytes,ready_bytes,audio_bytes()))
            elma.screenshot(elma.args.shots..names[case]..".ppm")
            if case==2 then return finish(true,"complete death and success SPU tails; sound-off has no cue delay") end
            elma.press(1,"SELECT");pressed,phase=n,"leave-selector"
        elseif phase=="leave-selector" then
            if n>=pressed+6 then elma.release(1,"SELECT") end
            if n<pressed+30 or elma.u32(trans+32)~=0 or not has(list,"Select Level!") then return end
            steps,index={},1;case=2
            add("select success fixture","DOWN","Select Level!")
            add("start success fixture","CROSS",nil,0)
            begin(n)
        end
    end)
    if not ok then finish(false,"finish sound: "..tostring(error)) end
end)
