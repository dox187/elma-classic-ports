#!/usr/bin/env python3
"""Stream RPCS3 PCM/float audio; explicit recovery supports interrupted dumps."""
import argparse,array,hashlib,json,math,pathlib,struct,sys
p=argparse.ArgumentParser()
p.add_argument('wav',type=pathlib.Path)
p.add_argument('--json',type=pathlib.Path)
p.add_argument('--interrupted-rpcs3-float-stereo',action='store_true',help='Explicitly interpret an unfinished RPCS3 dump: 56-byte reserved header, 48kHz stereo float32 LE')
a=p.parse_args();size=a.wav.stat().st_size
with a.wav.open('rb') as f:
    header=f.read(12);offset=length=None;fmt=None
    if header[:4]==b'RIFF' and header[8:12]==b'WAVE':
        while f.tell()+8<=size:
            kind,n=struct.unpack('<4sI',f.read(8))
            if kind==b'fmt ':fmt=f.read(n)
            elif kind==b'data':offset=f.tell();length=min(n,size-offset);break
            else:f.seek(n,1)
            if n&1:f.seek(1,1)
        if fmt is None or offset is None:raise SystemExit('FAIL: WAV lacks format/data')
        tag,channels,rate,_,_,bits=struct.unpack_from('<HHIIHH',fmt)
        if tag==0xfffe and len(fmt)>=26:tag=struct.unpack_from('<H',fmt,24)[0]
    elif a.interrupted_rpcs3_float_stereo and header==bytes(12):
        # RPCS3 AudioDumper::Open seeks sizeof(WAVHeader), Close writes header.
        # Verify its entire reserved header, never silently guess raw encoding.
        f.seek(0)
        if f.read(56)!=bytes(56):raise SystemExit('FAIL: unexpected interrupted header')
        tag,channels,rate,bits,offset,length=3,2,48000,32,56,size-56
    else:raise SystemExit('FAIL: missing/unfinished WAV header; explicit recovery required')
    if (tag,bits) not in ((3,32),(1,16)):raise SystemExit('FAIL: unsupported encoding')
    width=bits//8
    if length%(channels*width):raise SystemExit('FAIL: partial audio frame')
    f.seek(offset);remaining=length;peak=energy=0.;nonzero=invalid=count=0;first_signal=None
    while remaining:
        data=f.read(min(1024*1024,remaining));remaining-=len(data)
        values=array.array('f' if tag==3 else 'h');values.frombytes(data)
        if sys.byteorder!='little':values.byteswap()
        for raw in values:
            value=float(raw)/(32768. if tag==1 else 1.)
            if not math.isfinite(value):invalid+=1
            else:
                peak=max(peak,abs(value));energy+=value*value
                if value:
                    nonzero+=1
                    if first_signal is None:first_signal=count/channels/rate
            count+=1
sha=hashlib.file_digest(a.wav.open('rb'),'sha256').hexdigest()
result={'path':str(a.wav.resolve()),'sha256':sha,'bytes':size,'header_finalized':header[:4]==b'RIFF','encoding':'float32' if tag==3 else 'pcm16','channels':channels,'sample_rate':rate,'frames':count//channels,'seconds':count/channels/rate,'first_signal_seconds':first_signal,'peak':peak,'rms':math.sqrt(energy/max(1,count)),'nonzero_samples':nonzero,'nonfinite_samples':invalid,'result':'PASS' if nonzero and not invalid else 'FAIL'}
text=json.dumps(result,indent=2)+'\n';print(text,end='')
if a.json:a.json.write_text(text)
raise SystemExit(0 if result['result']=='PASS' else 1)
