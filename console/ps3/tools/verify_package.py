#!/usr/bin/env python3
"""Verify package manifest, stage, corresponding sources and current ELF."""
import argparse, hashlib, json, pathlib, tarfile, struct, subprocess, re, os
p=argparse.ArgumentParser()
p.add_argument('manifest',type=pathlib.Path)
p.add_argument('--build-dir',type=pathlib.Path,default=None)
p.add_argument('--allow-older-build',action='store_true')
a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[3]
m=json.loads(a.manifest.read_text());out=a.manifest.parent
name=a.manifest.stem
if not all(k in m for k in ('files','stage_files','kind','built_elf_sha256')):
    raise SystemExit('FAIL: old manifest schema; regenerate this package with current tools/package.sh')
errors=[]
profile=m.get('physics_profile')
if profile not in ('sdl','classic-x87'): errors.append('missing or invalid physics_profile')
expected_name='elma-classic-ps3-v'+m['version']+('-classic-x87' if profile=='classic-x87' else '')+'-'+m['kind']
if name!=expected_name: errors.append('artifact name does not match physics profile')
build=a.build_dir or pathlib.Path(os.environ.get('ELMA_PS3_BUILD_DIR',str(root/'console/ps3/build')))

# The SDK's debug PKG is decryptable by its own listing tool. Inspect its real
# entries, rather than inferring paths from the stage/manifest. Finalized retail
# PKG installation is covered separately by the isolated RPCS3 install test.
pkg_tool=pathlib.Path(os.environ.get('PS3DEV',str(root/'console/ps3/.toolchain/ps3dev')))/'bin/pkg'
listing=subprocess.run([str(pkg_tool),'--list',str(out/(name+'.pkg'))],capture_output=True,text=True,check=True).stdout
entries=re.findall(r'^\s*(raw data|directory|NPDRM SELF):[+-]\s+\d+: (.*)$',listing,re.M)
header_count=struct.unpack_from('>I',(out/(name+'.pkg')).read_bytes(),20)[0]
if len(entries)!=header_count: errors.append('PKG entry listing is incomplete')
for kind,entry in entries:
    parts=pathlib.PurePosixPath(entry)
    if parts.is_absolute() or '..' in parts.parts or '\\' in entry:
        errors.append('unsafe actual PKG entry: '+entry)
if ('NPDRM SELF','USRDIR/EBOOT.BIN') not in entries: errors.append('PKG EBOOT lacks correct relative NPDRM entry')
if {entry for kind,entry in entries if kind!='directory'}!={item['name'] for item in m['stage_files']}:
    errors.append('actual PKG file entries differ from stage manifest')
def digest(data):return hashlib.sha256(data).hexdigest()
marker=b'ELMA PS3 physics: classic_x87 (experimental)' if profile=='classic-x87' else b'ELMA PS3 physics: sdl'
if marker not in (out/(name+'.elf')).read_bytes(): errors.append('packaged ELF startup marker differs from physics profile')
nm=pkg_tool.parent.parent/'ppu/bin/ppu-nm'
symbols=subprocess.check_output([str(nm),str(out/(name+'.elf'))],text=True)
if bool(re.search(r'\b[TD] \.?elma_x87_sin$',symbols,re.M)) != (profile=='classic-x87'): errors.append('packaged ELF symbols differ from physics profile')
for item in m['files']:
    f=out/item['name']
    if not f.is_file() or f.stat().st_size!=item['bytes'] or digest(f.read_bytes())!=item['sha256']:errors.append(str(f))
stage=out/name/'ELMAC0001'
for item in m['stage_files']:
    f=stage/item['name']
    if not f.is_file() or f.stat().st_size!=item['bytes'] or digest(f.read_bytes())!=item['sha256']:errors.append(str(f))
# PARAM.SFO has little-endian index records even on the big-endian PS3.
sfo=(stage/'PARAM.SFO').read_bytes()
magic, fmt, keys, values, count=struct.unpack_from('<4s4I',sfo)
if magic!=b'\0PSF': errors.append('invalid PARAM.SFO magic')
entries={}
key_order=[]
for i in range(count):
    key_offset, data_format, length, maximum, data_offset=struct.unpack_from('<HHIII',sfo,20+i*16)
    key=sfo[keys+key_offset:].split(b'\0',1)[0].decode()
    key_order.append(key)
    data=sfo[values+data_offset:values+data_offset+length]
    if data_format==0x0204: entries[key]=data.rstrip(b'\0').decode()
    elif data_format==0x0404 and length==4: entries[key]=struct.unpack('<I',data)[0]
if key_order!=sorted(set(key_order)): errors.append('PARAM.SFO keys must be unique and alphabetically sorted for XMB')
if entries.get('CATEGORY')!='HG' or entries.get('BOOTABLE')!=1: errors.append('PARAM.SFO must describe a bootable HDD game')
major,minor,patch=map(int,m['version'].split('.'))
expected_version=f'{major:02d}.{minor:02d}'
for key in ('APP_VER','VERSION'):
    if entries.get(key)!=expected_version: errors.append(f'{key} is not {expected_version}')
if entries.get('SOUND_FORMAT')!=1: errors.append('SOUND_FORMAT must advertise stereo LPCM only')
if entries.get('TITLE_ID')!='ELMAC0001': errors.append('incorrect TITLE_ID')
if entries.get('TITLE')!='Elasto Mania Classic '+m['version']: errors.append('title lacks full release version')
icon=(stage/'ICON0.PNG').read_bytes()
if icon[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack_from('>II',icon,16)!=(320,176): errors.append('ICON0 must be 320x176 PNG')
if digest(icon)!=digest((root/'console/ps3/assets/ICON0.PNG').read_bytes()): errors.append('ICON0 is not current project artwork')
for license in ['elma/LICENSE.md','hqx/COPYING','hqx/README.md','elma_libm/COPYING.LIB','elma_libm/README.md','SDL2/COPYING.txt','SDL2/COPYING.LIB','SDL2/SDL_PSL1GHTrender.c','SDL2/SDL3_PIXELART_LICENSE.txt','SDL2/shaders/elma_pixelart.vp','SDL2/shaders/elma_pixelart.fp']:
    if not (stage/'USRDIR/licenses'/license).is_file():errors.append('missing license '+license)
x87_notices={'README.md':'README.md','UPSTREAM.json':'UPSTREAM.json','LICENSE':'upstream/bochs/LICENSE','COPYING':'upstream/bochs/COPYING','softfloat3e/COPYING.txt':'upstream/bochs/cpu/softfloat3e/COPYING.txt','softfloat3e/README.txt':'upstream/bochs/cpu/softfloat3e/README.txt'}
if profile=='classic-x87':
    for destination,source in x87_notices.items():
        notice=stage/'USRDIR/licenses/elma_x87'/destination
        if not notice.is_file() or notice.read_bytes()!=(root/'third_party/elma_x87'/source).read_bytes(): errors.append('missing or changed Classic x87 notice: '+destination)
elif (stage/'USRDIR/licenses/elma_x87').exists(): errors.append('Classic x87 notices in default-profile stage')
engine_license=stage/'USRDIR/licenses/elma/LICENSE.md'
if engine_license.is_file() and engine_license.read_bytes()!=(root/'LICENSE.md').read_bytes():
    errors.append('engine license differs from repository LICENSE.md')
for license in ['elma_libm/COPYING.LIB','SDL2/COPYING.LIB']:
    text=(stage/'USRDIR/licenses'/license).read_text()
    if 'GNU LESSER GENERAL PUBLIC LICENSE' not in text or 'Version 2.1' not in text or len(text)<20000: errors.append('incomplete LGPL text: '+license)
if m['kind']=='code' and ((stage/'USRDIR/elma.res').exists() or (stage/'USRDIR/lgr').exists()):errors.append('game data in code-only stage')
if m['kind']=='with-data' and not (stage/'USRDIR/elma.res').is_file():errors.append('data package lacks elma.res')
if not a.allow_older_build:
    cache=(build/'CMakeCache.txt').read_text()
    expected='ON' if profile=='classic-x87' else 'OFF'
    if re.findall(r'^ELMA_CLASSIC_X87:BOOL=(.*)$',cache,re.M)!=[expected]: errors.append('build physics profile differs from manifest')
    for relative, expected_hash in m.get('build_provenance_sha256',{}).items():
        artifact=build/relative
        if not artifact.is_file() or digest(artifact.read_bytes())!=expected_hash: errors.append('build provenance differs: '+relative)
    if digest((build/'elma.elf').read_bytes())!=m['built_elf_sha256']:errors.append('package ELF differs from current build')
archived_sources=set()
with tarfile.open(out/(name+'.source.tar.gz'),'r:gz') as archive:
    try:
        engine_license_member=archive.extractfile('LICENSE.md')
        if engine_license_member is None or engine_license_member.read()!=(root/'LICENSE.md').read_bytes():
            errors.append('source archive engine license differs from repository LICENSE.md')
    except KeyError:
        errors.append('source archive missing LICENSE.md')
    for item in archive:
        path=pathlib.PurePosixPath(item.name)
        if path.is_absolute() or '..' in path.parts or any(x in path.parts for x in ['.toolchain','build','dist']) or path.name=='elma.res':
            errors.append('unexpected source archive member '+item.name)
        if item.isfile() and not a.allow_older_build and not item.name.startswith('third_party/SDL2-PSL1GHT/'):
            archived_sources.add(item.name)
            local=root/item.name
            if not local.is_file() or digest(archive.extractfile(item).read())!=digest(local.read_bytes()):errors.append('archived source differs: '+item.name)
if not a.allow_older_build:
    expected_sources=set()
    for selected in ['CMakeLists.txt','README.md','LICENSE.md','src','desktop','third_party','console/ps3','tests']:
        path=root/selected
        for file in ([path] if path.is_file() else path.rglob('*')):
            relative=file.relative_to(root)
            if not file.is_file() or '__pycache__' in relative.parts:continue
            if any(str(relative).startswith('console/ps3/'+excluded+'/') for excluded in ['.toolchain','build','dist']):continue
            expected_sources.add(str(relative))
    for missing in sorted(expected_sources-archived_sources):errors.append('source archive missing current file: '+missing)
if errors:raise SystemExit('FAIL:\n'+'\n'.join(errors))
print('PASS: artifact/stage hashes, licenses, source archive, data separation and ELF freshness: '+name)
