"""Lower the complete validated fixed-point step to plain C.

Clang resolves overloaded equations, preserving original control/event order.
The optional C backend uses checked128-bit integer host intermediates. The
same C control compiles816-TCC with word-array math API for a native backend.
Only level initialization and harness state marshalling remain host adapters.
Original files are never edited; native-link/FPS proof is a separate stage.
"""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
UNITS = ['LEPTET.CPP', 'BEALLIT.CPP', 'UTKOZES.CPP', 'UTKOZES2.CPP', 'SZAKASZ.CPP', 'VEKT2.CPP']
FUNCTIONS = {
    'LEPTET.CPP': ['szogigazit', 'erokszamitasa', 'resetleptet', 'szamitfejr',
                    'leptet', 'surlodasverseny', 'kiszamolsurlodast', 'vizsgalat'],
    'BEALLIT.CPP': ['helyigazitas', 'talppontigazitas', 'biztostalppont_regi',
                    'biztostalppont_uj', 'beallit', 'vezeto_hatarolas', 'beallitvezeto'],
    'UTKOZES.CPP':['gombszakasz','talppontkereses'],
    'UTKOZES2.CPP':['utkozikesprite'],
    'pcphys.cpp':['startwavegyujto','getwavegyujto','spritefeldolgoz','pc_step','pc_turn'],
}
TYPES = {'wide_scalar': 'wp_scalar', 'vekt2': 'wp_vec', 'kor': 'wp_kor',
         'motorst': 'wp_motor', 'vonal': 'wp_line','kerek':'wp_object',
         'topol':'wp_top','gyuru':'wp_ring','ecset':'wp_brush','szakaszok':'wp_segments',
         'vonalnode':'wp_node','pvonalnode':'wp_node *','soknodecsomag':'wp_node_package'}


def ctype(t):
    t = re.sub(r'\b(?:const|struct|class)\s+', '', t).replace('&', '')
    for before, after in TYPES.items():
        t = re.sub(r'\b' + before + r'\b', after, t)
    return t.strip()


def trees(text):
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        tree, pos = decoder.raw_decode(text, pos)
        yield tree


class Lower:
    def __init__(self,bits=40,profile_math=False):
        self.bits=bits
        self.profile_math=profile_math
        self.scope='unknown'
        self.locals = set()
        self.calls = {}
        self.globals = {}
        self.constants={}
        self.names = {n for ns in FUNCTIONS.values() for n in ns}
        self.methods={('szakaszok','felsorolasreset'),('szakaszok','getnext'),('ecset','kilogna'),('topol','getptrkerek')}

    def typ(self, node):
        typ=node.get('type',{})
        return ctype(typ.get('desugaredQualType',typ.get('qualType','void')))

    def constant(self,raw):
        if raw not in self.constants:self.constants[raw]=len(self.constants)
        return 'wp_constant('+str(self.constants[raw])+')'

    def raw_scalar(self,n):
        while n['kind'] in ('ImplicitCastExpr','ParenExpr','ExprWithCleanups'):
            n=n['inner'][0]
        return n['kind']=='MemberExpr'and n['name']=='raw'

    def expr(self, n):
        k = n['kind']
        kids = n.get('inner', [])
        if k in ('ImplicitCastExpr', 'MaterializeTemporaryExpr', 'ExprWithCleanups',
                 'CXXBindTemporaryExpr', 'ParenExpr', 'ConstantExpr'):
            return self.expr(kids[0])
        if k == 'DeclRefExpr':
            d = n['referencedDecl']; name = d['name']
            if d['kind'] in ('FunctionDecl','CXXMethodDecl','EnumConstantDecl'):
                return name
            if d['id'] not in self.locals:
                self.globals[name] = ctype(d['type']['qualType'])
            return name
        if k in ('IntegerLiteral', 'FloatingLiteral'):
            return n['value']
        if k == 'StringLiteral':
            return n['value']
        if k in ('GNUNullExpr', 'CXXNullPtrLiteralExpr', 'CXXDefaultArgExpr'):
            return '0'
        if k == 'CXXBoolLiteralExpr':
            return '1' if n['value'] else '0'
        if k == 'MemberExpr':
            base = self.expr(kids[0])
            if n['name'] == 'raw':
                return '(*'+base+')' if n.get('isArrow') else base
            return '(' + base + ')' + ('->' if n.get('isArrow') else '.') + n['name']
        if k=='CXXThisExpr':return 'self'
        if k=='ArraySubscriptExpr':return '('+self.expr(kids[0])+')['+self.expr(kids[1])+']'
        if k == 'UnaryOperator':
            arg = self.expr(kids[0]); op = n['opcode']
            return '(' + (arg + op if n.get('isPostfix') else op + arg) + ')'
        if k in ('BinaryOperator', 'CompoundAssignOperator'):
            if n['opcode'] in ('==','!=','<','>','<=','>=')and any(self.raw_scalar(x)for x in kids):
                rendered=[self.expr(x)if self.raw_scalar(x)else'wp_int('+self.expr(x)+')'for x in kids]
                helper={'==':'wp_eq','!=':'wp_ne','<':'wp_lt','>':'wp_gt','<=':'wp_le','>=':'wp_ge'}[n['opcode']]
                return helper+'('+','.join(rendered)+')'
            return '(' + self.expr(kids[0]) + n['opcode'] + self.expr(kids[1]) + ')'
        if k == 'ConditionalOperator':
            return '(' + self.expr(kids[0]) + '?' + self.expr(kids[1]) + ':' + self.expr(kids[2]) + ')'
        if k in ('CXXConstructExpr','CXXTemporaryObjectExpr'):
            typ = self.typ(n)
            if len(kids) == 1 and self.typ(kids[0]) == typ:
                return self.expr(kids[0])
            if typ == 'wp_scalar':
                return 'wp_int(' + (self.expr(kids[0]) if kids else '0') + ')'
            if typ == 'wp_vec':
                return 'wp_vec_make(' + ','.join(self.expr(x) for x in kids) + ')' if kids else 'wp_vec_make(wp_int(0),wp_int(0))'
            raise ValueError('Unsupported construction ' + typ)
        if k == 'CXXFunctionalCastExpr':
            return self.expr(kids[0])
        if k == 'CXXOperatorCallExpr':
            op = self.expr(kids[0]); args = kids[1:]
            if op in ('operator=', 'operator+=', 'operator-=', 'operator*=', 'operator/='):
                left, right = [self.expr(x) for x in args]
                if op == 'operator=':
                    return '(' + left + '=' + right + ')'
                helper = {'operator+=':'wp_add','operator-=':'wp_sub','operator*=':'wp_mul','operator/=':'wp_div'}[op]
                if self.typ(args[0]) == 'wp_vec': helper += '_v'
                return '(' + left + '=' + helper + '(' + left + ',' + right + '))'
            symbol = op.removeprefix('operator')
            if symbol in ('==', '!=', '<', '>', '<=', '>='):
                rendered=[self.expr(x) if self.typ(x)=='wp_scalar' else 'wp_int('+self.expr(x)+')' for x in args]
                helper={'==':'wp_eq','!=':'wp_ne','<':'wp_lt','>':'wp_gt','<=':'wp_le','>=':'wp_ge'}[symbol]
                return helper+'('+','.join(rendered)+')'
            if symbol == '-' and len(args) == 1:
                return 'wp_neg(' + self.expr(args[0]) + ')'
            helper = {'+': 'wp_add', '-': 'wp_sub', '*': 'wp_mul', '/': 'wp_div', '%': 'wp_cross'}[symbol]
            types = [self.typ(x) for x in args]
            if types == ['wp_vec', 'wp_vec']:
                helper = {'+': 'wp_add_v', '-': 'wp_sub_v', '*': 'wp_dot', '%': 'wp_cross'}[symbol]
            elif types == ['wp_vec', 'wp_scalar']: helper = 'wp_scale'
            elif types == ['wp_scalar', 'wp_vec']: helper = 'wp_scale_left'
            rendered=[self.expr(x) if self.typ(x) in ('wp_scalar','wp_vec') else 'wp_int('+self.expr(x)+')' for x in args]
            return helper + '(' + ','.join(rendered) + ')'
        if k == 'CXXMemberCallExpr':
            callee = kids[0]
            if callee['name'] == 'operator int':
                return 'wp_to_int(' + self.expr(callee['inner'][0]) + ')'
            instance=callee['inner'][0];cls=self.typ(instance).replace('wp_','').replace('*','').strip()
            cls={'segments':'szakaszok','brush':'ecset','top':'topol'}[cls]
            name=cls+'_'+callee['name'];args=[instance]+kids[1:]
            if (cls,callee['name']) not in self.methods:raise ValueError('Unknown method '+name)
            return 'wp_'+name+'('+','.join(self.expr(x)for x in args)+')'
        if k == 'CallExpr':
            name = self.expr(kids[0]); args = kids[1:]
            if name == 'literal':
                value = json.loads(self.expr(args[0]))
                return self.constant(int((Decimal(value) * (1 << self.bits)).to_integral_value(rounding=ROUND_HALF_UP)))
            c_name = 'wp_' + name
            rendered = [self.expr(x) for x in args]
            if name not in self.names:
                sig = (self.typ(n), tuple(self.typ(x) for x in args))
                if name in self.calls and self.calls[name] != sig:
                    c_name += '_' + '_'.join(t.replace('wp_', '').replace('*', 'ptr').replace(' ', '') for t in sig[1])
                self.calls[c_name.removeprefix('wp_')] = sig
            if self.profile_math and name in ('abs','absnegyzet','egys','wide_contact_normal'):
                return 'wp_profile_'+name+'('+','.join(rendered+[json.dumps(self.scope)])+')'
            return c_name + '(' + ','.join(rendered) + ')'
        raise ValueError('Unsupported expression ' + k)

    def stmt(self, n):
        k = n['kind']; kids = n.get('inner', [])
        if k == 'CompoundStmt':
            return '{\n' + '\n'.join(self.stmt(x) for x in kids) + '\n}'
        if k == 'DeclStmt':
            result = []
            for d in kids:
                self.locals.add(d['id'])
                initializer = d.get('inner', [])
                typ=self.typ(d);suffix=''
                if '[' in typ:typ,suffix=typ.split('[',1);suffix='['+suffix
                if d.get('storageClass')=='static'and initializer:
                    name=d['name'];value=self.expr(initializer[-1])
                    result.append('static '+typ+' '+name+suffix+';static int '+name+'_initialized=0;if(!'+name+'_initialized){'+name+'='+value+';'+name+'_initialized=1;}')
                else:result.append(typ + ' ' + d['name'] + suffix + ('=' + self.expr(initializer[-1]) if initializer else '') + ';')
            return '\n'.join(result)
        if k == 'IfStmt':
            return 'if(' + self.expr(kids[0]) + '){' + self.stmt(kids[1]) + '}' + ('else {' + self.stmt(kids[2])+'}' if len(kids)>2 else '')
        if k == 'SwitchStmt':
            return 'switch(' + self.expr(kids[0]) + ')' + self.stmt(kids[1])
        if k == 'CaseStmt':
            return 'case ' + self.expr(kids[0]) + ': ' + self.stmt(kids[-1])
        if k == 'DefaultStmt': return 'default: ' + self.stmt(kids[0])
        if k == 'ReturnStmt': return 'return' + (' ' + self.expr(kids[0]) if kids else '') + ';'
        if k == 'BreakStmt': return 'break;'
        if k == 'ContinueStmt': return 'continue;'
        if k == 'NullStmt': return ';'
        if k == 'WhileStmt': return 'while(' + self.expr(kids[0]) + ')' + self.stmt(kids[1])
        if k == 'ForStmt':
            return '{'+self.stmt(kids[0])+'for(;' + self.expr(kids[2]) + ';' + self.expr(kids[3]) + ')' + self.stmt(kids[4])+'}'
        return self.expr(n) + ';'

    def function(self, n, cls=None):
        self.scope=(cls+'_' if cls else '')+n['name']
        self.locals = {x['id'] for x in n['inner'] if x['kind'] == 'ParmVarDecl'}
        params = [self.typ(x) + ' ' + x['name'] for x in n['inner'] if x['kind'] == 'ParmVarDecl']
        if cls:params.insert(0,TYPES[cls]+' * self')
        ret = ctype(re.split(r'\s*\(',n['type']['qualType'],1)[0])
        declaration = ret + ' wp_' + (cls+'_' if cls else '')+n['name'] + '(' + ','.join(params or ['void']) + ')'
        return declaration, declaration + self.stmt(next(x for x in n['inner'] if x['kind'] == 'CompoundStmt'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, default=ROOT / 'build/wide-accel-g32-c30-compact')
    ap.add_argument('--out', type=Path, default=ROOT / 'build/wide-port-controller')
    ap.add_argument('--persist-state-bits',type=int,choices=(0,32),default=0,
                    help='Quantize persistent position/angle at every completed step, including constrained returns')
    ap.add_argument('--c-math',action='store_true',help='Use plain C checked-integer arithmetic backend instead of C++ numeric bridge')
    ap.add_argument('--profile-math',action='store_true',help='Record vector norm ranges by caller without changing arithmetic')
    args = ap.parse_args(); base=args.base.resolve(); out=args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if(out/'port_build.json').exists():raise ValueError('Use a fresh output directory; successful stages are immutable')
    for path in base.iterdir():
        if path.is_file() and path.suffix in ('.h','.cpp','.CPP','.py'):
            shutil.copy2(path,out/path.name)
    bits=json.loads((base/'build.json').read_text())['bits']
    if not 32<=bits<=48:raise ValueError('Unsupported scalar fraction')
    if args.profile_math and not args.c_math:raise ValueError('Math profiling requires the C backend')
    lower=Lower(bits,args.profile_math); declarations=[]; functions=[]
    if args.c_math:lower.globals['G']='wp_scalar'
    for unit,names in FUNCTIONS.items():
        for name in names:
            cmd=['/usr/bin/clang++','-std=c++17','-DWIDE_BITS='+str(bits),'-I'+str(base),'-I'+str(ROOT/'test'),'-Xclang','-ast-dump=json','-Xclang','-ast-dump-filter='+name,'-fsyntax-only',str(base/unit)]
            result=subprocess.run(cmd,capture_output=True,text=True,check=True)
            candidates=[t for t in trees(result.stdout) if t.get('kind')=='FunctionDecl' and t.get('name')==name and any(x['kind']=='CompoundStmt' for x in t.get('inner',[]))]
            if len(candidates)!=1: raise ValueError('Ambiguous function '+name)
            declaration,function=lower.function(candidates[0]);declarations.append(declaration+';');functions.append(function)
    for cls,name in sorted(lower.methods):
        unit='SZAKASZ.CPP' if cls=='szakaszok' else 'pcphys.cpp'
        cmd=['/usr/bin/clang++','-std=c++17','-DWIDE_BITS='+str(bits),'-I'+str(base),'-I'+str(ROOT/'test'),'-Xclang','-ast-dump=json','-Xclang','-ast-dump-filter='+cls+'::'+name,'-fsyntax-only',str(base/unit)]
        result=subprocess.run(cmd,capture_output=True,text=True,check=True)
        candidates=[t for t in trees(result.stdout)if t.get('kind')=='CXXMethodDecl'and t.get('name')==name and any(x['kind']=='CompoundStmt'for x in t.get('inner',[]))]
        if len(candidates)!=1:raise ValueError('Ambiguous method '+cls+'::'+name)
        declaration,function=lower.function(candidates[0],cls);declarations.append(declaration+';');functions.append(function)
    if args.persist_state_bits:
        canonical='void wp_canonical_state(wp_motor* motor){\n'
        for circle in ('kor1','kor2','kor4'):
            for field in ('r.x','r.y','alfa'):
                member='motor->'+circle+'.'+field
                canonical+=member+'=wp_quantize32('+member+');\n'
        for field in ('vezetor.x','vezetor.y'):
            member='motor->'+field;canonical+=member+'=wp_quantize32('+member+');\n'
        canonical+='}\n'
        functions.insert(0,canonical)
        declarations.insert(0,'void wp_canonical_state(wp_motor* motor);')
        functions=[re.sub(r'return ([^;]+);',r'wp_canonical_state(Pmot1);return \1;',f)if f.startswith('int wp_pc_step(')else f for f in functions]
    own_constants={'Maxsurlodas':0,'Loket':Decimal('.06552'),'Omegavalt':Decimal('.01638'),
                   'Utodeshatar':Decimal('.008190')}
    own_constants={n:int((v*(1<<bits)).to_integral_value(rounding=ROUND_HALF_UP)) if isinstance(v,Decimal) else v for n,v in own_constants.items()}
    dt=int((Decimal('.00546')*(1<<bits)).to_integral_value(rounding=ROUND_HALF_UP))
    own_constants['Oszto']=((1<<(2*bits))+dt//2)//dt
    own_constants.update(Eddig=0,Utolsougras=-(100<<bits),Kajakell=0,Begyujtve=0)
    own_arrays={'Azonosito':('int',200),'Hangero':('wp_scalar',200),'Objszam':('int',200)}
    header=['#ifndef WIDE_PORT_H','#define WIDE_PORT_H','#include <stdint.h>','#include <stddef.h>','#include <stdbool.h>',
            '#ifdef WIDE_TARGET_SNES','typedef struct {uint16_t word[4];} wp_scalar;','#else','typedef int64_t wp_scalar;','#endif',
            'typedef struct {wp_scalar x,y;} wp_vec;',
            'typedef struct {char nev[30];wp_scalar alfa,omega,sugar,m,theta;wp_vec r,v;} wp_kor;',
            'typedef struct {wp_kor kor1,kor2,kor4;wp_vec fejr;int hatra_f,hatra_h,gravirany;wp_vec vezetor,vezetov;int kajaszam,voltfek;wp_scalar dfek2,dfek4;int ugrasban1,ugrasban2;wp_scalar ugras1kezd,ugras2kezd,kezdoomega1,kezdoomega2;} wp_motor;',
            'typedef struct {wp_vec r,v,egyseg,wide_endpoint,wide_normal;wp_scalar hossz;} wp_line;',
            'typedef struct wp_node {wp_line* pvonal;struct wp_node* pnext;} wp_node;',
            'typedef struct wp_node_package {wp_node nodetomb[500];struct wp_node_package* nextcsomag;} wp_node_package;',
            'typedef struct {wp_line* tomb;int maxszam,szam,szakfuto;wp_node** tertomb;int xdim,ydim;wp_scalar cellameret;wp_vec origo;wp_node* nextnode;wp_node_package* pelsocsomag;int csomagbanbetelt;} wp_segments;',
            'typedef struct {wp_vec r;int tipus,kajatipus,foodsorszam,aktiv;} wp_object;',
            'typedef struct {int pontszam;wp_vec* ponttomb;int koveto;} wp_ring;',
            'typedef struct {wp_ring* ptomb[300];wp_object* kerektomb[52];} wp_top;',
            'typedef struct {wp_vec eredetiorigo;wp_scalar eredetimaxx,eredetisorszam;} wp_brush;',
            '#ifndef WIDE_PORT_BRIDGE','enum {WAV_UTODES=1,T_CEL=1,T_KAJA=2,T_HALALOS=3,KT_UP=1,KT_DOWN=2,KT_LEFT=3,KT_RIGHT=4};','#endif',
            '#ifdef __cplusplus','extern "C" {','#endif']
    includes=['wide_accel_helpers.h','wide_geometry_helpers.h','wide_gravity_helpers.h','wide_compact.h']
    bridge=['#include "all.h"','#include "pcphys.h"']+['#include "'+name+'"'for name in includes if(out/name).exists()]+['#define WIDE_PORT_BRIDGE','#include "wide_port.h"',
            'static_assert(sizeof(wp_vec)==sizeof(vekt2),"vector ABI");','static_assert(sizeof(wp_kor)==sizeof(kor),"circle ABI");','static_assert(sizeof(wp_motor)==sizeof(motorst),"motor ABI");',
            'static_assert(sizeof(wp_line)==sizeof(vonal),"line ABI");','static_assert(sizeof(wp_segments)==sizeof(szakaszok),"segments ABI");','static_assert(sizeof(wp_top)==sizeof(topol),"topology ABI");','static_assert(sizeof(wp_brush)==sizeof(ecset),"brush ABI");',
            'static wide_scalar s(wp_scalar x){return wide_scalar::from_raw(x);}','static vekt2 v(wp_vec x){return vekt2(s(x.x),s(x.y));}',
            'static wp_scalar p(wide_scalar x){return x.raw;}','static wp_vec p(vekt2 x){return {x.x.raw,x.y.raw};}']
    math={
        'wp_int':('wp_scalar',['int'],'wide_scalar(a0)'),
        'wp_to_int':('int',['wp_scalar'],'int(s(a0))'),
        'wp_vec_make':('wp_vec',['wp_scalar','wp_scalar'],'vekt2(s(a0),s(a1))'),
        'wp_add':('wp_scalar',['wp_scalar','wp_scalar'],'s(a0)+s(a1)'),
        'wp_sub':('wp_scalar',['wp_scalar','wp_scalar'],'s(a0)-s(a1)'),
        'wp_mul':('wp_scalar',['wp_scalar','wp_scalar'],'s(a0)*s(a1)'),
        'wp_div':('wp_scalar',['wp_scalar','wp_scalar'],'s(a0)/s(a1)'),
        'wp_neg':('wp_scalar',['wp_scalar'],'-s(a0)'),
        'wp_add_v':('wp_vec',['wp_vec','wp_vec'],'v(a0)+v(a1)'),
        'wp_sub_v':('wp_vec',['wp_vec','wp_vec'],'v(a0)-v(a1)'),
        'wp_dot':('wp_scalar',['wp_vec','wp_vec'],'v(a0)*v(a1)'),
        'wp_cross':('wp_scalar',['wp_vec','wp_vec'],'v(a0)%v(a1)'),
        'wp_scale':('wp_vec',['wp_vec','wp_scalar'],'v(a0)*s(a1)'),
        'wp_scale_left':('wp_vec',['wp_scalar','wp_vec'],'s(a0)*v(a1)'),
    }
    if args.persist_state_bits:
        step=1<<(bits-args.persist_state_bits)
        math['wp_quantize32']=('wp_scalar',['wp_scalar'],'wide_scalar::from_raw(wide_checked(wide_round_div((__int128)a0,'+str(step)+')*'+str(step)+',"persistent position quantize"))')
    for name,op in [('wp_eq','=='),('wp_ne','!='),('wp_lt','<'),('wp_gt','>'),('wp_le','<='),('wp_ge','>=')]:
        math[name]=('int',['wp_scalar','wp_scalar'],'s(a0)'+op+'s(a1)')
    def arg(t,n):
        if t=='wp_scalar':return 's('+n+')'
        if t=='wp_vec':return 'v('+n+')'
        if t.startswith('wp_') and '*' in t:
            original=t
            for before,after in TYPES.items():original=original.replace(after,before)
            return 'reinterpret_cast<'+original+'>('+n+')'
        return n
    c_math=set()
    if args.c_math:
        shutil.copy2(ROOT/'test/wide_port_math.c',out/'wide_port_math.c')
        c_math=set(re.findall(r'\b(wp_\w+)\([^\n{;]*\)\s*\{',(out/'wide_port_math.c').read_text()))
        c_math.update(('wp_eq','wp_ne','wp_lt','wp_gt','wp_le','wp_ge'))
        (out/'wide_trig_table_c.h').write_text((out/'wide_trig_table.h').read_text().replace('static constexpr','static const'))
    for name,(ret,params,body) in math.items():
        decl=ret+' '+name+'('+','.join(t+' a'+str(i) for i,t in enumerate(params))+')'
        header.append(decl+';')
        if name not in c_math:bridge.append('extern "C" '+decl+'{return '+('p('+body+')' if ret.startswith('wp_') else body)+';}')
    for name,(ret,params) in lower.calls.items():
        decl=ret+' wp_'+name+'('+','.join(t+' a'+str(i) for i,t in enumerate(params))+')'
        body=name+'('+','.join(arg(t,'a'+str(i)) for i,t in enumerate(params))+')'
        header.append(decl+';')
        if 'wp_'+name not in c_math:bridge.append('extern "C" '+decl+'{'+('return p('+body+');' if ret in ('wp_scalar','wp_vec') else ('return '+body+';' if ret!='void' else body+';'))+'}')
    for name,typ in lower.globals.items():
        if name in own_constants or name in own_arrays:continue
        if '['in typ:
            typ=typ.split('[',1)[0].strip()
            header.append(typ+'* wp_array_'+name+'(void);')
            header.extend(['#ifndef WIDE_PORT_BRIDGE','#define '+name+' (wp_array_'+name+'())','#endif'])
            bridge.append('extern "C" '+typ+'* wp_array_'+name+'(){return '+name+';}')
            continue
        header.append(typ+'* wp_ptr_'+name+'(void);')
        header.extend(['#ifndef WIDE_PORT_BRIDGE','#define '+name+' (*wp_ptr_'+name+'())','#endif'])
        bridge.append('extern "C" '+typ+'* wp_ptr_'+name+'(){return reinterpret_cast<'+typ+'*>(&'+name+');}')
    if args.profile_math:
        header+=['wp_scalar wp_profile_abs(wp_vec a,const char* caller);','wp_scalar wp_profile_absnegyzet(wp_vec a,const char* caller);',
                 'wp_vec wp_profile_egys(wp_vec a,const char* caller);','wp_vec wp_profile_wide_contact_normal(wp_kor* a,wp_vec point,wp_scalar* length,const char* caller);']
    header+=declarations+['wp_scalar wp_constant(unsigned int index);','void wp_runtime_reset(int apples);','#ifdef __cplusplus','}','#endif','#endif']
    (out/'wide_port.h').write_text('\n'.join(header)+'\n')
    (out/'controller.json').write_text(json.dumps({'bits':bits,'stage':'Complete C step/contact/object/event/grid-query control; C arithmetic'if args.c_math else'Complete C step/contact/object/event/grid-query control; host arithmetic bridge','level_initialization':'host C++ loader; solver consumes flat precomputed segment/grid/object structures','persistent_state_bits':args.persist_state_bits,'globals':lower.globals,'calls':lower.calls,'functions':declarations},indent=2)+'\n')
    mutable={'Maxsurlodas','Eddig','Utolsougras','Kajakell','Begyujtve'}
    constants='\n'.join(('static '+('int'if n in ('Kajakell','Begyujtve')else'wp_scalar')+' '+n+'={0};')if n in mutable else '#define '+n+' '+lower.constant(v)for n,v in own_constants.items())
    arrays='\n'.join('static '+typ+' '+n+'['+str(size)+'];'for n,(typ,size)in own_arrays.items())
    (out/'wide_controller.c').write_text('#include "wide_port.h"\n'+constants+'\n'+arrays+'\n'+'\n'.join(functions)+'\nvoid wp_runtime_reset(int apples){Kajakell=apples;Begyujtve=0;Eddig=wp_int(0);Utolsougras=wp_int(-100);}\n')
    constants_by_id=sorted(lower.constants,key=lower.constants.get)
    bridge.append('static const int64_t wp_constants[]={'+','.join(str(v)+'LL'for v in constants_by_id)+'};')
    bridge.append('extern "C" wp_scalar wp_constant(unsigned int index){if(index>='+str(len(constants_by_id))+')wide_fail("constant index");return wp_constants[index];}')
    (out/'wide_constants.json').write_text(json.dumps(constants_by_id)+'\n')
    for name in ('resetleptet','leptet','szamitfejr','kiszamolsurlodast','beallit','beallitvezeto','vizsgalat','talppontkereses','utkozikesprite','startwavegyujto','pc_step','pc_turn'):
        decl=next(d for d in declarations if ' wp_'+name+'(' in d).removesuffix(';')
        params=decl.split('(',1)[1][:-1].split(','); originaldecl=decl.replace('wp_'+name,name)
        for before,after in TYPES.items():originaldecl=originaldecl.replace(after,before)
        converted=[]
        for param in params:
            if param=='void':continue
            typ,argument=param.rsplit(' ',1)
            if typ in ('wp_scalar','wp_vec'):converted.append('p('+argument+')')
            elif typ.startswith('wp_'):converted.append('reinterpret_cast<'+typ+' >('+argument+')')
            else:converted.append(argument)
        call='wp_'+name+'('+','.join(converted)+')'
        if originaldecl.startswith('wide_scalar '):bridge.append(originaldecl+'{return s('+call+');}')
        else:bridge.append(originaldecl+'{'+('return 'if not originaldecl.startswith('void ')else '')+call+';}')
    (out/'wide_port_bridge.cpp').write_text('\n'.join(bridge)+'\n')
    legacy=(out/'LEPTET.CPP').read_text()
    for name in ('resetleptet','leptet','szamitfejr','kiszamolsurlodast','vizsgalat'):
        legacy=re.sub(r'\b'+name+r'\b','legacy_'+name,legacy)
    (out/'LEPTET_legacy.CPP').write_text(legacy)
    legacy=(out/'pcphys.cpp').read_text()
    for name in FUNCTIONS['pcphys.cpp']:
        legacy=re.sub(r'\b'+name+r'\b','legacy_'+name,legacy)
    legacy=legacy.replace('pc_time = 0;','pc_time = 0;\n\twp_runtime_reset(Kajakell);')
    legacy='extern "C" void wp_runtime_reset(int apples);\n'+legacy
    (out/'pcphys_legacy.cpp').write_text(legacy)
    if args.c_math:
        harness=(out/'wide_harness.cpp').read_text()
        harness='extern "C" void wp_math_reset_stats();\nextern "C" void wp_math_print_stats();\n'+harness
        harness=harness.replace('wide_stats={};','wide_stats={};wp_math_reset_stats();')
        harness=harness.replace('wide_print_stats("simulation",wide_stats);','wide_print_stats("simulation",wide_stats);wp_math_print_stats();')
        (out/'wide_harness.cpp').write_text(harness)
        config=['-DWIDE_PORT_BITS='+str(bits),'-DWIDE_HAS_ACCEL='+str(int((out/'wide_accel_core.h').exists()))]
        gravity_source=(out/'wide_gravity_helpers.h').read_text()
        if 'auto result=direction*mass*G;' in gravity_source:gravity_mass_folded=0
        elif 'auto result=direction*G;' in gravity_source:gravity_mass_folded=1
        else:raise ValueError('Unknown gravity helper equation; do not assume mass is folded')
        config.append('-DWIDE_GRAVITY_MASS_FOLDED='+str(gravity_mass_folded))
        if(out/'wide_compact.h').exists():
            for macro in ('COMPACT_STATE_BITS','COMPACT_STATE_WIDTH'):
                value=re.search(r'#define\s+'+macro+r'\s+(\d+)',(out/'wide_compact.h').read_text())
                if value:config.append('-DWP_'+macro.removeprefix('COMPACT_')+'='+value[1])
        config.append('-DGUMI_BITS=32')
        config.append('-DWIDE_PROFILE_MATH='+str(int(args.profile_math)))
        (out/'wide_math_config.h').write_text('#pragma once\n'+''.join('#define '+value[2:].replace('=',' ',1)+'\n' for value in config))
        cmd=['cc','-std=c11','-O2','-Wall','-Werror=implicit-function-declaration','-I'+str(out),'-c',str(out/'wide_port_math.c'),'-o',str(out/'wide_port_math.o')]
        result=subprocess.run(cmd,capture_output=True,text=True);(out/'compile-math.txt').write_text(result.stdout+result.stderr)
        if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
    commands=[['cc','-std=c11','-O2','-Wall','-Werror=implicit-function-declaration','-I'+str(out),'-c',str(out/'wide_controller.c'),'-o',str(out/'wide_controller.o')],
              ['c++','-std=c++17','-O2','-w','-DWIDE_BITS='+str(bits),'-I'+str(out),'-I'+str(ROOT/'test'),'-o',str(out/'widecheck'),str(out/'wide_harness.cpp'),str(out/'pcphys_legacy.cpp'),str(out/'wide_port_bridge.cpp'),str(out/'wide_controller.o'),str(out/'LEPTET_legacy.CPP')]+[str(out/u) for u in UNITS if u not in FUNCTIONS]]
    if args.c_math:commands[-1].append(str(out/'wide_port_math.o'))
    for index,cmd in enumerate(commands):
        result=subprocess.run(cmd,capture_output=True,text=True);(out/('compile-'+str(index)+'.txt')).write_text(result.stdout+result.stderr)
        if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
    toolkit=Path.home()/'.local/share/elma-snes/pvsneslib-4.6.0/pvsneslib/devkitsnes'
    cmd=[str(toolkit/'bin/816-tcc'),'-Wall','-F','-DWIDE_TARGET_SNES=1','-I'+str(toolkit/'include'),'-I'+str(out),'-c',str(out/'wide_controller.c'),'-o',str(out/'wide_controller.ps')]
    result=subprocess.run(cmd,capture_output=True,text=True)
    (out/'compile-native.txt').write_text(result.stdout+result.stderr)
    if result.returncode:print(result.stdout+result.stderr);raise SystemExit(result.returncode)
    (out/'port_build.json').write_text(json.dumps({'bits':bits,'base':str(base),'c_math':args.c_math,'persistent_state_bits':args.persist_state_bits,'host_commands':commands,'native_control_command':cmd,'native_backend_linked':False},indent=2)+'\n')
    shutil.copy2(Path(__file__).resolve(),out/'wide_port_variant.py')
    print(out/'widecheck')


if __name__=='__main__': main()
