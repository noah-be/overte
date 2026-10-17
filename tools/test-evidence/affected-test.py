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
# ce4ef2b89aacfef4bc976dad9a57616e78d4b30e / tree 7ad20cbda62fe68397a02923177761e965bfb5f8.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'fcd94291aacea74e88084411b8e94003a81ab70feba7b288fa9fa6be407d29d1'
_MAIN_PROJECTION_B85 = (
    'c-qaK-F72MlAQ1L7=68*%E*lT+o#ac(LGN5vd~2m9008D+CBU3`YZvmS<@sU5~!6VX}71VTN8oI3=em6GxPua?H~8s<JTAe#XZIS'
    'ZX54*e>|oA-Er@p4ms`r@%v%-^xMDx=Wma@n11{B-%QgC*8cWyza73h{<a-slT0(@80W6(XA_fi^U&tpjL`<4k{#R0=>Nm<$Fu$m'
    '{KL-w_Fw<@wybBN@b&I__pl8=3afeFMPr6E%wrQ>3ezx-tkE=Mle@vkCXa)4&Gh+d&n|p(_v!AB-TqsC*!^*LpZK-zxZOP+3X7+1'
    '=-Rfo(~w&i$JX>iv@VTJJK1gy(T<((Mn8YP_&z=F4%_2y|Kl!vP2pQ<#Xj)xaxh^ulOAwNY0kaPjg2!ube>$-+T<@h++#W%?+!29'
    'W4ep!IX%Vn6t=0fE)O%iIQSv^7`v{sZ47fig?X}5>*F|tz@zqk&AO$vT<(IO`*s)y!|Uw_m!oMLZ`;;3(a$La?~*s4ul4#W54_xc'
    'dOF_y^Tj=E^ENDR^&dYTA3k4wh;8KOCF_Td=Q}h*)7svcevGD@dh27~#+b&c)%UyKQ#jt~w;wJqJI!t5W|PJ_OsVZdXG6p9PSFjf'
    'iKB5t+q3Lkv+UnLs*6jHdF0%5+4TKnk`H{i!`!uvaW0rRg*c9Jwl@ELX}@PVB13rC@|3@X?U&!v)3@!@;mf_#dw%}$`KrdaV0{R!'
    'x7LonwNo5IYsNmse&T`WKADk|v}V<3emO7v^13#UUD7F?I^Tq`jZ>2+?|INZw<AGnY7(E=x^;K{@~YY8vEikTCiDB+W_C^65glxp'
    '(`3V#U2y%>nKi5KU!E?m8H^o<A!avwJB|E2H+MrbPsVr2r`AT_j49_;YwAnhgs=PEW7-_T?)mbs=D0KsPu7`k82GM3nqA+yvFY21'
    'v(<+<$H}aF*2@l_++#WrxYK5z-1GM7{^B;`#Mc{!)DM=ZnT$=HnOkdJ@EmW`TRRwQ!ukjC^!&I9yQjRpy#DA+8YTkSFd1jsDHyJe'
    'ruT!JIMZ#z=0^6|tzKXEa@_p+J^PF6d%m;A+SvCamqg$2BziYDq2-3;i|lv`P3pW`y*^(cSLMaEQ^?)q2$?+xkGn98!FbaV+j<*Z'
    'YbJv2&{X_(MU+3>k1tQ@s7SZj?_Q2+6SwaEX?Hko!{unhZS38Ytm#9aEU$l_QgU3KO+OIzLiDXOy_r{U<0U>{T)3UM#gb{cF*xvX'
    '*3)MvLohkE9E9xo64N+VFMRs&&Z{qpnLfc|`tx`>0QDU9F}b$uyQ%AvHr3B*^nK(sa;KWcD@!Zx<H3;^9(Rx1a7WntzCCcGasa=$'
    'm$*G{&NrTJ*^4K#?~}8!b!3BGCK|?QXYQCuG0_aYUItHQym~jwsnp?ka4+PNm!s4;bb(ucm@V&Ph|Uu?=c%1@j$_wkV^Tx1)m*=s'
    '7t+bgkunBnrqB*kZhC&Z>q9$oHE>Kw_xdUKF50e5=IT9sOZ%tvuvy;H#huKp=Yc4rizCTvwoOaU*ABfI=OGVi9!I|4HebDyNB2a!'
    '9XI6oe9HSDo3Go0a+Qm_YIJc8*-pMmfiN<rp396|lw84d?64UvPwDzy?L7a|_d+lmLPshZdQY^pz8y!tUe`6TBYjGILBz2^|MdD@'
    'JfABM_pqGmy$i?7fo+N;;G=CP3an`$s`q_2hB%Qg@>!EG&oQ-=pRe8$IaPkx-hVw-$J$}+G8t9lZ11^R66f4ZW}JvWdO)#jsM+%9'
    'Z`e{P-QofCO_-XI3bY%jHd|#~WLZ3tnYY(W-86M=ym||y9g$$S{m#MOygj1JSpeUP^Ua*8-*^VyG)}~QKM;JgH-<P9h(FEskL7UW'
    'TwVTHW<HHkOZ&N-Lf{h0Gv96CL5-A?<Jfm|f5Ry{y8V5sz6CM~Z{sK&o0JE>k;K6^cI^2`Mm?c{{9ta<^>68vt-f9be)sYeT_Mo$'
    'nNWc>r02Yr#!v(ek^kEd!M4T^wsD3!!KPodr;6*TOWDl*?5W9Ym*&`q#^)G};Y*$(pRpoN$jyyATJES#RTvCC`Fm@)Fu53~7I-Hn'
    'Kk;Q#<v75BzW13l>&Ew%p1yDQyQfF~#nY?1T-LS1dFGtD&U@d7fh)qh0jz0AZt}nfnHxQJx9zF=7M+|OT}M?h4n9p_G|^Jsl7LZO'
    'dUD@^1J91^uiMUMOA>g0x;+Y+p!X9W6nIr=2*jS3<>x_APBVAhX+Gta?cTPvt8RHe0%(yC^Nr_uOk^QJbt2e^3FIO++s?%~{GzRe'
    '-Q$9jlpffSUFv2Mc{>{drQYX6(oFbfw?i~ObI(p){588er0?meP*qd1&Y{-}q=+N{G(4}VF<c*QmnP8AjzI2i+fP*_AU(8mCx{`Y'
    'JcoI3+_<h8IQ#)X)(pH*Lz#QyR^DYrkK3AWe9leh1Tb_75D(}sjJ=<Y2hmFGu4`Q~(b;_4zSgHkyf;VA2oBN%Yyxv-z(s3@*7AuD'
    '9Z;%s7991~eUTq+!ajlR9=Gn{P(TMLxvXuuXs6kew&l#jQchqz$*uv6C3TAP&3mdz2|6x+J{<lJXpu99Gf!3xqz`h_O#=n0abs-T'
    '+ctAW_C^lrvl+}VaKb2?T@PxS#y(q<95A(Sxd%-fZrj*l_p%4n3cIff+&Wy&=2$N_6h)3FBa|)0ZXQf$XO#ds%#nu{fS7LFlCsK8'
    'MF|VSM7{>t*N#1v8O;D53aCr$+CG7M5}u~!!@ke@?PRxocqstAbS6S_sdtU-U7%qylG{3RmeBH;Lf1_*4HR?ZcYS<(&fACdR;^t='
    '{v((E&^f9z;2<LA04&2}@#MRWAXz#)Z9m-jbszUHha)%1xAbFQf<`&><d>Xp>yzP|o_R+!cF1$R;iF1ZwsA_gR0JzFqb$4W%m^mh'
    '&Qs>?<(3$3t#3GC!P~B%!6NFe|1(H^{wJ4ji`an%@>zh6jy?AU1${#%+Z*4L$b!+*>6)gx4Ez3N33qA#xIG+}9^%Dh%+E9Z2sJwL'
    'lzar!7)hf&-7YuUG|>c##GJaH{B@_dzuT1pzAk9$iOJ2Q4K{|pCA3kWPu$?KF%dY9V^X)~DQ&qNI?Wtf4jx@YU~aM~fbV1gxPVPE'
    'cMg3u_7LmxrzbA|?`h-W<M#4RLT7{IgZO8BI}CI`KqX=h^w>K7UkAWtDHtjXg7d01U}Dp7iBp!TKpH~|1BJci#DjteJ_?j;gn_zm'
    '>HSHn&M`t~QtK)5sSj1P(gBK=)*iVAhrMa(paQ~I){F1^JvB#ZjMNskqel$N-;Y)WewxXiJB~7+HMKOgSsYg^ekx4EZl5;4b3Hz#'
    '%Qb{TE5VFDhou=m4#Nn_JU6P`XPQw1b*c-w5~F*+gU8+Xv=pOUL4~W(fJ=^Tn;SoMPB1QM4N0f&MsTs2s(qyKFuVFatcxlk@Wh*r'
    'W8KjD>S%QJ-sFykE+;K<0VSvcVfOXwSB4f7GqvO7RBMByj1wnLh?`pH97H=2-pRYW`h`#NrQ(@W1M%Kz=C)j4t>F|-<kFr#I*k_)'
    '04lfG)Bjw%^j{_H<vWB%c0=0ZNL_`6j4he{#DfRWZ+P7XoP>ldU%&jh+ZUc+E<Xp(oe5LRpYqnBg-~a3lMSH6+;j93rjbU=e8ooU'
    '*6(splhcs((d;DoB1_Gjhpy!hCI`AOz!z!Oe*z@z3zvhV;P#iXAn&<JTXk8vRRSTe@7Ys;R>4P@2#yn(MvVUIEz~`Uk>}5P4NY$c'
    '*#Po}gKfaWchtv;o1NsUC(pQI8$XU;cTaVIrapd(1VEi>p<zK0N<D-R>V!1WW1>3ddD$x-#y;JH=}@S|%^!RB{9MYif^R5)Gam(^'
    'Ko}U8qwgI(VJdPMV|*{*J6C)d085vfu){!|Hn14!T(oK}0u5%mZLL>`1mz{|OO?gjnSfB65X_^ST_<u$rWui9!;NG?w=Bs)>^)sZ'
    'QDE|l`{=5yfc`>H(;F_8<0pGqadbO_6BOv!3Ea65hOVL-I{osy?bGwi@e6PL;moSKBg4P@BawImt5FeM+zq`tRjIu7<@*a{_LPc1'
    'YXU@oyEBia?JKgRpLWCQcPWba^nPP1JvQ#BM^^@p991G|8a0SWUyiRLaC#|AMoaBMpE&8OtpG<q+gORTlQ{v(pLi^-um-Ns7^h72'
    'G1B_%eaHl`se&@IT-LAT#>-2Rs_|_qJEhr6L{JCZQ;Ush^1#(SguG#NxpK)@XiTwk!+UW1$K8JO!oOF@TKblQz#U1)1w1SaLFFG%'
    '>pYFdWN2cBVw5mmyN^@ld3WYYd^zmH|7-F{d1L?A=p>(S<-{pbfwg3s1w51VcAB7P@`~V|T2d}IfM)=dbAEX?Zh&Jq-LRck0AbnI'
    '<*e8Gv4u()0x^}4%K4?{u<$1`=`i~s`OFZGuH4K*;yiubkV)O4`tykc=an=twLnpA;x-PjOn7V5-Y)k15n19;LBA^Q%fD<N;tBt$'
    '1zd@26GWia%`kxIQ8keuFpi@T5HK>@EuHw8=Jw5<F}rt<t-wR!*y(u@5(0cpkh(_QV44gta)wrn2a{%d`^L7kf%dO2^-Mayj4aTn'
    'YGKb!bjuCAoM_bT=x7+X@af<eLO3_m{0nyW#GUm()5Gm)^<DnT5)s;iMbot=)dM>xdeY_xQu0t^sCj7{PrdJN-_<GUAx6CG&|bb&'
    'y@TX60xt6I8Uj`1K*pI*jV}(iEvNvf|KxAq+M3uE$us!&`S9V-6TjPurauHHg;E;G>UvPGxnFQB&*}R1aj9fq{PS0LD6pd;O%8;4'
    'wil>lg(i?8IRIk_0F<~~I3jKPU+|5cuEHw#dZf=ulmOcaEdb&;Es$x3GTsbr5J|1&!8PgjO&zxP3p-+q6oksR;!ySgi(G~jeE`}P'
    '5O>Ocnm7!!t^$cJ4-9-Y{Wt7w$#g2(?o*0pR(lQd>&&-DHB3d6z(RXUMA%3vf<FI(L+~mDxV)WA{}>i1kSwVU(9i@dG)QwnMs5U1'
    '(=X*lxN<wMd-$^Ms-)k~qV)c{=ml3z+)QwkAxc2q@}L%=wr0HgExzq)xhM;)8$nl)v$+o)amsQONxZ?az;%7wNvHs^`R3<y4)K>E'
    '9f^#(jw^=?87c$_D|{AWJP-m=9a{Me+G+b+_fm1pS{OAV^+CxPK^fug(rNeP!>AiTHv_sHM?ZVKc`N7o;pf9vhyabsr99F(aUO`h'
    '>kynl`p^7Z9WP8B6#(#Cx3*$SfPw%%L`C>o=y_;~Qf86=nbyIXLTfV$9&avGlX1J3fatul)TY-~!~)2=a4ciN(rx7?&<&-uMX{xP'
    'YHmOvh7L>|oSd@8joq3(l!{oYG>VXR>PN~03IY^)ow&@jl_F9M3d#|wT>bB^Y&6mDZBR4VOfMd~P>1MbriO=XLCOY!+R%kC^G6>i'
    '*PnaJCDbCdH25KLITgk9{y`J@VThIjq!-WEFVSQ8h`||mfm)m_(>;9IK-GUI(c0*r75a57%Lm-S^woWqJor_QqJ*!@4xJZMyc=D*'
    'ysRjPmob?+W@zX11*SwIgsKt-Efu$yc7<=IBjC}?>Mk#HN_dw4T<G=Ao$m#+_}q_(+aOhvL{qeNbg2~m6QY^;!H*LBm7au(e{uWc'
    '7UdL)^1^gE7C7W&=Mm-|XfRg^a-7BldPTj`V$mwwOuLA7*~KN7FNMUMzc13+jA{WI`Vf8t9H|CAYixkrh7_fp?B_u-;G;YCZwsD?'
    'A(y`sCuFbh8dz!oz9VhM0Rj|Xd^b}K^ryNw6n@{q?;bbbxwT_Cr2)pAsi}L8HsA;tKh!U<n(QE2!!jf@j6TjEHLp+EN=)CkdW+O|'
    '&qu9Zljt=PCqN?+V99|`T5LkqMVZef>EXXOk*23BEgIePQQDa$!u)MTp58k>Dzy`@5pL83it8O+Ci>T4353ycltdEh)|l#6JiMu@'
    'pD7C7{`hiWYt>N=&BUimPXo~o<P{)v!wyCmzzvO+&Ifnp4xXR4FOQp=jRdi^=_aLdY2$VYxiR9@UdfqaJ+xpb46a|fk*bFPUuK}a'
    '=83mfM9~p2poJVk{^8oehsmLKKx(*l?XY{`e%YN;_%rRX{OuzV7RrR0ZT1{(ZkU$l1@O9<d<atLF;8UqaqVsvz<6_?Xt<YJju5?|'
    '7;_fr<`dSe@-Y|<c1lB@?Ff<#21iv^y@lmFsCpMr3Xmov3Fmb~HA4XpqA#Vi+W%liyazC?w)$QC|M3p!Ts#(*gk(FBR=`MXkk|4%'
    'qXOVasHL4wRXoBjp!M3-E*aC|8{MnTF1$Q!|EzlUz^YoBz7^2PK*|G+hf<u*$!wvQ!)1cNM0RrJ7Ve*4HecaKKBPkd)}*HxDIR-+'
    'Y8zJeXlzGf0;JQax7Nb3<87qo7wiL4G}k*+_X5v|77bAW;usv#A!oJyqDm%l5iD|Y)HPjae$9p!fT^MxEik;7Zlepi4Ux_-YKa~d'
    'GE#-4SD3`R>V_+K#l^jc8FAQt<8NR8?qcFa6$CY9w&XyVEM!2Yk&Y~i%sA2QijqasLTInt&k2EWKOP8Zs*%$6vn%#zNVS3ZOLo-c'
    'q3_k5@1c++Y&@*;_mP&p=~92~v0A+!(|Q6&Ks(Y-GqnUP8dMTIvq%k2NDU<4-G{CsAMfXJ7rs>;Za1liLs30;W`L^$e}^kgLVjtY'
    'vRDgb{yEexe6AM#_9>RwmsF}!h7rtyL6^=q3JDa#QXGVx8G<V!)G$<^=jUzM*)Mtf=TWHt0)AeOYtrnH(2+;bdsJC0x&Y~<P!Et}'
    'Y7nxHaay<jUzDlpYlSl1iEc{s2-cYT)YQusCl?Esh~DTZb{|05x{d5*wX(0@1TrQ{A=-*!2LRDI54b9`8zeD^WXyyB72u_I6a2S|'
    'sIlUXw@Rs^RLFo}vxh>&rAqqA_lc|`C%6Q`QIcM{gHyg!{XC@Tpvo1@g$S4;o<2Cl5prUzX%NG87E;S(tMB^nJN|aFSQ@EXEkq~M'
    's)p`eM+ESqur*5gS(LB@ofHL*ScT=aedU5Pho6rQy4HZU4+06;8gOWDk!AUiz(Tn&P~4OjL@@K?KT?(Sik>?tgAP2`6)!r^(m1tX'
    '4g)tlnVtc?rvFe{a*?9F*5w7A@GJ$zOpn+k`u(;^FsASXkeSm&1DC%97)qspQ>T-r^91f>0NmkLwCY$>eIo)QYYE`*{YkqWZ0%yp'
    'FWsHn!TOJz)4xGx@KDiq6==$*8>!f_!5AUFK<ely*LnDGlla(L2p_SzW;@#_HGbh-_?L`b*XH@fzj9$N?}?Dl<qL=lIstqa0DB^x'
    'yJ^DN3RQ<-Jlvn!oAxAi8+xhqz_nCju3=gtEy4i20CWc|6`*tD6NLI6n5OH+UUMH=BCXiZyY>y~K~Bf*<K=6LI}ipt`Vq=r)WN!~'
    'kN|Qz==gGgq%kA^jqaLVJ@9ns_NG#3<}Ea8(g#C*hmj8t%D@t$2%!}x!5x4Fc!;@X506Vbkd{Pg4=p$r=nDuB02ApWcpeuv-%LMi'
    'Kg42azdl~G2ig0uhkdMg7Kxjwli~^2GrknycGxj+POwBk$`A+S3;+^gyk;M?MpcbJztDrP`Z%b$XDVTo1{`fDhA<mR`EmAON3@Hk'
    'tXpfCulhI^ux4|*w@xSf^80DHn+NJavRBw!ULYAzE}SJO0WbiAzM6F1=>ePH?EwJJyZPtiLxEIBGK0JX0wVVbhCtLi7XL4*G)PN?'
    'd~Q>U_V^37qCdNg8DOz8jP$G1!YRX#h{r;Vffx&Od`z=&?kNt}??tT4gX3c<pf^G>LBEYODTqSAws=#(x3bzJp}^M!dPz#xY~<h`'
    'pV6cp#1B5T_DjTl{suge3JZ^eIV9hb?Pn?;T4=t96bPf5k0xCe`;Stl$BGKTs^$PT8tIASIR{_d(1*YPk8%q};D{BD1q1ZgY~u8J'
    'ga-<-%X@%7CYeYCJK{4z04D+e2=WW$L$e%k9p2qoe{8~6cYKx6xMT6Gh$jq^EsiqXWm0W$6@YGT7RacaU!=<v?Y=&oy_r0ot)qZ&'
    'zZMVz2nhgOiGI%r-%4!*+Lf>ukhEaa#N!a8GSvsM6AAWoyX?Hwk~C9ARCCXTBnj##v~AK)TJC+A=+xkOL29H1DlwIsyh8zBy%ELm'
    '@FP5=bKVvLCq((%@$2FS@Q})NnRLid5{8D*#brl75fBuzfNmd19P|P~28{bfd#W(@f;57U9wK}>8xm%b{s&+$t3REopaFbf7*4-r'
    'Lvf4i-m$=VZ;`MEdTBIzy==Y)5v>CDuL<@LpBAjEtTOJG>}a3<`BIAckeT)A5aICi!sJm&C5}KGD697Egya@sj2&;?(8KP2`&5Os'
    '47AC(0+TLitS<SoL8~p<zu2<aQ*uLEab9lS5$MN38jYursy-&r4I#KoACYb;Z)`RLg$g}HOkSOrfSFtA<|jqN@l7>d+7s`Gw?j=r'
    '%V{JK(q*FKBjRPF3=e*9CZ$O6);%54k(=rsZ1>4MAHMDiyF#>U;R=H6((fGPsG_$R$u+GQ7EuIoDB8blS1->GJ9ims&O+fS;IR^g'
    '&5I8Rr3l2F4Dp#xw2*oTO?GH+-P3XREj^uSvzL=CFkG=>1NDmQ$;J^L5{;naAb*-W1n;f3=da#SjC-N+`;_!=JQX>DTw9cls9&JG'
    'fabwFon&W+SqPlQ$zrh!h5YJJ$v;q|V)ONQe69*ighcwL?ZT_TtASu(VSPeK;C_K)i3`<$cdHq0-OwTIx6d_KKV2<9U>6D!(NkZd'
    'Q6>2UgvBeA@*8&$sYod~Z`e?oW=fC5$bo>0GPY#KRI*gp*drj(!Z(u31rb&6uRic`_vnbz%k}Y>*Z1XkZTL<d${1L<%83??9APEg'
    '8|bejOxR4w*y+YCJ!~bltw8H2Qzn~GHDijMQOJN|MUY{P)TWkHagv&ch-81oeyD2Fwqyh(2fK*Zd*Ff~6G7Sr`$`856B!6*tr~)~'
    'PMaGyBsmlQa#ay}@g)a6rHcW3+Nj(D-h}T1QC{w8k*pf5qPuoWC&tm+8GENVyZq{Uxs+M@fS3?C(r7fHqx$v~Ie2e)WL{LK&9B;)'
    '{tA_`!jhGggx4k~D?FTFCc|0`BS@eu-g&zqlPI~n=@;!Qm+fuj6rDgEiH_0|S-8qFyC?I8h(oLdjU3U^+_)j#sufn&7_%rGWmvEB'
    '`RCNpj+oVpqfCXK11U-EA#>wyPAtbghwcaivZ$<p<qF}DRKucVMJIst%81uZwTQ!<tdnrKfN6T;uFm(z%TwjUqGJm#OMc7U?kHh<'
    ')J+pS5#c;Q@G$g&6R;`0c3bzm<4&A%67KWf3fVS9b_rfni~8D%<p`k?0)?jlptU$cl!GyPb@UdpAU>{O%gblX<Gn$~PiUsmDrzN-'
    'RW3J<8buReGVM(o-}%~&JnZ6PXLT}<x{UZ(Igz8)gF-Sd8UQX0Xm!*?w7tQ0vA<E|zF{vahR!eP9KNfr5?}`-Oq=2rswQ(hIw5i`'
    'jR;<q{K-a&B&w6!HnxbU<8so%uGorDf<}4>VFEwf847R^u^h%7qC$!|wL%wg=-NG<VUfQcQ+Z2+nW<pS=p=~)CBbkZi@Hl+mQR@&'
    'sgK%RUx2VGc6;adR|$?-QdpUe2)3g+fwMhM&7-Kc$nRmMLG=~c{OYviX{W}K&^+|-Jh2kv*KnV~`w!wOrbVbAPC=4kVF0c%k~86j'
    'b9Mc(TXM)#IRt0+r4SWS)L_H_k<`eTOhY%INP$48@t8EFApkz6t8ZAKMSa%P{DkZ}qz1^!$tqd;Zz2KiI5hqB2PpOe9#EE#Y)tu<'
    '9i6QqHpj1W-MhRU%zzv9DOi?dQ7&mS>(ljvX{w$V>=+b{SEokjl8ict=m_DkOgfM@m$MH09?WVc;YPv0r-R(PrF+nlO^!4*uD-{X'
    'n>5zl9W6IIZ2`>MaLgxvC07KbrX^1|8*42(UznXBd%1ou%N>ujqxQ5TO0?woyc?=Q8^AvBA4l{-WsTO84hH!L^FD?fcl7<S!r(*R'
    'A)qb{eri(-PCb!B!_*!;w$d865=pFGxH=E|J}GhiE;Ox_-ZSzF5N#G@-D&IvOHZ<g<jzucjlVQy((G>7N%~WKc{Qx7ZAV#rX0i|l'
    '4<6o7gj}NPkfA%=to*A86#`~=w`^*=Je^egm}Y}~JIECoVhz+5dEmjg!XnPfAO;LXhAiED+m3b>^%&!Rl$D9O%OsKrf7Vb)cc=(t'
    'R0Q8#5pld8^3+a_!Wee@0_D&uS?}cPFhbtOI}_O>@tJvPsclsmW=Q~V*vFX+7)p9WXm&7*@hJnt$1(^D-$3&R`?xO36on&?lGdkN'
    'w(@pQ5djN%PM~7Om=c5olouJx&|sQ_ZzX|{uY{_e+ngi*D>hT^4g!ElEred3Q#}fSp<Rh;75E2`0exS>6D0W?HY0gqK|4h#ll(>Q'
    'df58)oy_)vCc%*^!;T>Vb9fN=aLX=^a_iiP#8t$iD2LS&rCCinMMBDc=o%C5K<q@61Tv%Ixh3|#<q!!@2pa!_*%SU6SnV-Z3oiOh'
    '!;ojfTcfFBEtw7hnm@`{r&)jHo|~nySrGE$f{h*#=pAwy*eNecbDwBiP;&Am1Nz9F{+dgY2P4e{SjvfGTM)m|dc%FtYAB+Y7aL4t'
    '@F%WF&N4h55N9&1`rPXI0V|$YgM;Ni7kk@el1}Cnk-Q1$lGb1^Z!}LuHIvviYKUQBTu*s`PkNHT{@kB<1yQOETHtuoNP>9>n!?OR'
    'h&v=(GgJi3XJH7!#=`=31zhpTzLpZ9dRNHcgI*Taz_>>uC8o2Bl?T?at&HqwIL|!5(O$i)bMvHjKcvDylpfgvodKP5nr|=@;OHZ)'
    '<dUM9!Jsc=uHMgk7G>?GNcvy{7*$VDl<6ACV^Gp`9eTQ9p!V3=tVp*$+?4)V{hpTAHyi-u-O$HLOaTtTyc&f@B<e)!M%41=+C7E6'
    'JAB0!@@aQ;W&Jm>65N?t8VW2sz)vBO%l<XO4x?UxfJ?#GuHeW0%Wlq?Mg4Ff-k1iJGXIU~e+mO+p)DeDyjSot2hp??TUW<`pJAuU'
    'P03a$!k$1-2k&2#(y+vDn56`*8!J&VWhBWi#@jZfYPj0251*ATpG*Tuj%5tam_96h8j9pmIJk5}-Ei%W-jI~)4Pors`hf7XPr6q%'
    '#;IXI8o3}6M3{v9bF$>C-<uweJJ9W35g(~{Te3rH;a+|Q3}_|&qF+j$+GEg9t<JqNU%R7o`AI(Ya<5?l1t=br2`)RcujF2W1r6ln'
    'tWmt38eap|77{CjlEcm0Ikj_k_17D{H@R-|F@ZZ}U31Kuly;J82dEItF2P0d>BgNcy@A?2Y1Uvbg%`a!gbrk6v{s-jP>osv;$)K3'
    '_~E#oReL&oeK{&&tiMlyP6<dxcCApmI$V}$_Hgq;96|*}v4Q4;;<b8T=Z!3%_Te>RhL^=i`Ur1<6mEMtIpOw7z%0~33^HSFTtlIo'
    'AiSmT4ESQRyyNEimL2W<?<7rBsf10q#ZR$dgdsyEbgt;pFz1K+CciO4Ie1u<1{U!#cgvcD>4QD}^hd?il8K_csYxdGI2mD(0n&og'
    '5`0OFY8JO&o+1?1`W+=~ztf#s@#K>KnqOW<qo{zOP&R-H((#awWQ7Efu?g_o>-xjG<3r1p&o*=Jcb}ik`R~s4{N=4kKbN`7m`BCb'
    'IZ;R%0ctU2ApwDbL;o3S?Fzc{CtE3|{#+0sEHJC3^Px@-UQJYp`C@^$@>zqiZ|l$1(Rm=sGr@TI&m#983d~lGkHBk@r!mMG4;mhb'
    'SQa4wgD^Niw3RhY>6TrTo&*tvIRtW><I_Z3mozS|)u0j#A~Ab~nut$MQ=dkkKFz1C4lsH;(6<NoV<BA^G-l!vYXCQfa=j?MRLldo'
    '6XXO+Xn^;g+I<BX>a-7}d~ScXx;v>zO7$^vF9?{5A^;j$jxb=_5TI!8!=Hoh-7rNeuiFOJ+?%~q7Pz_BUrT*-nckwPiAt3*YeFai'
    'aV<B(YZ)3qe}*yDWIxmTUGU!@3s!9M78x}c0M0JJ1<VjHm}1sd1Ai9TFP#QA4C@v@y#jp(Rqp{-1vn!nbdVOYHo=>eb`&gdc#Jrx'
    'OPk9OLc2mAca~X6KXb0>%32;su?USZ!-oCpnU)FDo3?l$aiPxTPhr19Ang6RO`KuR*AJoKKu4jSg#60rnb9Fxv^)xKd}Tzp0+fb3'
    'V5XJdBYh{Fp6aB5M$=IutvD!mcxF+@LZI%{<i&f2cQm3#XJA-bw*v?zZkae)&ksOs3>lEn%!!ntBE5I+c0?+~Ne!65*#AS*xr^Ia'
    'Bq?Pnh&R$7;9`MLXV5hP0hyYb;0*@SG2#R7%b5F>ui+e`-#vmV3pKnf8fil(P1aR-WJKE{ECcg^vMGKvTqM8pjnLEbgi4*z!t!Xq'
    'q4Hz>r3wp>4xodXUvy}LC^g)sm|o!4wQl*BEt%f&Soj#xvhnNijMse$3`W1mpa;dd0t$;ry+MFo7gw)+_+wk@PHRH0NT8GjQpREr'
    'A;zwzGEwPaHUji*q=l|tTkiBHTGOMfOEkA2`5MnDi^)<8^Hu0N2@C+Yr90!qc?1~3a@%NzLf_uFlcF|=Notq?Of3vtd646ztBJ5s'
    'h8P>QcyFO3%hs>ohE_jwy(*~{4EdQ+NTF`jgl8ZdobR|VWRxHauuk|g$kU3KBT3Mmc-%jJN+s~gOGK{)VlMLG@cZL@Oxl$Ghm0m_'
    'k{DE70x72ko)b#l!Ct?s-*?+ZSFvb3Hu=Hb7i^i;dZtA#_E3~kKyFF8=nX1iaxdAzFa)c;en%%=C~ObP-22j$94z&+1}o$8N5}$M'
    '!c#0u0VC2kT{X>QVC?&R{dQn2?obe)-yX9U@*ZkK0m`AHCzrgglg<PmF}izPcFbX$G%iCb)*f$?Qo)o2urH&U9PO(=3uB`2uILm%'
    'JLEwl9xJ>N$Q*n#&~reO8qHX3OR#AAlR9zf#aCGnN|`O3ap^c?d5Fg}0k#?4l5Mjr0T%S5t6r63QOG7Zh0zD22}n^2#!eRaM!YEQ'
    'Qcfu)Grs+$QvKXw`WK@v+&aIN3~jQgu}URyJ_IFzirL~T5gDS1umE-jGpwOKnacG~Xmi0JP}5auYyrZ}03&j@r=GzZDymb#V@G0@'
    'nq0Z!St0PMrmg9<F%5x?fJ+LU31)$4&ALI^Bf2wnZ9=>Bn~J&g>kf8%WE-G<#i?VX1`AM7YhJQuZ=#-r``#}?1zdy}N5u%-V#fBi'
    '>>sCeaYvd|vMa}fj*cdyCzupK=M^V9FSfmy19TP>2^%ACVZK%_jUxjm>90pGrsnSQOUL<O5)n${zJsI?olNjhihy;(Gy$EWsE+G4'
    'un2hy!>*t@!HvMD#c3djfK)5jxhRi913Q4B=xtN`$d`%B1tKasM#?b_wgLtuNa4Gwp=0z>*g}segsHDZQNwm8#8iR$&*!i?zC4w@'
    ')ug)N&H}B4SdNS<X-Fp;X|{uHxkgN(4hluttJYnRH9g((I5{%>evwE>8Id)Tf_xOTDoCmhT?q4AO)qL{R{il55FJE9SEW6T_;e5e'
    '1MDa&vPl!QS&!D04l`xZi0yVua$K?a*-!OkPp~PQk8=ZYBhcq@npoWm8H3`>5u$@<GBiM1F%oLjEDflef2{lEtkMfTZJ2n(<pDgE'
    'N%HVLXKokj&*k+GwrDT%dwTkYz4;edHQ+E@8wH;{W@a$LLUW*?A0-W<4a)HGA%Nf#nW4!+E=rnS7d_1h*T_gOPFmjH7s~!#Q+0p?'
    'p_YUBAo3swApKCPt<Z^_0n3e0x%#Vp`Rj~nQla})c<OlXFRqTLU6)6UE*LZn-|SxQj-YhJPt<~Q<rWqq=k}tpEr2Y(_7LnL9Xk=a'
    'h-9cUs4C#!CBD2y#Ys_q_`2e`)minjab~2^gGf!Ip~3ig-bt_q)EI1su-wDi^h5XO&sSdg#tqsBGEM+4gavsSiwdiko5J<VRE7*M'
    '5a*U@%@!)2Im!xL4fv4Ll4EjZpmU-C5PKDiD$5M-AiuxDvX6`tbJgZ)REoS>u0@MK0sjFf!xlXi84;Z>S#{Dw%`{C*i|*o!Y(-w4'
    'KUDs{|Cuu}gA|WU3+p&~XUqW3;$kTogfI=qQnRLu74vDu!(tJAsH#gb)}$HL3NNG4z*qzWk7wjP!=-^-#7JrNWJh1S@UxV>jA$q*'
    'ooO0~DKM+AG01fYk|db`AF?KDATC1a<4lod@wV*J2`>u1@vi~3r)L0piD-#JO=um-2o=oe1Wh3SPDM`m+o}uMrOGb`dpJ1yW0Hmm'
    'MNA&$#0+~Cf+Y41v=Ojj#XGF8Tv=tsw#=;_<d47~&2S2#th8i$N{2A{l`keo7}sB8=GsLU9?h%R26da{K*eWH_C>8mW`_kBoJ;0#'
    'z@9^~jhd69dc?JX8qySrbg!E@(`Tq1OA1>n;E!7p>=gkEVof^dwC@M?@)>ljpHDH_uUmJ)V=0!O3+mp9mJA#(Y!@fRZdn8IfngRq'
    'N(?2J7!tHtx%R87kd*B5vRs6W9Ma@cdY1fp@lK>wLE^|bK6DudVOX3hm(3493XWOKJp|JRV<#Yk?vdjRSSr*0C+YR5P!Z>X6;v*_'
    'jf(}7`*tx<W&m~C_!^qs2#=u0GO0wJ0CsuWPIj}TfVH2~sp0aJUMLqYXY}Cdpkct6w126X@%xisGU{!{WW$}Iq#(tfUG2iZzdT<4'
    'hI-i=YW6iMbt5eTev=4#2j#UgV8n||^IL|>^-e>`Hit(Lh>H)HE{>D*Q+me^L#Kgxz_Y|nq{Id&PH}@2AlI(@O1~|?S_8>WKmbOT'
    '1WP_5lrdl}R4_zH(blnQXU0WXy>exw;>glDfpw7h(UufLMx`C?Z$=uyv_;O1sxcS+u;13-?Y<TIm`k&k3mz-_S^67~Xc}J)Y-(YK'
    'iSx^74_g~0G;h72h~m)5AsIn77aw9ZeD=5jfWwItq_9-y@UCs`dM^*h?J}qIa#_geC3(<_mL~x(u-dE^zUFTN#$((}yQZ!Fo?Zuk'
    'X2<e%%1;1oLQ|42v>;`Tf`UoFEEQb#@a6)8plSy8socRkhvcf|8D~U#gBK5kU))sXM=JymFpt|W35B62#w3Qy<<GvzIIBM#zZTE{'
    'i9PV7#ZeKR3|&dAlBiFK&-CGN-R~i?BUPzf_z-}X3ZN30J$G${gc;<8isz*j>_B+{1B(h(VRP)(EXXr19$a__>Ttnc#898JL#vJ9'
    'O-|nage@d>;A~unbM?AnQi0`F0Mx*SQtMI<14WNQAmlVm1jC^M85C-4mi9w!lzwwBdS^s+`KP0X2*apZ9vo%9WQ6*l<3Oi;<9zBk'
    'W5@}%_6|N_wt(b6;5mLPWbgz-{K~}50(#KADsoEZm1lws+YxUP|A*RK`rMCM@~c#ky;>Oxl6wqt{G(w-?JYakg`kOukSI#Qm}*Ow'
    'Q<MAhZ{?X{51MfuVj>bXr*LY<aFPP>aFuTW0QEy$wc-ZO%*Fc<1QuUK9LzPHmys1*7Ay}_wpHbinchI-4td$SRZkhu_OPqa^D-m|'
    '^*2AUm2_$pqep##nF@-_M41U!v+JsVH`ZmR^)F{WxZhC%;!=k6lLNJ!sztzozK_N&pE%PqLv0v&d0wEzmuC@L3LOE6**sS4iRHvc'
    'lGAgtsTJsds7C^lniX4WZ;F$LW?jj^DP^u#2aRmWE+b@Uj5ea^EOIOA7<`A5<y>2?oD3snB)WGM?%GU85{sDcShEBcqBwW+pxGo6'
    'VVH%M8B3V~s=%i|_op}fWy4>wHs2ITGqbpRw42c@4kKs-X0F(HjT*_Ka)}xS^`Kd^@av?i^T?6QpIR@gZhYyuso<aUb3p>+bzn8f'
    '!fHG?alCC;t$%jvud}X~Nfu9D;yajRbT~(5^oaUuG+mUuETGReMYq16c5p@{9^_@d$NB}dpy1Jo@6Cj`jD`r-ckrYkQt6X08r=g^'
    '7{tvFMQ*}Rd#GBN$4q<Q3v5GML(d7S76)4`R(eD@2Fd2Q3wHIw`nL<z5R5gzGs#$BF;XI9LJFiydkSd;7C<5xG8d<Ghn(ieRDEi)'
    '&SBbb1}Nny@x>t|LWWAclV*8t53rv_T`#QoynRN9QcA=qorJk~O^vh~P_UH$496fZ@lX}jMlRbNeKfZ6{RJi72&x2{rq*?x*cnkK'
    'k95qbhRLu2FoC9vO@Nby!t%*3{rOYd=Q5r~EoRk-r{Ay;1DI3~+fj%-KJ%bSbYn<xi=x#7o#IFLHW%^km6Y)2zE?fF5Q(*uQ-LOI'
    'SxuJ(jKI*PWiX>A0rU}7i7%5<Yc^Cf+Yli!Mycr7D5??ljGCQ5`9*dLtcy*ErUXD+X>Zz2-4sdB%qB)7qX~n`p&mQH7ZN%nbx6mi'
    '6zaR8-1+iOmMM(SZd(`&Xd(l@=(npLY;_<>(V<c&MrSgnMvO2hSVjAm^HzYlRf5*o*E0W)@dKDKV-?G+MPfR-qDF<jm&6J7FyWwg'
    'p>E-$3Q#of%!bfYC{_q`U%l*lowWCKh9_z7QOYqOg->&q!XS>-YcERJ(+!*U`(+{oJ-d>VC~nm7c09ZmTu#KXka!u7Gm23jIQTEQ'
    '52Dl+n^?&tn!$Q;0npgTWllZr^@<)85WSFKXlHn5md75v-@)%MN^oj^ew&zGY9%C<0Tl!UXm)(}0^p-$iE3P9>c3|36<;5{*jePB'
    'g^H<4qLCVzBPh!|AWNEd!cnIctFQY6QG*hM$luZQ;N93^lL#2ZL!qwF)ad}W$Hbn}WeXiVZ{E#qub&SDIUdxslO7v(7jImHa%lZD'
    'NX2LADd^XO#)Y*TIA?k_)1l<R0oO!XEvlJrIr?6>JlQ?e2oyC*=8g8sE!2;N;sA_ti=mdK55YYRwG5DzB*<%+fnBD7n6=xeABmbJ'
    'ekb1WzYz_}`)AUedVo$Mk;=V}I>;4=Lw&M?SF+6Is)Ny2uoED@k^7-wVj`^IDp+QS6>yd5)QELO(ByAhsB1z()W>n8^$9X1Q%Jc0'
    '!CygwSr{Og4xxC$rl{!t*VTV!8ZJI0g$y_=VG^c|&JAM;tN<_<8q~*;oCX+;JJE)lwoyTNgpy=97Yri<mSsyAmZI(A1q>oi4QLdF'
    'noj1XeN<0KWy%Rf&@2cECjyL?TKSaE%4F%K;nqcYnv15cf8UG-rEcmbZ|QQtE{)N}NT?<dYN9r=630tAsFor{)>z!xtM>rE<|*Bm'
    'HITrjJb#JGTKT^)LxiDbI0M5;#is$ucsGI16uAf=Zr~tGxzc?>Gh8VW;z#-svuugQGD-4k#X*t*E12(%O<WryUWZ&(4fA7}Y0)Y)'
    '^2|*O3uGCc1n`BdWRM6mto|xrw@^Ja7D8Eu^KK<+p?n+r<r)VxkTbKU+0uU1*qbZ&@iw2e%4i%)E)$7zt7+D)OmV!@NpcFfI5c~q'
    'o@o|m>(*}O)LJLK2vCDI8X8r&OCk4RaE?D6Ei?S-F+PkU!;@ues<Lx1SxKy}-G^o@JS`a(7gcczC@t?%BL<^s<Tqvk&W6QcR4HyA'
    'mnL{9wrM}v%PGTVM^6<(IH*yXs)oWsM)bTIDle!H2m|3C!iL~WqBI}Pbz7++a$_VIG>Z`1c`WI;=BPr0e8gd(Fg7=8$TjHR+Rz11'
    'j=@%`Apw613OCIN$jl`4)N=}zbU?W1Xkx?oq4w&-+Nklfc3@M5zj*ZP5XFG)Ap4>lp-F+&G%CDa=M{!G0bIbv%B|G-R&hHptOZ#p'
    '#86r#2)JkEwsPM^M9<lYL*K2<we!RF{wv?Y%lSfmgrHf_6(FVOE9}+XWC8(D9s)FjL~|4|n!ye96~x<Jn`PY#b9<5_sgmDK-g8{H'
    'MNtJol7=t+UeN6kZ!fSIqF75BNEB;Tk3{~ub}K}2_yz9i<(bc9sRehtTo|VYoKI7SGz$(898NgX91KjNAYC+YJZM*TA+CKWjEa5w'
    '=qmZCodn~qmjf!`AdjBHgVqw>Zdi{4H`A>ZO}q_jE0A|RhUJB<@nmi^)J;lyO%}lqm4+IE8(6eGN_tvb#C5DL{n{f7k9!?~8*(KH'
    'Ph%*2G`pjNH>W9P-1*1{d(Ej2Vx{!g@1w}wVoV1AhiU70DFFtz;+|&NsW3>4T13=D*juab5p7|WaG{gkG5|O}%SQ7Au!iO7h?$9i'
    ')+gE`5WA?3uGq&4Ap?tm$YA;<T+Bi#hj+}VpoYjfDVEs9gr^Bt?4nXqKnsYrE_pCwKRN--yybsUrp_u^(f%_e2n&wYRoY2uw>c~C'
    'N+lXpq!|r8H7ckb;WRSyN)%++-gF93CYnCMBV4<ObzEo)VXRMx7Mx6ORv2g~9vdgB?x4v)FtPbKRzC=$!(!@l?o^hC9b!xe0lJU!'
    'NhT9UY#}h4VwxEV%5I!2+EyQsH3Q#+IzkW*Woblkpy>ddj9?G~HHESU|JvTIPJhok;EXDSR?VKKUyDWzb~v3vXdXm!OtcuNfnZH;'
    'W09&2B|>}MMxJ*|NatqThHnM)2LKG%t@=u(UgHf=pn`NmuA*qt==Urx%5>dE7P>&qi)lzIv0q4J;usle1e-@1FzL$_H70?&Yxv>X'
    'Xz`@=g)NFW0gE47;zCo3uY-xk&=(*Na(A%-`q|ikFg3zRJ}b7JUwu^0?ag(4WkgW$G$>XB=&CxYV!T6sW?zFQghD(dBQnEvds*9I'
    '#;*{_*@*Mk;0A#5jW!5su_R{-&h#LA?RNCn?dC*jsoDtCEVw~jYEZJlH0%NbFXPQd*;&(@GNPrgenpG+^PHboYCu63C=@j$R8x*2'
    'eEOjmB@qI*<L1Q*i>EXAwW;9qHtgPZQVy%KY$Oe19r0Yzlp%BG0U6P6J1GXRRAs!HyJi=s_i~?hIN6jqn#>c1euB>k^DnS3f>0$v'
    '7rYnIyvaW#Xe-Zp_;4HNaDs`3CMs;7N|+1dZMa)$NRbK!i59qT_;8uPgBl2y2AT@mc;>1{@_Lq6a8&43V4Z=SAvc;AMm(i>vPM=z'
    'CZ`rEcmsC6I&WXL^N!0}4Us}UqnM<qCI_NvMjJ11A2Q>C%NGeG`wMdaxoSJF#^RLN_f_g83S9i!kQ@Ze;4>;I6dq7P$<={f5HUem'
    'mnZu*n>iD0YoCkJU=r8hV}~Gtb|%*`5KxpZks_FnM((;zUVAD3b^nODUx(A-=tn)vUgY8j6oVE-gBp=Q%eexI8$d1ur?q(_Z^x$v'
    '%T}Gobmn3)p{oZ#2r>$mIJofy%)!tf!H9-?jD-X2E2i5_cKt>omY#19gI9IGT?GF{5)LP(*U*4TT5xELyft{M$VdSt=nV!5!Ny_j'
    'hWIbXPjgKd4B&x85+c0%kZ@<TF=n#zI3Vr@4YkCVhIq4fBlY}UO{RAAeZ_z$%we1h4GqoR;#dUlu_wVs6tFhRfzzGM-UCC`9p?On'
    'T_}vebQGYD-U9stAdTEEEZkC5kqZ7uxL5At0>k#FGLxHT)-Br$(5Klks>YaU&3AH~Mw=&7mAv+#sJ`WRXdq;1KmyY3*wcGQ(IXE~'
    '4XnU+Uenibz9c1Kls5#qX)OYBCcAFV3RIc!6iOSo(|n7QY^p#gt$2WNR*dFjg8|@WtXA>bIC>V-zwV|;(4mK5ppW%dv_J7NxKr>g'
    'AVYD8oM{vSY=ftF>$icCtz_2Zho?I0a@ay&26;{+9bur#A{_?JpgHoKS=dY9a~#@X?cqGpfuB<$G<c?=)9sTtRl}Go;wF?_T$o6V'
    'Wd02cSbf=OuUfs1j64Z2Wl(EN-XTLnoGV6R0X=ijNxGoyZz6?X`yLkeu#;0r4U{c%PUb_zfCu{*M#qt{&)O8VUaR4ou)syzDD7fh'
    'MDlXtWuQUg4LglDMx2Y7(ZZRbI)KDRX$xPawCbCM#oHxy9`jR}Jmf@rM_Z43lcTFdFN>D6fuAB}78>}VyW3Z<USZb8;f4_ek#l6;'
    'G0>h~JW3XxKHTg9H;bMUKNZ<Ie|dJ)M?c0}4p1E$9PLSxMvfPme@~+uVkx#Tt!U9>D!T2S!^~&*?oSpD4B7*>iSTb2ztVEUqQeRr'
    ')J{_wIVl2hy3fN@w_<f*!;KI_YMNs7VXz$HvVjeR2umg&T=qduVuan|4_(f1T@Kj6s%BEkWG$m;XZXg*a+YBje7}&-n9(LLwYh3V'
    '#jH9)KRR=GW!xejES+qVq;Fs)d|EZB2{uDZ`=u{xg5ND$6DgR(l4QF$Xr2!B30A$#D%EEV0)+A$Mh&P((ed%!s&JCkhrSFuAyQ#('
    'ET_`Q*^$|4d``%Zh!Ks(v*2*V2%Tch`fk<A8v<#Fu~_>!*;P^hz|QZ1gAusncFv>$&<rM>6mj9dEnG2539c?KFBrOpNdr#@*h5e<'
    '97sV=p*-;hD8K*^K3n=!i{HIZ*zb;|vG3%?WI>vgiC+ZBQLE9|;8;P|0Cw2K>7K6gr#B)sW!~){)iXq$;U0ecM?nSzOu#sI3b}^J'
    'Pq$L@<rz2))xjueECy`D=Z>=P*E_Q&g@Ba2^fB+0*aJKL2{0S$JE8))FKGx#G8Vt8w=?EwE0#Uu{pGdQkz_n#($PWANBc$Y`8^|&'
    'F$&8GteIW#VXa;J72K}a0yqaeacFo{LG-=kRLVe0nHHdnPSQst4UGQutETEXY7cjmhneZH|M>l|d%Ez8!9U^S!Zgy15Oj4KR*(5g'
    '673A&3prngC;DlQ!z#Z+%D7wFoS<wUf5z|co+eAw1iOm4Qb0;}xf2+G!Q40~R*23zL8PB^@->e0JmmUtrx}?4IR1IOH0r0FLCk3J'
    'MxG#I1WInw=|P@?*mNQ9A#${zE6NCgcdtM4V?oCIA4k`L{nLk_b;|@vswb*yFd6D=nC5sj1&NA2pH-#R#HZHZ-7Q#qp(}-C8<GdE'
    '&(sTaDj7uxZI8-<HenCf9gG39_D}1k19{aQd=B*%&V?&~vN`|B=FL0ca{AJ1jxdxKTqv>hU`iSs2Sy>1yNK%m1Op$3fA-lX-hS_1'
    'ec63E5Q1z`5ljH*Mmigk6)45%=Pk1(sM(!7p_p^`(HEqa>lg37@twZ?$3oDRu{$$dsQ{>k99l?}^COHV%qRkp-$)NT+lsYLGcJ$+'
    'd-uQ6!x9hvr#pTvV6c2E@bgKyDTIW@dY#JXmbr8S$a&l2#|7zWb($pM>)n~1fhKVGTvkEi1PD(AVXJ~d3n3wB2o<)?#CwKfpa(>N'
    '`XTxAqczWeEtLPvv%~g~IG4qGaBAXFdBazS_8JGuJ<`?27M46^`Ck?WU110|!%N}Jaly5+8$x5~NLrwZp;eO2h*;^<hlGm{){7*;'
    'mp|BUIUQ7rSf)WwqkWGxA5v=MmP|3lKEDz5<3mc?2kYIxFwU^RQ0!)>t|)jT*Ch`Rmq}P>bpMc8;59*PfIB<at%pz9u{8U0(8MAn'
    'X#5~1jKf*x`D$8*UZ?kRkkwq)@ad5Z+q;wBz~Rf+ZN_69-0n0!?Ri&-1{kuT48`6M_g2Khbfsm>Mo0pa2UCQpOi%)?s90KSl{pbi'
    'm}fK_{@JqW#4!V-LqHi6vNW$cCj}FprTvHcslP3_Ux4J2KQ(qf_@NB&I#KlDX^bcq8ZMetJX$H-V8u2_Tbfj{;>&Z9nNMlhK|lxe'
    'oJDn^Ek|6pYVETLx(v93QAthiv(;jf&o%VsA0)V({)0@jif7WwgbNu2sSl$`0agYCD%>kjy?ZIX5#sV@&8k(IUa&3HOkU>bbR<x2'
    'vLv?#C3q({3ynyE*TF!y-ZW{|vc(H5NKH@Q3Q~0vcLg5<Ck+gWeu-hkjMMN8vu4p#Eq?hnL2V@1U#7auXyCxYVWDCKNkjijsseA7'
    'K4<gUvharPmg8~v&lg~hygkiHu6Vhm^UyFc%?9X|C5a45;cK9Fp<<L=RXT_8`BVOE<r<m@!UfD_hzP`4obTX<;J-o|D7z9VUT{Cg'
    'M5<l=tG|{46aC0R{C$|O1S09pNK^pzspA@@Ml#`{V4K!1Tr)lv0DodOH9j{~q;UA)%^~ZS;D@209TXwX_Ygk+&4<HFx`O~i_OiGr'
    'J|A64uFykx<_qFZC1Zl5)k?_Er_BQ=G3zlSYh*z@SFKsT<7gK^r?zgyAAw)xGyq2^2Q@2KE09jh1w<}fwOq{=2jogp&ma|so@ZQb'
    'iC3H@^bhn+Kmt5@{)oBHRJq`>lzBq!<27Qnj~Ykj`ivyySz>&qQ_Rz(k0>y9_-ws1#&F89D{><C&aJ`)!yTUG29C!FAO~eW@t-a('
    '{17S)TeaLX*EhvrVa5SmhX@GSXwDcDb7eHq@b`>w!jD_w*T}zis#@_Qk^WC{o^dM^zW^FGQ~Ch$A>tdsfL2^eJfdMYf+_o|#ZD7>'
    '3M43`QnO|z<GoB`3)JYr@TqNKPM|46hzmz;`1CZK<NE7gYsTw|G>yhWSn4d!ESESP3LFqXSt-hd_p%o^eZD05&sOpDZuwjeuO1!+'
    '#}+fGwauHOEx~8PL*$3^Kky@>ZRFp=r#r4*wLF!Ac97F#Xh!`oX-ABDD_c#-^$7Vooelg{5pJztnx=l-<;xs)6r-B^EQ2dLgqpvG'
    'l|2OuX1Q35F#-v!S*q&#)sYGQaS-M3`K7=CC72UwA@*VMY_Xk+RE4}=SRf>5G=va=Fgd(_<%;xdz${fbJ=Gwc5n2UVwWkyXI9)3S'
    'vxV^ajq<^otn<%@f@GVz0y+zbij$=^KoKS^q$nVPR?e{$si?l@wTqr*<AwQ2upmH_5o@SgB4P0A2cgIl`3Wae?iiApdBx(&7%HcE'
    'G3G+Cm<bSEsJvOwD%sdE=mg9GA~@|RGQ<xj1bnhM*dv{xqdN(^{w$;}BrCw4V2z$Rz08IHgWw)WBH02dVF@+Jz#`W#|MdK*l@E+C'
    'EsT`IcgHoFpe7<7Gqc1(^KvWXUVsKin*s2FGgiO$`8GO9>k0rcDiHjS9J6-FDHwNYS~%tqy+)0?nK}TNNn)z{#r5Z#w}gFL;?DNM'
    '0(kP!U^w0)VfNTFU=Z1=;KK$Dd7bG~{ra+r%nt;X*Wh-yur$A%L)`11emRMAzns&B?OCk4t!uL}XOHfDg4_kosa1Lp%F3uIo+8`@'
    '*o=rKxbVjR{%!x&aIW0?0NRYk6*Lcy1^go~D3KhUjt6{Y+&U<kxWu}Ot)I*&KMAHkxw(@u($6&@-g>=QAu)IaZ3mKb>3cPIiVI|_'
    '`NX9%LZ`WO94hLtB*SaY4;3bu1tT&YtrmwGjWEhN!%w&6nAOCzYOsxd1$R-yG+Pocc}`PKXet_+m~8uSfKGCn{q#s_6lP)$!sUR8'
    'JuYfLE6Fw!HvkMI7=oZW!cl?H7DVNxb@XY4d2$oF^CE`0ea-K}GL%ju>@_z5#8TvtTdFrUYS1zTpUC)hP(IDi5Bqz+DgCTLv&zN#'
    'U_uP$^h5y?bP!R@8fee)g)%4x3DBnpOM<Jr6S$u6sQnVRd6{8&+!i{VB(8LsFe5|bBcn%Tlk(@n)l?7yGge9PfT7#kh0DoYk3d*9'
    'mbCq>e5AQwF_%uT5ZH(&jRRx)&oR<}UGS%x`Enf+H2s-!JkEHA!~H<cku(7*NR~Hh77?Fn7;0B8!#|e(CAAL@4|oBQtJ7e>*C33N'
    'ZhQSHY>(c5`fQiAUM*+7xTSegFbn0smD-B*L0tM)k_>i`gbovRkgKEEz<=rUkM-vziLI~Q#mg`|qIif>7&zm(HKEbc5Js#vu%Hq3'
    'gStpfxUp{0HwE(LQ;DRr(J*oF?g^bI4Rd)%g7pK2<3T1(B|cBCZp{j)Mffl09z$@k&{cWpONBs$n-!_DR327D(z*qOKtC$l6=VW='
    '9+qJOe6pHwI%>dEE7L@gd1+9SqkqhW|7gvHM_ki*qc=#I!^eY(8(M@}qI%j;d_4d?+*x?f!eh$)x^)Xk78(PMQPR0U!A?<!Bgq7&'
    'hDHQ64XOD|9Y3sF5{~lra=9a&B_5d6(t4V+I4;1ZB)w#1Qp2{I6=~DTWnZ(Jf>jv?)zB>X*~$js0YfZd9vuTyC3hot;4nK|`IL*m'
    '2(oW#E9|d2^)jTUq~yr5we8`iYb+TQG~=sRD-wp}S;99oi`mNHW{N51+GJ@Lkm+Lx1jUldJrAo^{AhsA&yYJV-<p@hbUz+#2dA$Q'
    'catHXOe}_K7xa`rhunW&^g#OQcb7*+0@*RUZxX#sAMnyffLkqUGn6phGo(ar&Z}136j5i)9W?D&T?9(CNq#9H!Fq+0CZLfwaB}9^'
    'u3xr_ttzGiQ#TMM;~E6HUfe~d=}5;-n-j7f$R%-OTDSb7xhSyEs5gN4021+fRF7JCH-?{7Yy>Nrim7uwtXub_XejtQv{*@yw7><k'
    'nDp{qEi;6;(V=V;EDV(_4V~H#Ye_@laGv!@m$Uh%Uo6L+aznsAf+MmCNHvs+_>M9H%;;oQzUpH1*8mIzzfp0J&xtu72nQHk!{`rS'
    'cT(PQ(GvdcgZ{7o@qYjl9{&#'
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
