#!/usr/bin/env python3
"""Pure protected affected-suite selection; no suite/build/runtime execution."""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch, Mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inputs


def blob(raw=b'fixed', *, mode='100644'):
    return {'mode':mode,'type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}


def definition(scope='content'):
    return {'command':['python','contracts/test.py'],'layer':'host','scope':scope,'environment':'host-qt5-qt6',
        'closure':{'kind':'patterns','inputs':['contracts/**','source/**'],'required':['contracts/test.py']},
        'python_imports':{'roots':['contracts'],'reviewed':'sha256:'+'0'*64}}


class AffectedPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tree={p:blob(p.encode(),mode='100755' if p=='tests/run-project-tests.py' else '100644')
                   for p in inputs.AFFECTED_AUTHORITY}
        self.tree['tests/platform-profile.json']=deepcopy(inputs._AFFECTED_SHARED_PROFILE)
        self.tree.update({'contracts/test.py':blob(b'fixed test'),'source/input.qml':blob(b'fixed data'),
            'tools/test-evidence/sandbox_host.py':blob(b'old controller'),'unrelated/readme.md':blob(b'data')})
        finite=definition();finite['python_imports']['reviewed']=inputs.python_import_digest(self.tree,['contracts'])
        self.registry={'schema':1,'control_inputs':['tests/run-project-tests.py','tools/test-evidence/**','*.py'],
            'suites':{'finite':finite,'unproved':{'command':['python','unknown.py'],'layer':'quick','scope':'content',
                'environment':'host-qt5-qt6','closure':{'kind':'repository','inputs':[],'required':[]}},
                'candidate':definition('candidate')}}
        self.dependencies={'schema':1,'lookup_digest':inputs.affected_lookup_digest(self.tree),'registry_digest':inputs._suite_definition_digest(self.registry),'suites':{
            n:{'kind':'repository' if n=='unproved' else 'reviewed-patterns',
               'definition_digest':inputs._suite_definition_digest(s),'setup':['host-full'] if n=='unproved' else ['python']}
            for n,s in self.registry['suites'].items()}}
        self.seal()
        self.candidate=deepcopy(self.tree)
        self.candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed candidate controller')

    def seal(self):
        self.raw=json.dumps(self.dependencies,indent=2).encode()
        self.tree[inputs.AFFECTED_POLICY]=blob(self.raw)

    def plan(self,base=None,candidate=None,trusted=None,raw=None,registry=None):
        return inputs.plan_affected(registry or self.registry,self.raw if raw is None else raw,
            self.tree if base is None else base,self.candidate if candidate is None else candidate,
            self.tree if trusted is None else trusted)

    def test_changed_controller_selects_unproved_and_candidate_owners_individually(self):
        plan=self.plan()
        self.assertEqual(plan['required'],['unproved','candidate'])
        self.assertEqual(plan['omitted'],['finite'])
        self.assertFalse(plan['reusable'])
        self.assertEqual(plan['required_setup'],['host-full'])
        self.assertEqual(plan['paths'],['tools/test-evidence/sandbox_host.py'])

    def test_own_data_and_discovery_changes_select_their_suite(self):
        for path in ('source/input.qml','source/new.qml','contracts/data.json'):
            with self.subTest(path=path):
                candidate=deepcopy(self.candidate);candidate[path]=blob(b'changed')
                self.assertIn('finite',self.plan(candidate=candidate)['required'])

    def test_lookup_shadows_native_modules_pth_and_deletions_are_not_hidden(self):
        for path in ('contracts/json.py','contracts/sitecustomize.py','contracts/module.so','contracts/path.pth','contracts/test.py'):
            with self.subTest(path=path):
                candidate=deepcopy(self.candidate)
                if path in candidate:del candidate[path]
                else:candidate[path]=blob(b'new lookup candidate')
                with self.assertRaises(inputs.InputError):self.plan(candidate=candidate)

    def test_historical_unreviewed_module_on_both_sides_keeps_owner_required(self):
        base=deepcopy(self.tree);candidate=deepcopy(self.candidate)
        for tree in (base,candidate):tree['contracts/historical.py']=blob(b'child variant')
        with self.assertRaises(inputs.InputError):self.plan(base=base,candidate=candidate)

    def test_nonregular_inventory_anywhere_declines_even_if_unchanged(self):
        for mode,kind in (('120000','blob'),('160000','commit')):
            with self.subTest(mode=mode):
                base=deepcopy(self.tree);candidate=deepcopy(self.candidate)
                for tree in (base,candidate):tree['other/entry']={'mode':mode,'type':kind,'sha':'a'*40}
                with self.assertRaises(inputs.InputError):self.plan(base=base,candidate=candidate)

    def test_candidate_cannot_add_replace_remove_or_enable_its_graph(self):
        for which in ('candidate','base','trusted'):
            for operation in ('remove','change','mode'):
                trees={n:deepcopy(t) for n,t in (('base',self.tree),('candidate',self.candidate),('trusted',self.tree))}
                if operation=='remove':del trees[which][inputs.AFFECTED_POLICY]
                elif operation=='mode':trees[which][inputs.AFFECTED_POLICY]['mode']='100755'
                else:trees[which][inputs.AFFECTED_POLICY]=blob(b'candidate narrowed graph')
                with self.subTest(which=which,operation=operation),self.assertRaises(inputs.InputError):self.plan(**trees)

    def test_every_authority_change_declines_before_selection(self):
        for path in inputs.AFFECTED_AUTHORITY:
            candidate=deepcopy(self.candidate);candidate[path]=blob(b'new authority')
            with self.subTest(path=path),self.assertRaises(inputs.InputError):self.plan(candidate=candidate)

    def test_closed_policy_registry_definition_and_global_controls_are_bound(self):
        mutations=[]
        for change in ('schema','unknown','missing','definition','arbitrary-kind','setup','duplicate-setup'):
            value=deepcopy(self.dependencies)
            if change=='schema':value['schema']=True
            elif change=='unknown':value['force']=[]
            elif change=='missing':del value['suites']['unproved']
            elif change=='definition':value['suites']['finite']['definition_digest']='sha256:'+'f'*64
            elif change=='arbitrary-kind':value['suites']['finite']['kind']='caller-selected'
            elif change=='setup':value['suites']['unproved']['setup']=['python']
            else:value['suites']['finite']['setup']=['python','python']
            mutations.append((change,json.dumps(value).encode()))
        mutations += [('duplicate-key',self.raw.replace(b'"schema": 1',b'"schema":1,"schema":1')),
                      ('oversized',b' '*64001),('wrong-type','{}')]
        for change,raw in mutations:
            with self.subTest(change=change),self.assertRaises(inputs.InputError):self.plan(raw=raw)
        registry=deepcopy(self.registry);registry['control_inputs']=[]
        with self.assertRaises(inputs.InputError):self.plan(registry=registry)

    def test_missing_unknown_empty_and_wrong_policy_bytes_fail_closed(self):
        for tree in (None,{},[] ):
            with self.subTest(tree=tree),self.assertRaises(inputs.InputError):
                inputs.plan_affected(self.registry,self.raw,tree,self.candidate,self.tree)
        with self.assertRaises(inputs.InputError):self.plan(candidate=self.tree)
        with self.assertRaises(inputs.InputError):self.plan(raw=self.raw+b' ')


# Fixture-only projection of the REVIEWED PROPOSED SOURCE snapshot, not protected D.
# 4b4f57dc46bead393d7c77e2cd22f506ef4f153f / tree dbfec683f0de2625efe19e6f59fe064a888b5026.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'ec434b344bfb0ca7d7ca58d16236714b3937709f45b764f10e3f81cf33504945'
_MAIN_PROJECTION_B85 = (
    'c-qaK-F72MlAQ1L7=68*%E*lT+o#ac(LGN5vd~2m9008D+CBU3`YZvmS<@sU5~!6VX}71VTN8oI3=em6GxPua?H~8s<JTAe#XZIS'
    'ZX54*e>|oA-Er@p4ms`r@%v%-^xMDx=Wma@n11{B-%QgC*8cWyza73h{<a-slT0(@80W6(XA_fi^U&tpjL`<4k{#R0=>Nm<$Fu$m'
    '{KL-w_Fw<@wybBN@b&I__pl8=3afeFMPr6E%wrQ>3ezx-tkE=Mle@vkCXa)4&Gh+d&n|p(_v!AB-TqsC*!^*LpZK-zxZOP+3X7+1'
    '=-Rfo(~w&i$JX>iv@VTJJK1gy(T<((Mn8YP_&z=F4%_2y|Kl!vP2pQ<#Xj)xaxh^ulOAwNY0kaPjg2!ube>$-+T<@h++#W%?+!29'
    'W4ep!IX%Vn6t=0fZj94x+pg>K9QroLFtoi3gW-{nLvpS4^E}OIs9CqPmdjo6bKef*V0gX#;Bqu=<89m8Ci*#r;9c_O^R-@I<$;&G'
    'Pfy3Yf4;bfZQh3Et^VW3<HP5x53!A%ZIksw$MYSUp=oVzOg~1`O}+K8Z(~ej)$04*?<pMb^xF@Ym!0OeakEL|9H!Lvp|hdkcc<tE'
    ')5Os@9yrU+HOv0}qq?~Cm`Bb{mrdVKCi%dJJIr0%80UhCQ;6djXKVA{m-c&>BQk`CEl>GN*nasvJ$>6g9lqQ<z31m2pRa0+3)Y9w'
    'dTZ_ITRX)ev}Wv6>?a<0?voigNo!Vp=9lxrFRyF!*d?9Psq;-3+c-6O@}39nb2}2GrY7-;ty_2JFRz+i9vfcjXfnUAZD!ZB9nryt'
    'IZZZ<*#*~6omsQ${^jZ7n!(s%7-Dv_x6{bab8|N|^JILNd}?j<&6sjtwWhx0P58RsJ*Lee?4B?GYK}|O@MN9ohJo)oq}lbI8=JnJ'
    'I9q*)bDYe&XT9v;$vvh6fje#X$vtnM?k{d5PJF##Nc~`mn#tJInYp#r1<&y|y|sg}CaixDPtT8=uzSke%j=KMq+ueE4U=)Eor2-o'
    'XnH@mi8I|cY;I(a-RkvqFUQTF-?P8CzUMn@tc`s?a!K?JPoj5o6IyOazQ~TJ(4@}0)$8*Ga#dbjJB8d$j*!`N@VE=Z7>qX^v8}hk'
    'wPqsN4o$^xS48>4{rK{fj*4`f{qE(MHgW6jpLU1iHe8N2+{WHb$(la&$@2Q=DJ93%+4KWZFGSxu)0=tqHeTZM#f966TP&HD8-oKM'
    'XFYv(G6a)j%R$JVFENc{^}?qQ@4WhwnCTNdrazCD15nRlAGxW!zMHx(X;b~2M&CzHBX_E4yt1_7J{}x-;c@r44R?gS@7n`6DhKe3'
    'dx_iQ=6vJnmc4i)`#w1vTSqq7Wujq>cIJ+m6cf$R>t*m{#;bR;oJt*z2lqlQc{xgrLl?O9huQKzhUh$TbDr8c=QwsvHYPPBTg~;G'
    'c_E#=94TXPW(w^v<)-JiyFRodR|Cg{bg!Rs@1pJ6WUk)Bx3qss51ZvJUEImsdLBp|2kw26*KC_M``8Y>8RsDnX&y(u-!@;plSlVN'
    'x*a#<_<YLyADge+gL0LNyJ~cC4cSh<Nr5mjrk=};Ta;YEbnLJhEl=tCUF|&o()U6z8$w4a8hTH(w7wljzFyZgu_Jv-d_lyqLI3pn'
    'T|A#F5BIQ~>b(oc%Yki*c4|l4P83+vKveJhZVYiEU*xkUVV+}ZCqG}kC333#u)Y6!td6zA*kv-R#@XI;wIt5Dnans5fAoN2*HE+N'
    '(ciG8Qo6+h=$kM#BNb>jP;Iu#y2!G4Br|WXnYwA}+IaOANIN3IZu^~sy?J{?m$LxA73Z5dQ@`;Hx@nw<`+gw!W^W8}CJ=v`>mSSE'
    '$ho@wvCMoLqn7q_H-*3@lxM!%z=IkoC&#hx=Kh9LbaeasRDBC%65hszNcNEjzLCViHg@d!NJc%Of&5@@()DlYl&!vA1%CJP6kQ?E'
    '@R?A7HKgafmc~#74Uzxb55cy^54LfJI>Dx2w5N*esY}_+{p_j9Y?tQPhsINY8^f18MLuIioRFIvceLD5o2oDvdh++yaA9&WPA%|G'
    'On&0arpj?(1by!_Y1WPJEj@kT?srd*{EMeoce$)<h4aigb)EOV4+B?(cLP`x@WkYS4>C7;>~7mr^({I%JGzdlVjO&$z-XeSx+MXl'
    'y!7P00|%ZR*<ZJv&6Xta{&ag3GC}VrJ}B_2&=80{FU!wEm?tiajyuh#+_K%<wszGm??(VF5@NpbJdcSiB&bdV8!>@g#Ae&MIEP=f'
    'wXl0!aFWsk8?sB?Od@Y*L!i|AoJg7p-|TjX#%J!?sf)j6SBLaHJr$~IN>*Svy+Ddc0zkv_ni|9P(ROJ94ebcz?za6@MFP@8J9mN@'
    'VgebQ2gi-;nt{U~0A$U;3pJFvH*V!!R`j^7`NrqmbWQ+6mjLmA?!wsn*?17G#O}J*C7?^2Z`;@U)QI=y$Qi*wdVoz}t_-+n&Cpst'
    '@u8bqc4(XIZ`~L9(I)H@*zR%b9u5U`fRfAFmWy_pJ!xCcJS^n|#*^$Cz*thJIN!Xdnv|g9^5?_h|9}=bV>t6<)j;|nH{CQ)pc*&E'
    'w!LjLS7dMGkUpEi3<D>Ovf1^ZrfKZ6HOT=}`<8pqwBfdm9d<8!K&`O*n!v5Y<!p}iVnb2ncrrrSQtalzbaqw=ki#5#XaR`n#w{tU'
    '+*FjXAWY<IfPL-QQ<-JYJ=21^#IEfVxF_LhYCi1ytlv&{+lQ9|&^y^FB$s;ESXvb{Oh$5BN6r#j9#iPLX{Lc<Zv3u~kI#Agklw1b'
    '%g2A@(jPiUbp{+n#2kQScr2cLw-F>uXQ%Cl8^7-3{^fAwCi#|r>`TxnXP*3$^KE@HeA6@UD9iw*jW>K$Y05TE>6VIM#b%UcH=P;5'
    'MB91FyuI8K!>#oVCoFi|^)pyR-SvM4sn7r9@@)}2&_F&5(9yByzM!CQ$YgutdlFeN+I|YtRF`4jzbxS{?H{*?!_q^%n2gakqaUG0'
    'N1l?8U>YN7w5QwUMw=#@K#`bJ_mjWw^!9hVQoz>*O+7KWd9=Ys8hV5_>hp;kJT@i*#|<C$@;+Gel(t+Bon{U#2d|_35tT&&d?y3I'
    '1#FVJbLgwFhgg?CJ#qPePa78>x0i1cIvXS(#6RQPVW9f~DiL#_$JX)xIsh(9!BANcoL8*@6Pt!hoU%*>(il=0DC{jK9u!3IQJ`ES'
    '4Agx~?@v;7juASOT2GNreW<FH4p6kT_Q*9j>`hAt6%f9%UVPv0sX0nxq_(hKj2$R{KUx*|X(oH_ILdt1)Y8;uaa^(ZsW1(@ecJra'
    '_4t%7*ANP=1T*>^mS+4o3?nG>+^BM&X+{mysV?M7jPCso9(Ui<QjBs16|O=9E;+VsZv50a!MLO~B%Qh&!Nq2(_L0WJ?CSThE~<pU'
    '6K^_>bwlf`qtVrSlRFx^oV3IRl%NWP+1IaM8Cp!t)Q*!=tqqPcPMkO)Zfc!#5bZ>GC-3g+7e2+8if2v@#CxZi+j4!ihEq6^OMCk0'
    'G+saesN7;t|8woqf0eM8?+_Z<4QY=fbrlvewq*7b4<10j;dL8u5)!g}{qpB-UwD4G{2VxUCQL1V%3FsPLY=`)Hh>ay&(TkqMj9>i'
    '6&tBrzso&MPD9p5vy<eDEH!f;x|Tnf9O%N(`q-@h1W4EyE(b@!?Jr|N-gA?->audH1VUclv!?*9f{!o}949i382!~-sCyD4&!6=g'
    'n%)kw0ptw_+kl7fsE-pjJIPf~o^i!CejLB<p6UQief$&&fI8Dc!-67|dI%rX32CCoM0L#bvR6EeeYywJp-_pNKlbkVxs+uE-%$Q$'
    'J_<sCFfcAh-#dE3ROB$m_+G$wuJ|wjmM%A8hk-h6U@_9UXw_N-8q9RtTCWfZ%1hdpDvP%>0iiY_m`69ePUMnIGa|)?8_9xhS(1a;'
    'd%BFGz~mM8(N$Ri{e_;UH(V;mPxi3l=ynDtDA2JJxN{*4T}3r?`sH`qr{|aB7vB2AnN@X1hJW`*BJl=RqawPv8+vuBQhDpk_ZP_Q'
    'DHVa%1c(54XC6!2S7b>)?S|FwQWWv&{l-*!Y}`?gt_&PGszlN>Y7mjW9A8D?^ir0LmfC|pane^?0gisQu@Y$~a{`n<@mN}64P2pc'
    '?=scLNb9rrArru+3d+oKS-+ASFE2@|#<!{Llx8mxK^<^UEjFgf16TJD@`lmn$|YZ+F~!Oa@4@XKcl*r?|6U<$>01s0cO)Gb@USoh'
    'm4863^E4Whp@|uaQNnobK2DYA-I*)#<**O`ugN3jjs0JvlYG9F6Q@K4){<!!@J!O%X@Z`~D}sA!Nx9qro&iwK`Q_QT0gl~t!**T)'
    'gk@WovtH}R7Aj!~#8g5m=a-tp!k@^b!|a3PGebDKax)8w^YnE?CUuAE&nFI?SJJ@L0!6in+c>~7;jK}7yV&zbWQjus{i?Vx|FV6E'
    'C;X=ta3!)$5P@1Z!vLa3)kK28IF3R<z{qH~bmC{4+c$T{?A|@L0uO~_r{_gT2=FyQ>Kb)}X)?gb8Co$OOq%WO8{5(b+P}WkGwJ*?'
    'vOu4zg*`XXEjRFTqEWY_qhZ{_r-NSz;oMB~FWA`=ch&<<54We)clj$zL}(8dP1l-K5A2-iNt+)?$wQ5y=A~^s^}fG-SEr<h81b${'
    'd-+oJ4wBahxX8O}2vm^+8D~B<zBt&npaP)&lfQjyYhqU<&*0nV!-qdl{B9?j{t%oLN@*ag>p{Kde!;Okr|a9trILN|&tKi4z>bDA'
    'IS}UAUZ9Q@nm~r+0E{63P~vjoh_vm0!8dlg3ajAjkv=C;0&FL=0EpwXK&BbWcr&y?B(;_Y*QDDwb=cl7?1(K=5Gvn_L)il?av4(e'
    '0ccx5+$sBM;xN#<3M9HbF!0s%->|nO)2V2?Pbr#N?KQ}+Gv6N7Fcnb(3+*WpVI!po`uqzH!K)D9@^&))V_2X-vZOXZLldyjAk76C'
    'xe*{uzmyx{%I&=F;mf+Kl72sn();V87hE-QGr>`YC;@fLgIa*vn(^wl__nL%qAaj(1YJSS=00@9Da%nL@dn2N*Y#~Dp#sF_o1f1)'
    '#9xMVBr@tct{g68s1TCk5X^%ELLjO`E1y9-ZGY=tDvntTqei4YC>bLtBfMQY?VfxXbpz;TK$qj_XOA~;<y=4feAo&Rpi#M$M>;3Y'
    '1F?4<f-^|}nSZO}g{h+g0DkM%R%{7S5Wt712ww|54=qv3Eb>3oIyh5kZAQW4&4p?*Zub%pop+Yn^xBG809hA~Wh^+;&B;xm8%k+A'
    'g<1L3+<-s~9hf*cIc1F-yES_#6|q!l6d~=@kCX=#1Ss-4ahYi=MWh%Mlp|8P`rlpIXrkZSpk}a{UOaT64$;X>4G-CZlnny4p$lQ='
    'k3LSWKlhYNs6}dN@I&HqDvIg-gC_FB5G@5rFP^VoqQ~$NgEQ^|wK!R(d-$?}s{c-+wb4H-^y^rb54eNrtNSc@@T(q03162TIxnVp'
    'H@b9rSy2uzV={Bh(9Y=#Oo>DYRV55sDsC_B3g1jez@wMdU0&vt@GSqi(CeK$-wS5(xgQa?L8>H)rfBQvQYrc;L^JV&A0_xJJqZ>6'
    ';`YZa$|(}%h3RrEaLCEdBg{L{V6GD6IE@MPih8BRqE)t;b`kBei%TwF3W+&?U!=1c)dDp1A^Zk7QVo38*Z{c=iNbvf{X8fJe00bD'
    'ZNU>U<nnjogzWWQ14|9SccjfYK!D<l?`Eoj{!|x-!tXoy-Q(svw{|S2G{BfMHFeL?1{?w7hx!FplO05BScYVV(Z~6t=JhFCiRt@R'
    'Z;|@$`KZ-v61_&^1ZX4zEIIH=i%qDyDD$}_J^c43()4ttMWcH@N;|Ven7^&a(|e~!rFP;q!i}0halNC<ME@ErfiOCbl1M_`8dKeh'
    'hc{LAGeyDMA72h^tvafqnfP?+X&~BxyaI%7*ue+`xS_Gq`QWbH!SnO><#AK9ks!7<-J~=wZQL#)H%6S=D>+lFhZYQl!SyRQQuPqv'
    '%M7&FJn`0wC^`ZLw2&jnKU_QbFrh+jkQ%OCJM12~Uv{Sy{!Du;fBQ&;g)*ULn>|OH8>Xds0lY3IAA%Hm%oACDT)UeEFy7oJ8t$c*'
    'BSbGK#+(JZ`GhsAd<;f|ozjqJJAx#G!BLe}Z(;cks@?^Z0;I`ZCZLIGh5{Z$UrK4U|G|uS4`5nt^}G20;~mhscq}Xl$#x>GfRWfB'
    'ujO|}1;CL|OFNyac!XU*>$R(0GN!{fx>uWBczM|VS@rCJRkbvIE1;8slm{9Qr8u3F*+MUe%LIXm?BvQV+&{l;zQT`uNQVNfNl!6S'
    'JoX0FHmvN?*p9>mNT*Y8t%YO9+epnX*axI&u6L;J1)dQt8lnQkF*u|{&T9Kbl}zFySmflWYr4+-nhh-gQ$;gcV0bUxMi+7$BAs8<'
    '5<MzpqzXx|Fo}274Oi}pi+c|<;;{Y3-@g9c#l(v$2x`h~$$>Cg$bd{E9a$8aaiZH5C5xto&|bNp69VCWJP^=SBc<(USM1M_Y6J0?'
    '?5N2@->W;{Lm^4ncv$7{BQ1N=rT*GuwR%6M^#qQ9cBIAC!gsJ}P)YF2A~iT6HIRIFAG(Tsyr0Ki_*Qke-J~84MfKR30j>`G9j-J9'
    '`K5`<Vl9yQ=TN)wxmxtwr&wZNQmINAMlcHoT{_<=Bv1%TaS(Q92(E}w!%%&mpSNLWzvS(oN1^@;_<1?5NwY&jM;<}%QDw2{0;H2d'
    'JwT4BLC8ABY2EsNQKqV|70Prcx+%>gSYzr_Q!iVbTr6B7dZVM*eE?<aHnNx1%D#RR$e1XFXe){x07U0J;Hu1Ski;O8F%tq*fS1}$'
    '@ZTz;#)>=MDy522Ap?TV9tshcD(NTRC$fs1;1UE!NqXfDPWevt^N^y0DpxQUB4CPm`rr^p$cgd!K@8VfNG+4CzU#m5_}k55X{2hk'
    '5S>V?8oGBK5x|SW)+ps?QNj{*QWQ916_(fbl?%=sem*+rS_9fX2qa)@z@fcGmgPeN3+2K<aZ_3l!OV~UNLA7+dhVbMI`CXqyy!ej'
    '<J5vV4BYT!dIt2G{zGZWMT+)Xmlt%xvlJ9FJz|sS_uD4Hn8Fi4W=<0gT>cVZD3t<Eolct06S$KBaEDvbs$)&{jR=UWC4j&8C+&8y'
    'wTmskba!qC>pyNz{|1@CLq*$Fpedhjq+-VgV}$qusiUJ@=i$Rm;$v$ee8lFO?QEaa_=R)fUov)Go97q*%7wYSCqh1#FCZ@H1n^w|'
    '?1^;lrU_>&R2_oxJly=7_9S&1da3llwNzrRVOk<B!T`JgbO$UIpmXCBg!&$srt8ICb01kEt=P}I_6_MlPRH%z<!g#N5C%K?5z1cF'
    '!Md%G0CGC$_;P@xF(dzt?wVaa@O0?*rc!9;Ei`J<2Sa^_kq-~bz!IVep%o{=9e@RRh`DADk4rm{mPBa}EjSkF3kVMY6X_#(9v3#>'
    'Oh0Qs#A0Z_K3=m2+551EeXMvEiJPgD;tAI?z7*hg*fDTUutY%05V0sjl?XTZntjk3RW<(nLJz*`<DllAsf1A)aI~Qq!fYhv$Jv7&'
    '(Jq>@ZmnUy>f>0zn$79nI-Tsx@2BBz9;gS&USV%}fn-3raF(D1zyJ*TYSMM52W)<~2LL$l=AVxb1yUW!4Du2Ph}<U_0#WZ+{J*Hu'
    'AT1H{xlJkB<1g5X{_HYlfW^u%(yvYnrwl(L9t$xBVl2$@G0nocr#M`{7qK!Aj*q2)-U!76{Wj91APNE7;!OeHlFyLQO!%5WFG=Z|'
    'jU3$LGn%x6_`#>veu=ox-+(7lVc~HwhvZwb{Y=F}3(fbC0%271(WI+l|53{HSWy93)f~V^BRz3E=irMQ`Vbi4QEtHq9I?W&V1WLb'
    'O`JZD@IWDUc@OZ%Bom2XM|>s-;3VK5L4JXJXqE%6!@C>nk4^aMj;}HrcPyS2@q|IL#ZjiaOsWm80?^IP0vVO_i*%Wy-Peb+H<QP+'
    'brcZp*8)NSApw9Z(eD}ITd8e8yAt*Sk``>5cpQRMrurauBEg<+mz|edl4h!iYVNs^BtiXzwoUp;%e@a1of<qZNR8A$C8ko7cPQYi'
    'H=-CGeuRf~&f7xZgeZSIeqG!E9#Xk3lMWe5!q5=9xa{aB0)j#o(Cq_>gI*xWfN{TQPZh>qkVf#)LxeA9L&7Z5{{ZY|^`|oxG=L8b'
    '!|9i7C~k4xI~Ex4EfV%XFO5d8m(AB8qE*2DHNhU@(}H!CRmT029qrRUUrI3_GP6D%A{>5Rm^><}#1V)CW!1i&klZ4SvE!{9df44>'
    'pQ^Byfi@XeVA2JR)g@mxXtgE#7h4v4N^VFi&daSk0{u8hqwy3{)yD+7Aq02nBhoG9jm>7DP@#wDBT0k=%-l*hKPeiHZ>s6io_IgJ'
    '9cmI<P9uSkE)yLe5ic8Mc<_5ODMgC6?&*+@+*J2qyHD=<@O4+%6{1}WR}f^Ee&--Z6}`nsu4%=vh$4tX(f(z-dU<}>xyw*<779-R'
    'kCiBFUVK0(MIh#6h|hGQh15f6vO|08o{qb3>FG?Hy_{@;;ffU-s8?K1HjeO+XapSx`P1AXcyF~mfAxl9+zXB0r=)-5smKxJ+M;Yk'
    '{Q~6$G!NeCBs)9ILf|w`7K>dd<X4AE{(%}5o3F>?b5&p>B+@r+7hVNk4Fm%V>k~o(_X`|LT&M=TTg`Cmh7MuBeXhCs>1z1_yHJpb'
    'p867vD#;%pEMB3M-?)QFMM}we!-mQ<Q+gyu4g^$`vF&6xO@(c+M?j*5ZzPusBC6hBec<En(GjPY>*Fu4@5}Mp@SQr8F|crz6D=4y'
    '!b-R|&|gWIu$hpt(~Vnt*h*?!f!0x`Og5ov#uPiFkO9StAj24`O)aV7BsC8a$^MG{P}QVu$p}aeb`h`lzy(1jg0v0xl@1yvG7!vK'
    'H3Vs$HaBiaawh!csv<PvK9~{^d>YO)m@VZN@Fsj8i1Knzi)7Vc72UO4Ix&vk&e%J}+2vQ)%cacH2gHQHkw&8l9o4s|$iaKVBlDs<'
    'ZGP3Z^jD~i6_%`|B)m2`S>fRXGa1%m7(oK@1)F%gAd@J$yXhD0E0^tU<P@Di9Epz75?Q#)GP@`9hKNI~1dSZg(%iTq-KrH<))=!W'
    '9A#Lq^7-e~(T<qai=#}1o&zaK?ICmHZcZ%6J%{cH1G1>BfaMC|kW|B>WJM={^va0WO|^)_oUD^@xPWPT<F3y4$IDaY!=hsgE=zvP'
    '-R>x1d(=%6JQ3kMK=3g1ffKMPy>?soyW>urauV+I-U`_^M0N>YQ;YiAiscBQ5(0&%0HC!vLX?9sdUf;`vLHULV9U#A%;UX5#!qOb'
    '(JE>sja4o;jv7T1U^4AZ8sGWajXdn)VrO+SkGhQbSUHiS)q_GZFB$+Y4QO@LM6|uZcCo)v<i24qDu&K4=^VbRt`cAeBTSp(6{;q4'
    'JUStAEsY3XmHf#@iX^I&+cvg{sN-_d!mikgP=ZE!2w?(0+ZhUQ5V0J_9il>tIJH6-aOm1Soneu`9#eTsgPEyd&FCbF10}(5A&a_8'
    'UzSgq7^#oiTwj2&Dt3G4_g4vySW;M-jtI7+If1i1PR*mJw#e^cra|=;+5GCX<Y}kIk<dK!?>w;*<JWMX!TS&5DyBuKAWlJ&VPOES'
    'F_JUkg>!ZNv0HM;Q#k}@_N5RNQPg0>0Fl(lm`p=Aph$s0sPULIr6B-5rmJsQphbPw)cl0(I-~~3%E>BO`fnlu?l?64^#>^S0v=G7'
    'k8Di&mK~j~AvVXaa^1VU9n63m^(k1EWKk|@Gwaj!gK4Us7wi}mjaR2e=aP&%i0BC6uuM9THkY#w`yR|{CgDcGz^8-UyQO>3l1+{@'
    'HLkwLmYX!z-5o7AJ8c2X+HlM#e<fE0q^2cLHydj$I$xNbAbYufFUuW|w4?U4BTBU7_`DmcLL0z7@E=F?L1m5BlMV*?2lGCL8+Y{m'
    'vBKa(-XWka41Q`;3r;<eL&MY_Jhsvrw-QOLUAQ_A`aUUf{Vp`El-@J)3J`4;WZh}(1xrt|hvd#ub&bC?Wzy_!*h%_Re0epjt8GVF'
    'd}gu`1`i(IP=s8f>X4y3+^qbo2o(ZmceiY6yF8s#`<P~fd^^Y$8Db687J1;oxWXdN${+>|M20NgeA|w874;b7ew3AoxyvMy2!Ga4'
    'NO!0RWK;y-ToG}+9`e*qj=~sr`vT?ADp~L3>M%my#yb<)Bk`GeX{l{h8D>cUZ`j9~3>Zp!Luhs|i}5J~!^biR3*SKV2m81#$`pko'
    'kCN7>Tek9cPZ0qNc}}2W#+VX>1C$pT%g|t&gKs5)kgtTQp4*%w{wp?9?hXQgNiBq4ol`vufuUWAY8ChgkO6&P!V@I<8#W_(VL>}Z'
    'D3km}?t0kz^_|T2f+oR{D#MN;0dsf|_;AZEj&keVh{RRIq9}*e5~W#9Iz>Xte&`w#?m+BBlms%P;<+XEzU2@JP6!(Rg4q-P8d&Wy'
    'RtqlrOv8|8!ds)MVl9~t0h&L`SEpHj<(`|Ru~`uE<ARMI5$GLq8Q3W=N^_rRTTpWHB?J1%o&K6jk_RKr1X#+6V_Oiv(R#yu&}t~6'
    'mlqpMWAG=gNX{}m9S~<Stoq#Q`2j1QSA&D)KNox3WRgzi6p_3M=#ti8FK;wYMKzPyHEM`qVO&pnfKPgo!2aBycm+|a4O-xM(@27O'
    '2b#jnMu<BkTQgJy%x7T;!p6e_b_HDV$-b5np?X)y;DcTk*1)(&A|<A?i<Jk~u&s>jXgJS2z|mg4t8??Dc0Z)TK$ITY0-XV!bDD23'
    '6X570tmKlSnZckhW3JxMdlqHwrbzl=0~l3LP?YH!$YW5_bRBxSVW9Td*{n#nKHQZ4S^b`t);Amg<lWH6NlXC_!MqxUMkMM)>PFP^'
    '=Gr}ly*qrx7V>F#bY=ZFuoB#vSsDr~JHSsNk<0!y!VaTefPhQE*RJ5l{mX97m__|?Al{e;l`{X0>3<3XWT7o0alBXXG6&JL6kAuv'
    'fS+Nf%1y~uD8imVPzUc{lhUxnZ<wV7ts5&*GG!#mF2>t7rE0j^t`DD;E}u*TNseU<&X_(deHx17Q8>7CL)~!gj^2=z>J4G++WLU-'
    'v`@NMHO8r7KpMFq5=5AU{ByG8tKXX*jyurpUJ)OucU!VUYT;gf1`KE={i0t=p4wy3Pp!_qGGDu+bNNX=^>VLa0R<=?lnE|7v#;b{'
    'f&~ra<g8J=of=;Q)fN&fgp$L}+c~v!cJ<dAy*IgT@-cxsWnFX3nv`~uY6qwg%r3!2@#)5$Exm!-J!#fpFNGJqIfM>mWVBYGEKrSF'
    '0petm)A-@Io>hA~e0@18VXVJTfKCZWMs}@GyE<H!X!daPLL5Q`MX`bAgW|P%U+0Z1pZ4K3VuqK+NcsqGffR0gIXU6>O291CK@2iu'
    'ZCpd4n;^WU?+o~2v%KTx`Ia5+{O=@9RH=kbxW!MgV1yw<C3LRn(J<$S`zF6JLOFO?lm-^@F?Y+Fgz1Al{q#r0)RKv!ys1eh_Ba_~'
    'kO9(y(-M41jA|CQU!Ecq*7_YKY`@c;TJhwP|C(Q3Mx&^Jpink|3exeAk7R`ekg*By+w1zny5mF3mCrVF?suP`%=z!m_59_nNI#dk'
    '%a}*S)HzW|83AfBWg!89fkXcpYV8WT^Cw#=rv6+IAS^JerSqXq4qi=Ei1}iHxAIwov2W|o)zNt%$}_=u`OhNv9tzA>jgP=<k*6`p'
    '84nsBh*%aO0D~|%K(v)LP3e|hl%50;g*gOro8!|&T$eO1t<|6s3?eamg_?*@PE(&opFYi}tqw4HI?%TV_hTVl7c^$#5o-W9hH||q'
    'y;RHtxD(_AN@#%hp4xo{8S1nTq<n6Fwz@m1NJ{lFaxVy&iXs3SS&lGZ+7O^<?!%vh?%gm&DzDoH*4&%DQx>?n*I!G0beZ0wsEJCI'
    'F>6970dXxi!fP2CK!1iY)nq@@`d#qf9}8A&@)j927XZ#Kzy-_@FPLK1RRez(*)N?2Hw^0*KfMBd2379?Rs}dCCUlS%u{Ob*ly(#>'
    'aCnS3s7ss65JI~`A9t2nNk4P0>B?FjNU;cwF~f%a>Y0`a)0?(<AaSA2<xgS1Lm=$^x=oy6&({y3;6O*AorL_#=$X+WS+qO~ZhU1#'
    'w*r)gJ7A`j-y?k|oSy2Wfkx9&BCR+mcX(z|$3md))a1o`hIcfgMrUAHTDJoTC2pBGS<eqZYz!HY(9DUHp(4F^?sh~f#7Pa9z}Wvo'
    ')47Y=SR^TBDTp`HAK+qvP-oCJ0Rfqsn&1rv(lO!#@5`9`m9OC(qTfA&DhoBdEE;J;Cr#E>cw|J|A}j;*fU+rmG+ZRV@{Q2b@`OsA'
    '(8BU)z@hSE{iO;EkPe`OnO}5hgD5rJrkGyf*0pZ=mo1sz@mTm6(X#RD@Ql}e2@FQR$e;(sxdIA{NWDRTT^CocefVQr>P~Ayu1KJi'
    '1yaUh4<W{`rZQ3KVKxHvZKQ>+UR&<;CtA~^tV=YvAo&{4DT~Qc3-eXzItdH_x1~Gd#CZf5!gAYahC<)oxRatbh)HUg08A|mTzQb='
    'q^pUrP=**AwRmr#B+J&X--cE{bG<656%6^AQAnX~)P!ds8=UXBFJzP;3$RZ3GRV`4mm^8gop{_oeo7_q$xB491!6Ap;qd$8d`#Mu'
    '{)dbvYLXaKT>>em2A&g2-N9bJtKWCqMOU$CJU02k-4|?`)q18yF7{BAQb2A=y66omVRA3o!7v1?y?#e0T_|i1%G~?XlpHMevIZ;T'
    '@<+%5S;A8+O93O&H(fQ&WMJ(3eEoJ{E$&bdpWhy{7xErzLjlU6qbHZVu9MCLA2GUnTz1T1n=~#%D%Kuvl2XBx1h6lonjGz`KMP}`'
    '@UG|-Ks)3?BOWWf5y%{TGthHDlN!xfZA-9d`ja|w>BU!B5K5UXoN?(mV|j?jGy%35-I8syECCkuqpMz(V^PQ^IEB#%qX|e+3dT+r'
    '_(r@a?ov)EB{RPLrBeOeV)_@OF5Ei5l?-jNsIf{Va6SYjfQs4TD-ju@iLd~61~aUoJ(<e&PiS+&AW+j)X>0+)%>W~Ex2K-L8!D<('
    '!DB~am6}|+;#nc^s-~^!wJ{BWjDSlDoe5@vXwAAo*(16$b!|es^qY#g^y?0Gdt@7+e#NO{qXr95P-|YYW^baNg!|qvLIqre7)Qkj'
    '++xP|w(K9Lba6+TRI)3_gN}|SqbHaYK<5=FIxn`pm;-bc6A2q5Z(+VxE{!7tC+V+8FQ(@1@=M40U=k5Z<GzEW5S>i$P>O(c!ZZP$'
    'qNtARHn0eJ3d63TI>C*=r^RU?h=5cp*SRQ<LIXR1q3CT>`^cAx%LO7TI!4Md4YmRXBuL@Asi9-^QP@I{D1@o6MNz|cC&W~N`p@UE'
    'IlerVyw#+-;m!iBg;<V^D``k48fmtJZMjBFp$-Z~*{jxFkTpHs@;Es%{C<&0NEwkel7f5`v?@rd4qXWITTL%&YF7R66c8OmLRY0d'
    'jrepB00ZnODzZrvwONnWl@2py(TMGKOLAPX_}NeOWKXaun~!q?aU;;@ahh1&3K@gq%Mqf3XEHQES}_u8)GQ6Cn}4kP<*d>RJ#CnH'
    '#N`1zl}YmOJ!ftg>d)o%54LD8@_TyvhQ0Y0ST*1<TpI<SJZ5Gv!a{SPpdTd-q7BOM@gacV5}BdNK`u&~UKc&h3D?L-FHTzC-WSUL'
    'UQ=~|1EH3K`5^Kj2O#}Ws;$t8oB_*?P`Uc6efjH*X;Pv4RCwxm?=P;7s9l#wj4l{74BzZt?v9{z#81?MbLAEmBIov^u`PfszV;C8'
    'Asssrx`<?`GpH)y-zC1hM#V`{e)ziLxz$<qvT<gl(St}$qoKk0c-~2{2GkgAhp^nk+Vn&B=g(JO`Nj>}2Qp3oE`$Yn8H)<5mz%=%'
    '%2b97FA(RJY0VZYo;k`2Tn+e;(~@IyWuSAS01$f>iz>?u?;yXw!m^Ky6LZz(X;g~5TCPQlKLP&%C&Ly!6&VqoE?ITbL(MczON;K}'
    'i)=++o<CInzW<psF@qG3ObhEcdS}c4&f;Pz8H6wm$5OMVixu-}#lvC|eW<ESG1jCR)e0}8(ZE;)1CM9qJ;SAeT*OFe^<+n1yYRD='
    'yo_ilD4l5<h$%3uuQAAV2$Ce303Wg@Y9KB`=;KV0W%0J`(g`mLzVWXCwWntQd5LI=LQQBL$p{t9=mbq5|4v0t_}i)r*`>-a275R-'
    '`eTxY2}MjE<-`no6@n!84zv-lVZ}SFuUuJW#kS0?9^{X}AI)$Ip{%rIdP;{d`IRpwM;O;%W9HgL7aq;4*amf*<Uqw|PWDBuMrMZv'
    '7@SMyaKN5Jv5lIOqI$%&ff~{jiFB`<IMZjS9ZL#ZE8ve?66_TL3t~+==d|w!_3{~Xte;OY*{@r7!DA_wp9|{ViIxl;FKibl#co*x'
    '@qu9$J4y^CmlzVXSh@DAs*sfI^0Hinj2zPBQhJvBdht%ARYBs&I6ib424Ps7DwoX<KMIan%sm9t24g26gYJ>z3|K1D{wL}6s8A8-'
    'f)!LQw~dPhllyitP-Xyi+V~op-3X7M$1<rzod9-u+D>+}q=2=b)2ZR|lwK$oFK6`N>7Zf2n6!VXnDP6QUoz@##$>~tp`;+io?Y$2'
    'zrQ?Q{)T$l8fx}6Ds>|*0)CSSdI#mTGGN4uO!HfY%Joh|$To*Z5QvKpm@bZ!^iz7r4nwDbdBC&8O{ByIC{A&M6d>2G`%1qpzgh#y'
    'PCx)gmIO;aB9t*;EmSZ>NYU1@YG=kpSiN#(q~gfZIe~SM_|cXWLq????QcdJ!L&urjjAyh{jlHG-|fB?`j|_zmJ1#$`dRuLk7ycS'
    '4Qy&*hKcjbXb)Q(B{Xlnporqo$RQa)HWwdaHGKBC0f57a6r`|J=kTs=?RqZ{$L%tw^m19q=p}j3ik2q<FR<FI7QW_h0>)$9OuMG7'
    '{+?b3e`d$>b;?fwZ9-F$FSH<Kje>$nz$_J9_VDHcgP>{#_Nm;#JBQ?|<r!y0dV?1agkRiL<wq+74=|70FA0UAC&na(%H_|#$T+J%'
    '9KROO0Es>Dq{UGYoeW(`tdgitiO=-maNX}AvLjWgT=)=xmkOW~m_2uGgoGL7g^K5;73@HH00WB(Rbg}N)-1>~E*@NX2kLOaUc^wJ'
    'vqP(m;Z087{)8<gb>M7VhjaD1Vp4(SRRGk$hEnTN4g*DxLLlTcOa#NB0vQx)Y?k&zZIpg<FM4N0b@`{Gh6ux`Ssol^zGQ^@pyNQN'
    'eB*rTIAh2Ow)PG_VYYzeKj1ljD`fBlL;T9b%>sJRyee`^=9OoH4BHWJ690$VT>9LPS@Nq?kiA+N3X*#aa{QxVMeQv+*M*>oh>$2s'
    '!I)}GmQ$1a@^9stVh@^e9bzI9HK%ZD#&D7X@NkuH008wvT(#l`&dkO85Cj%qMI6jEotKdnTox=3Q?^y*kD1;;;|_V*x>ZjZ&-SpZ'
    '(DO1R2=zBVv6Xac6r)Fdftd=5%S4$8SF`J?e>c`;r}ZyqKDgge0^(AJ^pgX%oT^2@fxeH%EuT2kGed0{d3j!-#Fu9gS_&Njh}k?='
    '?1|;XN0QTXvZ)p5f2c<SlA0A;YHx~@hh|;Lz$s;}R|k!3$u1*gXpA<Z=qz$8>KJ^7ljU4nuAB@bWhA<H74F(hM-q#e?^v@07NR(J'
    '^Pt%z5@DEymKjT#0jj{KKli6M{AI&mu{PfnNHepzd$gO;D-I)Q17@z+c#Rs#qH>8E2KAs>v+(Prs`JQ^%b!{=t8RShxT)Zu^K(H0'
    '<aJ;*$iiwoIB~pfSFL|`>aVk|mq`{+UgA5LWOO)3X7q^qYBXJxyey#4Hbu9-pLTFYBp&2tzQ_6nw4mV8iSNyXxQvDf)_3rvAyVm+'
    'FdE$hQy9d}4@GXmPkX3Zn8!?e-wSL*TSLzYsul-ZEmnF&I0nh)xC?gm!uq!h)DVm{z%$8MU@=l6V?qj~OM41w1QtLd7%~^9bcdYg'
    '$5ef4vd&@JZw4skDDlN1BtnKty_05nZV#}ZMO`nf_`H2ah*C<#D4m44cukG88c?v5{|v_<FY!<n)kZGc9DOvl^8E!R-UzA$nx@uu'
    'o!A*sCXaN?sfNk00Wg84i%o!&g~Ia5F8%pa+vhT#MlEL5h^ODM5CfQ058F|QJU;WFNpxdKaEqeV1D)bW_cj;t?v<4A=Dt@wyAX-B'
    'lT(2vY*|g01&qMZrDZUqCIR#jRf#W?QfoF;Gusd$F-EEA*eI$I^^BUGK>0;>3apDwh^7QUTWN3FPTdqq&&(!9Bclm}%Ap=Rz!wra'
    'BXvl}rWESCqTKoNPL?T*&u&{73uqz(zv#EC9&B|WNztKFCq`#7rbdh~C|E`Nmh)DCxmAMJ*w-@ukMRSTF=G|WtVLovx}rvfzL&%a'
    '_Aud~ccE_KqY6+o@63kKQz%vlbYH#fdY!cQbcQEs?@`JzAcaqJmck&8)oU+G*wYQ0_WNZb1U<WwlPGS~@OC`B7F<rmv5<Hfk28u<'
    '9ys_fxeub$6`NSeB$~l`aRJcS$7N1E?)8cu6cD|TU}$G}XO_nvyx+m^FG_G~etw&nU1}vHl>rq51ZZ}A_X6OfWQl5AW9q+V@fBYm'
    'z1Uggo`s63N}`b(nIkC6J0MG%cEVAo6|1lN1W|($gvj5~^x)mtVUq|L#6zL3(A4Pww#USt(q#)BJa693ZLgmX1UVkmw38kib{B74'
    'gK}v7G)To~=_%;fgT{rm8#rfrHPfNwzya4pSuLuWZaMm1xIEcC)Cd$cN#>3A$}QB7h2j8=a*Lssr4PY94YdrAl_bb(n1NlUfta=1'
    's2_=%C4MK~@V^la%KK;1oO*yxB9Y3yjylK{heLg`gIBW5<*I|xSFjTxzLEQ(U}7Sy;3`;Vh!t>^>C}jIMbPALTc~S7Le$4`r1c3h'
    'B~wVb0Ks2Df>{_Km=2+M!ltO`{@2xiW*RO&B!vt(D`66*jm`~Y39JAx7aG*Zk(>q?jXTkXo3>Fwc!ZK<I2Q~f1D0h=7?z^#;sp#M'
    'P7P=jg_=(0rhQaTNM*_iMbIn=2`2)KmRk9g&&p)!rQy~^d76u+u7BT*2BmK5CU5C-z%Gr^#Ym_o5Ne_}u@c8iI;fT+Mb=o{*{k;e'
    'zve03mo<>UraXU%%3ArqFhhi)W;g@GNyVoD$#^$`&lI@`A8z0vOS#g0K{H$_65>bt5wmQG#WG3qYQ;g40V|mAjZIt|B3_4FRt@uG'
    'nQ74~H1f<%3kzf!odocOtYnY~Gpzn9U$;;_G!{ZxhVyPEX`y@@`{f!3G>|j1rrFYd)!3UW_whELwaRE5N-h(La;s_9txR#e(n)d('
    'xHvR>p`K|LXY1B(=G0mzy$Dc)HX0gLxJx1TVQ`K=9W68b=`lWxBEyqqYpSwyFj+~guHA=bEIch478g}<3Meh_Q6mPUY2-I%0nUcS'
    'U{on?9+xI~D7I-o*~=-zW=BsILO7^VnW~1uLPqqw8Y(ZS4+sO{AHs&<OQJL%&2?L;A#!6R7&MCz+j%VMxaO!rgM7qcpfEN!YREO{'
    '-rCRwP>#V?sUZP>3JN#P2*}JN^we_-m2^P3=xAcY_@Vad!`i6vvvy!pg}-?8>k!3&?I8Q28=*;o)if%+Ugs5tHvwG0#mcSJ`Brf|'
    'FsubxD8x`&B?!1@<+gI)MMTfpi9_G5&9(Ex_Wmp1!pr$WeT1M{&=nx1=PT^h-DCm*P#yv_gG6%_F`B^*^cBS0U7Kay3v+vtBdL<#'
    'P2O`{w?$C}L6U|q{a(=R5pOTB7@}B98b}mtRgXmex^^o>arg!9>E)TvWT^#ryIdHj2Aoe*hcpWg5FAc8(;N&;q99!~a6D*Nb|J2P'
    'D2$4I`sgb8shtGlu9pKU;2@8l!h_Zl-fmcr12@yH6-~SiYb%g<J%;6ltnp-SG}KK>dQBF=50!=*f*V-0JxY37Tf}v&F8$gg3y*sp'
    'fg5rq2~T4vd^EeGgEyxsX59J62Ybz_4`QYC*YBgq-C|4z|A%Socqst}x8j~=*{Lu{j9Nt0MA%!a?-6Zbm2jbx-7)|;KFdb)1h9tX'
    '>4=$$fYvA4A`rW%j;`3p3LyiFfXHC_C0xuxDTjB=sGx?(IVqOd#e}B`SL~uvQa}rcwk~-vVm~?o%)I4)QKrr+S<(J8BnS(R)m7R_'
    'X}38m?@A>aRHPXVJvAz*9pN-G^GXzC*xqysP$rr_!6RI|hjm<N3Sq2Ih!&hoZdMp*C>|Rps_vl4KrpfSI95LhqQhe9bM91@haF-}'
    '2LZZ|@<}EWMr<K4n_`+73CeDqEZSBdkTnC}gE~SG4rOUXaG>b`oQz-)0yTxQ2LIaLtxkW>JK&5egjUU-reBLj40br3LTDaDb4;`t'
    'sDWTjZex+E4JAT*-A0~wOGxKt+lFri^9KM7*sc0XrC#F=P@sZzL$0D|(&+arF3NP>Mi#n2&5LPBDzRTkWa1bZX#|@`8Zhb06g4J+'
    'x@-91+Gz2l^@S~pI01_vTjD}fim!u-#?Tia4{~?00s7h4fG{<}NIomJonL)a&h5>0ePu*Y@H8k^1L&$csbaiCer8{TCWJyfBqK7z'
    'b$eOcVaBfz$k~YV*Wd<#@{KkKYOy3|3eNN(d+m1g*X`y+X{p)>)GW9`Txw9V!8Ggw0x#puM%h`@n=+!MuYN^~_Vb*dS86~(7bp}p'
    'Bvez5A$<Cw7bOt_x8vr;3X7*R__e9v^ET|>c2W+jvTP&`V;%8a(Uc)`<^dVeZ#yXluvBHdn!9Efr}uK7b~xFTIGW58hJJ$22=gzn'
    'FM?1dK^MFi(Y(n&BxozodiZb~=Wv3Fh9)X(pGueu<88QGX-JU@1&J28Z}@PTz=IkHmIj&%+IZ%wNAh}>S8!D5RbZWgoFO-w7e+j#'
    'c(O)TLnfydDtH5SzB+GTw)2k5S`CpxJ)@YUs3r%ZX+|3_a33<`fy);OB>M|;|G8>Aug2n(*!NZHB??^p+K?Os%-}OBDHI-1LCMvD'
    'T@W!rSeGaJHJdpTZEK&4(O?qS;A4j%fp#X>F%VFcE|DUbk4EmgO<sE`|8@U}xnGCV;pj&_%U<N-2NZ)AM1vZUK+CxTiW@*K1gEum'
    'BX7s21<O{Q$8_dmF`=smKnOAlmN>Za1kAzEAHj%*dyItx>?@|*Om_W7B9@+S4}({Azg-0XMG_7trq|GbNm_7djJ!2?tH?+JCFl(X'
    '3Bkr;?S}X-$4_%j7YyKmL=qyr`jBvEv@vF~@;D&w1`V~umxg$=b|dxtT}`HT^nJyEC(L1-3k?m;-QrjT@3AMrMij6%%7N3J&E5k;'
    ')g9*ig<U9&z;qO#j@|<O10apuE-c(qRFMk)NVr$-;sV3=r!te9X4Wm+3(%+8F{;LxY0Y<XoJN}`Q<c2-ps2p(cxWJGX+Q$f?by?M'
    'N6{k>Pz|iWc3#uhaK0oZVU#xnxoIr|awfZO&I(kS@DxfLxYK-#lWeL$D6M#aa8``wV}k+UWvo{5+BkX^)4%SfNYJ5&V4#onR<u9y'
    'F}PFkEg(a2h@5E@0&Ih)ck8!-k*#Fb<cFs^>vGsaUj}(jBOPI&$|4;G&7e8*oLSgQ;By?>VeR2O(Se^+AvAcVq0{Y?H&w%!E8-@U'
    'TwIt)jAZ@|3s`;GXs=qmj*L7BFlA6{OWq+vL!2u{VgWsK&`G+W>~A84U;7>w_pp;wNDY)Na!%$$#DE9;7e>dCvCrBRwO*^?o3Ow|'
    '+bHc~T}1M7;$@&g;te~EH%6R`n9;(Sp*n!XMrjLQrL^jsg~i(?bsqCmm^|b}dPiH2dy}K9L@$e$w1J-@WfmIvpu5{wuU=u+#^Ht$'
    '1d(%O-Z9XgUOY+`o<7{{0XK`D5<eB$Ie&R})JH$YTMkei8XWCOl17dfnSW2C8)7N8Fs*3OV=B7sp2N&%_wG*?4h-4@wu$g>7{AhT'
    '!=l3q8q`ix896Beak|gLRJUSvV8e|NLu#60^kJ|Z;<AAaga}I}9$fZ8PGW@J;tyTUa9s}A!K!9b%4990XlMAw$a0op7<|8w&zR9B'
    'FSWU9Ma8T-LO(ilcxBuo9xR<~lcaB8C45>nsR=eiOZ%lSYJ%S_TN5dm!;)mXIB1>@^$AwJ%qrDq4FZJn97YYON73=|-Kubs)rY<e'
    'J0VhGZY-zL$k~zEX?#w|kBAYC#<SpX#0Z^Y&H8TD${PY{h_P7vIN4QE|G>`gfrAma<95!Z0niL4ofL85zb#xbN(rtmE-x6mhDifY'
    '2iQYUG8{-jPoX^V1}MM)5I$S_REyuePuTB{rLphi#biO6l!;#i$Wg1&*x*<}*8q0d#Oa={@~1Z<HD%uIAJsENo#7sS{6|3s1Wdp<'
    'cM7?N$WOOY^W_;h4b{OYXe<V7!{?5&@7FuCCWU~My!0{el-L71{RuD|>pP+Xxi4u5Nir6{s<$)dXe*XI<Nf8e)sbX8V$#t;&PV%2'
    '?)g0<k}(R)39Ol2@L{c8`xV@-*aA2QJaK4vR6+E;<W$N)OPLm+i%!x<Bn^!I^sA=oIcg7gl!uw=u>bh|uzR}ji@`tP<H9u3j1Y8n'
    '8di__N)qi1;0rllh9~-Ij>9UyL&~^Y+MJ+lAAiR0@17=0)C9YVxl%w%cDWN6fWh22C{~EhIzgnLbMiHg^E~AGaHkoV|2Y16yfo^k'
    'ok7fK@kX8?VgyQV(&<5-g4lE+?;&!upDW4;fp@Pz@?$~9`yWTwf&J5mpmoaxNvbERYA_k<YnbMEH3f-^KA%;k)x@XP-`y=(d!Z|Z'
    'WE+wPuFup9bSfD|2yKtbfi__e*By)jv-VHxrUQA^9efV;7S4q$f3i9M$>z;F;BxxXYmP9K7F;N?^k7OF90x`rlDmlO00aXchky3j'
    'Cf<JUUVYhpIS_(uQ4vf4=SDgkk`*Y$=;tl7C8*h*JfWC#_t6)mmg^VqzVV&D{l`Mkm9aZBT&V!4h8$W*l=CBuCd?=Tk>5xUJKKu2'
    'PBSi#|9khp(!&xD{--;BEnu*GEAaD4xG98$#d@8}=$5&30?2vW<HrT*X?2<;;p^R*oq;BB_gq#%;sgj!1YxU!LJJ`wXb2Uy&BS|#'
    'VxR{^fchc%^P@G-e=U^%%(KJxkT{pcdT?suQF+5xhxQr=%01H6#uk=5W%*wg23=tYHp5Hd%yGfBvKvBU=tx?iilJ4K&4^g((}#qM'
    '57vt$!IwYSZaE!Pidd#WPosU0H6K!H<d#e^#Xi3g_2WZI+6U|1zc9|Qz)<XFr>-b?BiAJl50^<;XLSFNSl~55Y=ApE*R6+7*|9YH'
    'bI`;hBxw8~CXB;b=J{$`hF+)la*)+r*6`_(4BNYt-@xI^*KNjQ9Ng|SKJ9r|hz1z4p$x^|5cgKZ!gQr&%SK27lLu3TsZ3A;t*BU9'
    'Yn3?>Oqgdh8~)j{>BKPuqeDO$6tXn0Iwu7ao~8YV`l-JyxL<(el0P+eKKP*w@H$cS;c1L078)*^R6JTK++f8vNL!jzvEs{fk(p0v'
    '*g-%C^qfU?p)E&Tw`%RP3AzlpgHcIM?z7cmlFv2t<{u=uoc@DMvx;ZZ%7hCU1gQ_BNdZ;{1S;GsP`!I8z7gW`X3eTqnO?9h)J$IH'
    '=yW7dZn7k|1|@hWHw%qOg4e-7x85{q)w0D4EJ#gH-wIN75_bh311Aj(ihhY<#EjGM46|m@Q!Re^HbHG9*k7i)%xK`i!eOCe1W7~x'
    'OR55Il|E<l*|PA4?v~?m_s<t#j=Vk1Nv?Rgr1Q`)G0g_(l_iM`O5tmucA;XFTva-U@cC2zY~>o72*L%-WrzsGS)A|ShTy+K8YsIG'
    'DPC|t#zd-J{j0y00u%knLHvD~uLL6L%}7)L^{L|;rA9L0p<tWVE?hG{765-@HZ?vsRHShD;LRcHmf(k>pdAz;&i4>L|ILTPOS*#q'
    'L-w+`C_W!uNv_aCc;*Y@P9<Z4q}58u&!^1;Co$_WBWq+qJXft*zT;>YK&Q5D#2<lQ<um|CC<iqwS1XWC%LPO(T(w-y6$j)>QqLe2'
    'hMs3!ZHZT$CG-#UO+W%XdH#sG&s4eKv6Oj2?c+6KwT~J{=K72z<ym5Urc=z*q>m^tcKB?)GsbYru`6;S_Rg)s1;ZVl<pz$&2p|V#'
    'KJlL}F8mNG4O_L`GuJo8U}44qT!#n<*=Wuf6LV!W(eU?-Z^DmT;n&E&cB)$OBa!}3ah`E26Tbi&HdFcl@gd?H!GKm=N<5-rH-ahq'
    's>Mzdc?u*bq*AkHCgZ(KVhhyh!SJbVVNReaLx>AUZTR#woa6fIUu(wei8PJILRji7&McQW9SR%}Kv^lug!i%+H+{Y&`OjAI^ltfF'
    '4zC^_1;-XMskP0Uqb<Q_!b9YT^FQz-qHW~g!lyf~UbQ@xf_9M8WN1eHFlk4OdMjH^$n^;MI-L#tR1t2iUz(<V+~vz0b`+zU`z(Vi'
    'I)s|PhLt@93ud`kj4=WUtXZn+`qhyM{&5iH@cE^{0VS9dX(9Gu@ocf3id2QXURWR`Xf%WnfiO9|e&vevY``p4I6c)Moe^3ES+%DW'
    '1vp(R2D63m`Hk|ynymBBhk|6Ax&k^2h>DY?H9!$2ETkwPfmY736sf4b=CzBSW#fhUNw6S5lM!pES|VZa>Ib376Zr`zQ|=g&nR&(H'
    '$`~rAdG+ADfV$lxkHAu$Pn_n71oYTzV*}NR^PFO=UmWa_&d|}Fgk66YQWugHU{A0{&zxRnLx4eW4<wOnft0X>8f0LR>z99ee$>hb'
    'Mwk{x%Hg}?8ck3W5s#T!Vxf7t6>={?gQLv=_`n&fU;BI;ouqXI02mbr{zr~kJLD9MyEH8vbBJD}M%_%j5Y3t$Rvc>m`Q|NQ-<G(u'
    'y|4hDJTw@Nw@8>h_6!(Awkr6rK|@|=`c%KZY$Edmf#o&0-7PH5FXs^V`lnw`;@mIibYXiIt8VMsY|PoCJD(tTL33)A-h;9-YKo@_'
    'cL6pdq6sd%@xOoDe>I#dw?2S2qj3ezgJS{z$O}s3XwmV2uZ&v<B@>reSF!bz8RaLz^d~oWGDiBj2E<#h7b_$NkD%>9axQ(Z=1y^e'
    'Of{dlR7U7DmySb49hPKx&H16i1hZg7rlZy3P@@q>IcNCkwj8sXm{tw8(XZexYM5qA;w8^%$_Y(HBNLNt9}dt-PP3mLDUHHR%t5#u'
    'FtNu)?Pn#~X5t2bfdoSkR7W@}5ZZ#MytIx!tuRk+LU&%o5Vx=SU08<FX@tGzCV*Iq9CAzb#zqZVrr;A9pAO2W`T1dg?>D8NHE343'
    'SRYJ?!JM8bK!Oe;idh5gIlfQ^#UKIt^k7MFb$0^S6CSl+;x;cc43FDFhm*vWE)!;CXnbV!h-^~+T)3JFLSV)!2_7(XTf1;Mnd=b<'
    '%f^znpOud^_bcYo2^Iny(WG%;O#eAX`mYQAR5M?$LxQG1Q;x?O&v3XO$T^ZGAO*?tM$IDPQw>Ay%4PV+(!Zqk!QlZfAaZpY4EP#^'
    'QPOR%KZWhl`%j<kvev8R%on#bPYPzC{I^nDF(*x2`c{$*c94V)6LpZQqu9WI>GO~E=Ou})uieGVFgv1nh*B6h<GD4V(b5n`tTwQq'
    '5%q(*NKLr0ZqYXd^5s*Bq_fd5aq#X5ohJ=*c}Ifv1BT;4CQT(iPp)pw3aCZ+FXtXZaIw%;dFV@pK!lqWsj^faRz%Xe1%*IAD%urf'
    '0(l;mVFG-zns7R5z*8&JM3H%EP?Mv7%!U7G&4ou?(|DsdNSVXOgNYkjgju3`+E9Ew06pAUc+bLP`jDo2Vci0fg~mW*lyojouv66G'
    'NHT$`p%Fn%Lux)##}Dh4grmH@T<%C`i3cXNw4UZHjtj6UNiSKM)Ud5)McTA-+1IS5U{!`eH8cx;wz2_uzz|EAN5{Za$=%2uILyvg'
    'KII}Xg6x~x3j3>0y$q=-!SJ$dZF{)s8cPNR&G_ooii9C~mhcVDVzx54nPQ5$Hd)#QWcnBaL9wKA&%>$}KN_I(GvtoTx8~(A-H%7x'
    '!Rc$n-DJoo6N{nR1wG}@A@`pbJ&=C--Q`h{Kz7XTn?x_u2fVZq;8u&;3?)qW3@MSD^Qsj$MbsH{2TeOx7lBf3l3xl)uwLP$325XE'
    'oSb>K>zA!!tBUEs)D48mxCTM47k80qI?{2|=7ekqa!K5n)-AtiE($C(>J1=1fJD3=)uR^Pjo~L18^KDZV(MHE>()If8VddnEmjgF'
    'EpWjsCcV5@%M2lIbST>d3qvJKL#Ot`TGCKBoM%1K<!rv`7t3*{+z_yj;D~GjQVnGyzN3r)Gdfw7ueuohH2?#_Z&V!Qb7Ia1!T|=?'
    'F!}@7os@T6w1j{Ap#STC{2w39{_F'
)


class ShippingPolicyTests(unittest.TestCase):
    def trusted_main_projection(self, root, raw, source):
        """Authenticate fixture fields; never call this native D evidence."""
        payload=zlib.decompress(base64.b85decode(_MAIN_PROJECTION_B85))
        self.assertEqual(hashlib.sha256(payload).hexdigest(),_MAIN_PROJECTION_SHA256)
        tree=json.loads(payload)
        self.assertEqual(len(tree),501)
        self.assertEqual(tree[inputs.AFFECTED_POLICY],blob(raw))
        policy=json.loads(raw)
        self.assertEqual(inputs.affected_lookup_digest(tree),policy['targets']['main']['lookup_digest'])
        self.assertEqual(tree['tests/platform-profile.json'],policy['targets']['main']['profile'])
        self.assertTrue(inputs.AFFECTED_AUTHORITY <= tree.keys())
        for subjects in inputs._AFFECTED_SUBJECTS.values():self.assertTrue(set(subjects) <= tree.keys())
        # Installed workflow authority changes only through a complete enrolled
        # tuple, exactly as shipping_context overlays the reviewed templates.
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        accepted={'npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1',
                  'protected-producer-original-default-v1'}
        matches=[row['workflows'] for row in generations if row['name'] in accepted
                 and all(source.get(path)==entry for path,entry in row['workflows'].items())]
        self.assertEqual(len(matches),1)
        for path,entry in matches[0].items():
            if path in inputs.AFFECTED_AUTHORITY:tree[path]=dict(entry)
        return tree

    def target_context(self, root, raw, source):
        policy=json.loads(raw)
        lookup=inputs.affected_lookup_digest(source)
        matches=[name for name,row in policy['targets'].items()
                 if row['lookup_digest']==lookup and row['profile']==source['tests/platform-profile.json']]
        self.assertTrue(matches,'actual source namespace must match an unchanged protected target row')
        target='main' if 'main' in matches else matches[0]
        # Equal namespace aliases (Android main/VR) must also share the complete
        # native reader proof, rather than choosing among incompatible variants.
        self.assertTrue(all(policy['targets'][name]==policy['targets'][target] for name in matches))
        return target,self.trusted_main_projection(root,raw,source)

    def test_shipping_manifest_is_complete_and_backward_compatible_registry_is_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        registry=inputs.load_registry(root/'.github/test-suites.json')
        raw=inputs.load_dependencies(root/inputs.AFFECTED_POLICY,registry)
        manifest=json.loads(raw)
        self.assertEqual(len(manifest['suites']),60)
        finite=[n for n,r in manifest['suites'].items() if r['kind']=='reviewed-patterns']
        self.assertEqual(finite,['documentation-contracts','release-bundle','embedded-web-qml',
            'places-native-qml','recorded-voice-qml','snapshot-qml'])
        self.assertEqual(registry['schema'],1)

    def source_context(self):
        root=Path(__file__).resolve().parents[2]
        registry=inputs.load_registry(root/'.github/test-suites.json')
        raw=inputs.load_dependencies(root/inputs.AFFECTED_POLICY,registry)
        tree=inputs.full_tree(root,'HEAD')
        for path in ('tools/test-evidence/affected-test.py','tools/test-evidence/AFFECTED_SELECTION.md'):
            tree[path]=blob((root/path).read_bytes())
        tree[inputs.AFFECTED_POLICY]=blob(raw)
        # Both the source PR and its exact installed successor run this test.
        # Authenticate the actual complete deployed tuple before constructing
        # the distinct approved preinstallation B; do not bind R to B instead S.
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        previous_rows=[row['workflows'] for row in generations if row['name'] in {
            'npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1'}]
        previous=next(row['workflows'] for row in generations if row['name']=='npm-consumers-sync-ci-v1')
        future=next((row['workflows'] for row in generations
            if row['name']=='protected-producer-original-default-v1'),None)
        if future is None:
            future=next(row['workflows'] for row in generations if row['name']=='protected-producer-seven-target-ci-v1')
        endpoint='.github/workflows/pr-metadata-context.yml'
        approved=[future] if endpoint in tree else previous_rows
        matches=[row for row in approved if row is not None and all(tree.get(path)==entry for path,entry in row.items())]
        self.assertEqual(len(matches),1,'source must match one complete reviewed current or installed tuple')
        if endpoint not in tree:previous=matches[0]
        enrolled22=any(row['name']=='protected-producer-original-default-v1' for row in generations)
        codeql=blob((root/'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_bytes())['sha'] \
            if endpoint in tree and enrolled22 else '3a273057a38255ca368d3028594fb94227ba7c3b' if endpoint in tree \
            else '6d55d0fe4e9edc86204c66e1fa3967681793a2cd'
        self.assertEqual(tree['.github/workflows/codeql.yml']['sha'],codeql)
        tree.update(deepcopy(previous));tree.pop(endpoint,None)
        tree['.github/workflows/codeql.yml']=dict(mode='100644',type='blob',
            sha='6d55d0fe4e9edc86204c66e1fa3967681793a2cd')
        return root,registry,raw,tree

    def shipping_context(self):
        """Use the actual complete prospective installed S, not source-only B.

        The native inventory includes the new reusable workflow's membership.
        Its protected certificate must already name S; this fixture never
        rewrites that certificate to make the shipping positive pass.
        """
        root,registry,raw,tree=self.source_context()
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        historical=next(row['workflows'] for row in generations if row['name']=='protected-producer-seven-target-ci-v1')
        self.assertEqual(historical['.github/workflows/repository-checks.yml']['sha'],
            'd9fefd275d9e3c6977cf9350a1945a6bbe5051b4')
        future=next((row['workflows'] for row in generations
            if row['name']=='protected-producer-original-default-v1'),None)
        templates={
            '.github/workflows/project-tests.yml':'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
            '.github/workflows/parent-qualification.yml':'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
            '.github/workflows/repository-checks.yml':'tools/repository-checks/workflows/producers/repository-checks.yml',
            '.github/workflows/pr-metadata-context.yml':'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            '.github/workflows/sync-validation.yml':'tools/repository-checks/workflows/sync-ci-selection.yml',
            '.github/workflows/browser-client.yml':'.github/workflows/browser-client.yml',
        }
        self.assertEqual(set(historical),set(templates))
        if future is not None:self.assertEqual(set(future),set(templates))
        for path,template in templates.items():
            expected=blob((root/template).read_bytes())
            if future is not None:self.assertEqual(future[path],expected,path)
            tree[path]=dict(expected)
        tree['.github/workflows/codeql.yml']=blob(
            (root/'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_bytes())
        if future is not None and tree['tests/platform-profile.json']!=inputs._AFFECTED_SHARED_PROFILE:
            # Source13 keeps all original owners. Only the installed Android S
            # fixture applies the separately reviewed exact six-file handoff.
            owner=json.loads((root/'.github/android-owner-transfer.json').read_bytes())
            targets={path for group in ('legacy_workflows','source_contracts') for path in owner[group]}
            self.assertEqual(targets,{'.github/workflows/android-tests.yml','.github/workflows/android-vr-tests.yml',
                'android/common/tests/android-workflow-contract-test.py',
                'android/common/tests/ci/validate_ci_contract.py','android/common/tests/ci/test_ci_contract.py',
                'android/phone/tests/phone-release-metadata-test.py'})
            for group in ('legacy_workflows','source_contracts'):
                for path,item in owner[group].items():
                    self.assertEqual(item['source'],'tools/repository-checks/workflows/android-owned/handoff/'+path)
                    data=(root/item['source']).read_bytes()
                    self.assertEqual(tree[item['source']],blob(data))
                    expected=blob(data,mode=item['mode'])
                    previous={'mode':item['mode'],'type':'blob','sha':item['reviewed_blob']}
                    self.assertIn(tree.get(path),(previous,expected))
                    tree[path]=expected
        return root,registry,raw,tree

    def bounded_context(self):
        """Seal a small synthetic repository while preserving real definitions.

        Real whole-inventory shipping/legacy routing and protected iOS proofs
        remain separate. Repeated mutation cases need every actual authority,
        required subject, CI exception and currently reviewed import root, not
        thousands of unrelated application assets in every negative plan.
        """
        root,registry,raw,source=self.shipping_context()
        policy=json.loads(raw)
        required=set(inputs.AFFECTED_AUTHORITY)
        required.update(policy['suites']['device-control-plane-full']['native_independent_paths'])
        # These existing importable mutation subjects must remain edits, rather
        # than becoming new import names in the smaller synthetic inventory.
        required.update({'tests/device/self_tests/test_voice_roundtrip.py',
                         'provenance/artifact_identity.py'})
        for suite in registry['suites'].values():
            required.update(suite['closure']['required'])
            imports=suite.get('python_imports')
            if imports and inputs.python_import_digest(source,imports['roots'])==imports['reviewed']:
                required.update(entry['path'] for entry in inputs.selected_entries(
                    source,inputs._import_patterns(imports['roots'])))
        tree={path:dict(entry) for path,entry in source.items() if path in required}
        # This deliberately synthetic fixture exercises main's bounded parser.
        # Full source/shipping contexts above retain real Android13/19 profiles.
        self.assertEqual(inputs._AFFECTED_SHARED_PROFILE['sha'],'d63537504c20204de9d35d9be61da72a56df59c3')
        tree['tests/platform-profile.json']=dict(inputs._AFFECTED_SHARED_PROFILE)
        policy['lookup_digest']=inputs.affected_lookup_digest(tree)
        native=policy['suites']['device-control-plane-full']
        native['reviewed_reader_digest']=inputs.device_reader_digest(tree,native['native_independent_paths'])
        if policy['schema']==2:
            # Keep the versioned main aliases coherent in this smaller fixture;
            # shipping/all-seven source certificates above remain unmodified.
            policy['targets']['main']['lookup_digest']=policy['lookup_digest']
            policy['targets']['main']['reader_digest']=native['reviewed_reader_digest']
        sealed=(json.dumps(policy,indent=2)+'\n').encode()
        tree[inputs.AFFECTED_POLICY]=blob(sealed)
        return root,registry,sealed,tree

    def test_shipping_five_controller_case_omits_device_without_running_any_suite(self):
        root,registry,raw,base=self.shipping_context()
        _,_,_,source=self.source_context()
        self.assertEqual(inputs.affected_lookup_digest(source),inputs.affected_lookup_digest(base))
        self.assertNotIn('.github/workflows/pr-metadata-context.yml',source)
        self.assertIn('.github/workflows/pr-metadata-context.yml',base)
        candidate=deepcopy(base)
        for name in ('attested.py','postmerge.py','producer_workflow.py','sandbox.py','sandbox_host.py'):
            candidate['tools/test-evidence/'+name]=blob(('changed '+name).encode())
        target,trusted=self.target_context(root,raw,base)
        native=json.loads(raw)['suites']['device-control-plane-full']
        self.assertEqual(inputs.device_reader_digest(base,native['native_independent_paths']),
                         json.loads(raw)['targets'][target]['reader_digest'])
        plan=inputs.plan_affected(registry,raw,base,candidate,trusted,target=target)
        self.assertIn('device-control-plane-full',plan['omitted'])
        self.assertLess(len(plan['required']),60)
        self.assertIn('attested-runtime',plan['required'])
        self.assertIn('test-evidence',plan['required'])
        self.assertEqual(plan['required_setup'],['host-full'])
        spec=importlib.util.spec_from_file_location('affected_host_policy',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        selected=host.select(candidate,plan['paths'],True,trusted_tree=trusted,base_tree=base,target=target)
        self.assertEqual(selected['reason'],'protected-affected-dependencies')
        self.assertEqual(selected['suites'],plan['required'])
        self.assertTrue(selected['full_host'])
        self.assertEqual(selected['include_platform'],base['tests/platform-profile.json']!=inputs._AFFECTED_SHARED_PROFILE)
        self.assertFalse(selected['affected']['reusable'])

    def test_preinstallation_source_cannot_inherit_the_prospective_native_omissions(self):
        root,registry,raw,base=self.source_context()
        self.assertNotIn('.github/workflows/pr-metadata-context.yml',base)
        candidate=deepcopy(base)
        candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed preinstallation controller')
        target,trusted=self.target_context(root,raw,base)
        plan=inputs.plan_affected(registry,raw,base,candidate,trusted,target=target)
        owners={'device-control-plane-full',*inputs._AFFECTED_PRODUCT_SUITES,*inputs._AFFECTED_SUBJECTS}
        self.assertEqual(len(owners),23)
        self.assertTrue(owners.issubset(plan['required']))
        self.assertFalse(owners.intersection(plan['omitted']))
        for name in owners:
            self.assertEqual(plan['reasons'][name],
                'fixed-subject-or-reader-not-reviewed' if name in inputs._AFFECTED_SUBJECTS
                else 'product-component-or-reader-not-reviewed')
        if target.startswith('android-'):
            original=inputs.full_tree(root,'HEAD')
            owner=json.loads((root/'.github/android-owner-transfer.json').read_bytes())
            for group in ('legacy_workflows','source_contracts'):
                for path in owner[group]:
                    self.assertEqual(base[path],original[path],'preinstallation fixture must retain every actual legacy owner')

    def test_actual_child_namespace_cannot_be_claimed_as_main_or_trusted_default(self):
        root,registry,raw,base=self.shipping_context()
        target,trusted=self.target_context(root,raw,base)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        # A real child keeps its extra import membership and native readers.
        # On main, a synthetic neighboring import proves the same refusal.
        foreign=deepcopy(base)
        if target=='main':foreign['ios/fixture_namespace.py']=blob(b'new child import')
        self.assertNotEqual(inputs.affected_lookup_digest(foreign),json.loads(raw)['targets']['main']['lookup_digest'])
        for old,new,default,claimed in ((foreign,candidate,trusted,'main'),
                                        (base,candidate,foreign,target),
                                        (base,candidate,trusted,'unknown-child')):
            with self.subTest(claimed=claimed),self.assertRaises(inputs.InputError):
                inputs.plan_affected(registry,raw,old,new,default,target=claimed)

    def test_exact_metadata_and_source_reader_bytes_are_independent_but_membership_and_modes_are_bound(self):
        _,registry,raw,base=self.bounded_context()
        paths={
            'tools/repository-checks/metadata_context.py',
            'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
            '.github/workflows/pr-metadata-context.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
            '.github/workflows/documentation-push-owner.yml',
            '.github/workflows/documentation-checks.yml',
            '.github/workflows/workflow-security.yml',
            'tools/test-evidence/source_admission.py',
            'tools/test-evidence/source-admission-test.py',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
            'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
        }
        self.assertTrue(paths <= set(json.loads(raw)['suites']['device-control-plane-full']['native_independent_paths']))
        candidate=deepcopy(base)
        for path in paths:
            self.assertEqual(base[path]['mode'],'100644')
            candidate[path]=blob(('changed reviewed bytes '+path).encode())
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        owners={'device-control-plane-full',*inputs._AFFECTED_PRODUCT_SUITES,*inputs._AFFECTED_SUBJECTS}
        self.assertTrue(owners <= set(plan['omitted']))
        for path in paths:
            for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                changed=deepcopy(candidate);changed[path]={'mode':mode,'type':kind,'sha':'f'*40}
                with self.subTest(path=path,mode=mode):
                    try: result=inputs.plan_affected(registry,raw,base,changed,base)
                    except inputs.InputError: continue
                    self.assertTrue(owners <= set(result['required']))
        candidate['.github/workflows/pr-metadata-context-extra.yml']=blob(b'unreviewed neighbor')
        self.assertTrue(owners <= set(inputs.plan_affected(registry,raw,base,candidate,base)['required']))

    def test_unavailable_graph_retains_the_independently_selected_legacy_gate(self):
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_host_rollout',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'new')
        paths=['tools/test-evidence/sandbox_host.py']
        without=deepcopy(base);del without[inputs.AFFECTED_POLICY]
        for old,trusted,claimed in ((without,without,paths),(None,base,paths),(base,base,paths+['README.md'])):
            with self.subTest(old_missing=old is None,claimed=claimed):
                selected=host.select(candidate,claimed,True,trusted_tree=trusted,base_tree=old)
                legacy=host._select_legacy(candidate,claimed,True,trusted_tree=trusted,base_tree=old)
                self.assertEqual(selected,legacy)

    def test_changed_graph_cannot_expand_an_independently_reviewed_ci37_plan(self):
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_graph_preserves_legacy',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        candidate=deepcopy(base);candidate[inputs.AFFECTED_POLICY]=blob(b'changed policy bytes')
        options={'base_tree':base,'trusted_tree':base}
        with patch.object(host,'REVIEWED_PROGRAMS',host.program_digest(base)):
            legacy=host._select_legacy(candidate,[inputs.AFFECTED_POLICY],True,**options)
            self.assertEqual(len(legacy['suites']),37)
            self.assertFalse(legacy['full_host'])
            self.assertEqual(host.select(candidate,[inputs.AFFECTED_POLICY],True,**options),legacy)
        with self.assertRaises(inputs.InputError):
            inputs.plan_affected(registry,raw,base,candidate,base)

    def test_each_device_component_reader_data_discovery_native_and_variant_keeps_device(self):
        _,registry,raw,base=self.bounded_context()
        paths=('tests/device/catalog.json','tests/device/self_tests/test_voice_roundtrip.py',
            'tests/device/fixture/new-resource.json','provenance/artifact_identity.py',
            'tools/sbom/verify-artifact-identity.py','libraries/audio-client/src/AudioClient.cpp',
            'libraries/shared/src/new-header.h','interface/resources/qml/new-component.qml',
            'scripts/system/settings/qml/new-data.json','android/phone/new-native-input.cpp')
        for path in paths:
            candidate=deepcopy(base);candidate[path]=blob(b'changed component')
            with self.subTest(path=path):
                plan=inputs.plan_affected(registry,raw,base,candidate,base)
                self.assertIn('device-control-plane-full',plan['required'])
        historical=deepcopy(base);historical['libraries/audio-client/src/AudioClient.cpp']=blob(b'child reader')
        candidate=deepcopy(historical);candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated')
        self.assertIn('device-control-plane-full',inputs.plan_affected(registry,raw,historical,candidate,base)['required'])

    def test_optional_ios_adapter_and_historical_native_root_headers_remain_bound(self):
        _,registry,raw,base=self.bounded_context()
        for path in ('ios/audio/IOSAudioAdapter.cpp','ios/audio/IOSAudioAdapter.h',
                     'ios/audio/new-private-header.h','cassert','QtCore/QCoreApplication'):
            for shape in ('candidate-only','historical-both'):
                old=deepcopy(base);candidate=deepcopy(base)
                if shape=='historical-both':old[path]=blob(b'historical native lookup')
                candidate[path]=old[path] if shape=='historical-both' else blob(b'changed native lookup')
                candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated admitted CI')
                with self.subTest(path=path,shape=shape):
                    plan=inputs.plan_affected(registry,raw,old,candidate,base)
                    self.assertIn('device-control-plane-full',plan['required'])

    def test_native_independence_is_closed_bounded_and_cannot_exempt_unowned_headers(self):
        root,registry,raw,base=self.bounded_context()
        for paths in ([],['*'],['../cassert'],[inputs.AFFECTED_POLICY]*2,[f'leaf-{n}' for n in range(1001)]):
            value=json.loads(raw)
            value['suites']['device-control-plane-full']['native_independent_paths']=paths
            with self.subTest(paths=paths[:2]),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(value,registry)
        value=json.loads(raw)
        value['suites']['device-control-plane-full']['native_independent_paths'].append('cassert')
        forged=json.dumps(value).encode()
        for tree in (base,):tree[inputs.AFFECTED_POLICY]=blob(forged)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed')
        spec=importlib.util.spec_from_file_location('affected_native_policy_guard',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        with patch.object(inputs,'load_dependencies',return_value=forged):
            selected=host.select(candidate,['tools/test-evidence/sandbox_host.py'],True,base_tree=base,trusted_tree=base)
        legacy=host._select_legacy(candidate,['tools/test-evidence/sandbox_host.py'],True,base_tree=base,trusted_tree=base)
        self.assertEqual(selected,legacy)

    def test_reviewed_product_owners_share_only_the_fixed_complete_lookup_proof(self):
        _,registry,raw,base=self.bounded_context()
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertTrue(inputs._AFFECTED_PRODUCT_SUITES.issubset(plan['omitted']))
        self.assertIn('host-selection',plan['required'])
        for name in sorted(inputs._AFFECTED_PRODUCT_SUITES):
            subject=registry['suites'][name]['closure']['required'][0]
            changed=deepcopy(candidate);changed[subject]=blob(b'changed reviewed owner')
            with self.subTest(owner=name,subject=subject):
                if subject in inputs.AFFECTED_AUTHORITY:
                    with self.assertRaises(inputs.InputError):
                        inputs.plan_affected(registry,raw,base,changed,base)
                else:
                    self.assertIn(name,inputs.plan_affected(registry,raw,base,changed,base)['required'])
        value=json.loads(raw)
        for shape in ('unknown-owner','candidate-scope','missing-fixed-inventory','extra-inventory'):
            changed=deepcopy(value);changed_registry=deepcopy(registry)
            if shape=='unknown-owner':changed['suites']['producer-api']['kind']='reviewed-product-inventory'
            elif shape=='candidate-scope':
                changed_registry['suites']['device-jenkins']['scope']='candidate'
                changed['registry_digest']=inputs._suite_definition_digest(changed_registry)
                changed['suites']['device-jenkins']['definition_digest']=inputs._suite_definition_digest(changed_registry['suites']['device-jenkins'])
            elif shape=='missing-fixed-inventory':changed['suites']['device-control-plane-full']={
                'kind':'repository','setup':['host-full'],'definition_digest':changed['suites']['device-control-plane-full']['definition_digest']}
            elif shape=='extra-inventory':changed['suites']['device-jenkins']['native_independent_paths']=['ignored']
            with self.subTest(shape=shape),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(changed,changed_registry)

    def test_javascript_and_performance_component_data_cannot_use_ci_byte_exemptions(self):
        _,_,raw,base=self.bounded_context()
        paths=json.loads(raw)['suites']['device-control-plane-full']['native_independent_paths']
        for path in ('tests/javascript/README.md','tests/performance/README.md',
                     'tests/safe-landing/README.md','tests/mocha/README.md','server-console/README.md',
                     'unpublishedScripts/README.md','tools/jsdoc/README.md'):
            old=deepcopy(base);old[path]=blob(b'old fixture contract')
            new=deepcopy(old);new[path]=blob(b'changed fixture contract')
            with self.subTest(path=path):
                self.assertNotEqual(inputs.device_reader_digest(old,[*paths,path]),
                                    inputs.device_reader_digest(new,[*paths,path]))

    def test_fixed_ci_subjects_bind_all_three_trees_without_coupling_product_owners(self):
        _,registry,raw,base=self.bounded_context()
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertTrue(set(inputs._AFFECTED_SUBJECTS).issubset(plan['omitted']))
        self.assertIn('documentation-contracts',plan['required'])
        self.assertEqual(plan['reasons']['documentation-contracts'],'unreviewed-import-or-missing-required-input')
        # Apple retains two additional audio Python readers and a changed mute
        # caller. Their genuine import variant must keep this extra owner.
        if 'recorded-voice-qml' in plan['required']:
            self.assertEqual(plan['reasons']['recorded-voice-qml'],'unreviewed-import-or-missing-required-input')
            self.assertEqual(len(plan['required']),33)
        else:
            self.assertIn('recorded-voice-qml',plan['omitted'])
            self.assertEqual(plan['reasons']['recorded-voice-qml'],'unchanged-reviewed-dependencies')
            self.assertEqual(len(plan['required']),32)
        for name,subjects in inputs._AFFECTED_SUBJECTS.items():
            for subject in subjects:
                for shape in ('changed','removed','historical','executable'):
                    old=deepcopy(base);new=deepcopy(candidate)
                    if shape=='removed':new.pop(subject)
                    elif shape=='executable':new[subject]=dict(new[subject],
                        mode='100644' if new[subject]['mode']=='100755' else '100755')
                    else:
                        new[subject]=blob(b'changed exact subject')
                        if shape=='historical':old[subject]=deepcopy(new[subject])
                    with self.subTest(owner=name,subject=subject,shape=shape):
                        lookup_change = subject=='tools/test-evidence/producer.py' and shape in {'removed','executable'}
                        if subject in inputs.AFFECTED_AUTHORITY or lookup_change:
                            with self.assertRaises(inputs.InputError):
                                inputs.plan_affected(registry,raw,old,new,base)
                        else:
                            selected=inputs.plan_affected(registry,raw,old,new,base)
                            self.assertIn(name,selected['required'])
        # This CI unit-test leaf is independent of the actual product tests.
        changed=deepcopy(candidate);changed['tests/unittest-runner-test.py']=blob(b'changed CI regression')
        selected=inputs.plan_affected(registry,raw,base,changed,base)
        self.assertIn('python-test-runner',selected['required'])
        self.assertIn('device-control-plane-full',selected['omitted'])
        self.assertTrue(inputs._AFFECTED_PRODUCT_SUITES.issubset(selected['omitted']))

    def test_fixed_ci_subject_policy_cannot_supply_unknown_owners_or_subject_maps(self):
        _,registry,raw,base=self.bounded_context()
        value=json.loads(raw)
        for shape in ('unknown-owner','candidate-scope','alternate-subjects','extra-map','missing-native'):
            changed=deepcopy(value);definitions=deepcopy(registry)
            if shape=='unknown-owner':changed['suites']['producer-api']['kind']='reviewed-subject-inventory'
            elif shape in {'candidate-scope','alternate-subjects'}:
                if shape=='candidate-scope':definitions['suites']['python-test-runner']['scope']='candidate'
                else:definitions['suites']['python-test-runner']['closure']['required']=['tests/unittest-runner-test.py']
                changed['registry_digest']=inputs._suite_definition_digest(definitions)
                changed['suites']['python-test-runner']['definition_digest']=inputs._suite_definition_digest(definitions['suites']['python-test-runner'])
            elif shape=='extra-map':changed['suites']['python-test-runner']['subjects']=['arbitrary.py']
            else:
                entry=changed['suites']['device-control-plane-full']
                changed['suites']['device-control-plane-full']={k:entry[k] for k in ('kind','definition_digest','setup')}
                changed['suites']['device-control-plane-full']['kind']='repository'
            with self.subTest(shape=shape),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(changed,definitions)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        candidate['tests/unittest-extra-runner-test.py']=blob(b'unknown neighbor')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertIn('python-test-runner',plan['required'])

    def test_unknown_root_import_shadow_cannot_inherit_any_omission(self):
        _,registry,raw,base=self.bounded_context()
        for path in ('json.py','sitecustomize.py','tools/repository-checks/json.py','tests/device/new_module.py','namespace/__init__.py'):
            candidate=deepcopy(base);candidate[path]=blob(b'new shadow')
            with self.subTest(path=path),self.assertRaises(inputs.InputError):
                inputs.plan_affected(registry,raw,base,candidate,base)

    def test_existing_ci37_metadata_codeql_cleanup_and_lock_plans_never_expand(self):
        import ci_profile
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_preserve_proofs',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        ci37=[n for n,s in registry['suites'].items() if s['layer']=='quick' and n not in host.PRODUCT_QUICK_SUITES]
        paths=('.github/workflows/codeql.yml','.github/branch-cleanup.json',
               '.github/android-orchestration.json','tests/PROJECT_TESTING.md',*host.PACKAGE_LOCKS)
        # Preserve the exact legacy37 contract under its actual old namespace.
        # The new seven-target namespace deliberately permits smaller proved
        # Qt-free selections; SevenTargetProfileTests covers those separately.
        historical_policy={**ci_profile.load_policy(root),
            'generation_kind':ci_profile.CONTROLLER_KIND,'epoch':ci_profile.CONTROLLER_EPOCH}
        with patch.object(host,'REVIEWED_PROGRAMS',host.program_digest(base,root)), \
             patch.object(ci_profile,'load_policy',return_value=historical_policy):
            for path in paths:
                candidate=deepcopy(base);candidate[path]=blob(b'changed ordinary shipping leaf')
                package_paths=(path,) if path in host.PACKAGE_LOCKS else ()
                options={'base_tree':base,'trusted_tree':base,'package_paths':package_paths}
                with self.subTest(path=path):
                    legacy=host._select_legacy(candidate,[path],True,**options)
                    self.assertEqual(legacy['suites'],ci37)
                    self.assertEqual(len(legacy['suites']),37)
                    self.assertEqual(host.select(candidate,[path],True,**options),legacy)
            for unknown,regular,paths in ((False,True,[]),(True,True,['README.md']),(False,False,['README.md'])):
                options={'base_tree':base,'trusted_tree':base,'unknown':unknown}
                self.assertEqual(host.select(base,paths,regular,**options),host._select_legacy(base,paths,regular,**options))

    def test_fewer_groups_cannot_replace_an_existing_narrower_preparation_route(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_setup_dominance',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        for legacy_full,affected_full in ((False,True),(False,False),(True,True),(True,False)):
            legacy={'suites':['owner-a','owner-b'],'reason':'reviewed-ci-only-inputs',
                    'full_host':legacy_full,'include_platform':False}
            affected={'suites':['owner-a'],'reason':'protected-affected-dependencies',
                      'full_host':affected_full,'include_platform':False}
            with self.subTest(legacy_full=legacy_full,affected_full=affected_full), \
                    patch.object(host,'_select_legacy',return_value=legacy), \
                    patch.object(host,'affected_selection',return_value=affected):
                selected=host.select({},['reviewed-ci-leaf'],True)
                self.assertIs(selected,legacy if affected_full and not legacy_full else affected)

    def test_nonempty_or_changed_platform_cannot_enter_partial_route_even_on_both_sides(self):
        _,registry,raw,base=self.bounded_context()
        changed=deepcopy(base);changed['tests/platform-profile.json']=blob(b'{"schema":1,"platform":"android","suites":[{}]}')
        candidate=deepcopy(changed);candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated')
        with self.assertRaises(inputs.InputError):inputs.plan_affected(registry,raw,changed,candidate,changed)

    def test_protected_producer_declines_dynamic_subset_before_any_runtime_preparation(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_producer',root/'tools/test-evidence/producer_workflow.py')
        producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
        registry={'schema':1,'control_inputs':['fixed'],'suites':{'finite':definition()}}
        tree={'fixed':blob()}
        policy=type('Policy',(),{'select':staticmethod(lambda *a,**k:{'reason':'protected-affected-dependencies','suites':['finite'],'full_host':True})})
        with patch.object(producer.shared,'prepared_tools') as tools,patch.object(producer.runtime_ci,'validate_environment') as admit:
            with self.assertRaises(producer.PreExecutionUnavailable):
                producer.selection_profile(policy,registry,tree,tree,tree)
            tools.assert_not_called();admit.assert_not_called()


class DependencyPolicyRoutingTests(unittest.TestCase):
    def module(self, name, relative):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location(name,root/relative)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        spec.loader.exec_module(module)
        return module

    def test_only_exact_ordinary_new_leaves_are_ios_and_android_independent(self):
        ios=self.module('affected_ios_inputs','tools/ios-build-qualification/inputs.py')
        host=self.module('affected_ios_host','tools/ios-build-qualification/host.py')
        android=self.module('affected_android_inputs','tools/repository-checks/android-build-inputs.py')
        paths=(inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md')
        for path in paths:
            with self.subTest(path=path):
                entry=ios.Entry(path,'100644','blob','a'*40)
                self.assertEqual(ios._kind(entry),'independent-host')
                self.assertEqual(android._kind(entry),'independent-host')
                self.assertIn(path,host.CI_HOST_INDEPENDENT_PATHS)
                old=SimpleNamespace(entries=(entry,),revision="a"*40,tree="b"*40)
                new=SimpleNamespace(entries=(ios.Entry(path,'100644','blob','b'*40),),revision='c'*40,tree='d'*40)
                with patch.object(host,'REVIEWED_CI_HOST_BOUNDARY',host.ci_host_boundary(old)):
                    self.assertIsNotNone(host.ci_host_omission(old,new))
                    for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                        altered=ios.Entry(path,mode,kind,'b'*40)
                        self.assertEqual(ios._kind(altered),'application-input')
                        self.assertEqual(android._kind(altered),'application-input')
                        self.assertIsNone(host.ci_host_omission(old,SimpleNamespace(entries=(altered,))))
        for path in ('.github/test-suite-dependencies-extra.json','tools/test-evidence/affected-extra-test.py',
                     'tools/test-evidence/AFFECTED_SELECTION-extra.md'):
            entry=ios.Entry(path,'100644','blob','a'*40)
            self.assertEqual(ios._kind(entry),'application-input')
            self.assertEqual(android._kind(entry),'application-input')
            self.assertNotIn(path,host.CI_HOST_INDEPENDENT_PATHS)

    def test_exact_metadata_and_security_guide_ios_exclusions_keep_neighbors_and_modes_conservative(self):
        ios=self.module('metadata_ios_inputs','tools/ios-build-qualification/inputs.py')
        host=self.module('metadata_ios_host','tools/ios-build-qualification/host.py')
        paths={'.github/dependency-security.md', '.github/workflows/pr-metadata-context.yml',
            '.github/workflows/documentation-checks.yml', '.github/workflows/workflow-security.yml',
            'tools/repository-checks/metadata_context.py',
            'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
            '.github/workflows/documentation-push-owner.yml',
            'tools/test-evidence/source_admission.py',
            'tools/test-evidence/source-admission-test.py',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',}
        for path in paths:
            with self.subTest(path=path):
                entry=ios.Entry(path,'100644','blob','a'*40)
                self.assertEqual(ios._kind(entry),'independent-host')
                self.assertIn(path,host.CI_HOST_INDEPENDENT_PATHS)
                old=SimpleNamespace(entries=(entry,),revision='a'*40,tree='b'*40)
                with patch.object(host,'REVIEWED_CI_HOST_BOUNDARY',host.ci_host_boundary(old)):
                    self.assertIsNotNone(host.ci_host_omission(old,SimpleNamespace(
                        entries=(ios.Entry(path,'100644','blob','b'*40),),revision='c'*40,tree='d'*40)))
                    for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                        altered=ios.Entry(path,mode,kind,'b'*40)
                        self.assertEqual(ios._kind(altered),'application-input')
                        self.assertIsNone(host.ci_host_omission(old,SimpleNamespace(entries=(altered,))))
                neighbor=path+'.extra'
                self.assertEqual(ios._kind(ios.Entry(neighbor,'100644','blob','a'*40)),'application-input')
                self.assertNotIn(neighbor,host.CI_HOST_INDEPENDENT_PATHS)

    def test_complete_source_reader_complements_exclude_only_exact_new_leaves(self):
        ios=self.module('affected_ios_reviewed','tools/ios-build-qualification/inputs.py')
        host=self.module('affected_ios_host_reviewed','tools/ios-build-qualification/host.py')
        root=Path(__file__).resolve().parents[2]
        revision=ios._git(root,'rev-parse','--verify','HEAD^{commit}').decode().strip()
        snapshot=ios.read_snapshot(root,revision)
        doctor='tools/repository-health/check.py'
        paths={inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md',doctor}
        self.assertIn(doctor,ios.INDEPENDENT_HOST_PATHS)
        self.assertIn(doctor,ios.INDEPENDENT_EXECUTABLE_HOST_PATHS)
        self.assertIn(doctor,host.CI_HOST_INDEPENDENT_PATHS)
        self.assertIn(doctor,host.CI_HOST_EXECUTABLE_PATHS)
        added={entry.path:entry for entry in snapshot.entries if entry.path in paths}
        self.assertEqual(set(added),paths)
        self.assertTrue(all(entry.mode==('100755' if entry.path==doctor else '100644')
            and entry.object_type=='blob' for entry in added.values()))
        before=SimpleNamespace(entries=tuple(entry for entry in snapshot.entries if entry.path not in paths))
        self.assertEqual(len(before.entries)+len(paths),len(snapshot.entries))
        app=ios._boundary(before)
        own_host=host.ci_host_boundary(before)
        self.assertIsNotNone(app)
        self.assertIsNotNone(own_host)
        self.assertEqual(ios._boundary(snapshot),app)
        self.assertEqual(host.ci_host_boundary(snapshot),own_host)
        changed=SimpleNamespace(entries=tuple(ios.Entry(entry.path,entry.mode,entry.object_type,'f'*40)
            if entry.path in paths else entry for entry in snapshot.entries))
        self.assertEqual(ios._boundary(changed),app)
        self.assertEqual(host.ci_host_boundary(changed),own_host)
        # The historical anchor is independently reconstructed by the complete
        # immutable reader audit; a shallow candidate need not fetch its commit.
        self.assertEqual(ios.REVIEWED_REVISION,'2fc894a0605103843b36653f250f854714a963ee')
        self.assertEqual(ios.REVIEWED_BOUNDARY,
            'sha256:8e66f6e9de251fe1a19feb867df56a714fb126cd8e66e22ba370d03af4f90aec')
        self.assertEqual(host.REVIEWED_CI_HOST_BOUNDARY,
            '90da341e226f56b8dfb8b925af7c0273ecc41772ca424e3426b04c80acdb9a7b')

    def test_new_policy_uses_existing_native_browser_and_package_host_routes(self):
        native=self.module('affected_native_route','tools/native-tests/check.py')
        checks=self.module('affected_repository_route','tools/repository-checks/check.py')
        packages=self.module('affected_package_route','tools/repository-checks/package_checks.py')
        paths=[inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md']
        self.assertEqual(native.plan(paths)['mode'],'skip')
        direct=checks.direct_browser_plan(paths)
        self.assertFalse(direct['browser']);self.assertFalse(direct['native'])
        self.assertEqual(packages.select(paths)['package_set'],[])
        self.assertEqual(packages.select(paths)['tool_projects'],[])
        self.assertEqual(native.plan(paths,regular=False)['mode'],'full')
        self.assertTrue(checks.direct_browser_plan(paths,regular=False)['native'])

    def test_new_policy_is_python_only_only_for_existing_ordinary_pinned_leaves(self):
        codeql=self.module('affected_codeql_route','tools/repository-checks/codeql.py')
        before={p:{'mode':'100644','type':'blob','sha':sha} for p,sha in codeql._REVIEWED_CONTROLS.items()}
        before['.github/workflows/codeql.yml']['sha']=codeql._PINNED_RESULTS_WORKFLOW
        before[inputs.AFFECTED_POLICY]=blob(b'old')
        after=deepcopy(before);after[inputs.AFFECTED_POLICY]=blob(b'new')
        self.assertEqual(codeql.select_languages(before,after)['languages'],['python'])
        for shape in ('new','removed','executable','alias','neighbor','legacy','mixed','config'):
            old=deepcopy(before);new=deepcopy(after)
            if shape=='new':del old[inputs.AFFECTED_POLICY]
            elif shape=='removed':del new[inputs.AFFECTED_POLICY]
            elif shape=='executable':new[inputs.AFFECTED_POLICY]['mode']='100755'
            elif shape=='alias':new[inputs.AFFECTED_POLICY]['mode']='120000'
            elif shape=='neighbor':new['.github/test-suite-dependencies-extra.json']=blob(b'new')
            elif shape=='legacy':old['.github/workflows/codeql.yml']['sha']=codeql._RETARGET_RESULTS_WORKFLOW
            elif shape=='mixed':new['actual.js']=blob(b'new')
            elif shape=='config':new['.github/codeql/codeql-config.yml']=blob(b'new')
            with self.subTest(shape=shape):
                self.assertIn('javascript-typescript',codeql.select_languages(old,new)['languages'])


class NonreusableRouteTests(unittest.TestCase):
    def execute(self, status=0, product=(), include_platform=False):
        import execution
        registry={'schema':1,'control_inputs':['fixed'],'suites':{
            'selected':definition(),'omitted':definition()}}
        observations=[]
        def run(args,suites,cancelled,result_callback):
            observations.extend(suite.name for suite in suites)
            for suite in suites:
                result_callback({'name':suite.name,'status':'passed' if status==0 else 'failed'})
            return status
        controller=SimpleNamespace(ROOT=None,run_command=lambda *a:None,
            Suite=lambda name,layer,command:SimpleNamespace(name=name,layer=layer,command=command),run_suites=run)
        with (tempfile.TemporaryDirectory() as temporary,
              patch.object(execution,'checkout_identity',return_value=('a'*40,'b'*40)),
              patch.object(execution.inputs,'load_registry',return_value=registry),
              patch.object(execution.inputs,'full_tree',return_value={'fixed':blob()}),
              patch.object(execution,'platform_suites',return_value=list(product)),
              patch.object(execution,'capture_execution_environment') as capture,
              patch.object(execution,'_runner',return_value=controller),
              patch.object(execution,'_write_receipt') as write):
            value=execution.execute(Path(temporary),['selected'],include_platform=include_platform,
                receipt_path=Path('/fixed-receipt'),_impact_selection=True)
        capture.assert_not_called()
        self.assertEqual(observations,['selected'])
        self.assertEqual(write.call_count,1)
        return value

    def test_empty_platform_context_runs_exact_subset_without_runtime_or_reuse_claim(self):
        code,receipt=self.execute()
        self.assertEqual(code,0)
        self.assertEqual(receipt['requested_suites'],['selected'])
        self.assertFalse(receipt['reusable']);self.assertIsNone(receipt['environment'])
        self.assertEqual(receipt['results'],{'selected':{'status':'passed','fingerprint':None}})
        self.assertEqual(receipt['platform_results'],{})

    def test_started_failure_stays_failed_once_without_runtime_or_full_retry(self):
        code,receipt=self.execute(status=17)
        self.assertEqual(code,17)
        self.assertEqual(receipt['conclusion'],'failure')
        self.assertFalse(receipt['reusable'])

    def test_impact_execution_rejects_platform_inventory_flags(self):
        import execution
        with self.assertRaises(execution.ExecutionError):
            self.execute(product=[('actual-platform',['python','actual.py'])],include_platform=True)

    def test_legacy_owner_forwards_dynamic_selection_without_capture_and_never_retries_failure(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_legacy_route',root/'tools/repository-checks/android_handoff.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        selected={'reason':'protected-affected-dependencies','suites':['selected'],
                  'include_platform':False,'full_host':True}
        proof={'reusable':False,'environment':None,'conclusion':'failure',
               'results':{'selected':{'status':'failed','fingerprint':None}}}
        shared=SimpleNamespace(execute=Mock(return_value=(17,proof)),digest=lambda value:'fixed',
            _write_receipt=Mock(),inputs=SimpleNamespace(load_registry=lambda path:{'suites':{'selected':{},'omitted':{}}}))
        controller=SimpleNamespace(android=lambda:SimpleNamespace(_shared=lambda:(shared,None)))
        with (tempfile.TemporaryDirectory() as temporary,
              patch.object(owner,'gate',return_value=controller),
              patch.object(owner,'host_selection',return_value=object()),
              patch.object(owner,'selected_host',return_value=selected),
              patch.object(owner,'platform_owner',return_value={} )):
            base=Path(temporary);candidate=base/'candidate';candidate.mkdir()
            status,observed=owner.project(candidate,{},'a'*40,'pull_request',
                junit=base/'results.xml',receipt_path=base/'receipt.json')
        self.assertEqual(status,17);self.assertEqual(observed['conclusion'],'failure')
        shared.execute.assert_called_once()
        self.assertIs(shared.execute.call_args.kwargs['_impact_selection'],True)
        self.assertEqual(shared.execute.call_args.kwargs['suite_names'],['selected'])
        self.assertFalse(observed['reusable']);self.assertIsNone(observed['environment'])


if __name__=='__main__':unittest.main()
