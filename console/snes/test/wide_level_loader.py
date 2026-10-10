#!/usr/bin/env python3
"""Build the complete C solver with exact binary level snapshots, without C++ physics."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from wide_probe import ROOT


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=Path,required=True)
    ap.add_argument('--levels',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--reserve-levels',help='Comma-separated level IDs for a smaller native test allocation')
    ap.add_argument('--host-split-sections',action='store_true',help='Exercise the banked loader with independently allocated host sections')
    a=ap.parse_args();port=a.port.resolve();levels=a.levels.resolve();out=a.out.resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    out.mkdir(parents=True)
    for p in port.iterdir():
        if p.is_file() and p.suffix.lower() in ('.h','.cpp','.c'):shutil.copy2(p,out/p.name)
    report=json.loads((levels/'report.json').read_text())
    bits=report['bits'];controller=json.loads((port/'controller.json').read_text())
    if controller['bits']!=bits:raise ValueError('Precision mismatch')
    header=(out/'wide_port.h').read_text()
    constants=json.loads((port/'wide_constants.json').read_text())
    names=report['levels'][0]['constant_order']
    reserved=report['levels']
    if a.reserve_levels:
        selected=set(map(int,a.reserve_levels.split(',')))
        reserved=[r for r in reserved if r['level'] in selected]
        if len(reserved)!=len(selected):raise ValueError('Unknown reserved level')
    maxcell=max(len(c) for r in reserved for c in json.loads((levels/('lev%02d.json'%r['level'])).read_text())['cells'])
    config=['#define WL_BITS '+str(bits),'#define WL_MAX_LINES '+str(max(r['lines'] for r in reserved)),
            '#define WL_MAX_CELL '+str(maxcell),'#define WL_CONSTANT_COUNT '+str(len(constants)),
            '#define WL_LEVEL_CONSTANT_COUNT '+str(len(names))]
    raw=b''.join(struct.pack('<q',x) for x in constants)
    config.append('static const unsigned char wl_constants[]={'+','.join(map(str,raw))+'};')
    (out/'wide_level_config.h').write_text('\n'.join(config)+'\n')
    for r in reserved:
        name='wide_level%02d_data'%r['level'];blob=(levels/('lev%02d.bin'%r['level'])).read_bytes()
        (out/(name+'.c')).write_text('const unsigned char '+name+'[]={\n'+
            '\n'.join(','.join(map(str,blob[i:i+32]))+',' for i in range(0,len(blob),32))+'\n};\n')
    globals=[];assign=[]
    pointers={'Pmot1':'wl_motor','Pszak':'wl_segments','Ptop':'wl_top','Pecsetalso':'wl_brush'}
    for typ,function in re.findall(r'^(.+?)\s+(wp_ptr_\w+)\(void\);',header,re.M):
        typ=typ.strip();assert typ.endswith('*');typ=typ[:-1].strip();name=function[7:]
        init='=&'+pointers[name] if name in pointers else ''
        globals+=['static '+typ+' wl_'+name+init+';',typ+'* '+function+'(void){return &wl_'+name+';}']
        if typ=='wp_scalar' and name in names:assign.append('wl_'+name+'=read_scalar(constants+'+str(8*names.index(name))+');')
    globals+=['static int wl_pc_obj_active[52];','int* wp_array_pc_obj_active(void){return wl_pc_obj_active;}']
    globals.append('static void wl_assign_globals(const unsigned char* constants){'+'\n'.join(assign)+'''
wl_Vekt2null=wp_vec_make(wp_int(0),wp_int(0));
wl_Vekt2i=wp_vec_make(wp_int(1),wp_int(0));wl_Vekt2j=wp_vec_make(wp_int(0),wp_int(1));
}''')
    (out/'wide_level_globals.inc').write_text('\n'.join(globals)+'\n')
    for name in ['wide_level_loader.c','wide_level_adapter.cpp']:shutil.copy2(ROOT/'test'/name,out/name)
    source=(out/'wide_controller.c').read_text()
    # Keep original code for review but replace only its grid-reset entry.
    anchor='void wp_szakaszok_felsorolasreset(wp_segments * self,wp_vec r)'
    if source.count(anchor)!=1:raise ValueError('Unknown grid-reset declaration')
    source=source.replace(anchor,anchor.replace('wp_szakaszok_','unused_original_szakaszok_'))
    (out/'wide_controller.c').write_text(source)
    commands=[]
    for name in ['wide_controller','wide_port_math','wide_level_loader']:
        commands.append(['cc','-std=c11','-O2','-w','-DWIDE_PORT_BITS='+str(bits),'-DWIDE_HAS_ACCEL=0',
                         '-I'+str(out),'-c',str(out/(name+'.c')),'-o',str(out/(name+'.o'))])
    commands.append(['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),
                     *(['-DWIDE_LEVEL_SPLIT_HOST=1'] if a.host_split_sections else []),
                     '-DWIDE_LEVEL_DIRECTORY='+json.dumps(str(levels)),'-I'+str(out),'-I'+str(ROOT/'test'),
                     '-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'wide_level_adapter.cpp'),
                     *[str(out/(name+'.o')) for name in ['wide_controller','wide_port_math','wide_level_loader']]])
    for i,command in enumerate(commands):
        result=subprocess.run(command,capture_output=True,text=True)
        (out/('compile-%d.txt'%i)).write_text(result.stdout+result.stderr);result.check_returncode()
    toolkit=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes'
    native=[str(toolkit/'bin/816-tcc'),'-Wall','-F','-DWIDE_TARGET_SNES=1','-I'+str(toolkit/'include'),
            '-I'+str(out),'-c',str(out/'wide_level_loader.c'),'-o',str(out/'wide_level_loader.ps')]
    result=subprocess.run(native,capture_output=True,text=True)
    (out/'compile-native-loader.txt').write_text(result.stdout+result.stderr);result.check_returncode()
    (out/'build.json').write_text(json.dumps({'bits':bits,'commands':commands,'port':str(port),'levels':str(levels),
        'reserved_levels':[r['level'] for r in reserved],
        'host_split_sections':a.host_split_sections,
        'native_loader_command':native,
        'change':'Complete plain C solver with exact binary level loader and active-cell linked nodes; no C++ solver/level construction'},indent=2)+'\n')
    print(out/'widecheck')


if __name__=='__main__':main()
