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
# 1acdbbd274c7c95d88faf1272b9fb351a469bb03 / tree e4f9e2f547478da8e0178ab5603fda405a08c218.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '957250ccb6bec47e2174095ea480e9d68bc23e785cf54591771a7e4cd83dbd64'
_MAIN_PROJECTION_B85 = (
    'c-qa~*_Iqf(jDsi^B8?CG-4j~6k2DU`&u!007(`qt7~AB($c%1&myzXU^glwGK(4{{Xd%^)$SSLVQ#i<?`{9%Z-4)Cc=`G|ejXm?'
    'r{iJ%bo}Q-diwP8G(0>n>FMvkJRcwa_Fw<U-@YB^^tb=|w>-<5s`}f1`P=i?!QU3`oTWT#mU-^WtnTwU4MX1)%aXNoHH|4%ZPDfN'
    '|Ka72$M`Q8?~mi({^x)BzU*kB>FcM*<Naa!V`H^(EayCLQq#BDJfx{>+SVFb)@DoDjB~cMO*LfQ`>Q<;)33vq^y#0+r(c)*<3B%r'
    'Nq+6{ayULbZ!Dh5rYwrO>YAk(=C;V|X0C?RW<^(({WMo?IhO6%zrXlXdOSWKUXD+He44(d>DR3l>&e4grhIDiE*@}7sbA`9$*Q^c'
    'L;G$hiz<y59_~wee);tLdU#2n=Jc2z=JYTf($=~~*5q|pE$xzLd6Q4$IG0sj%yT^yZQs^QGqht_EPK}7T5DL!Y3%EwX`9^Zt(#$)'
    '^CBCoqNuWY?9()jLmKn<*Lr)E&tC3RdU*NtkJsV;upFlKt^WOwZ};!7-pqxcR-|fdO3$~+nyjemJg?h1FT1)L=lI#F-L?AD@s~8c'
    'e2U-xe0kZfFS4P}Q`=8nD(b1Mrp)h7^U&nk+~z}5)Ryh{Ec>5_>f+Mv()w=7C9mr)Pvhj^Hho!S`7liR+)Z=a&V5z=<lT->mJ=DK'
    '`-7+ac{+UlB|ZFlczFK&Wr+9u_{aOJ=J_yH<1`gxRaNa+RNdT6Mc&qFcF^j4sZ-wilCD|x(J%MHFR$wmmnpu|t{k(eE#@v;I_G(4'
    '#-(TlsV+;7*mdh3$IGiO!_sD6YMU>9Uy=1gR+OScHT9{hrgj;oq3+83npK}(A1<yr<yF%(^D^{f)wO=!(3eftcllVRF%{K3W^G!Q'
    'tJaK@d^df4I(|!c&(rbo@~`%}WSJ*B<Ym)1*Hh|;x*Xc9E;`><J<a{x<<~vybq5c_xAZJ<r@N;#JRTmtT-?UoIlWVp>ZTGkQ(mPq'
    '?~AG$rm=~*R#i=2<<s>K;^Fbz-E@3d4wu(&hdec%K-P5mkQd#QyEd|VY=+J^U1T=b+GBb3`f)GMcfbF(j2G7*owKZ}=DHTDn>zC('
    '>Y>l3!VT#}mYzbE%5k`QeJ9XWd2#JDEoC<dnY9nkT{yK<KIWy^R#($d<egyKWIKL)M3jFHe|&yOFA?ePo{q0C>25v@UmlLnFNf)J'
    'v~e4cLzk+&p6XP2{e73x;OflkM%0_;u^93?@2}p*>->0e;i7YkrMz%s_~7S0p1z$lQ@+fF4`CUd#MHLC7d{=l^XhA27Dw<U{r++}'
    '0M$PBHVs8tmt9$=*i_x8cC2S#qdPUv#>mn(_i;bS3tx`k4$~)L@3+IV8`TH+d3c=<FL&n~FK*e3Uu0dUp_+?9HdrpA;XGHpJEn`6'
    'm^XF23{R%Lc{l4<86U^}@G6(Q9HrW(oZR|NUwI$RJdEOI-xd9`%x#%1d7d)KR(AVlUZs<lBjr2|c{deJw`8^7KGajux*B{Y(!IJ{'
    '>S3<RBIP&l;n(!^knZo+w{&qQeKC3<bKAK0C9g}B70WmmO`W%Wvoxu1Tj#e}Zr;ha;X%4R-^uYE<)=UHz8;<<SGl;WEH18Qsk$*s'
    'lQ7bz+GXYzl`G`(PFGpwDc!!S<LF=dZ6la9Qz;dl>QS_;#-eSV-l5FqQu>sfAaSgTe|q~a9?zA>aKC=lPs8+bIk0te)fH`3bPBAl'
    '5!LIuY^S-CFFMu|=6+5^H}*GgNlvxgAHIBj*&S<}wp?UX*-+J^t0no)^Db{Y@h2Y8TxM#vr5!)8rLA<!1E{m9%UTs^*{C*)$hu@%'
    '9!c-*WnI~IWij8p1!>1D*d2cJVc&g!M3=JwXJr_(eo?=924&ZF;{MnOzRQ^B;>;xeWVb(-=NI4A<-^iD8f`2+_GLFsE}^A&ZYK|_'
    'RZg~TUH0_{zM_}m=}X#u3oH`eY?x-*$I>_>$%ma+ZS9b>@q`-rL7%1D-_j{teY*<A<LkpbYy=v|L<N>f&%KsRu{$)g|64axRpet+'
    'Wkaq`sM24wrybW*nU=h-`%z6+m8qZWDI1r0%5x{Vn;qkbIMb4Sa7XJMb+;=FPPP2K$X%E&#;ySG%xUbLY*o%smStU!i!|$l?=3z2'
    'c6d5IeDg1!Uft!gt_Yl`Us73)<5*9PD`FfPSW}aRZUi4JZuGhQ*q(OZqTNunL#e80n=y4Tnz>TlO2CwtqujUg!P`;w*KOzSAPM|('
    'x;-{B!Ex*yD0tPB3B;q9HTKQacP@+4oi?VWu-%Vs?WS9PYynylVrP8m+awE_qE3X3K%C09TB>rG`{^&*+I0N3;v`!StXYOs_7eH3'
    '&jreOpPi&x__o_-&d0?)+m-WQv#aOyTYA{2s+Fw$RL2WcL<#_z=hbDo>!T=B2MsL+^5J9q*%b+-hgDw&#4x9&pL!@@Uk+L0<DUSs'
    'dE<rV%G?ib<%g{3+hNZc@0Y9`0$?Z;5D#=Wwe{HNBSb6NU0Dn%pNDGs*uJh$jl8!(&Ikvo0h?g11-Mw{O;I`GP1zN8SY^xj(S6B}'
    '?xv>%+kH6<_s<*XfRd}K3KwnHkJ7ef@vtH%$VbU;4vdvL&Hab>v?nDfUH%S^{{t-=^4vEss|M*qZpyAvpyoq67sbamb3^tfha4Bk'
    'chmU7l+8m8HBEr;Do+ELdMw<7c`<!#W6#IeC!p4J{F>m_)8%Z=dUK{I8a$am+0tD0O<q=glmN@r&mP(YV*22gBCEXHQNlu)<ZHmb'
    'qODbC%jljdpe}P+)Cuk>JaySm`##riXBiInuNy#bS9MbwQaxl<Jxm%Vt=x8yvrL7@G?iu7YoO#GJl8MZ9+$&?`d+PF{`^~)ep3#r'
    'GjNcI*??s{mQlW&1thDpQ`F4|Pxs5y>+_47<k$4a(-t)9o0nhuzN<0i&UEh`O+BDA8*_&$bxSpO=_3`v6`P4HJ1g@RCR+5};_WSk'
    '7+zIl<_nv~s;qlh#J=nQ3{s!}$>rN(E}?;r1$4Bn-4_b_OeS0BV=a+|(bnD6b^9{xFRyF3OHbbp&(CWQ@nSMI_Pu^YG&+_pX{zaC'
    'N~1^JuA!|`rwKHRIs1O{*JHf><8dqC#|5pP=!U+nrfQz*LTFQ;cW&@G%V%($&t%`4r?lmA=*;`6@Zpu(A9G|;fbWz8xWFchJ4av5'
    '9_D@d(}T<Zw{$nm-wu~=5}ggnhxnI|MbqehKqcm7(qk+AzY@SzDHwJZ1m{)vfQeb=5?7W*fz(cEY83XBFCGdK@X@4P69)F3r60ef'
    '-8sfo=BXGJ`Rc={T6KWtN^4K9;bYGV9aJFv&U*33e$Spysh!mpRXNWkl)rAPDDYD+doF#-j<s4^Z8o=8EPg6Xr{hz)`^EM6kS^B{'
    '5n2T^eU3^qzHOQo%G_sBx%Zk;jXHIhmYo>gk30Bw{4K4;s4HmWD$L=MZBZ=Q*p)-TxY8O)XWWf&v0l~QYCQDA{ykh5Ri?=k&q|+l'
    'ru9{7bk$?Nlp4CewB!Oxr~*?z?q7drXvybA?br=bYr|36&KDPmTeQx7h*c-N%e%|{3!mc4j%Th0^4>Lb3)feX`wBa`^r(-n@d5!*'
    'xy`ly=e0}!tAxFLhiGJH(w;%;8dykM$m}~09-yCj-8q~@Lblw#{JGmVJ-%Lk4!*m5>I#4At)qpgGu&hil-NC|pU|}$E&UA}*|&bV'
    ')S8^RtWUF3@+C`Md=F*e54r)m&=ljGU4H~5>?@bUr!YKS#)8JtO<F{k)vYoKd39}16Iz8sm;}d8rZLas&0E;_BwEkkdYPv8fNX%g'
    'F<={b_=Ea5x!EOGwLIg7ZT#`__4u$4(2T>cNC4_|D-8=pDAfob>V(wkF{zF{uj+<}@sz&6bQCJ{-9Mj($H%QKYZ^1<@8VDh1%ZLN'
    '9LE}OXi|}5j5#mxof{4YVCixbwrSL9jm4yMa}}*c(BPumR*VrMp}f+*w6l0S6A<<$1bsX7LmA|fMKdDJnH#BsZdH<lxgK>Hg95W$'
    'aUb2373eS2n%=lngP%NN#p!lVLqLIpo#4(*Q&aA!hEBiy)8XOq_2sj-et%|FeUjmS`e%}OgVj_-7k8sq7gegazMj8HX0KEPtpy+g'
    '?p{2WqTZ1u{b@H=|CHt+KK;0{C_V0mmw0sBz|o*el%}acg7h^w6_c-5S<+T&4}Ibkr*;Q8`rgL2NIQ!!Ao3@Vr3kFS6*|w|qWWmH'
    'KI?H>1h8%gWoEss-^h)Zmz1hGn~|Mr_KFD60Uy<3ZR$pFb&ZhMw8OG<$v0>$V&$FpFg$%bKHa_g_cpSYy6_>mBXwNhVN)|j`3Gw4'
    'yEe}kG_hPUDva;l$EouCbmmHYetw$%Pm@QsH}=1cPV)X%PMne`u+~g-1J9J+b{%@ASA=_7Nx6mwo&hNL{dzV-gJaiyU^{OB!n&=?'
    'S#LGA1uEe*iK#-W?^n%H;ZH2mVf&DLE(k|AZe}HMo=!J1>F~V!_{@#(RT`KIP*joJ#uJu_x2E<U=Gq_05}O_LtId6luZR2jg#YXX'
    'Tt&7H5vUk?3?MzKY!(FCwhaUXMyB0T20t_Z_~y=--4Bm#gNNd?i{~XIO!%6Rx-7cEnhY2@O%aTTJoVMbH+IkldU|`QXVUp)WI>;*'
    'z@F=L%X7S(Igf5fsbO5;)8Q8)oabHt7wqi8oprD2F+6GYT|Q+=gdSnhy4F%X*tzJb%@0x<QDfA++QwZy)*s*1Dd`a-e(2C%zEsBn'
    '$*Tn}dUu&XHTxjv-cfVnux+6NQ2%cH_|~q8U9&vH*>~{q=f&@$)AUDhicqS799<9f+VB^AmgjW+@NKPRU&qI<!}A6^8fmf-=523M'
    '#|D}pLmB|a2mnf47fz72$G_l=ovy-N@O7)tDN4Y0rUHQ2b}MAMpp0itF$GDj@Zhra@l8D+zO3ws11X5gcgIIr0~TF|iavmL1;p)^'
    'vFm&cT33@q*8_vErvC+dTQi*<ZTBwCc^~aH<k#NWQw^(#5-hY<B4Q(@8T$Med<1VofXmxi^pCMXL9$XC&`<{!YC>}%BhLen)-QD<'
    '+_;^$J$%0Is?_hdsNP>Wj{#S8ZYCUML<!Wb5o!Uo&D)#b;`d#x7v%=)CZH?iZ1>?HPE|fdi8mYzt~(ZG2o(^UKm2^oA^tL?6C$Is'
    'bmh2^Q6V6#_$*>P2tiawEAOG5RsGSu?D)(IjG7?zp=7jBM!a2}_EA1e-2mO3=yC@A?DoT3IoA(={@6AmKo;fF((0THBZ$2$3C@uI'
    '7ynl2g+)gN0RGXfU9lygAizgd#Mh$d(Gpc=$^Y_Vz?q`8X#*b5E>x5A;VA?}=bfb@y|p4%Kz5j3wz1$vH)qKv-B6`%H}#QE^%(@B'
    'DPiJpa%IiXme=fItB6&lDME^_Zj}cL0*bscxXjv0Gbx6GvL%(<|GRfKn)G`!YKCgji$@nKiB5VoJhFw94S_n>g~<D#9ZuKZ@UU#5'
    '7OBwSN8%cyDAxOjCi-DSOB2$|==6u^arzm9b3RULaarbY|M?D8{|AZIUHr3+ew}3<;1bg}?z1$)uWE`Cr>knpF__|IJEY6Y2IcTF'
    'CezOg+PS_!mn1?|l^C=t?lH70&P*xb>1CCdmpLUo>wn(p_4egh2h1`qbxYiaR4Iv8w3WJ45&aX<%>0ud74TPj2vq#@@bq$^oRTQ7'
    'OqZ7p4!P`n#=L_DyGqD$vV77jsv|89T4k|l7ipJWTyi}r5_5mQNoUKW7SPZ~_?>X1GJMuK1GzOx;oePk-$V@f*&X{I3!aD}m(R%%'
    '$X;D$SZV;@R-3UwfO6u?UNumk>f&kR_dSotZ+E}Bwdd`W28`LOscWA$a0JGW`UR_521IKtLz&?`&i&7t*Qab{PQM-EEvoMxUt;w='
    'iCz}s1T>NWEPe1P7VD_Gl=&{n5&u1#H9d!|Md#u1CA2eZg!zvZJ-r|FsA?y#5jU!X;*NtZlm0a<K^Se@kVv9#wQ1jq&)-$mkBWlt'
    'e|$Nx712?hvd+=f(;(VGUIC%!cF<w~XBsQzI1M-M;PLVB`t5GdMy6nE>n5dkZR3`S+?Y7Ej^r$2Jz6jd!%$zjkzEe~U#8Js8^zly'
    'h@veppg@k0e+)%4PTfH5Kx%mH+SBpg{c=2|@MqfN_Sq*94wQ+Stsi~bZkR&z0=ynfK7tfI=1!JBU%Q(XFuwbeG~BmZj)-0;#=ZsJ'
    'd||DMd<>(Z>Qb}xRSQXm!Kuo2Z(%(LyWRy#0cmo%2xvhyqkxC#hf+G)|1cx(0j5>#ei#3DyaSz!ZyQS@*>=(jjKqw**6*An0JcJ{'
    'cDky##V*i#E%z=tr{`aFukMc1>;2*PUC$n@8cXY2fleAJ4;qhBT<4^((93a|5SU~qH*Vp}<Llj5{K)(Cya8+KDb9+=I;Yyk%5L+j'
    'l$d~Y%IK{XICkDf%Kn0VAVs_0QQbFqMp`tY0^%4BX|pWR_M4+*3NAuLPEK7@mib?^p%q}-(Tol-ybj$)IW5IB>-<tn)Kti%3MpP;'
    '3f@)O+_)<j_Y-Es^Wj&2`}TJi6E9T|YD!<pftV~TK&DnlmLhZRbi3w|MQb4xH}2<zKn#D}3usXzrNety?4Kdk4DnZXlr2qNM|ZwP'
    'AxUgJs>t74E&IGo^{t=P)%(edQQ(+pM~bdjOJLDZNqA<n8eB-7B;VyvT}6JrpKr(M*Igg?&_xeNQQek#gR6tT<4Ox5e`unXU@ge}'
    'muc_9=W200Jj`3{OO<LU!vwP_r%QK6kw6ia<|eSSTyP~qotoX>^W$MUR-c!{?=OM+ui)q9xE7in37tGb?=i~apbJPR1NDF$t3hNP'
    'ZFk-J|DsIozE+g!L(ok%kFds~Ppw|AIJs1~M0%rbu=@aI*KOn}tX7`(Z-R_TDWt6!>;MqmFalS@?1m(UNG9(HPysJ{H{riEh#FVi'
    '@l~W$bEuGkVEu?f<WiM>I-g_}OTs0X1|{i@J2>S#yProWI#js<a}fb6;`PB1N94qOeu&|?(P&p!yYKqnj{f#;wKR%qbt5`St1{iY'
    'QUn--!j?tKZ&6_hos<G6ScThbk2@Faef$m`x>iHmhd=^b1BccXS=KluSf~qw;$~|>f|)=5d)g(v(sPG0#0T%X@}ieMG)@J~p>e~@'
    '^m6F6{=?Ris}$|6F5l1z_o1NZ^@#JN-(O`3V~Qt0m^pPCxc)L>C~XCteL88KC%97%aL27EqGPT4CIXVROz`*mq}`sXy^F2C^muLu'
    '$A7##{Tnia`yFl908Jg;S;fu<qeXl{>L``#9zJf8!&V@C%-Jp5IXpz;7w2MpUD$QqJ-&`_T$syy67pTXKwRhq_-+FB%sO{n$JvUi'
    'BVfD{H~&L>3UwR3RJwO9Z86uFmV_3e0WW~=z)}-BH=iKtdoWE|2YYS!nI+N{`}v`LBRyEs%i-JQYswvn!A?J-?4=Hl+lmCx*P-L<'
    '0}73q{C6I1+10(LquZOdLbJD!MU#Hw$))C*J*XT@ND-nH7lJ#01w16bWe?xhcA%ET)*cEt7W4(e17MOq!t-3%&P?6Me#Bz5-*LWW'
    '4`J_P4^Q)sXOY}YWhkDwo;fMtcI+6O6P5_140A)y0Fap4TlS$f8rAsYs~-HW!=dKxRl<}8K5Z03%tk3cXAe8lF6x%JwVM8>!?A)j'
    'cc**n^krXuKbgC^Q4h*qvA4zm$w0X{ODF*tfK!~BblcYhn?F7Q0M5Jl$G7_pQk`UmyaWN!eZmk(y;Jf3Ql%j+3HfeQMf?00Y$g8e'
    'GG@SHrD^r6)5<C1N93`HF^I94<8A5#=kDg__Pqov^LcPsHqe_uF`?giXi|tmU|Zf4_*On6qv`mXpqHd{%SN7uZ;v!-&%qBqwf47&'
    '`~C)=sKVlL&`)VBWc!PXM+<GNkpeNQ9h!7g?0*Sm`n;n8sG{Zo8?}1kJm>JmbA1Q~c*-q|z?KzG1p^#!*~IC1O!o@0%X`2d3z^6a'
    'J9112;6lLPLViI$n&rTCyt{V)XES{rUfyIh!^`Hk5<Fo@c5sw+m!;Zp6+pL}1sT=%OS-IRANPl|?<S9D>nITJ*A0XKApyXZ^m|%-'
    't7sc&S7I-aw6JONI091X_6M;O3HEfm9LG>gYNiHJZFt;Bl2AX<wxyq1?)B8^)bPBJ8bt$DOjVPY6!5z@5;1)GW4cf0ylt9%A(6km'
    'd|llD?$dT%7CK~<geDWZTz2}2Ku~0XxP6c~^a3FR`S2I*X@{{F(g+_tBK&YR6lO{PrzPAu{b{d)2KZnYc7Mr+<^$Kgmkq{yLBc-i'
    'rD^nzVe{1l(Q0D<ny`l)Ev&00%DBH|M^EV=uUj!6nK_P*2*=Nh$zvpy9D#gLRkUwAl3T)<s{QDO?vGy%54*6IMw`qPnBszFb?Ib7'
    't1H=muw~g(x*@CJynJ*=(2wWPXgo}5*I|Ng1cJNv5p_$wu|97UDtd_HEQtsKvs>xIPfEk_yJ~uCPu`EWqbAXEY6U`FCLNz3US^Tu'
    ';rA|5iZp+8PtWPaP4xw~`!GB{e?4yOifFgO6@={ScQ)au5^r&qYgWOqn1djWqWzcc>h<ydI9!IBmq6ha@T^3!dHH}SMG$iq#Alu8'
    'K<W{is;2npo?ec>riU|a_HwcX!wpvKq+S_n**M{$XoQYK{?wNQ??r5Hym>?O{1j;XQ%dn~JZy3VU0cdV>KBw3Xdd2a7j|~cLU0<p'
    'ip4Gp`OTryKZr)f-Pf0w$6bL*NYpniR$c|K2Em}h`b0=@zu;JMp=x-y=FLYp^gKNs9`{`Rx>{qyE))_`t1oF(C4WFzUZKiw?jWHe'
    'RdRk{L)$b{J(4^e2vn4FAv0FVs;=21kZAFZbh!{w)#J?{{Cxa2h|}x!@h`9M%kesQP6x^uEZoS6R*amm688rERl>w(B8;6rxTX6;'
    'NNsnZb;^{kN>t5Eu@?#%DAo)aW~9~?QpGORJR(x{SL{bslMY)(K;d9F^Ln3L5Hb<cHtehT(3r>|m=)0w)H=;RxS^0U@t4~bp^5u2'
    'B@lcv-!#ltxdq<D_d%2o_q1774XY?`-O`D1^!*$AL2-8Z)z#rrR_OyWAsD35G@)(u?G-t^H%2lq)oJ!uZ7cqY%DBUlRZ8Nug_9Kz'
    'C(LB5#i@k^@&)U>UC1OQciH_#`&zc`ZNe!!h0%N#T0r$MZ3WSl%o`C$tb|6kv@{>wP~56JtgIQcL^xWoUc=|#SEn7(M=ws9ik^d%'
    '6z!q>gS$Dg9G`r2FBp)U$_gx3ghQ!DMafDhKzfx2uUoaqVJ@tbI9y<wesEXk`{VUt=fl#mh0Drs-R*-Cwx(|C@I(UV0l{PFgA>@4'
    '-ny+X$CqPp$|c<Ay=`RMi0mPFO$GIJ6)Z=DN(72g0id<mBFbTm-W<IHSqMIEz?PT4v61(Nj9+NhXbozm#;VKBr>1BECTnkMd@r|d'
    '<o-CXc2+0zsLO~?6;9-|dMG6QssV6mpw+2~w7p@w>~A7+e_$_B44q%nIehQBO27_zVA_gTR84a{%0T1_jR>zQ{K;BHlIrAR8(T%x'
    '^ZKPt$IVtmBxuq@gb9AOJqqv?#Bz)~qC!Pnv_e;K=+-@*VUd45rtK{?d9Q-a+aV-zP!fg<OHg<9WgTTPG7fcqdjVoqc6;adw-X$x'
    'q_AN+60n`-1ZR6r&23O^$?q}KP<?}Jesfy#aE!)Lpn3G~p4b-SH+P@m{ZGMFOsh~KI0Y#T3ny?*9&#pLI5*cH$2EsMl|wkQuNzU3'
    'qJ|LzB55ARWHEFDMG68DjmH#I8YbXly7`6$Eyl4{^9$MgkQ$KH5LU^d{}u_j<7oQFA5iQ~JfJFvtWC>Dc67FexO@2;u6via!wfi!'
    'K80l^i{X;iTVK}?(=>Ws*fA81H>XDDl1v>WIwBlylMX_g>s!aZhgtO!ZVCoRhupi+Jt$<8t)|A!_t<)q&in3;!p*KNz^sj9zWi0L'
    '2&C4M*Ue_FrSrw?gzV+^y{vaUX~*8LohY%A<9j!%!fJwj@E<4oP+8M@>R`w}%=>6QxTD{`?J)QV?+~bq!B0gh;MAQQ8dJL&*-FQ_'
    'm04mvOgHC2zjcwg{uXH3R(fyb6%eft$hwTN7nbhA9@3o^)ir-<Wl}$UU?=JK;LAtDdbjPU#e0*57(9%4Lo;$oRELJ{xLN(HgbEY0'
    'yN_(@us)r%_c8T3`Suj9$cQzlE#ZNOam6C83WFFJNEot|{l|86+)<Ai_Y+xJFn3KNnek_Hg>*?p5JpA#<`EIw+ab@`$xC1i$EOX-'
    'VHL@G8Lkd3@;2{GvPbdRytGslQ5h~F0sO!|&Sb!8OK*r~hgr<042I7#h=uQ@`NKZ0oWm5wCr?Q`rjKmp`#mKBZsa+WikUGbgagV;'
    '#?oX=bNE&YgieX7-fiv^|0_1L-5msgg<6PS-B;ZP0;63?wF>?LGSK%Wo*-%bz-B^TxS^dA%0m7U?s{zf>N3psrkDgLRmP5yfDJqd'
    '#_1!wcnP=8yC89GVo}QBXo+f8OQ$5H_M>Yo+(GPuC<!uC@q8rqe$OEiP6&<vhS?K;4OV-`YT=^y8it;Ux2CC5RWcm`+8-@9r&<5X'
    'J@3}W=7x};3pPC>=pDHXcIrjN+$U`dC8v`N^a*$RTP{ftCNvYUloQ8xL;R-o#(l7gp@?I6v0)m+pIni?Wjq~-vkYs0ZuNN2is#MX'
    'VExaVy=|G~5atxKya{xvHCTr?+Nh%HC3aaf#8?>br##@3o+Pk;?oYgdD7y_>aJ)5=Fz=u#W;P=3NVa-Z1m?3Cg4lR0V6T8H-r3h$'
    'BJAE38T=G4i#0I!NK#^*T~;2fVT&-b({S!Rz_z-1SLf!*-u+00L6jreg3dsE=bCSr2{`(Ml`bjG41>P%{O0}q$fDf4DM=qTKpxc-'
    'in6XjcnpR#JwAHfFsMB{n=8_-pKdDt+5SDPt#2Fv@^18Ti7DU^=9NWgBvBWsv!Iq|x9(|r8lJzhg?u=^4BPr|uoCV}9~ugl9q>~m'
    '^00rMvBT602)GKq;tGD;zwPFXS?nJU<c-CkQuE(T|BEmn3oVGmd9Uy?hiF!ct(#-OpJAt+n+jW@8GC}D4(~rErLn}%%u+(@W+f_9'
    'CP^OV`D2@kYIwI@AD@+SIhh7Zj>8z-m_C+1nIgFj96WSGWpnF}z9T8SH^kVr7$?HhI>o&jW1KPr(&U09h?s=_xh(nS_ZAOlc-HN{'
    'B0j2j3)!JsxDG!916rkD`la&JnnAx>-M!M^x}$UXDW7`%62k&Epm-<~F1y)R;a<Xm203|&QM_d|z8cjQi4~z_^Wp8B+BwJl*PGs3'
    'xNbU3aHl1%IkP51JE__M6~gQiF3OlbxU;o4uy;=}Yp@Q5m);zqgN#gT1!X}sS_L33lkD1`j_bK<PtRXpUm{`Lf1iL(1*AOeT2Z@7'
    'E=!s{ZeGM8Dk#MU&4=Q3_rA^>S&#PfTg04RS0m{cyag%T;c{}~_DWzDb&x@3*5(?DZbEpg?;KN@m++43`;YACIQ}AOQl$!;xWy0i'
    'h7m>>D$%*pqcP{leG9)ap&TAIhX$7T*xhnX!t|3p{ppW3Q%e&?y{Rrt>^T`R$bhtPTEdrPRI|GMdWtBl`*)Psey2~-ikD0NdwzKt'
    'jZy)jP-Z}d(DBGemIw)uu@3k>#`VX#<ENG@?``JX?>;}7^WUB8`O8}g{hXQIQbjms85B|@Kr5y!5)cd={b$tLE9lPeY-Ka`cR@f{'
    'Fsno7qfVa2XrdzK2MfFipEZpAYX5ijGK?U~Gr@TM&q3~e-e9)I_y}H$o<<YScxZSKu_Xur48m}Lw3TC;(nof&^&~_Ta|pt1&e0^U'
    'OEE63h(RR`BALCSCi2P2_NUROqxo=%515_~`gTA3v68MgG-kmgjse^Z<?5jHs+b$N6LNwQ8t`7L-LD`+o%TV>H$0uK?oKL_t@@bU'
    '3js5t2tZ>AM;Mqk0+i-H{v5h@W{T8u-8NWr-#rbH1>Sv$zi#!>!}OM-W{y;uSrefI;@Xl0UTbK8{){ozvY+nyUHI>xH>}vgTcnM-'
    '064pV3(Sx)V2VDj8vI$ZU!8`bX|7xR^a|n_?0OGa6>vr-bV!S=O?Z=PM`3~EF>+83ZLT4N)fM`<v&<^=Gv}IaTg!tKOK8jt8~b%M'
    'EfdpQTYQqZsB`@(_B#S$JzlqoGwk_x5H=j>6xu0}-!OVMI%El2o`RdNOwg@>(zpY8cjbB1cjEN4Pa2rVbd*^u4&{z#mO2)Jx{M|-'
    '?-}o?rA9X}EM2z)gpy&MIJuu6Kx~W*C^Y*b!%$K0-Q7;4B2LDD3C8|EHJ!V-ja8DeEd?3#&>wKIAk=B%nm|BSQw!cOkkW_`-k0-I'
    'U-=r&A^L|$u**V?mqixZ&@LwHMtC%$Z55WmJWw`+AB~GNUin7!v__#azR->3X~0qWS${=^1*8LXnE9ncI|Zf2ZOZh5Ti12VzaC_I'
    'FE1O1k(SM`;~5|KB^XS<D5nSIT!F$8q~0k2yK=sI?dN|Uwz|_XAvZ{%%7ReFvWE!9ZcJrT=`kAtednQt-o19X)1PQf-@>{i<`$%J'
    'kLOgyWU0V>4Rl=s1K_T7XNKTB0)|*_=P^T}E<U)EO>K}#YD@sS0s}WZ$T{i8L|Bv|W208@ElRSb8n53*tbXQt?W9&1^3zjDQ8&hf'
    'XOIo&JNHExC4>c78Tc~f>57*VlAuq)<No7MsRW<ABzmn7^ClmT-=FWJi%rG<$Y|!6B!;Rhkos!yoG5jh>h@jzay+cMidExrx7-h3'
    'Hf))r^{ho6?4dc70^ybv7ky48EcXgK7(=j%+jn%*g<^XsbH8j&$ziFt#9(DEe?k^yiKo~S3YZ{$>#D^}24mm*+qZ+Yc%&dczdf@T'
    'mM7GP4Jb!PFI@7<GIS<<#B}#ucIL2kF)kxitTk_vt%4~9z`l-Z8nmx|-xw3cyP}K$T9OB~JXX9BWDaKrJqMbU#f;Tr3l>eks}t8='
    '{4NW^P-X|txOSXb9`cwLV6%2uvu(=?u+Wck_o_aNjcmeKIFC~v6OiUmFqUC~p9e3>UFs`UGV|@<D%H;|rhhZ);@0`=mZ8lO)YwQR'
    'I3Gd@P%#U>60;$igaz0cW>}*=<vZ6uq0JixfiYcGV+#n^14hE#UOmGbYK~5Y$4+9EvSsIrXNAC<ns!gG%`^lVflG?cgjpc1S=mJP'
    'NOu-po2gj)O`Ey&+YXLTWE)Vw&8cH;3>HvO$Gqg2y-7WZ`(Cd?1ujCyQ5k`|nX!Fe_MfM8@hDB&vMc97r=w}~gh>H9ubk+{VA}_C'
    'KxZ*Y*o?fzeBHS;M+RTgzaD)sHIJ8HI_HBfh)^-^dkQH;876p?BCt+O6X=wpdcJN0tB_}7*cGZ1ZUmo}AqIj3kXnW7+#DW-Id*`d'
    '=tZ{ok*^b%H;AZojLNYXYy}1sr1);e&@p`!Td0XbOnu!HH5`tCm`0%f{c*Z`d41UORtwdQI}2KiSWd>3Vn`>AwC%7hj}cSULDQz}'
    'HP&5`wRpPQ<K$%c^(v7FWyBIADdeNjswt%E=t9hIV|r1xXVpI*CZdB`=-O#d6MQ-ZzzI7_Mb^bcZR=@W#mB5HYT0fVlH(nVpZ!!%'
    '_5^p^=HqT4H-bLT5EHA5K*msfeL^~T`GN+h6%#^@Jxc?1mp`ui<yNT!J<Uu!a(RHK7D*o8b91|>KiAjaRGao9zods>*_(gHs)56}'
    'Ha2|n%*-&tBIZD$AEg*XJ4J@ihXBE4Hbc{gyeVmVTl6$1JVr*2!AV;VUpC7AI;QG?15wLiK13dJ0O?1h+7UX*8CY&iJ6C_RFMpdc'
    'EfxBbHl8}~{ngcx+I4-zbivRtzS(uSJ3{HiPinz_=N48X=i#EUEkKs9J%T;b@eqVAk&HS+Re^t(oV+ZGlTG>I+luE_=dPE{nNg#M'
    'NG(P~!}vV!6tD(r4BH`=d#p`=>i+!x%2&Seoc2M+3E(0uSk|$qSiNqFp^i+YS?~fmw{+KRVaGG4tl(<kAg49QbY;*vDFA}K%A%?='
    '!+Q$9zl~+T87DUEHcwM2dbO^_ia&w>z{#+nr;-urbcI!?9_pfLy0z$WehpiZ*T<hKe}DX$y_g}zlWDPz(>pT*cnL06B!dXkIF>PM'
    'db46at@ylJL_hDUOBriwMiqgVX*3v%kmK>R-ZL%@a*>hJ(UWb*y$e5vlGlia4W+ZDK`;gS=xa3LI)o%C6L64Yq6Tphq0f+SvMjzY'
    'yLQ4i1>gK@p!RwO$V;Lng<7C>k`Wb5I|MXA{+%{C;onzX$u7J6V%Wps=(i~}OcXIo8&1sFs|b?p9kdbHu<{P8cdi^|#bKLU-Go1a'
    'Kk9J`QC13>UZg`ze!~~jC(QLX&-=ZLt~{DIu?=-w$bmMWx$H}=CbMG!hI45S2lgDrHZ`ZBy5-uShRipKbZ?tD(`VF<TMFAMfIqh+'
    '?3I9pSX1X*`@V@@zCp+F^A(fzb?dHptYZ0bL*3hH$>4agUF;%uhc%D`#w@lCF;uw3NYLh;Yrm-qrDT_vbrBjl6q8H!EdBc6orG3}'
    '#L+lDx{RDKZ0>e0yWIb=;h1IaAxs;_E+9kq<TwpWW$k}S??{D8oC_=1x!hr1EtrO1F9ym5pstM{L$kBMBlK9hC{a7WuBSbO-K-RF'
    '?{PXcTprS^a`AFT4^M}NfibmzRm}YU!Y`S6+n8+J86|}jyC3#0{LAaN%V($#Tf>-rO{JcP7J=U+L2nazZ5S}}B8&Mg&Cc~sL&)x)'
    'zd;}_K44v(A*7$7cPtq?HRb{LA#Rcq=b*TV8&ZH}@49dF+wE7IBiRKIz{patbciTpU@a;b5i)4&tlG`En66%VXQcAU>YQL5BtN>6'
    'VuVp?sr_xF5vDCUH&x@Z>4*J&{p0c1jXvhutaZV&qVGe0GZIbn)nHSL85W#hqdls<Q6lE8Zz!UCG~tj;knQ3lR^zkh1^|bP6jE5#'
    'Io@@(cfHs9m%}=z^m18f^ip`x1}!fHykNCHTKF-46By69S-Ym#eV*P1e=dXN_bERC+CozbU+938V-yr7fmteC_IPu_AXLp@pPf7S'
    '!6A9q^2QlSZ+P(_{BlzbKiWX>fO&4e6ex_Im`Myfmp}U=b5_59`MQAygxG^8Ek{K<8C^+MN$OMaSs#w;evQaZs<Lz8=Lx*D0V=`l'
    '-L*3k<`iD2JTI$&9h3(cSSr*An{9c`f}Zi_hl_U*9WLxehWfr8tv17(hVb?mwn*yWY_7w8_qxHPg5~W1sKJJz)>RIJqT4_q!f99p'
    '<4{2cMU8FgvDq7?zq=RxU_^EKr&B{rO&ha3e9BHTp+0mRbn1*d>YOpc33l%te8Oyj<bU8f{<@LD3x@p4f|~_;h<R0VO7qGWLB@81'
    'H_88DZ!UfA$E^8P+K|0gVJIl~Xu|PN!%FQPcCITylZa3hRWPQ#CCjPFefhU~rtCo%u0tjwsW}6uHilCQ;NeET0RXC-`KlG~aAq#v'
    'hY(o4iX6;iI<JuxE(^<J$`(=iGt+A{?#RooTlJLj9G;Im^t^@yQGff1MM$UGVDv;^pjSb;Od>OJH4o+P-_5%0wEpGHhx?rpkV_fq'
    'rw?lVs#XC9eV@jyBW`-;v^R{rKCV#W>thgFHaY@`*&Zu<;&9@V<kY@wwSxXf^hhA7OT?DFH^s?Ab6?5eD>c`vL?c_X%NZG((Z(Ef'
    'mT)U74Zh=K+3zh^PKJ?TB>FV$aMv~+DOkkLam*4}iQ?|&CT5d_2qRx<ne$d=Ko$7#`_t(Sf4=iq*5-E`q?tard)m$PicJe`VCKrk'
    'tBsK?Q7)-rs0Z_F7Ji#lbsjl#`KZ-l)y<dAO@)8%=RyL)>!6B37FCP~7srd@s`bxK{rjxz!z9a-5Ahu)nGR=bMo&;*^O!CwFPrGI'
    '^G&zDKkeX*NZf~)`4j6GXu*a@C*PZnxJ*NY^&OrxB2^rTJVy6m3Paq+W|N!nr#<Xi*kjh-9|LTot<iHr)$(CSi&c+^V^G)}ms551'
    '!trl!P(v7Nz%ykmSd2<!CZr%;?J3d-7C=ETG#6*<4mr(_*>%*yI>)r%1yJf!a^eVy$WYZgsSnTX2Kzav>l-UR9v%r%wh}R=Q(!J*'
    'OpUB!K*3u68;&6_8BrCZjl6Ah^s}**KVDG58=*?jG_8iR40gsGCXYJis$m&6024I5*#tOQD6B_z?a!auK9}({Ll1+RqEd81#^ACm'
    '49ggD2KJw6*wi+JzFSZ8S*Q5h@O>`gr#Di<clW*BvkOVAhj1#030qZ6mjy;JbSVsGj7b3XOjR;&lT!C=XwPgzLSja#bZm-hqMkNp'
    'Cn&#Ur(j(+Au%NYZKe3ocJ@t?9L;Pp8kr^xl_PrWfG-ldJk%kjO+~0LH|5Tkcd|}ld>jrNV*wo)+>v3e2aEV1rRb>C$>}ksCKzET'
    'Sey1O=dFObqXgY!Uu*uK@dM15S;d;QD5ldDWl`vlA#uVU77prR+PCma6reQkW<$hN*sKtAU&pZP9YTArGu(yto>I<$6i2fUg~8nJ'
    'UVBx-o^IIm^t4Wd(6ife66HpXw=?3ka5)K%MTnPqoGC^<aQLs>hbZ-mO<c(&>S4WH0AlRpI;Wm{{Sb2?QFQ|eMmyu3xjpva#~u9g'
    '8VSyxpI;=iOREr)h5;1<0-Bw39{~IuvczayGxfh_@heWBUTh!ao|TFjl|&Y5WS?MI-hnJN?E**bu2}uLBS;M@2+7}RdU!XMY!ZP%'
    '9*VjmrcO_=JrjGjE?ac)<?e^M?fd5gA;&{a%g|$EcX{J6C`aojBNgvMPoZBAjhn9Bz&X>~HIfu2VEphD60`|3L%wZjSQi&G3Qn&b'
    'q<}6q=Tp76h5cipd;o2@#i(WVA>7lbWk6O*&=|uEs&yJje(g5)k3?NU{4U=3-$aAq{nN#qdO)X06y;v24jMLxL%p+uH?qv-s>A3j'
    '>;zeZ+>e6EMA(3<u*`@RxXP5#h#fXTlmFPlz9uB1KF5(_Ovsd`kh%cjuaIC11A=u3gD0GCD!TuD^*=KWS09p%3>bJ3MmYw4!ej9@'
    'bgHD_(Z>ln4H(UxSWO?=#ty<GN>biWie4$Hp0~G;Jw!9jqA!nG76t`FO}qR<``A4p)sz!OP#+KyCjv%GMfjBWk;&?%aqCi^E@gN1'
    'W@1q4-M-0NaXGL{GrE|Bs)JCA+F~WgOC8iokrLKe?(D1gfM4^FzHDnC!KR*nh{}rae=$SEP&3ZJIH`OZNXE+!KC{V1_~{0o!%}YR'
    'zR(Ph6p8pzKcWv?;$WGi@M`5CX}}8ey*8V#4H0icE_V&{vrM;Y6|(TmO)Cpz9i0UDA}eV^ggIS(D&MxSduS{|*@E+4g``FK*4FDa'
    '4m1d7=9p%y{TgF$ZrsQB`K-H)#!+%jBwC7?W?h6S&KT*WoB|g|vlsO&W^oq7wVOG$)}<E{YS3K_je6Q>)U{F<#S8!%-V1`%qML$='
    'pT$(=VZdaSSlzmhn6dD%W>_w&%_*Q--ffH+obxRF#wx&Bvl@&>io3LH6MWii)4sEpQ-*Cv4?Bc#s8NfmMqv>~^j?k13-y685dRPx'
    '!bwt^xA|>b*+b-JBsj$^LbmfP>0EQF&?$VxF;I-nony!~bnn{G1t@2*wbhWopF-i*j6i0V(5vSnRO*1Z=rpl0e$-y|bZyl5vv%Na'
    '7ydHRuOo_q?T~%xMl>l{O;h33@x5Yr3*f+~`pT{B^R03_7}i1-iWsU@LcrZeZX52qMD)I$xv9%*bM58+@a3zs@Or*bzaeOD=n6>b'
    'ox(c0n<fx|@(9p!63sS<(FQl@D+F)%+AQl!U~UiLNE*rS-SXsfJ#3091W65F{a)yH%i9YUBZ?K$KvArSdSv$3Yquhb;};AMuaAz&'
    'S_>YJ%f>i0aK5IFGz$j^hZASohruKY=_14N(5@_}`PzqKRP4jgu982slQ8b;a6knPdh{p;T1&j$SdW97b!&qrUTlJ`|GxAOJ%;s#'
    'T;s`{#Zb3U(#K>GeyAF11UFc;H6^{)mblL9a=iAF#pAw?z>Qof;mLA^Pt5Kp@#bQRnLD3+u#P$PQ?OF%+xM}_-7+S_|1oWyml80z'
    '2=3_;b}9ymsYQaCh`n|7JrY~EO1Myl-7)~2&vG8~1X#m*I>F2&pdFL82x6D&=!Sh<A!M)!M26{C;9?a@Io`2RL7B+eMJ%aS6P|3k'
    'VHZ0k1zJGby7FLRKb-(GZ~ZT2Y9A#l?Y|*GEI6*N(oRadyR-6ct3*RZ>S^fJs8BoM6tF!71sU60r+_jsuM-~OwR^aZ3#|}leIi=;'
    'GTp2gXcUjx5LDeJCIew&I~-R(2+?6R^*MJcw}%}9^%0<9CJ;oKFtJ5|*@|g15+b`9!lLc!59FGG?^ASy5DvrANN_*}11IOvYLJXi'
    'G5EKthpW@y^A3EY5khy(p4P9W5yKAGDMa%S&6#K!s6nt6Zez2mjS``_Z6lAzHKe=Q4%4q2<_`c2?AAD?p<eR_6sVAH<SIo|jDBB&'
    'i_+b;k(Dm6=fz}_O7;s$CeFwxMzD>f0bQKTpvEMqdkjCkHd;Ky`hhJ5aRQ5<E%8QE%IPrC7<~bG(A{MN`q^wiOpVAxJ{xSi@#;_I'
    '+}^yduS^7mr=eJ#psUeI4aPh2vwbx&Ar$dYMwB<V?d94IGrvNRa~_<(j2i&un>GlwSPEwf-*gl9+C@9wwwn{BW!FYfvv7l4YAD$-'
    'jcNsf*YRd;*jejM<v~lo`W3C(&vSmhQv(WJP$<Tb(3o<J@HsYhP!bWi2RAP(EKjEyuT2FX57Y7cPPW5pST;(-tP?y}nldtH4=4}%'
    'Z5fIIma4|94Y%y#^j^NCBPW|Jj;49S=qG$e%)ek?gisZNF1(kZdCNaS(6&A6;iua;hZ80mF;U_0u!Xr8Z{u#&kdg{bAzE<XIJhS8'
    'Py=CU&{SyS<u^T&w{Q6hj*4Cd>kM*+C5w4s;;G`P%EM|XUs8bzp25zq&fC}R{J>@14UwXrDJB)wav)7JZM?~SXvTxfmju%Orf~nc'
    'X*+Mm;!5l<d(=y^fOch2tLJJ`b(2d36y<(Y;4mT`ZmqrHrf=v>wB7q$@)%4qWPI!h60|d2#~`3Nbcu>!hbG*0v*p@L`Cs=>F!%T2'
    'bR7NEv-T1$exMjykQmfR0v*m3C~kmU1gC5BMsH_KE0!H~p6Se+#Y9{^03l=)mN?vaCgx!DM;Ot#$1EJMuS~b;s_Qp0v-JG_FubZS'
    'hgI;uNy72P)G;)m3oSSrqql~)N=6El&>NgW2-Y^&ZpeQ*Kh0~pV1NgSBqDtDA#rD7V`j2?9EiJ947EgS5pS;D$bSBAOr{?6eS-ln'
    '%rVYIL!-G{9gFZDYY8?{z_n2hPIoqYpA1zWnDcM!BEpETH~@8e3;G8jO}JfDxTRE)5&TKGuiV82hV7rqOgBv*w`?7NzGg=oHAb&B'
    'Uxwo}ZC;qFEZ2T0QQ!JJVj$$!fCSR*xz>B9=m`(d7+Aq}KBlj6zLb&}<&7ZMU5kL6$*y;21!|b^Y?L;*)6QZSHdPSHDtLf6D|yVv'
    'h5_(0j#hDh<u=Y@`nTO|5_I$sa`dsf3ff=rG2AJ93uGt*k+Vi2U>lxZUcU`Swjr~YAD-&0%VCSY40$d_I%1%PMLGse6LaK!v)D`U'
    'IUj9v?Z<hd13#vX&@h^YuG<&hRGBeX;wDNi7p69DIqw2|r!PBKH?6*pjNAoaYEWw-?+8Of&K0d#pl1%9)CIM_P6~hRdsyAWPEH|v'
    'pzI*$EDj<A9`-Lr$I00H*pynYh~b-9;6dBi+QoGdX$&V`0}YZlJj8fo;#^|J3TH-jfW)S>#aG!{^}B_|_e<(L=4WH_&=90|+IsFy'
    'gRYWZmX>smpAyO}8u%&h?s50(JIvaA+!#TKoUM7spuKqUlq{Y;Zg#`XLSnU~O?J+|JUjMBKjSSMRELbCy(FpidCB~1jc&wJwlGD|'
    'qT96TwtEgU@7=q9vT!hH4{S4|-Wk7AxMAtArWn+&sZ35vAg=q|bo*A^9oV=LGNjfN(}!U><g%IB(V1AG;Bwhd;Up&PZvN2q8{U@#'
    'mRQv$rF2zg6m5@hOqR0_!*G6)&&+5GFSUNxiV?H+5&G%O@ygsHBP?CEDe1$@Wkb16YQknHv|s8?P4ExP?uiuUu%xhEY+{~{`h-=l'
    'S*3BTAwZPp7&TCjO~=O{R>et<KJ;bSiAcrVSYKrx&W>iMIZot9Vni0>SvVXSp|e@D{;=xK8-g?>uUPvGVOOQYjGbSDg9+TZotrcO'
    '%`oX?6BquEg?Efn!qw&S!q9c<V&G|mJ%o}mKniMwa_0?@*aHyWTl!RsfBG?D|Mapo_FY~q3yMjZ{30MnMU2LVV@+`lu)`LoYhC4c'
    'Z$vfaa(wz0Jwxh@;r@^Rz99nw6By^Nkjq4V-O89RZ{RelLmok6HDGJrca;5cy)$bv5Rfe|ede7Z_F$*q0kc`(i3)OGX^145#c$Nx'
    '3v;w9mObPB+iOQh(s;xapAI>n_Di_u*G42W3R@Da*)ANcYuA1Qw|8s-&VeV6hNlYB_X?*{11-a}fG#?PJ|e}y=yy-Gs^=y4@JV^N'
    'm=62*U!IQ-7k)AP6CW4TC}xDv)y1%S<|`>^XMitqz6DS8-5kd%zaV9NTHBmZwx1v4AMc)Q2~iVvmAO(NrE0ws48Slq4#kS-tPF_s'
    'eNKLi<2(<!e*P3QF#rDY`^%+KKSd8Q)8d^yL1F|Yw{*G*PeC?a<UJxs@xG!=2>kT+BY!T)`0>Z-I@rHHgx0MIlBy?FwE=zVYfN)q'
    'O;d=9-k((!s|BAr{_fL?wQqE#NVbtYxIU{FbSjM^MB7t2XcN}B?l1;s?eEr2&+@8I_#Dw&I2W$|<nH_@ci+7OE~hVb%n?Ru;X=vM'
    '!;~}}2cr<>F2QvG!QkWgXYXy|`|o{<zU<R>AS7~D5p;m_Jajga74~)X^Oe~WYW5*Kq0G7a*$Il4>*sO!)j9qCA2)(-7`vO{ssd0A'
    '4YZJy^DRabGm1&%&qEK}S3A}^&A5E||BnA}x?khLe;Z!DZeXy^3VyzXTOkx!>=<9=Jgjr+0wDLc+n*Ptr`0t{rmvsQ><pT~<Kwmp'
    'k`o}F2w`gkg#saAiXl{No5g!WG3WsaP=8AP{Mnl4ziwDSP_{b7H1g<$L^4%L@2bn)tX3B#xDFUnq>Uv{S^nphLANmk+wfAHITu_J'
    'c0)9VgQNvjj8-XZMhH@HPUn5=&641k4VhMa9V$hZY3ONw7;8RKYH~|cOxfpWLH+nCCG98ceR(y`aD$;(_Cs_<;f=0KnIM-*tTWv|'
    '5({1vVgv4Mzi&N0WiMN^Kbx3X#COjRGGQEN+4GHQ845_5U^vLeT-NE`PjWhZI{6JefBt${c#OmCPUF)aj~mf|Asb~VdqeK6#KJJ|'
    'uw@gHVDd0UOl3g{TCrp4SZkXTVZyx8Z2Yssrjug^qeGw!g{<aPIfR0VXKDRY{nURf__PAaTmIDSeE6X>c%AG+cp4MM`c7z4d9*6r'
    'uwpaPmMra9@%3?&nXfb~5zv92eNbJr<;3+WTKhJ^%78nVN~#;)TWwC^bB*5ohXmKx{~V@So8M#=CR}6?QXh&%z)C});$A`Zu0!!n'
    'i0jSfSFLJ#!C|9j8p9l2M}l(Gl5Pzpco}XMF(L`C!$7w>&(c-PZeCzhsOj~skg8K~SNIqVC}81k1ZZu885hGd@@p17)#8_L6KbP?'
    '{liq(j0PVp4vUHrl1Be4Rl!@;=gi()7H{a&`gwf%$19j)Ih^Js?|8Y=c{EI>*?``#Bng93d<|+B6=N7khR$Jn|0%z>@*bK9;R16R'
    '5kZ{ge1{vte?=M?b|s;B;eO0Ss<`@Bf87d9`jJiW_c31uqR^X3RNQ0gxGYkmFyT?Kb=NMuV|=U{LHk7I7L5fw6u%lbr&&QBL`P#$'
    'H0YSoy}R`D^K1Hq03&-@T@)W*hAp{5jqvOQxl?6KNLob*`5kQ!Tw+!;Bg?{qxZkzr_8q5PfKFZcImirEm>7G~F$z*iVHlf{@-85`'
    '@UG?dTyY>*NxeZThMq56ZN)3!68(d|2_#^Y=eNv#x}6KYY-OIPeblk6_Nj5gT;E7i&yw+3e8rxoK4O5e&3o&eF@{r)y(1^GcejcQ'
    '#vQ(d8#s><Acrzv{C9ZpLsS~ouH_zG--^MF83)Cx_e0Y%XUxRhFq+8xz41-_xFh`L;a}VBTJdKh{XfNd<5oJq01exeJ|I3KejYGj'
    '6<o?tA})a`kGmE-P2|}iL6J)JF*BL>a)U_$&4%HtZ80Zk$_R0B)S7p{hI3qh`|F<ZdO@0|u?Q@+56-MhT!(@K0+dxz7I?3{4Bh)n'
    '%6|?KPd}~4<@wFSW5cl}@1nKs&1p+GCLW?6?td^4<|+&S7Du<ede!Zz6xu;UOole<$E2NL)K_7viCj;}SH`!&PnB@%`lU7X=i_pj'
    '!%i_8bDzWDN{2A!ud%W(MF_B*gGOjDuBz(&tCI=-^EoJokFOgXP_w>7TEsr~4i(#}SykxuBK}FxG=zviOb*|_@{aVZVU`*=y=qWr'
    'M5|zl+A|adoUS7V+rl(uSFCBBf81|Kw$&9&9*D{imeznGCM;4Ew^|j>v5Hixum0La&$982`AJw1&}3qbsFoxQWAuY4@`C)t$<!Sq'
    'ndz@sJTiuz)4W1u$3c`f7wIcrYz6OybIVeR7jTi4|C~RrINGpBouQZEB<%WqBXyCifIVT2qdC21L%<;111U(hASISiO&C}#`<H)s'
    '{1z)e8)3RJQjYJ=ki`VGAmW*s6)dzd+zQ<bXmHvLz=z_RpMJiLPSUy!0GJAd|IuL9j-0}{%e;^}A$qkj>ZU6JFkOhL_AefPe)m0L'
    'KWuSl>%am$c{CWGcaSh^_6!UnizxWmppn<*b=tpv*hDV(0?S))`?Rt&Kc7R~+n;_uiE}@n(}lxXta{kjW{ZSUu8Z7-=2S#_4`nrK'
    '%2UK$z-A<xaN)K8>$m-{hV#y?H_&DpS7;uN1^&?(P@)`N#{*xPTZfX#C06d(`pJy)onZPWH+LDMer^u&j@Qcy$>0&%4wCcG_r}~Q'
    '7f83~h=<CEPIK)z?5M+17+(8+RG2UeBQgiAmVp{g81<d;(=B{vdt%yduuU!EF3L=^m3W2cwAdC?(PUy_+s6Sqh12Z2pHz&(Oy(e5'
    '4w&q5sr{;uY@4_NFbKgAf@+JS0$rSf%BywsZiRVr6Z$j;F=Tk!^SfAv>NH}n4ILm>kt4T^-dG!hmKA(K#@9i4H$Q)V`ZC^a{j4Tt'
    'l?Us?gc#=ZqJRWF)3o6l<o?lOX5f&@cR#EUTzxu$>xoD0=lQU#GYnr28y!xGt1c5WG8&&SdL)|+e=e@30U?;ND!~Io7kd}pPUdO?'
    ';jppP_N&52+WpF0I$<H$NK6_BV~+1*r2oF)pK9jIb;uOcpOxct&odnNgPbG91f(fsd2P%ha#W{g@5<ZoPo;mU_Tlir3rMc6!NAvG'
    'YD2m`#-Cz))Z@F)c3tbua^~}}HcvLpLjAX@t;|UaE`1S_3_D1H4vRYE>J%INm)<|De_m2-ed{h>hS`bY5v5R*d2V$yS}}x?)dmZi'
    'pnj-}q6ydTTlBjE`SMpu(wW6Dad>y6N*d<j9SQ3PhVvi`O(mbFVc(iNpq9XYefJE(gM}WIN1RjyB5qbv<xqK4K_uO`U?9-nBHC@p'
    '1eU&8hY2{cG2yh00Z&DkCI*>TgIbRMb1wYP)?9hSdm3+ggUTF-hlv|4LLZ`fZ78P)(BsbHJ&VWmQ=009bvNc0&=|xRrT8u=*cEjg'
    'NjjJsjR-Z3)Vx>6H`gtRqkOnr?u5>g2c}v&o@O5$7qF?MS5_8k*dk^{R_V%R-?Ewwm^KS5U1>fq1+FlXP$~EjvT=QK>S#Mq5$#-i'
    '6Br@;R$H;ZDx;SXYDyU161KKAZhDL*LqW^O-K%X9hQhPN8R~=CYH+h+%3K@lJGC?;G_#6%>^f%6RV)5%fX<&GcP`&CFDH;ukr1aZ'
    '3+|>NpC%Tg+R^Em_LA>g^jZ2j9xsoI1lgJ0*9E;S4)EGWz^x8yGfG(8Gg6|VU#?p5ZWDE8?hw<Cql=(a>%uRk!)f#iyO@9`Z}8>x'
    'eRch^yV$D1bTD-T_{=p3xjwjyrs;%^TbmQv&e;_=y6cu-H5VH!H1!6E50J>~F?!UHgE0J5u?bdf1Sx;oT(|B?(Xip~;8WG77L&S)'
    'Nw4=>nIYsxN7)uEa+R!x&fbHyrlB~TXFby8Y(A@3%kd#{LtvlaNH&2~qfF#GY6MswU)Ii7y&3&u00zPD9C6TbGUtPEz~CCAKfvx%'
    '-geaz{>Op-pa0MQ57G$!SO'
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
            'sha256:8527f25d58c8ebf8eebab8a9e43517899b7afce2e511026d2873a69ab82f1794')
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
