#!/usr/bin/env python3
"""Bounded GDB capture for hash-identified Steam64 or original1.11a shareware PE.

Start an authorized private Wine copy separately; this tool neither launches
Steam nor alters entitlement, executable files, game data, or PS3 physics.
The output contains private runtime snapshots and must stay under ignored build/.
Classic capture uses hardware breakpoints and selects the Wine-reported x32
architecture before attachment. --skip-fp-registers avoids a GDB17 mixed-mode
XSAVE assertion; its manifest explicitly marks FP state as not recaptured.
A bounded partial capture keeps only paired entries; complete=false remains.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import signal

SUPPORTED_EXE='3999b9c2a1e666fca3f47a187d7066cae22106a0f80ee47bf396e48718dc4be2'
CLASSIC_EXE='6781a4e1af27760086ae3e5b1e8e689824694483c715b51b3e5335c905d44737'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def commands(out,samples):
    path=str(out).replace('\\','\\\\').replace('"','\\"')
    def dump(stage):
        text=f'dump binary memory {path}/{stage}-%u.bin 0x%llx 0x%llx'
        return f'eval {json.dumps(text)}, $capture, $motor, $motor+440'
    return f'''set pagination off
set confirm off
set print thread-events off
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
handle SIGSEGV nostop noprint pass
set $capture = 0
set $active = 0
printf "MATH_IMPORTS\\n"
x/gx 0x140549240
x/gx 0x1405491f0
info proc mappings
break *0x1400e8fb0
commands
silent
set $motor = $rcx
set $active = 1
printf "ENTRY %u motor=0x%llx return=0x%llx most_bits=0x%016llx dt_bits=0x%016llx gaz=%d fek=%d ugrik1=%d ugrik2=%d\\n", $capture, $motor, *(unsigned long long*)$rsp, $xmm1.v2_int64[0], $xmm2.v2_int64[0], $r9d, *(int*)($rsp+40), *(int*)($rsp+48), *(int*)($rsp+56)
info registers mxcsr fctrl fstat
{dump('entry')}
continue
end
break *0x1400e6b90
commands
silent
if $active
printf "EXIT %u motor=0x%llx\\n", $capture, $motor
info registers mxcsr fctrl fstat
{dump('exit')}
set $active = 0
set $capture = $capture+1
if $capture >= {samples}
printf "CAPTURE_COMPLETE %u\\n", $capture
detach
quit
end
end
continue
end
continue
'''
def classic_commands(out,samples):
    # Same440byte layout, original32-bit cdecl ABI. Hardware breakpoints
    # avoid modifying PE instructions; correct architecture is also selected
    # BEFORE attachment by the runner's -iex option.
    script=commands(out,samples)
    return (script.replace('break *0x1400e8fb0','hbreak *0x420c20')
        .replace('break *0x1400e6b90','hbreak *0x41f9d7')
        .replace('set $motor = $rcx','set $motor = *(unsigned int*)($esp+4)')
        .replace('*(unsigned long long*)$rsp','*(unsigned int*)$esp')
        .replace('$xmm1.v2_int64[0]','*(unsigned long long*)($esp+8)')
        .replace('$xmm2.v2_int64[0]','*(unsigned long long*)($esp+16)')
        .replace('$r9d','*(int*)($esp+24)')
        .replace('*(int*)($rsp+40)','*(int*)($esp+28)')
        .replace('*(int*)($rsp+48)','*(int*)($esp+32)')
        .replace('*(int*)($rsp+56)','*(int*)($esp+36)')
        .replace('printf "MATH_IMPORTS\\n"\nx/gx 0x140549240\nx/gx 0x1405491f0',
                 'printf "CLASSIC_INLINE_X87\\n"')
        .replace('info proc mappings\n','')
        .replace('handle SIGSEGV nostop noprint pass','handle SIGSEGV stop print nopass'))
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--exe',type=pathlib.Path,required=True)
    ap.add_argument('--out',type=pathlib.Path,required=True)
    ap.add_argument('--pid',type=int)
    ap.add_argument('--samples',type=int,default=256)
    ap.add_argument('--timeout',type=int,default=180)
    ap.add_argument('--gdb',default='gdb.minimal')
    ap.add_argument('--gdb-data-directory',type=pathlib.Path,help='Private fullGDB share/gdb directory when extracted outside system paths')
    ap.add_argument('--generate-only',action='store_true')
    ap.add_argument('--skip-fp-registers',action='store_true',help='Avoid GDBmixed-mode XSAVE assertion; labelFPstate as notrecaptured')
    a=ap.parse_args()
    exe_hash=sha(a.exe)
    if exe_hash not in (SUPPORTED_EXE,CLASSIC_EXE):ap.error('unsupported PE hash: addresses must be independently remapped')
    classic=exe_hash==CLASSIC_EXE
    if not 1<=a.samples<=10000 or not 1<=a.timeout<=600:ap.error('capture limits outside supported bounds')
    out=a.out.resolve()
    if not re.fullmatch(r'[A-Za-z0-9_./:-]+',str(out)):ap.error('GDB dump output path requires plain characters without whitespace/quotes')
    out.mkdir(parents=True,exist_ok=True)
    if list(out.glob('entry-*.bin')) or list(out.glob('exit-*.bin')):ap.error('output already contains snapshots; choose a fresh directory')
    script=out/'capture.gdb'
    script_text=classic_commands(out,a.samples) if classic else commands(out,a.samples)
    if a.skip_fp_registers:script_text=script_text.replace('info registers mxcsr fctrl fstat\n','')
    script.write_text(script_text)
    if a.generate_only:return 0
    if not a.pid or a.pid<1:ap.error('--pid is required for capture')
    log=out/'capture.log'
    with log.open('w') as stream:
        try:
            gdb_args=[a.gdb,'-q','-batch']
            if a.gdb_data_directory:gdb_args+=['--data-directory='+str(a.gdb_data_directory.resolve())]
            if classic:gdb_args+=['-iex','set architecture i386:x64-32']
            process=subprocess.Popen(gdb_args+['-p',str(a.pid),'-x',str(script)],stdout=stream,stderr=subprocess.STDOUT)
            try:
                process.wait(timeout=a.timeout)
                status=process.returncode
            except subprocess.TimeoutExpired:
                # Interrupt first: abruptly killing a tracer can leave a live
                # Wine process with a pending hardware-breakpoint exception.
                process.send_signal(signal.SIGINT)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                status='timeout-interrupted'
        except OSError as error:status=str(error)
    text=log.read_text(errors='replace')
    pattern=r'^ENTRY (\d+) motor=0x([\da-f]+) return=0x([\da-f]+) most_bits=0x([\da-f]+) dt_bits=0x([\da-f]+) gaz=(-?\d+) fek=(-?\d+) ugrik1=(-?\d+) ugrik2=(-?\d+)'
    entries=re.findall(pattern,text,re.M)
    pairs=[v for v in entries if (out/f'entry-{v[0]}.bin').exists() and (out/f'entry-{v[0]}.bin').stat().st_size==440 and (out/f'exit-{v[0]}.bin').exists() and (out/f'exit-{v[0]}.bin').stat().st_size==440]
    (out/'inputs.txt').write_text(''.join(f'{v[0]} {v[3]} {v[4]} {" ".join(v[5:])}\n' for v in pairs))
    complete=f'CAPTURE_COMPLETE {a.samples}' in text and len(pairs)==a.samples
    manifest={'exe_sha256':sha(a.exe),'script_sha256':sha(script),'gdb_status':status,'paired_steps':len(pairs),'complete':complete,'snapshot_bytes':440,'profile':'classic-shareware1.11a' if classic else 'Steam64', 'fp_registers_requested':not a.skip_fp_registers, 'fp_registers_captured':bool(pairs) and not a.skip_fp_registers and len(re.findall(r'^fctrl\s',text,re.M))>=2*len(pairs), 'boundary':'Selected PE under Wine/host CPU, not historical Microsoft Windows/CPU validation.'}
    (out/'capture.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest));return 0 if complete else 1
if __name__=='__main__':raise SystemExit(main())
