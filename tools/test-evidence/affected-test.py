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
# b689cd891d74b8541dddcaddeecacfa83196729e / tree 21c26d71d13a709d9b1f1d0efb1622eb05ddaed9.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '0cca47ea7b7e139d8d7249d61253939cb79892a4d6c410a44cc0c4c2c610c785'
_MAIN_PROJECTION_B85 = (
    'c-qa~*_Iqf(jDsi^B8?CG-4j~6k2DU`&u!007(`qt7~AB($c%1&myzXU^glwGK(4{{Xd%^)$SSLVQ#i<?`{9%Z-4)Cc=`G|ejXm?'
    'r{iJ%bo}Q-diwP8G(0>n>FMvkJRcwa_Fw<U-@YB^^tb=|w>-<5s`}f1`P=i?!QU3`oTWT#mU-^WtnTwU4MX1)%aXNoHH|4%ZPDfN'
    '|Ka72$M`Q8?~mi({^x)BzU*kB>FcM*<Naa!V`H^(EayCLQq#BDJfx{>+SVFb)@DoDjB~cMO*LfQ`>Q<;)33vq^y#0+r(c)*<3B%r'
    'Nq+6{ayULbZ!DgctSZ{9?dmR-MJm!zHp9I1b6V2e=Z*h8RH;kvFaDGskI#pf<I^9Xrmt!Gb!)|X^6-`^pW3{O2b@ysm%6f#x%Wf+'
    'ZYYZ?jTav7OL~6!^!$2wNuTEQm>%ZzFdfp?x<%IHbyqFzl4p67Pvbb3Rb9+;Jrr%<)=M+AV_7VF*4<ibSjuVa>!N9!-0Q8IVVUzH'
    '8>^zIvU%*&G>t<V^Y_<!dzH^#?o)br`Sg$1;r_53ruD7<{f}?=@2}p>g`ZZWYHUi+x5=8UsOmhg+c_`0x*F&B*{R*N`qS~3G`)O^'
    '-~N1g*{(0Lq0dv>PhBeNsjQ~V?{<KiJe%8mXo}jh{hnq2^H5z}x?Nh|O}XTC-Q{VV`e|<ZvdHpbnDV)s=C+;ts`|;h9iJ>GGEDae'
    'Px<q7`20(H`1SDc{Q1ie@A>hM_gBsHVXDSyD#og++Oep*xtWT*t<&tF)%jAVylu1MnpGeDaxeVyx(;!fsv)&qIc8H^%w4v0&hyZW'
    'OVJ8aU6vfN>()JvmseeerOmw5HWw4>BI}2&DBE(ZrapDm)Gos`)Lofhv+C39!^JhHylR?eUWR_Gy4KGd`m)LTE+5M@rlOk1tWC>u'
    ')tYgV@20O$$8YKGc{)B`{?$I0Ec0ZCylfihdP@CJmqVM?Md#b9r@5cI{JLko?%-kgmYxOfboZ2o$HT*yi`$qxr*~>n-BhAx%Bxi7'
    'eNk1zG&T{}s;bGWe7gQYJUo88n~o35;qv<Jkf){-$eJ!6@}isa#^+U!&CvO#i_GR)dn~VBKknuE?)Tr8@#6ZUbCy-rT-QQ%Q)iw;'
    'J@naBxFMa$(o@J%ISyB^?*zIkFRq=YrR)YFv-aVY?KrhlKIWy^R#($d<egyKWIKL)M3jFHe|&yOFA?ePo{q0C>25v@UmlLnFNf)J'
    'v?+UcMwhC*p6XP2{e73x;OflkM%0_;u^93?@2}p*>->0e;i7YkrMz%s_~7S0p1z$lQ@+enhk6;E#MHLC7d{=l^XhA27Dw<U{r++}'
    '0M$PBHVs8tmt9$=*i_x8cC2S#qdPUv#>mn(_i;bS3tx`k4$~)L@3+IV8`TH+d3c=<FL&n~FK*e3Uu0dUp_+?9HdrpA;XGHpJEn`6'
    'm^XF23{R%Lc{l4<86U^}@G6(Q9HrW(oZR|NUwI$RJdEOI-xd9`%x#%1d7d)KR(AVlUZs<lBjr2|c{deJw`8^7KGajux*B{Y(!IJ{'
    '>S3;AnEB0n_%%H}r2D(|EnVD6UyL5e+&1q0v22$rE0%FCnmTX$W@%F2w$5*{+`N--!-I5tzLVoS%1?jXeLXx!u5xi#SzKJrQgvgN'
    'CSjyawad&cDp$zmovyOVQ@VXu$I-v^+eR>Jrcx?8)uU)xjYZo!y+fJJrSvH|LE=~w|Md1<Jf16$;eP$9pN8q>a$xJ`sw>*6=oDC8'
    'BdXVR*-mpOUv#V`%!-ks8~dBLB&S;L4`05%?2fffTP`xHY^dtd)slSYd6&1H_!AFkE;BXT(vBb4(pI|V0o2*lWvvRdY*d>?WL>f>'
    'kEHkZvaam9vY2n)g0y26><+*Au<yP<qRUx;voefXzo_3lgR*Noaer(C-(}2mab^;KvfCfa^Na85@?q&6jW(7Z`?8xRmylw$m?saa'
    'RZg~TUH0_{zM_}m=}X#u3oH`eY?x-*$I>_>$%ma+ZS9b>@q`-rL7%1D-_j{teY*<A<LkpbYy=v|L<N>f&%KsRu{$)g|64axRpet+'
    'Wkaq`sM24wrybW*nU=h-`%z6+m8qZWDI1r0%5x{Vn;qkbIMb4Sa7XJMb+;=FPPP2K$X%E&#t!N+%xUbLY*o%smStU!i!|$l?=3z2'
    'c6d5IeDg1!Uft!gt_Yl`Us73)<5*9PD`FfPSW}aRZUi4JZuGhQ*q(OZqTNunL#e80n-KuiFLR~3m4GQPN4am~gSVsVuiMVuK@#}o'
    'bbD-Mg5%gZP;*;MnLs>xS!3T!edn?$-DzW53fukI)^57x#}=R^A$G=>zD=@_De6Sn2*jyutEDQ3xu5=`txd;oD^9ZYz?x-9WiOGh'
    '`dpxl_t{CBg>SoU=6qb-vt2p=HM@FFzomzbs#?j~Pj$RNMWg_bd0t(XyFQ9Cb<ogKARj)qpIwnadRX;kKnx(ye(IrseK}-}kADKl'
    '=8YGcD|0`%l^?RAZ-+f+ykD|%2!NqXKs?ah)YfC4j}Wb7cV#i895lOpY+u)>M&8>XXM}^)fK4#h0$i-}rl=h8rtAtktg>bN=)UAf'
    'chggX?Y<m_`{xaGK*?2Ag^RZ9M`_!#cvz7W<fCLa2gXXB=KjNb+LIELE`JBd|A7__dG4E+RfF^)H)Yo-Q1hXki{fLOxgmR#LyimN'
    'yJ>u3%I2YlnkK+^m8StrJr?f4yqG?=vFGFK6Hse9eob)e>2fw_y*X194W3M(Y-uk0CNHZ#N`PhRXAf-xF@11LkyYO9C}AN?@-<*z'
    '(bg)nWpvLJP?xzZ>IC-`p1SO(eV^;MvkZs(*A1YztGX!-sUEVb9wrTwR&G1US*F5cn#!{4HBj;op6i!ykIUgceXrIofBvmYzbOaR'
    '88}G9Y``)e%P8N?0+Q9)DeC5fr~BpU_4&n3@@x9zX$u<l&C4%+-_@9MXS(-}rXEn5jk!aWx}}=C^pT3-ip@lpot1eD6D|5~@%ENN'
    '46mv&^My@gRn|Q$V&C<D2C2{g<nnDXm(W1R0y^5(?h6HdCX=o6v6jffXzOn3x_ue;m)AAirKfL)=jXMDcrh6p`(8gH8XZfQG}ZJm'
    'rO~5q*U)MmY68t-&c2`g^%!sec-#v3aY3smx}k5YshX#{5Zct|of~}4@);cGGugN1DQ&qNI`e)ie0Zhy#~fJ{;5+32F0jes&e2!1'
    'hk0NA^x*RUE!_?Cx5MR|L}x?tA^zoK(KNarP>Fe&^w>)OuLN*a3Wl8p!Fkm^U}BcJ#Fb@HAhlDP8ijr3i-&>)d^9Q7gn@l$>Blc='
    'caAZYc`8OlzWOk#Rvn<Z(%O@2_}H^T2NejvvtInM-?QgaYG<`YRnBt><*(Z+3jEZ|o=cyyW384}o6YSNi=PV9>G+iHesMiMq{}r#'
    'gjT^!pQCDK)nC&>nfoj%_g*uqQKt^mvJ<2GaR=XyzooSpbp>r)g*jZZEs7-@yK)E^S6U<KjJpvo)~niEjfZ~NzlZCh$~1Z6S?ROR'
    'w7yD>u6oRuQbX65mRvvyRbcAJ{p;@xE&05t9lIfFZ8%EX`Qid`i`KahvFe0(d3U*g;ZuCs@yyjg-n(XQ;rc3aUtuSg9`(^RULXJ}'
    'x4G8;ymsk-m9UrZ5RL3i+A~O90}E*jnSJNM1N1YmJBO1<$d=oeKX?14$Jfix!FQKWUExo?b+iz5hMTN`61(U06S`KTrN3b#`_?a)'
    'T9Y%E^=WoWzGSJ3@1ZRGK{r4bnqr)@>yLnhedTia6o#kESkO4SNsH*Rx>Y72udeNBLaT5Hli=9NH0F7{c?<iVMC<umFVplMkPVPG'
    '25bWle^4JMH@oDjmS^0sjXz$#9v}7rnsN9Q2|%50rD356r5fQwosc>`Ce^X$Ro(C~p3)bXjzVR=`{&c}__&p2O=G6~T^tIbATThO'
    '<5=SjO)7GXG3N!obHl*^EM0EGHjO&1v6ysjuA;RF8eDYSiZMbYlvmo9b{21E0>a*epl^qMD1%(GXhx(tb0byItx9q**P||DP+*oT'
    '?xUNs0{w+r(;Js+@RLWZINi=^2q<u{6WqCJYRVne(CL?dIy^kSzI^u9@6W8NPcr;Z|4b5Zu$qeK;%@ZnqDuAF*Yh{Y?3Ie3wE#rG'
    '-HXRk)H|}IKkdfqpVAz}ryn;KrN`ay5|3^hI2u%m(lj+lkiG_|V)FGWOWI29p--IR)b0RB-`m(0X=m{TME>Nl6oECkLg%?#R3EL@'
    'XFX1f0M_lG%&eF78@ciFl2SEiGqO|7UJ)TW;G<fsP2C8tt`YK@c35^U`38+eti1CchNo}Gr@L4G-bU6^7d`}cq>c+bY-*+`|3IyM'
    '*XH?xCYCEkh4H=nI8~mX&RmJl&rj3;Y4XVS#{Rd_N#5VeiBl2<)|zQ<;F;3fu0zlCif~UWDc8`zGXUkjU(aS}aO}DdZ08L?ShsaK'
    '>#fGNKqZ_eF;z(Q{i-=C{E0<6Y#)-(1>xw%&8#HO)9FSg9iDd|pSkh9N&`~?iYk)Zc)~LA*3{m^T>B$gVzYyOwYjhH^>9C*@SnYa'
    'tH{<N0u@7#0i;Kj&4NJNwt;}a$h2F^;AiF^-`p9q`{A)|@KAhq@w|kD311UZmqj;NlK~^ADT48kr@s35#tzy*Pj4^vOgg`eEa+1e'
    '*mIq3d5)Je=h5vbHH-^<I{ZR}^StZ-f}K6Mv+gxLh9|AQ%cm@f&?78b*IKFvI~P5*`9Vq}YK)p!+qkR8`s2GgB|T!q4;|Xem+Ckm'
    'd9}br?=BOlW*_9-J8DiGwk=cu>fenY-`X{?YnEp?`wl+-y!c&on*In*5lS_XqwAqw8~%dN@|><8zO9w)>-hL}c-~+~BTY8KyzNcu'
    '*gz9xNCUta0YHiC!U@v$_!pe9(^a?&zHaq7MG4r>Q~(g$ZiP%2l<}-7rXZ;m9$c0_zNzQKmz5oHAO%tR?)WHcz@p1g(Ff43fVkZ<'
    'cAbww>uQqddSLL?^uJ(lYo@cK?cSw1@1wnj{MtKvs$msTf`!&fL~NuqL!bYGkKj!RaCtk6{xKFPNLFeC8tTA8O=vD;<aq$n`lW7!'
    '8@KbehtJntmHPb_)%z>wG2p7s&4i<jD1o{)LM@=Sd3*C){JyL8qTFEJ1ayU*?LHjDsmiA)@rGl;b;qI%p#oy_ho8?m#9xMV%A!y#'
    'xpG{{s1OiVd=@btgdnP;mG{ujs{ZI+c6??9Mop0VP%>I5Bi^n~`zRl#Zh&r1bUA~5cKhM2oa=`_e{35OAd7NoX?0G95yW1W1ZPP9'
    'i+`*1!lI)B0RQOLuGkV#5a1&!;%m|KXo)Jb<bQcF;7rllv;mK27plqm@Du`~^Uf&D-dYhWAUjMi+gR|To3mt-Zm80>oBGJ7`V0cm'
    'lrV8Pxw2+x%WL+qRm7^&6d^@dx5@(r0YzRJTxM;hnG{1o+2(b#|99_fH0k$d)C|?47mqGf5}ovFcw`GH8v=E%3z7FfJDje+;bGZA'
    'EmEPukHj@ZQLOh5P4vTvmL{Z^(diG-<McBI=X{*h;<C)){_`EG{tptZyZC1t{W{A!z$K<{+-GToU)2;PPFK~GV=%?bc1V|(4a(tV'
    'Os1a~v~zudE=h!_DluqP++%20oS9O<)5|I^FLO$G*8jZG>+Q?24wz+J>Xx_-sZtWHXe)K8BKjwynfWI_D&Vj55UBX);pyc-IVDkE'
    'nJzCI9CF$DjCltQc9oFhWcj35R7YAIw8~=9F48W$xa4|LB<B8plg^e$Euf)~@H^p1W%#Uf26AhNLv@tvzKIy{vpe=b7CaF{E}xSj'
    'kiELhu+#v)tu|wW0OiD&y=tI7)y31s?|UAP-|l{MYtP#$4H&amQ`bIi;0TN#^$S+B42afPhBCu>oco_OuTR;^oPImRTU6gYzQpQ#'
    '61^<M31}n%So+{oEY?wVDf3;DBmR3fYkCe_i_XL2OK4}-2=gB+dU`+TQPoafBW_d&#T^G-CjDzzf-u^)A(2GgYSX?IpTDcB9~A}P'
    '|M+rXE25)1Wu2p|r$MxXyaGbc?V!Z~&NNoaaT;#i!Q<oM_1oQ^jZDGT)=f(7+Quyjo(tmCI+C-9^=QE;3`2e8Ms_^}e3?djZ4_^-'
    'Ad0rYfC4!}{xKBIICTTH1F7M)Yfr~}_sj8=!k=l6+h?CdI8Y{Pwtn<!yI~5=3-Ed{`3O?<m^)eieC=*l!1(S<(s18uIU;(Y82c7<'
    '^M$o4@-d8ts!Pq%S1lwN2B#|9y@mB0?0Od{1*FO4BA^A;tgeu)mQYGZ`yXcHJ;1bz-S6W6j(4DQ@oi&CB->6}fsvSz*ZQ4v1i)6P'
    ')lOFxx7Y<*ujSq)=k)xm?$zCKdc8mVzU$e8Rby#=E6_<J<w4_7itC*86?!=?69SX$<i;(0d3?S5iXVBOo;P4kJ;hn^Sm#vRSlMk}'
    'l@b$>P8q$m0>{qVNZDVo52R?<JF5Ez&q#|#R6rcVA#Ii=+J1ACOu<E{$jPZ|$}<0JHnajvJDSk}hS#CnD5s^EW}RPZiJA(TR3XJH'
    'Ou@S<n;UoK;(o%6cs~5<Z{PmzV&bI=LQUx_IS`YD1<2Iu$Wmm^oo?40vS=-Y;>P`)5QyQAdjTzKq;z=iiv2eu4a8sBQMNR79o_jF'
    'g(R`@s3L!Fwe0gU)wh0DSMMh;MuB6Z9VxnAErCTtCE=OPYH%TSl6;pxbrt#fe!d;2Uw3`nLl-?9MRi-|4XzIUjw>yM{Go|jg0&#?'
    'U#7hapR2|3@Gx(&FIB3c3=_<zoG#rNMFK@wnw!ARa>11db!v8h&yR=cSbbg&zrO_Pzk;8a<63BTBy{o!y~ikvgDxPQ4AcX1tOk*F'
    'wB2><|BEuU`&v<^4?#E8Ji;1_KDBzeDp84WiS$O>VD|yauG`2{Sgkzm-vk+xQb=1d*a0BAVFa#**$qhykxbqZpaNd@Zo+?S5H+s2'
    '<Eu!i=1?I6!TJ$}$fYX%bUw){mV`?%4NB4*cW}ygc0Z3$bf|Iz<{|=C#Os42j>w7m{1C%&qtULecHi~C9sTXyYH1YJ>PB>uR%N<('
    'r3f$vg)NJe-=e}2Iw=KCunM==9(OL-`}iF?bghQA4}k=>1`e$&vaE4RuuvBU#m&}&1T%m9_q0oTrRNT1h!5U%<wY-jXq*a|L*s^*'
    '>E+OC{fDh3S1H<CUB00c?n6P*>k;QkzrV^7#uQJ0FmviOaQ$V%P}&MO`*hMePjIIk;Er2SM8{h7O#~!snc(mBNxMB&dly@O>G9kS'
    'j{kUf`Zr_-_dD9I0h&6xvx=P!MvM4@)KMzeJ$&3Ghpj;Pn6q29b9jixFV4mIy0GiIdwd<=xG<OZB;>n%fw<5K@ZALLnRV{EuBE!6'
    'uWZBiX)Zprr%<=iOQn0)(iU@#X-Q}i8t?+>4lFgHbMpzJz6aBkb+FflpIIVZv7aB>H`0S8y&S$>zNXxP80_>T%3kW=xUEP4eH}W!'
    'KA_N;$$#hJmR;R@I=a1SD>QoxSv2V<o?L34*@MclgcKoKaUr+^SinQ_TlVm6Z3k*eZ0(_dV?kdaJOC!?BRtQA?ab7D>_;p{`yJ<7'
    '_7L_y_V6_CcoxacREFY->zR`RZpV(nIbn%F$}l(N3;>C#y=5O-qfw1NzUsm6Ivi^5UL{Ov;L}Di#B7xEbM~+!?V@gpTdV1BIvgul'
    'b9cJ8PG9!r_mjDs8}*><6?<z8kPMWIvxE|W0XW5}Nw<AHu=(Q?0N}ive|)>&Ak|4`$V(6q-6srz)H@abFI5`Sl92B<RkY84!B*nW'
    'E@K8PR+?77I<1^CencLN7=sv#Io_r|aPDqyZr@9=GM@*BWdpql6chTLhbDz61h(Z(fp6tAGMbLB33^FNw`}Bj`1VMX_8k1+Q)_>V'
    'xbJV^i7G4}2mO@BLbkuCc(l;Q8YvK?+M!7|#r~I2rq4SnfGTPZuu-cg&T|f5JlBU{fT!HT2y9v5R4~BtmQ9?F$8@g{ySxYdv5<+('
    'up`HW04@alE#w#Eqgf7I$GdCye>T(C;pI(6GrVkmE5Q?nWCurCcUh_pR{?apS&&hEzog5G_HlnW`)=}hwvGbfe%(L_5E1}fNx!GX'
    'w~Drbb|v-#Nei1Mk0T(JZhsIvkzh}^%W({~q-JUm)rQB7BnkBsZCm=O<z7#nP7TissZlgg#Z)zUNddomBN4-=Kc@S1&fBKR7ZUl~'
    '%h%Nn;682FWuZexNoX>m%VnpZ2n0nIh}#E=LoX0AkPm;+o^}{}A&v0SBf<}7Lt&Qme_Fzw)1US#Xn+rfVfUA8Xg+Y=d)Z*T7bNVH'
    'UYbVl7&c!`5UnQmuL*m|(Zae~qKx}XcJ!3~@wyfBk(uM@h;aP8m^?;O$q~p0RYm)@Be^AvsoIZj=>GWS@URPOX|%~)fhjI%R+mmT'
    'w7Qc02V0gsr5mye&dW!41pRmpjmE>2b{!_@Mj*IrA5pi|8{=ZDP|-siXGuf|nB7Vreo`8a-&NCFd-8s~9W{xTQ!5baGU@mP@iL1H'
    '55ISjQl$B#dwNbUZmKV^-G|}v`Rj3GS46uNt{`Mrzq1KPm3WJ@T(b&>#T*226z#ukSFexv$Kf*6yaWobfM+F&&C3TwDT0`@AU^9v'
    '2U3sFR5is%_w;i7H9eeZvzL=C7;dm)C-uru%f<;0MI&?^@~6HecrRjm<INkI=chp9pHhl{<6)B{=-N^?Qoo?QK=bfUyRfrk7J}2*'
    'RV;Q<$Zrmn{y{V<?!LafJnjliLZZHDvGOW-H3$Y3)+a)O`vu363su9rHE%w;q37x8@VMvd*VP&ucA=1nT75~QD)|G#@(NXca|a0('
    'sgm;p8``Fs>XGE(K%k<W3z@M>R&~uDfkcaMq|1efsvd9t;OFDFL7ZN%kAHc6Uyj$gb2?DQVBtniv|{9hmAE(PuM#FU6JhN1!7be%'
    'LTbAMty89SRibKUioH<CK(S`XFeA0DkScbe<`I#qzhXbCnsnGQ0tyGanb-T|f{=-jwqakzhsHz(!K{depw?;j!3~9+iND;g2u<9F'
    'DS_aV`KDpE$}R9Fz7L{&xTnpsYFI^i>y}Q8qwn9?4~nzPudWW4vPvJ23Be$ZrU`AMZ?DMVy)lw`sZO)MYFqJFRK^{atWpxMEu5@)'
    'IAJDZElw>YkS|#0?LsCgxy$Y^+SjseZxc?@DU9Z`&;qK5X)B1XWZsB4VkI=PrKS1chT>M;VP(yjCBo5y^$HDjpgZk|K6-J=RP-FA'
    'q-YQ2AKcA}<@n^Id%=L*R90ZQA{<IJDoR#50n)2Hc-^W+4s&6h#Nh(d^n<%P-yg3JJ0F&gEnHT9>uw*Eur+m4hbIy^4+tJZADqCZ'
    '^ww>CIldf&Q!e2??`<R7Mr04cYbvO(t6(`IR3cD}3IMIe7Eumk^ycUt$U^XO1Gc>Ujg7oFWc)(2Mr%+jHCA12J~c%XFj;$3<9oSv'
    'BlpL7wX-^zM_opIs&FEw)k7iaR}Fwm1FcR?r0oscWq%Wq`vZH4V(9#m&f$C4RRVU%1JhQ#qH3DsQ3fJcXhe8b;ZN2ol2j)j+t@0i'
    'p4TsJI&QWiB0-ZLB24hJ?NNZIAeLj?5fv)pq7}M=L$~hf42%5hF>P<D$$J%S-VPy&gOV^@Sc1B%FY73ak#VT=+Y1n@vfDeqzn$Pn'
    'C4~*sk$~+qCpg=4YHovSOMZ`;hUyz+^PAI>hhsF30?ng;_r$gszq$Ji?|%xeVp@d?!6`^#SU7=e@{lv}!nwKrIIcP5sT{(YecgzP'
    'V~m6WWa%E!>BZ0u6e$QqG#*n-X_$bI>E;_2v>3-)%`ar{Lux=)Ls%t;{#zvAj-%-xe?YM}@qnrvvNkOr+0oe=;_l^Zxb9uv4m02^'
    '`V^LxEQU*3Z+%@qOw;IjVaHH3-kchpOEPtk=!kH*O*#l|u5TUt9%j``xG5MM9dhqN_n?qXwwf9@-(%}dI`6wX3OBp90JAoZ`SMq}'
    'B9K~3UN@Vymd+Qm6S9}v_p;vcq#b*|cA~^ej_=*53abhB!GE0SLuF0tse>W^Fz=)J;EsO#w!`2fyhETa20t0Y1gGxg(3slI$W}VW'
    't;`bZVY)dF`mKw^^|wINw$gheuYhQMK-Oi9y|8o__K@zZsIK`-E0g-+13O8-2VXuK*1K&-E#8|f#Nc7X8=8?zqB=Bm$Ia?rB~+N0'
    '-F;+JhxO^Cy^pES$+xF)MMkVaZ3z!Nj4Kv#RT#v;K*Erv>_4`n<BodFxSz<%g1KuF$&5dnE2K**f-ow=H;;(e-VS-jPF@0II6iGq'
    '4y#Dk%W!pQk+*qgl0Ayg=B1^gh{|vY3E&6zaV7&!TY5t@JIrD}WiWh}K`eYH%^&u0<s7CcK6y&oF@0n!-|s0Aa3jx|RLqPiAskR%'
    'GL|M|n!~qJAaqJp^=@;Y_+PP^?d~7|EYw2u>b~kW5E$)Bs#Wk0kb%B0@dQcZ2R0M(!VT?|P!{r+aMxq&SC?V7H^n44sWNtq1Z?0z'
    'Fis!Y#Y?z#-UW$k6N^#~M@v+*S~?{mwI5w$;SORKL`jgDisvJ-_j?YJa6)MOH_V>+Yp~igRtp!s*D&-<yfsags*>pl(Eez-InDZ4'
    '?s>O1HaCR)T(Id8LGQ?Auv0H8=00g#C^?;Epij8d-*QQMFrk@%rJOjn8{#*uH|~Q~3`HEniw)Bl{^W}EE#v7xoMl-1bF0UDRy=P8'
    '2kU>{>}|^=hcKs@<xQYVt-(6H(MA<jFR{y_A;!XZKji_R^dy1(bARFuMA>c7g5#}`gn0)|samW{a3&TLIvk4@8r?#pp}qpHcxPX0'
    'iLiTDWbjkGEY`r>BT0#Mc3F9_hAqO#PQ$tP0Nd*3U7edJd-o$122qY=3pxYwool{fCgA83R=T7#GYtC5^PBhcBa3qHrX+pX0C`kT'
    'D9XA9;V~G}^!Vs?!=U!;Y_3SRe!8jnXZ!cGw!U!y$h*<UC8mHwm{%5|kwjgj&VpK=-MXjgX?Xt17V_cvGHmO=!AiI@eP}3HcEC@O'
    '$ix11#tu_2AmA$aiYxeW|F)YmX0d-bkT({CO3i;W{V&3REVLjJ=e@$q9HLn%wr-9Ae}<iQZYperX6y-qI=ugwl*ST2GfN4ro0X_c'
    'nIw6b=Z|eFs^Q&seSB8R<zyNtISylRWBOS7WQycAaPZI#mCda?`i`XR-VkHgVw?z1>lF8DjB&~gNRtbaAYu~w=d$FR-&;JK;aRu)'
    'iukDBEo6sk;X3>b3}}^p>6gk=YX<#lb@xht>yFOlr+n)5OAHIxfa0M{xa?+Mg?kAL8sy|9M)8)>_-a&JBvyoy&4;&hYUdpHUvGME'
    ';kxNC!JU@4=FFN5?WAf4R0y+6xF}=#;Lg_Gz}`K@tid`IUV3wc4l**W6_f?lXcd6COtNc#I<DucJw1PYeTjr||9t{F6_E0<YenrU'
    'xh!e+xOowWsGt-ZG#`rB-TOLkWIfu?ZxM5PU5%t)@D`+Shs(){+be-t)IkQBS(|Gpx(VT}zH>}rUcx)B??1Am<M@lDNtG&W;ub&5'
    '8%7vms6^*VkH(xI_bvR!gmQS;92!{SV|U9n3DZyZ^rt`COf5|m^`^QovFBvOAOq6EX$fDFQO)Z1>nWnJ?%z>j`<*^TD_$=7@A>6r'
    'G)e`8LYV;-LdPQ?St2Ar#ya5l7}p=`j-OhtytkQizx(`T&VP5V=Pz$1^mAr*OBLamWl%_s0Iis^NI)=f^q)~{ub?}>vz5)%-vt3-'
    '!K@CQk2-l8qlt=`A1v@9eAY1btNq{A%P@i{&jjQ3KL@$@d4t&+<0E)2dKyhQ<Dua}#FiigFbKl|(pHXXN*~$9){_uX%pnN3IY*PY'
    'F2%UCA_kQ(h-CJPn#d<7+n+|Cj^@K5K45w}=-d79$4a{1(3k~}I0kStl&gc%t72~8PRI#LXux}|cE5rQb=n6h-|%#{x;v>zw(4VY'
    'F9ghpA^?pg9ARME2vC~)_;cvqnJH4sb=zRgefKm(7I^n1{<_si57S$UnmJNsW=(_=h-*t0c&(uU`ZLB<%YM4+cj3Q(-mqc|Z;>|U'
    '0^sZdE-*vJfGPU8YVc>tesvm#rnzqM(<_K$u<JcwRlpgU&>=0dHsMXG9fbvs$H+lFw7G^5R#)ib&N8de&zx(zZ7mN{ETJ(oZ0y(3'
    'v`kEIZShIsqR#cF*zX90^?2PT&amg(LD+DhQ)s6^e#7Y5=#V97c?xd6GC{WjO5+aX-IeE2--*-HK51Yc(@|!vIFvh{S?X8>>N1+V'
    'yl1?lmKxo_uyoxH5K4x1;^cmQ0I@MLpwR4#3`0e|cXvCHiZ~eqCK&tw)O7CRHdaZ>wiIN{Lw~@<f>5W4YXSjTO)YrCKuRM%cwf#-'
    'edTL7hv*+3!7d9mUKUwsL%W!)8{yH2wpCaL^FY}Qel#x9c;y?>(;9`!_(C_9rvXRhXZ;lw7LX3mVdj?(?G%(6w<*&LZe7<c|9X(='
    'y}WE3Mp`z%j%R$_mtZjcqMRO-a|H@Zkb0*8?8^D-wV(fa*y>Klgxny3Dhomx%N`;ayD^nXrN?Xp^qq$mdiUDlPJf~`eGBW7m|Kv>'
    'J)Tn)lcfUlHPCel41l}Rof(4j2pD3yoyQD?y7=HuHnl+}sWAcQ3Jl!vAm^kT6Jb$?jE!2ow<yV$YP^0MvHF?owUb(5$WKopMco(^'
    'o<TO8@7xz*ln@qRW#G$@rz>7gNP<2EkNb~5r4oGdlIXQU%$s~Tet*7?E;beaBcqvPk{GJ4K<cZ(bE4F3s@r$<%ki-4Dprlh-Eu#C'
    '*|24f*0UCQu!rVQ3WQryT=Y4Wu-q%`U<|=3Zr{;K7mDqn%>A-8C5NTn5`&ew{0Ui*C7xnSC}4v0t*aI@8H|1JZ{H5q;*o;*{PxUV'
    'Se{TDHlQ3Gy>Q7Z%g~wd5!2ms*_p%E#kh=6vDUmvwhE>c0Q)+sY0$p<ePc`%?}{=4Xh|N_@>uakkU5+g^c-kX7Bg0hEm$=Du1;Kg'
    '@w+StLzx{o<Jxg%dB|g0fX&)r&9*Hoz(POD-K+X6HnIs{;XF=xOhB4L!B~a`ejdCicd4&b$;`KZt5iR?nEuVEi(BWfTZT4EP-7#N'
    ';Cu)rK*cQhO3a365*A=*m|>0fl<!>sgf?#&1jck#jV&Nt4;Tq|d-V)&s5v?n9y^Iu%9fogo)rRbYT7-$Hq#Jf1THB$6J~+5W@QuE'
    'Bi&haZKh)FH*Mz9Z#y_Xk!?WzHm8oYF<3xB9rKc7_9pct?t8ro6}Si)M`Z-=X2$k?*?*qW#iKN7%dVUUosOo_6D9@dymF!&gKZzo'
    '0iDGpVKed;^L6La92tB`|9bSn)I45(>6{O`AVS5s?<u4ZWtiYmioiNCO`ubX>iN12tU{iRVOOY5xDk9>h8PGEKx!4Pb8~nU=GXy-'
    'q8HiTN4`#6-XNmVF)GJmuoW0kkm9=;L&x+{Y@sF!G4*v*)NnWkVj6+^_s8k(<@I69TP;*K?ks36VmTRCiXoje(ze64JVs1W2Thx@'
    '*I0K&*5c`IkCT((*Q-P#lo3meq>zt7tEP~uqYE*=jp;?%o>l*Nn1~K$p=+l-P4MXu04MAy6<HS(wXLUh6(6&*sAaodNRD?be)dy6'
    '*%RDtn~%GJ+z9$SLrknL0vSW`^$F?V<qI01R!j&r_ACw5UH-W4ms_O{^fWW^$mIc^S|oXV&&}<k{#;*wQ*GLd{E{AiWpDl&s|F6^'
    '+Su^PGc&^oi<kq2ew1Pm?Gzb49|8oI*$hn|@}{KeZPC-5@E9361}AMfeAy`b>zJwo4n!@7`4D-?0i++1YDefKXJEN8?OgrMzWi;*'
    'v{dLz+IZ@`_g7a(YS;A<(*;Ar_-5DP?g*t5KdA-#om*ImoQI3Xwg6ea_6YV!$3qahL^A3ORR#WCa`Lh$PB!I-Z!4Z#ox5H(XGV=4'
    'BDEL|4de5?Q@|RiF>Hre?y)xgsr&Q$D_{A>bJ_<PCxDBvU|GkaV)eQyhB`8pX2A>O+|pgMg&ohFvVyCDgPhhJ)0IKzqyPx^DvPSh'
    '4DTuY{x+8VW}Mit+dNIB=+(LwEB*xj11H0Ro=Qff(-l^odZ>%0>DHph`88}sULSv|{QdD~_F{$<Po~8>PVdYN;3c?NkqjbC<5<S5'
    '>CKAywBqw>5&gWYE@iB#8C3*crqN(5LXOANde68t$VEm<M^CmL_b&VxN?s!xHk8hq2Ei2Qqp#6~>kyKpOu#{oi5kR3gg!&Q$+Gyq'
    '?Ai(66nyiqf!gaCATNoQ6l#IiNk&vK?GVre`FGmngnwUkCA;kMi(wCkqu-{`Fj2%TZ8$MwuOdjYchE*)!^%6X-nnv=6^CtZbrb#w'
    '{;0<(L|G|hdXWw>`3+x8pD@?oJn#1|y7Fk=#5UAzAqU!g=CUufn#_&`7|x|R9N2Rd+ti$j>XvJR8ZzG`(!FisOrKFZZYgZ50RG&P'
    'uvY>WVojZM?fWKr`34=w&sR*=*R8wav5Mu#4Rvp)C4=L|cCm}t9o9e&7_-<m#8BZ9BSD*YuKlJel#*Ru)<tOKP)sh>v-InOcM@6^'
    '5=Z0s=rVG`u({j0>~jCdhGUkwhcImzyMPScljAfjm9_sRy(1MWaW1T2=W>U6wO|^4y%;DLfVwt*49(60kI-Z3qD1WgyPozCcC%8z'
    'y~pX)aCu0t%EikWJv<#62FBF>RWbAX3%_LQZDX==XOt9D?0(q0@Gr05E}x+~Yz<@fHI;fES_FQR1iek<wPC=>i!A21G&|Qj4I#UG'
    '{sw`#_<(hBhLC=S-mzrp)R+g{hqy^foP**bZb$)^z3aZwZ?|7<j${`=03%Dm(jlUZfwib$M9846vuZcvV!C?eosr5Xt8;>Nko@RM'
    'iV;SorS`XxMwqtb+*FOrrXTkA^^eD2H~N@sv(^RAioOs1%}6xOSA$J0W>|23jrOSaMv0iWzM+Wn(S$=XLAHyJSdGt~8vq<GQb=J{'
    '=XlrE-t}JZUk>Y>(#vI`(M#b$8??L-@PgI)XyM2FO<+9ZX6>3{_j!67{J9L4->3WpXbVj#e4ztUj!{sU1ZJsl+2hRxgHSbteRl5P'
    '2Z!Wc%Nu7Tz2U`!@XJj#{AdHg1LnE?QlKz;VkR-{T>k8f%vt^Z<?99-5MmFWv>X-bWOOB2C8<xvXMH%X`!ymvsmjiUpC|Cr2B-wH'
    'ch}BHm{WM6^1Q49c2FK*V5v|eY_{b!3wp+zA1>ZObhxk=8S49XwAu`B8p7LO*dnQev$+oY-RlOE3YND6pavU;T30y?if#je2&Z8Y'
    'j6($(6g9S`$7XMo{_bA%gAvu`pH2-iHEqoD@F_dVg!<5N(5W--sB^{$C)mAr@Cma8lK+9{`0GXnFBtMG3vL$ZA?8)dDa|Wi1R2{2'
    '-X#Bry}9(cAG79HX+!o}g`uF_qY1}94J);G*txC*O(H^3RKb|`mMo_x_vPQ}nX(66xDJ_!q~;8q+89nLfQK9T1^}pT=Brk`!<o5w'
    'A3|XHDsnK7>AXf(xGXG>DO*J4&rGk;xFavSZq-x9b9g@P(DND+ME&h279pK#gV7UxfnEjWGKtK@)jX8De>dy0)B2Y)AMSTbKrUsZ'
    'pFXJdt6Bvd^nDt)j=1TW)7~)h`nW=gua7}!+2{x$W_zsciNlFcl2iM#)e8C_(IbJRE)iSy-V`Sf&3z?<uhd+x5{+!lE@xzDMjLa`'
    'S;DQTH298_WxuyvIT=QVk?7N~!(H2Sq+k&{$1zJ_C5pS7o0v@!B8+^cWzJif0af6`?@y;U{Q1sbS)1Q&kY@Ve?rAsED>f~(ftf2C'
    'uQo=qM7gAfp&rbyS@>;I)p_K|<)c=IRX1NcHx>T5p9={HuY)QESyV9|TpTZotJXg|_3yK;50flUKE!vJWICL!89hOL&11T#ylkS+'
    '&Ntoq{<MQLB5@yH=1;6&pamNqoqTUP;xY{p)^~W)h*WVT@)+HNDGYHNn@w)QpZ2h8VUJmRe+;mVwnonhRm+DREml1ujzM8_Tu#;1'
    '3&+2`K@DN70ne1NU@<C@nUI2XwWmlUSO5jV&|I9YJLEJ!X4g>*>m1X57eJ{`$%!K*B12X0q&_^i8|>$xu5YaPcz7g4*-FHePJy|M'
    'F*UM^0R?OMZ#ag$WJFbrHuAR3(a*+K{&+zJZ-gpA)3h4OGT0e&m^|v3tA=IR08G&IW)t9Kp|Bp=wLgDq`&`D;3_T2Lib~N58H3BN'
    'Ff3!p8Q6cOVN=@>`ffeVXPx42!}qy}pWa9b-`)3i&n_gf9>S?0CTvwPT^1O@(4{b#F(v`jGgZmBO-kLfp*^z=35gk{(y=M3iF(?Y'
    'ouK@Zoq~1Qgv68pw3XsR+u1ioax}BaXk?l&RF3Ge1HMS;@=%AAHWi`1+>|?C-pM+J@o_k8j0JRHa7Tu<9xUR6l%k_jC#T1lnqY*X'
    'U~SsBoVNnzjuLc_eXaR_#t$%KW)*AJqL@xsltrOGhQtYbSU9MMY2U&xQGn9Cn+*|9VY5QeeI3KDcL?ph&TtpndrCP2QXI`b6b5s<'
    'd+k*Td%9uM)6+T;LeFl?Nt7Ek-p+{E!sR4579n2dai$pcz~R4gAEMMNHgP4BsE74(0f@1W>zsP-^+U{oMAZ!>810OA=JwcwA9wJ}'
    'Ya}>(etwb6F0DdH8U|Dd2xxZBeE{%t$P%M*&D8&z#jiMhda-?wdsZrDR1#UJk$r+;c?Yu8v<n=yyJGe0jvzItAS8dM>EYd2vPlF6'
    'c_`|Nm^wYd_Dt;Ax@^(Gm%AV4w(p-0gd7hwEklou-Q|tPpd78Aj8wc2J%xTfG;X?f1LsU{*GN*BfbqjqNYEzC4EeU9VO?C%C^)@#'
    'kOI2coKN-M7WR*Y@&UBr7NeHchj34$mH}BML1PRvsMcv9`L)~FKN58b@w<5Ae-jOc_fHpd>H(c1QIvb7I%wD&4)x9s-pDeSs}7^D'
    'uoGkraz6?t6JZ0c!ZIUP;3`u_BX-yXP5xsG`<jr5`W#1!F(Ff$Lh1s9ze0j73<%aC44!blsp$Uq)&I;iTzyD3GGO3E808rF36I6s'
    '(5aGwM;|BTG+;D$Vl{ne8#@S(C`oxgDSD-(dfwhX_7Kf9i@rQ&Sr`-yHSO{b?PK?ZR8vkAL480-oCp{#72#9fM<%P6#;r?vx|H43'
    'n~6cGcl#!9#pS>*&FEqhst!UeYKxT|FLh8WMM_v>xwEg{1Afgz`m(Ko1e<#PAu21v|HTXuL(Mn?<D~LwAQ>+^_{=63;insT4okVM'
    '`$983QY7L>{fItniGyX5!mE{oqya0;_u6c}HblG)x!g6(&obSrRmj3KH?1s?b#xNoi>#yx5$1IDseIeQ?xC>=Wed)G6_OU^TU)Q!'
    'IM5)RnPZx*_G^s2xp5!g=d<oI8b`@Bk!UGmnspJTIAf%fatd4=&0f^An8jHP*KX$2T9;l-s6lrzH0o)iQP)ac6f*#5crOT2i*5=g'
    'eil=ehXIpSVs-02V#dP5nqj%9Hm87UdABiQaL%*v8>;|k&1x_jDels)P4H>6P5aJXP8qfxJ?s#|p++sL8ihp|(R(#2FVqLZK>R~&'
    '2q#Ht-sZP$We<^?k>C`w2-(iFq;t)wLZ|Q%$3QVQca9;~(7kIz7oeQM)>cCTe+q?LGXj}eLa&~SP^kmrqSM62_)&Y+)3s6K&)R{z'
    'UHHpLzm6ydwnO%%8_}d-HBE(A$M=fiEr0``>MOUh&$r6$U|0)TC}OBq2?2K>xox=b64Cp1=B6&M&9#^N!<Vnl!t41${f3~qp(`Mz'
    'cM9w1Zkj*<$|FF_Ni^FaMjPCquMoW5YqP8`fw?_|BWWbRcgvH{^{^?b5F|Bx^?RY)EpIPaj3`z}14XeS>XF%Buic6$j$bf5ygoW6'
    'Yb|&@E*s<2!1<aw(kvVx98R2R9|n^sq>Bv4L%Xt^=4&5{QLzs{yGs7lPQtjW!vPgI=+UDXXf5$}V?7RT)~yYic(Dn#{`=BD^cdC`'
    'a*Zc*7DL@aNgtC%_@Qd35!_(W)|B*GTjDya%kkPz7LWTn0ylD{geS`tJ~6wa#G8vLX6}6Q!8+#DPr*v5Z{NozcgvUz|Hrg-UP{2='
    'BDkkZ*r^yKrWOfmBKFqR_egBvD&ayIcFO>8KFfK`6JQPN=>#*AfObsUB8Xk8qZ{^dg^<A_5E-Ulfs0ir<#@+N1!W><7qO&TO?a~D'
    'hF$EG6leiy>&k<P{d5A%y!F47seP2JwEu<#vEaD6N;@g-?#{})tr86tsi&b=qeAV3Q^58V6l82~odU|lyiRz8*Y4puF0?|J^@(WV'
    '%XG71piw+#Lr`^_m<)u8?QmTEAVi1N)aTr(+#Yra)JK4ZnLrR_!o(H<W-F%6NQmra2#dC>Kagt%zE9B+LO2XdBf$X`44j-tt3fh8'
    '#o*tn9<EM*&pYsqMhM+Cds@GiMhrV#rx49UG-sk^pa#KOxQ)%KHcEuzwv9X<*O2aJJ50ZBm_Gn8uv_DlhI-8#P@qD(k*gF<G5UQ8'
    'E=qUXMpnAOo)?ozD%me2nK&b(7{NA@26S;UgBp{d?lJuE+Gz0*>j$<N#0e~Zw!|AvDW}6kWAp{&L3fu8=x4J5F*PC&`E0Q5#;ZS-'
    'b9?i;zA_OMo`zy|g04m<H5l*6&-T^Cgiypo8ByNcwwG%=%=`*L&UtYDGHw8rZ`vT#Vkw*{eA7+XYZvW!+ip&jmR%b`&B6_Gsi9=U'
    'G^!N@UdNlYVP~y3l?N^T>Q}UCKhOF3P7Nq@L7^B!LSxD?!spo3K}kg59^AaFusoe+yfzhlJWR*$JJ}AaVc94Rvrh0_Y0Ai)J)k`3'
    'w`C{>SgIPYHr%p{(|h@nj+|_^IGW}Oqo42@G5>;n5kgf6y6|3t<}LpSLEHAMho5fa98Q>M#6*R|!xrXZyp6k6LrN+%g=oQj<KUXW'
    'Lk)zbK~tfPm*4bA-oE84I4XJ-tTV_NmMrFliKmLEDi5ond`Sf=cm_MaI&WXM^8=T4H$;khrkGSz%Yih_wDBhQp&1V@UlK_Bo5KC)'
    'rtQ2Liz~6e>`^bt0@{^9t)8n%)lDuDP?Y;ofy0P&xV83%o4%nl(RS~1$zw3dknyo2NYKu79fN@8&?PE@9hz|0&6aB~<$v8j!Q9`6'
    '({c1u&)Q44_<>?*L1IuN33NDDptu2Y5uC2g8@-(|typ%{d8RXO787yx0ECcHSmJQwnV5soA7Mn}9<y-3zB1jWtFGV3%+mAw!|<xU'
    '99F^qCJDzEQ^(MNF0|lijNTgFDj6wILT_*iAz0g7yCMJO{4}rWf&m^Rl8Erphs2$UjhV^naUkwaG1L;RMZCFoBm4QgF`0VM_YDTT'
    'FvmC-4UOh*bu7YrtR>h)0oO)3INjOoeKJ&iV9vj>iwGmW;sDg?E$APBG~sqp;g(WGM(`)$zH%2A7`A^ZGu<?O+_H55`kEbW)EK?i'
    'd>M|@w0U8wvRwP2M1AY?h=Gt>0}@EL=UVTbq9;5+V_*f_`Ix@O`BF+^lsAH0cP#>PCcEC96{umtvr*dMPCJWT*i=C%tKb3RtmH8t'
    '8wSA3I9kR1mD@Or>ECv<Nzl<l$kE5@DrkSf$8e|cEs&uMM9vz8fNgksdHpsR*@nzoet4?0E{84pGUT}!>4<?E7U>u?P0W$^&0;UX'
    '=X|uywIAn+4*ZxlLc?epx^7>1Q)R|niJK_7T$tLp<-7~<oxbc`-L(2XGIAGysX?uUydw+^Iajn|fu1>ZQWw<zIw}0M?_qThJ2{2y'
    'fwF^~vp9$hc-X%f9VcV&V^eCqB8G2bfd_44YZuo=q%oX$4KzsJ@DSsTiF1h=E1VhC0TP?i7GGs+)$bM--!G~2n4gWwLqm|>Y3sQ+'
    '4Z2EtSz6LLeo82_XyB)~yT{$D?=WlgabpA_a<=9jgZARZQ?hvaxY-Ri3yIZ|HrYA<^6c0j{fxJ4P#rRk_L8L5=Oy#6HM$W?*}@b-'
    'i*D1V+wM8cym#;Z$-=>)J+RG;dT0Df;fAHdnqpA9rZPDxfw=B-)9qVvcVOd2$dFo7Odp2jkjrLfM`vP%g3Dz;g_D@DyZJ-cZ+Kr0'
    'SYlP1l+sm|QM5h2F<H(!48!?FJ~N{&ywv(#D@M%PN9d<B$18J-jIeasrlb!qmks4QsR^5*(0-{mHNihDyC+hZ!;->wv59#)>JwJI'
    'W|hXVh5%8XW7I%BHXR>-SQRHZ`p}nQCn6PdV||r*I6Io1<~Wfbi4j?hXW?*UgwAHo`opR_ZwS(mykhM$gk6;mGj@Ir4kmEtc5c!D'
    'G{dBmO<edt7Tz&R30IfP3q#kbi-D&N_7F<O04b;y%AGerVh=!gZ|PGl{^`er{nN|V*mrrcEGQ;r@{52R6)_qcjy1(Kzz$oSu632)'
    'y%E)v%kk-3^bDyphWkJM`-Th%OkkY5LM{{ebt_}Oyn)lG4tWHP)qt&e-%<9*_0FuxKtQ&<^qF^t*n^#Z2h3)DCo0H&r6H1J7Qaz%'
    'FU--dSoVzfZ?7F4N#hYyd^+TO+ArarUmKCkC~QfvX1j2(u3h^L+}^PTI0v3M8lEah-z%I-4YUl?0=noF`iK+*qu)K%s-BnF!zbn8'
    'Vmj>Ke|bJWT=>QCPkdZVqnHswR~N(TnXjavodLec`4&9UcXJ%8{DPG6X>D^t*?xYEf4qCLB}7fwRpv^8l&bYkFaX2cI20?Qvoavk'
    '_c{47j`KX^`uS7L!2J8m?=P1|{S-aKOpAB+1c?!p+|ubLJO$Zwk@tuk#rujfA@I}NkNmkH<HsMT>tO%-5L&k;NUEMx)duvbuQAPe'
    'HBBKZdVf|`tQLIg_`6Rl*1pk|BH2dr;QFjy(5W<v5N%K8piNlgy2BWlwZB_8J<F>;;d4Z9;as@-le_bu+<o^BxSYP!F-I7sg$pH1'
    '4^z@`9E?Jgy9Cz(1cQ&`pS`z<@4xpc`m#^kfsn{qMbH7x^U&EyR@m3k&sSzksM&|`gfi#uXD29HuAj%@SLgKmf7}SVVeD>(s|r9h'
    'G|)m)&bJs%%qS+2KMy@@U+q}yG~@E+|2zJ_>3)p||802rx`DwuEBN^mZiP@_v15Fd^RUjP3xM3)Zhu~oo>tc+nZABHvomM{kB{3b'
    'NKSxwB806G6bgidDTYw7Z5Hnh#h?cyK>aEC^Ji<G|GHrTLD}jQ)5xP263J90y{j&Fvszu0;5uMPkv5h*W%-|12HnOGY{N@&=3H<^'
    '*bUJb4w4pBF<Pat86il)Ii2^dH%o$FHe_1yb*L0srlF_#VXXN`smU!(F=d~h1@+^nl(e6$_vO_%!wrUF*$>ebg*Un`WrAELvCee='
    'NGy0whz+>2{l4}1l)Y@t{%m4m5#K#O$b@m6WzRRJWhfwJg5e+=b6KZ%KgsFv>Et)?{Q2u);V}-kJB?3!JZ?k-hHR9f><ziM5(~q;'
    '!<J1*g2}@aF_i@+XvL1DW36pYgbDLTv+>Ukn@)}yj1GY^6tbFE<q!%co~89q^;7?`;L{2uZ~0TR^Wlfm;B~SO;b}}1>pP)I<<Y8e'
    '!-~yFTe7rc#n;D8X1>y}L_i06_Ca;gmJ`>jXzkksD+BIeDyeRGZ?!pv&oz4U9}-+&|8tmTZGMwgm~fFnNPQ?40V@rGihBjsyAH)S'
    'A+9%@U$v^~1&58AX$*689SO=!OS(0b;AOa3#E2xk4g=llJWE$CyLo|4p{CcjLaI)|UEyOepn!$D5umjVW?T%<$gf%SREuA}O{k3m'
    '_778CGa7ubI4mkgNE-dGR0VHUpEG-JS-hc7>*w+5AFp7J<#3vlyyN9c=g}~kW&?V|k|YdD@inMjRE%LD89ImQ{ipoi%6n)cgbU1N'
    'L<Dh`^Bryo{}pLq*p-Chh5IoRsp9Hi{dFra=|?uf-^Y9vh(d2BQE`u{<FZJN!h}b`)?K^sj`6W-1nm=*TQnB%Q2c7#oMr`i5FL$0'
    '(V$~S_wLfq&#&nd0*vfsby0kL8MfpKHNvwK<W7|_A!!vM<ae|^aEV#Xj4TTa;(phf+jpFH0XlW%=O8mwVPfn_$0$f8g<)()%DaH%'
    '!n>B+bH#yNCG`fW7<#^NwH2>?OY{%=CXj$pp5HR}>2@yovXyzF_EE>O+NZ_|bA2O8Jxj)C@fCZT`iKF>Ht(%>#u!dH_Kuv$-rXuL'
    '7<c#*Zs0sdfE>zv@!#RW4^e4UyOw)&eJchxW*ii&-VaU7oG}w~!)PM&_r^Ez<Bsr~hktFiYsH_5^#2s+ja%vb0yJz>`hfU|_<6v9'
    'Rd6XoiMRx&JnmZTG?8b61Vt*<$IN8j%MB(4G#iGmw#A&FDI>(iQET4)8qRV3?XP>r>ji0=#v-uPJ~*>3aUBW{2vAl<S>V0)GIZ}R'
    'DgQY{JpHsDm*+PRj}6C`yo=VhH>WM(n0SbOxc|XGn5!)OTO8f?>Q%R=QfLPaF&WyZACq>1QD23vCUQL?Um4#9KUKo5>zCHlpO4FB'
    '4m-tY%zX}nD;>g^zsAbG6d}NJ4jQ4sxT>o6uTCcT&*z{VKE7^nK+XCRX%YL_J5+3^W>ulri})u&(-0y8F*$ty$~)4thFNOh^r}If'
    '5v_tHYR^y<aJr5dYzxzrU9qNh{&Bw{*;ZF9c_1o7SXu*$n6OAu+-g-g$0|~(zWQqyJ<G;7<|ko6K$D3zqFRzLjL{FG$P4llCsTKf'
    'WTwAj@yHl<PV)+f2t-=b5x9#$l2RBTLC8Qz94i#7VT`22+rK#MQD^97I0?Ic-$-2~D_~Dp<7iH=*$^-Y_dp7gEl7zaR1*dkS1kYV'
    '_$^j`Ho|mcq#WO!A&UuWLBumND_Ce_xD~n=(BQNgfDgX0{cE3Zqm#650|2H1;eRxkwIio6?lLc=PKaJ@jJoMc08AHRs{M<{pWl5?'
    '*biIW**dTQPaX}%=N%->nmq%9$RY|pHfZE^d7bvJA2yN8y}<Go+&--=&Cll$_x7isPvYFq=XBw47ONiiwb>$}l<OjQp*a<i-q&$l'
    'VN_B-L4w<XH(Iy<>$m-{hV#y?H_&DpS7;uN1^&?(P@)`N#{*xPTZfX#C06d(`pJy)onZPWH+LDMer^u&j@Qcy$>0&%4wCcG_r}~Q'
    '7f83~h=<CEPIK)z?5M+17+(8+RG2UeBQgiAmVp{g81<d;(=B{vdt%yduuU!EF3L=^m3W2cv~nV*qRGU<wvPjJ3a8n3KdBgnnan}h'
    '2$*K8B?z0O%ES$TK?sHrR9hSs=;9PqUag~dE6kId(5EqoA;Z(2-^DUirxAN?=m4>b9Jyum#@ZOPtl$eWz7EQ}`T6tHm+@}vXEiaa'
    'JXjwl#4x891tjR1rVZC1_m37c1BX<;`(cIP>eC5aPdsWr&xd85Vfb>`=x|D0b(xrv(fEYXBiUs5b8$5d2*He12_6`_*t_s{GFKA_'
    'hmEDSUll&m?pNm02@AnSV$wJmb9^5o{r3g`R5M?$L#CMitQ?<vp5eG3<Qyp`AWb35YhxCXqdGNvSKfwyD*a2f4~GX{Kyq~r2EGPU'
    '8`AAD{uJAz9^ZYo>soJ?GoOdGd9q;^>c3TOWlmaf>5GtL*g*<(Skxg`r`X`X^!{P}^O9ogTX*p?%uW=KD21BLbE~7#iXn`wHdxRE'
    '^+R10O}KX7qTdzBm%mDq&MbzB!@D`l1PMD*Cs;o)oCjHGD)~GO`_|k6wFLg_yJrX<EcB>6;-n%FakG*thsvW0BI&*b1A+b)(QZQ~'
    'u=LG3Ou&(i38!rgcq+m)G040c)N=HnbK!rs=E@`9(|FSxROUE5Ox$P@`ViG?LpeQw9(NY+Sv;nn(o`?3yD`6j#vsNh#dkr$uBhWk'
    '(!tbdM5t+`=Dj+;xo$}u<-_H2Cv=uPFxArWH2dJVfK4U6va(Ra7BMTbN>?uXmep*)v{_i`^0(lnz!gRkDg_@xHm*-j9c>3HqMd7R'
    '0wZMKYAg0vW%M#aO$ozW!q&FNO^>l;C}{b(d$mo%P<WO&Lwzt?4Q^IUnQMc6r<P`fW>zteUB|4sYQ>)o(D^gu&gDDi<peS+65{k_'
    '!QC|E)5Ky_J32knUh;j5K1)Bx<K<D2AUm`Bx}cZE0bbh(xYa>zMhT01MoKjF%T+7hZKBT19b(#XbP<$lUHGMRIE`Lm7ZcFr4ZfVd'
    'udZKq7h5%$4yJAZpScDh*9UjeG@a0KYjYyoIlJOUcir-<=3;||rrrSY0TOvVMvoeD5Qd*BHo>ZmAmvY+>()If8aDhLe5(4?Vp3Nz'
    '>GfVKGlbmeDBFTXu9DTz*?X|oG!%#PtVg<>&1dy$IX*;g2<#Ia$tI9$l!<&tjR4Ez%i8&>H=}<Hz##aYBMv%F=6nzi7+hoY2iRT8'
    '+pb!||2WY9^Z)t(0ef5k9s'
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
