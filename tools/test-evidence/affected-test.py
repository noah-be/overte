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
# 06f9b23d389c63d22026c00f329f1dc6936f6b4e / tree 8dc5f24f83eb3d933ad1ba34a8d6ae0cf82ea533.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'fee9e9084ab0589e674ab507410e71ae53a90d24eaaec246f6cc95a9be6fe38d'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*emU+^5jd(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNecq}`row<ZFa86NKDX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xS{?|=KZ-;SRhf7{yFB-4yJ#<^>T*~H}BJhnMEHuk}%)Z2D4`u}kH_M-m+'
    '|FrkN{nx*JU)Hlw`26s)f7*s`h1I<8qA_C{XWK-V!ZcdT8ck!H+>Jgq*^a$yrjJ*9ap8-5Ob>tT4`1@r{*Q;p#IJRy?S6MGES_@H'
    'x3;m<Fr}_dZF1e{VxD8lDb8l(f4e?S>Ep!@>1BW1p7w`t58-nPUrH+ufrpoa3D!({z$v9U4?X*cGe2~mT-Wx=UwOEvbUZyAU$>|9'
    '5YtQA#k33CR9d%<U7p4~52kJH(3-h5ENsKr4MR3&a4y*#8dI}wX{|U8e%9yG<<^g`b#6#@&Z+CCd5mrxP45lw_2aePUgeROdq}&}'
    '!#`i$(>8Cz@>c)x?fL2B)yK$h?c3D*vE%uU&Dga4z)!T%bkorLIJ7aQy44T+-%~g}=(iuQFFVa`<7UGT4O41|(Dk8lIr0IGris?L'
    'u^m`;u37f)AJx^RZMK}7E}LPPO!8q4ah$uhG0p`Orx2};bKmE`FYOO3M`Q?3Tb}Z#u>JIV+I`vXj-MW#-t)`1k5@Iuh2DqI`o8b2'
    'Z~G~Zp*40$ahQ1Ec}T|Erd_k@3%{Hfetq3O+b;EduT$rnVB0t~dGekI?Q?4hQd5&s2<z6}`|GP_mu<sKwT755w9V|AwzHk@!<?o*'
    '*zAHErp~Nc_3*m8x@Iu_IF2#9+4qy>=efBXn|U(6OFp%I^o>n9uUb=I@+N#f?4Q%-81^sMe>KOYX?U{EbmPc(9n$QE&e>*YC(hOo'
    ';v6Tl?pZH8*tzF)BygwAA-R|B?(yn2;>6b*#x#sQQ8Sr7bp)`!cfoVK&CvIR6cg4zh~3NcChT{4dwqTDOd6+d7{|#t(@w#R9It`c'
    'HgTrghRs>_*sWe)_j26)`8E5i>wCVlrtjl0ST2d7;Ykc`ZbHiq$rsu26q?j|w|afPK(5NGYp0OA$q_OK4qj({u)%oK5!;47xYkSr'
    '+p($m?TRRWxNo0!>7+=vIqY9gX%n~ZakoF7w&8lT>E__wlzKCSA@#iec}mG~bvDCD)C<wK&J1Q=y^YuSa&_T$vZG0+<;LK^$5~IG'
    'os7ZcNa`?TuDU*1TfOl4!@I1$Bxd>qPwCIo^#C+**llucH*{0iC2eY$ll4R7G|nlQ#w$xJ?&Hak7oPUd+wefx`?@`HqjCU0x!1To'
    'Z7w&SZrQ6Rau|~9W9!HUyG%5Uv7fnPCdEWE4tg0p8GG|?mQ$(2@#J2~C9g**J9dFvf1G>X2N{MZZq8FX=NxU<klv(*WUIM-Gq0qR'
    '*CS;N&P<^lr`!zub~l99ay4*FNcV;*4=(m(nC9j^d`X90dfF^+>FQ4A*7HE39l7^?XLH}Q*~fMqjGf0krrBD)-!|X8lV`Uh-Hsb_'
    'd_LvFx6SA6QMt<1T{XJ6#@tW7Nr5n8)4*lMElRFnI(FFDo~LyCuJ)dP>1!dFjiJlYguxRnd*52i*Xz0_cBD^<FNioc>Yv`ei<e8~'
    ';hvULeQ@D)J+Mu&pIY0u69v{Z64i&Hvms98i+t8?-%yOSlb>(i5;;|V+CF|hRma-VcA1Q-asA-AS`z2nOvX;cA3dPhHPmd``a8B%'
    'O1F3bLldUPQh|0O)n==#i!6&rGV}JDshg&*jW=(Bv?CJiwqH5eo9~b4dKSR9;(Rk_>NlQ2H`$4}??-}f_J)GS1maI~`(rttI9Jy{'
    'mYGk(YH2@rQwUr_6sv6vJSa;!Y3<O>!yTvS<PMLi`WDC}yp0Qy>?4nSBZ-4;dOPruSUn+XKQlM!_P2D-R^P4yzkl6DR|qtGCRAVz'
    '={c{ZF%&^#<o^z1=v(8*zHx>+p-;bPPZifwm$I3M*;AACU7F(%8lPh@hA(-Fe8!46AvbsKXt|>{Rbem;<nOKF!sKF{Ks{Vce&Wlf'
    '%5hx>B;Ye?)}8My?Y?dg``t7D;`!BGFY8+2JVFUN@BI))t_bf&u%<D&$+tW+ZuHpQx2Nh`baK6Q9aV)LJpj<0V^4KU0!Df1$$du-'
    'JUi-t-F7xxlEBCF?NP`Cy`T7?qHRM%Aojd0KaXLaxGXyEG@o+IcJJHTO}D(a09qu(eB*hxi7X_jP6Qh<fn21|edppFe$m##{&~Sk'
    'N)K$zE_E}Bd_NlkrQYX6(oFbfw_`LubI(p){588ermtyNsH!Ph=P>96QbZB}8lKnG7_N`DOA}~lM<93i?WZadkRJAPCx`*aa}M+9'
    'xN%)Ga`*#)tQmQshBEigt^AM`J#TBi@fq;Y31H|FARf?NuwaVDgJ>mo*R?JgpxJ!izSgHkyf;VA2o5s%PB2#nT<p!*_I%=FH?{1r'
    'Z?eC4U*t!da7bXgr>%QB7SI7ouD)-%Xs6kew&l#jQchqz$*$>wCv}SR-FvD@2|6x+J{<lJXpu99Gf!3xqz`h_O(O-WaW=N?eVe%<'
    'dn1SR*^Fi!IboE|ZU8k+cF4U+&T!?l+=HeK_igOBe?0(dh5hFQZXK>?bF3E|iXz985z3ZgH;<<4XO#ds%#nu{fSB&wlCsK8MF|VS'
    'M7{>tM}vUMEPL*m7SttnE%?33gr})_x9_ulJK1fYUJF3))K4L~G`OZ8T%ciM$!#4uOK5paq3foZ28y}!yFNX?<n2@XUaeg}{+3IB'
    '>>Sk@a1ar51eW2kc=FvwkSv{@b{Oycx=)AK<B6N(OZs*wL8F{`@=MNl?~~!1o_R-M1}JU3;iF1Z?&Fm1sR&kVMp<^#84D)b&Qs>?'
    '<(3%U_rBqT1>bkW3>Hy${a--p%Rjk(Tf`1Dkk0~i)DGMi6!Z<5>|p#rA`3=4OktYpGVI6KCETUM^Y(aLdWct(F+bBr>(uDTQ}Pi^'
    '!;(h(#`n(BI;05{i8*yY`SV_Hf4?sUd|lAg6O)^5ANm-Eme59hK5>J`#zf#aj!E5`=d|T|=rnU^Id~oIkEkpP;5!)rE?|?)okL%Z'
    'J;b{FX~*UNHEmpc-d?{+=xmUD5dVyC$C2&_s6@<x9$Ux%>j1cV3Wmyp;Ie8BnAkL2;*@17kZed{q_FQf@t`1rj{@ZyVW93?`tc-H'
    '=NO?gsr3~3)Q75C=>Wx^)*iVAhrMZ|p8?@3>%|}YJvB$kMrw<`i?IXcA8fAzKh0#%^l}rQHMKOgS+pw_KNqH9e@L6(xgK}vdJUn_'
    'N-(3((T|bpZ?vGybEC?ArWrL-r@D|UF}fdj@Vx(;mSU7EsBje;a7o*?x$#ry1mlv{kaX&91Q(mB+AWQT+12l1T~rByC*E`%>xR}>'
    'N26=-CU-P+IcbRtC_xnnv#(#jGPIbOsU0V$S{oe2PMkO)Zfc!#5c`SnPTt+sFMN(K70;X+i1$u2x8?e34X1D-m-h70X}o{{P`Sl{'
    '{^#1I|0-dx-yt-z8`2&}>MAV6wq*7b4<10j;dL8u5)!g}`|_7=UwC=F{v0@WCQL1V%3FsPLY=`)Hi8m!&(TkqERB}=hK<y%-{pZO'
    'ry=X3*-7$6mYO*aUCSR#4s>B`eQef$0wnAUmxH6=4%e|D@3~1^by>Mp0wHf0*i(R3!AF<~juV+ijQ-{=)IABy^Jl$=rniG^0C~f~'
    'HsIkq>f^-CPI5JnXWX!jZ>P`uT^*pQkDnp|P-j|bSWtx00O5l=Ax-p{sE&DF{S6P}kRHKwC{*I+kAr)8DP>u~H<Z7bkAhGj42;Xs'
    '500KN6*-JCz8CPF8$JwxrRz=DaimTgS&Vcp_G&Ex4Q9G+tyhQy<t6P)mBrhIfKZzd%+}4W6S*YQj7YKJM(RPgdXj@Uc)E<Dz~mM8'
    '(M?$a{e^+1_sH|-Cwo|NbUT9+6zJFq+_?amtD+h@|MG|J?&bCLiMRfAVO2el;XnM5NW6j7sEDrahF+bjRNngX{RJ|6N=2YG0V2TN'
    'na9!&6<N|xyJ7W*6h(acabqeyHtwWHR|bw8RU&B`HHb)Gj;|tcdMQh6PwhdUIO(gc07pOCSc$ZgIRVO_cr2~32CmQ;r%d%>X?+ep'
    'WCGY!L77=D>o;=a^(9Hw_%@ZD((EN7r~~e)#cY~9aP{EeiCC8_mwbc96e~Bp2X}bhA2zT2dxflJXgLVnk#t<Z!@?L;{sFbllQkwo'
    '6EhT}gz?&aoGZ_V3s>UP@euxBlSj%M`@cpf`FJa5PKgSvCDSb6nWVSV6zRSg1NXEi<#Ho<20%IImuKTfICj$=+j#>JmTg_ndV6nM'
    'sDvR9Qwgb@UuupX{zN7nW*;P<8N$(xn^{Pl=dT+wsXJDGK5^u{k_M(0D5_1|#sQWIZ;jg9#eqK}OB^fcSH*q#*X>h0<3F{4E0Jx2'
    '2-Lb61`s`}CK3d!wL(C^$Y{58;%A!sH+RA8et2vJ9ty`!&x?={;A?`^HR=Y_WPp(~wqiWMLGJJ0*p@cX;q9efNaxp)1^QGi?74|<'
    'xq+7xjk+Bj4dWI*9sEKF=VqFJ!OnKvSx+=Q+<{i#^{*@up*>hMU29T3uydj(ZGIpn4>g9Gm$vaV_~HItos%A7#19?X>zAr`ki0D5'
    'BJZvtP(==8ocYxF;$Yi?3V`}g{{F44iCvLAgKwV?AO1Y?yPatILvT_krGc!j2lbl!1;_G|u5X{0O7_*ie0IkII~vmDNSJ4PfjU-b'
    '0vVD6Fopm?iOYo}(zgEv-`M#otb(sCeNLhT*iL8x5bd-;rWwk3Gqyn_wU!6hr298@+&(Vsh%HhOD&LAjIRGqj8B+8CX!n4)Q})xu'
    'VW4#tNOXB%;H&AsVQ)*OQ_*&xQZ%#LYmi@OzCEg8Dxw4yI#43QMoJO%`4=35HzC0F?PU7Lut0%iNo|0JCSakl9jOZtc?giEU&@Ve'
    '<96Qm@M+yuNxz>(>HT%l3$B{Dncyfxlz_VBK`lUSjlKCTe&5w{Q5IM?g03KEb00e5RL@Z)@dn2N*Y#~Dp#sF_yPwY`#9xPWy0)cQ'
    ';>zJdh6(|~3ZI1-4}?HehgLp=cJ{-)d#N~PEsPqG`k-W3P)2yWblN@nFzN=-&EUvJ>1W%!w{oc;em-o42+*ip%9hTF^FZufhu{p-'
    'f9Buncwy?O0D#}SwG~?e6a?@gD#F)7&qGU;GK>7rplPD7le`r?-dw3B<Mto{(Pd{S%-&iN3n1&lsf-0@x;eQCbVDg^r!Xs@ni~*^'
    'u>%taC#S4&wp+7@QV~m)MiJ6ZgQYy6AV87ViOWn|DI&$7ptNQf>wkA;qltcRgPNhw^x~llb%;)8YIw*Nq-+qV4P6K`zxQ!+{kdH('
    'p%$s7!4HYcsVJuR51PmiL$nkiy?DNUi5|my49>U@)Z%2B?&;G8s{RiWt&RR!p<l<ce8A}6THR;KgI^6OO8C0^vGZbzch;rr%ZhS%'
    '9g~@3hIUS0U`ixHs48L5QgM4}SNLW+0v^4r?)oz4glGBBg<kL6`9Uy?&x1wW2C0%Hnxd_vOQq<a5Y5DQew5&^v=b`+$sJBxlv5<i'
    '3)AIP;E<D@N0@h@!CWQCaT*io6%9&@MXPKx?IPM`SC?GA6cTg(zDQ>?ss(81L--AFq#F3Fu>o=$5r@)I9#At91Kzu1|F+<n7;^nP'
    'aYFWnu7RZn;A?3!ju4>u;=7q@U^v&sq44{Te*e7r%B>yCDGe~@Oiev-v;jxJ_@RD*)no_J8kQlMVf1l+uX%mWR$}_P)mx;#dpT+K'
    'nnbUWH~|`o080*h(qa>;F3Nl^Ne}<Mi8MW3Y0>CjPSVaS5$10z^7Q_Ct~|Ad*9bRi0>$-?E))H0umr-WwUS6e-Lk1}#p8EX^$SJ8'
    '_dmWK*jjZ|Lo@N|($he+19=4q-LL}-1Gu5F()r+S+`-Gs_VsyFvymXSHr=FTmo{#P;JHPdIw(0)tcMm1g~1IgH&XQw;LD7(*F5pI'
    '7g5v#2DFeP$Uj^=`Y<`v4oD5xt{wJI+%Nlc3V)$JmcM-@!a|u)v(28P%?;DiyZ~MolMg`(J?4olKd#-)0vK-|6AkxL%Mqd%6l2Z;'
    '-F(7YuY3$fLq8>i+Pwuy27{w2tKP!$9aOywC<RE9yG%e6)okb?TV*Mw)&2)F;yr+Awbk$9|BrV-=i<4rBqZC3v;szAgS?jC85IC6'
    'p_X<!Rk4L#K<l-uT{5QQ7rIxQeRzG^{#o_xfmO9MeJh}ok(37-52ZMrlevdp4wnf66WPg)TX=kV-F${0`IL?YSd*S&q<F*<fOZMZ'
    'e$#g(CO|r!dTT8lJKjcWe!)H<MRUDFbuaLYXweWAAdbNy9dlOOFREk`7okT^j=HAn%&*zd0x(rHqXmW!(rt7hw;|H`MJ+L)LPn~P'
    '^a_)BSKWByuDG}lFe8rJFZ}J>-(5|-sDhxT%sn~KOlktiWa-GF$cz)+t|(bFErj;Q{hSd9_w9**rWz@2Ke}T7#Yh9<FWFI($6-)+'
    'et<%fu<_`Xzgt@Nrc1-E$7=O{OzR080qsaT&D0XGXi!P;%px^7AvKVEckjB2yuY94efUy!xZR{44n?)?%m`Np{tj1~g#6M(Ww92>'
    '{Bx*X_);zU?JkzsmsF}!h7rtyL6^=q3JDa#QXGYy8G<V!)G$_`=a+5R_n-3i&y!I91^m1o*QD7Yp(Br=_o%X1bOF*yp&lT|)F5OX'
    'c3QXoUzDlpYlSl1iEc{s2-cYT)YQv;2bBme5xr3>b{|05x{VxUwQ{K61TrQ{A=-*!2LRDI54b9`8zeD^WXyyB72u_I6a2S|sIlUX'
    '@0C(TsgMD|W)FpkOLdUni$_+G6I_DeC`oVJ!8zZlejZYEP~{5dLIg|^PahoO2str6KZxPF9#YHHSKswt_x$Z<u{2V(T8K`hRSn&{'
    'jtJmIVQZA~vnXK+Iw=Yqu?ov;`^p7p4nH3qbS<oKI1n?~8gS^)Bg^t3frWBmptvb5h+yX1f21nu6+L%Q1|4{=D_(S-rEzM(97b+<'
    'GCc!&P5+^^<RV3TtIG>I;aLibnI5r8^!xiJ!I;7mKxR%84P5>bU?`OWPMuDg&J(zk0dR*~(W+xj^^FLKtR;ZI4`=Om=xY~Se(C<w'
    '4%UC%oc|3ngQtqNt3Xpe-AKib4TgpI0;!{;T<77#P2yu~A$-K<mhEhJYW%{v@UI!WuFcD<f8)Yj-xDF9%NGzAbOQJ;0QN*Wchh81'
    '-Jq`o#`AFV@7j~pZRn-a6W3CSxrS+pv<M^c0?-|>RDjNnPY~*RV47|ad(FLPiL_!rKeTU14{|zfpRZq2+<`FI(T`B}q7K$=g#?h('
    'LC2Q^B#jyQZ*;fp>WQaAw>OnSGjE|$lRg;gJB)mIPzII|MF_1p3GM(az(dR}dw5>jfwUw_d%&AZ=nDuB02ApWcpeuv-^?&;Kg42a'
    'zdqiw2ig0uheND*7Kxjwli~^2GrknycGxj+POwBk$`D873;+_r-m(u`qpHSVUg^PCeH_%>GnFt(1CBNnLzs=E{5X5CBicn%)~z+p'
    'H+>unShG3bTj!H~{rxoD%_H?7*(>ZVFOUo<7tRut02qKlUroC0^nlIp4*&p{-Td?UsX(eDnL%Cx0g?LzLm=v%9{(?@G)PN?d~Q>U'
    '_V^37qCdNi8DOz8TKd&#;gsP=#A6}GK#YYsZqqEBdy3=jdl4)1==fL)=#5ZJ&~GD63Zf9OE#4IHE%^)?&4jNB^pccr*~rm7zo1Dw'
    'iXVJ#?U#uA{0(>_6&4-`b4b1=+s{-yw9xzjDG)|AA5FR`_MfCoj};X_ubKnc$kG$Xa}K_^p$~xp9_1E{K#LVl4+iLO*~Izt2u~DZ'
    '*Y^N_Ofr!OcEo3b08Rpa3-Sx(L$e%k9p0U-KQ`gBJH5$h+^Kk0#1jU|7Dt)xGO0GW3P3kE3uIKzFVba-c3&UPzMDK=tfPQ%KNk=J'
    '2nhgOiGGiTZ>6>Y?Mm1SNLsLI;&BL4nd*bsnFM>jUG`pTNt&r5s=1d!k_7b=+BWGYE%zZzbZYRtAT?40m6%FR-l2f6-iTs&_!geh'
    'C2tFX6Qca>^m%aucuM8EOgdyJ31dU(;<BTk2nY&UK(`Mh4tjwg1IGQLJyjTcK^nnF4-vkc4GFVI{{ygBuRoospaFbf7*4-rLvf4i'
    '-l@QNZ;`MEdTBIzy==Zl5v>A#o(c94pBAjEtTOJG?C6mG`C5wkkeT)A5aICi!sJm&C5}KGs9x>c3CS(OnBLyIp{M=hc2|Y9jI_zP'
    '0+TLitS<SoL92VRf3an;r{sq0#d*1RN1z`^X*6~rReemL8$xiGJ|f*x-WV>n6e{!(eI$vHfSFtA?k7dV@w;lev?tyVZ-<(MmXjqA'
    '(q*FKBjRPF3=e*9CZ$O6-aQ@DiJR&XY<K5gj-U61T_M`-;R=H6((fGQsG_$R$u)a1ETRbFP_%#9u3lfB_U<~=oQ1+uz+)u}n-?Dt'
    'N)d=T`0|n+8zJ=&n)<Q5cTcDNm$bXkX0In(V7Ow%2I>_zkc}feBpN}-LH;y%2;N(5&)>YE7!N|@4=L&2*cCZ~Tw9cls9&JGfabwF'
    'on&W+SqPlQsmEd$3i-{Ul7FB^#pd(r^ima=2#NGf+l5zwR|CPIhxG{|f%^rHB`#DW-mPZ5cSFZ;*uK<U{dBebh+Qa1#6W$CMwR3b'
    '5Eidc%5U63q#~u{ykkRUnkhXJBL@O1%Gi<_Q^`_YV~>DD3*SgC7erKpzxlw&{j(!ZFW1LkUf<W_wc$H;C}UvZDkoYna)gy|Z=k=D'
    'Fkv$xW2ZZ}^t6@KwgRoAOqu$Gs@W6%P{@E{MUY{P)TWkHagv&ch}8dz{ZQ4UZOI5o4t5c*_rL`~CW5pL_LUAACNdDrS~Ub|oi=xF'
    'NOC6p<*Fhy;y#!X5PTZWG?*>r7Vsu~ABggDPm5&LU=`i1TRJn2zMrul6ld38-5{5;o<1NZ1dcQsO{i7ho+1bD4Uf!=>a_V)+tOd5'
    'GFDi!l9KS+<Ya}16U<~-i@|~f;tMwMc0ndla(B}&+E*^y+sG+8fjAN!r6ua&D$DGi%o`#Ou@W@WqNTZWL%LNftgJC+Q8>c#9zD4}'
    '=!tg3tX>>tD)bykNoo(7J9l$tIUYE4Cm4`LWd$r(2#2H^JxW$|0!Xinc->TsILyg935N@qrg!e@a(}$;DjyadTX0$OTkdv82|J)}'
    'n&62D=K+F;p%0vZP3f)MdfcD(;*^tcU-nkWwjr`h@S0lG*S%Pd5Go;1cnSboix#3BjM1B;w~z(#aRpmmKVu&64KjX0GmTbJD`~89'
    'xpCAengEk&Z_@bAw{GNV9~V2Tvw75Y#HW`NIa)m^B=e#H;L?CrM@>ZATXPqvtcl!r>_x@U<t1Ihchyw_>|lgxQ@ldeWR6ECM6RU~'
    '!K;!#nWadgI=OFSi-<ZdCoSxYtq3J(q=yhD@Uxwv00$AvVca1qq=-{1bODEM-O~jY`Rg&2w=|lW3f5RBNgOB%h6`ELUHY<o%EU;0'
    ')aLdAgjKQIyS%?jaHJ=NmFb9JJDL+X+vC)1MYTnK4>Jv_ugK;%rzN|+8b?C&(7*G<N{nB_eFpD8h^v?up@KLCNrr_1xW-7%gcr`u'
    '^~Zk6A<yLyoY~hxRP-7N1CT}c2%VmWZa|R&fl%WyX-Y!?d`vgrut1CYtf~14*>y+_kd>2Fvh?3X0^D(E`s)u+>;*iadOk9n@;y7c'
    'SVL@1pXIuDeLI)|H|kTcEXkr=(q`7D>j%?RJulcXC>n20jV>h_br8`J!eN<oAZ;#Z9rit#)l9;Tf`Ly5xpzzVpe38MG&OF%$CjHk'
    '*4-T~H#=<s%-V3wCx0bZ1f-@VPd6KDEjnMAogjO;eJ{%$kF=xqv?EIF$?<tNRE2#2`@nx3(Fc_^T2DF{<R8rY81LNC*XIg@4|#`x'
    'x-j^OF-+jp6FD?Y?a^Z^t#K=n#M*_M^PsPj64$Rn(@N<*Bd-9_W<l1S#$K@WBzs8iELGR|OH(Gz?v9<LKgE|<!@Ambl*MNz3t{l!'
    ';SEK|C8`b?y2H)Nzlu;HV0L%Urnbw|Nwtq@HpsVwT#+HxKy8r+9*iq2;(8gxfPu)6rJL{D(Y~S{W89CjGBJ0VL=xf88VczS6@iS3'
    ';F~KV+S?&d?c^kkVSgx44tpi*om?F(<ZZk&kv$ThnU|K@R+V9v1n`c1T*!c-q&I|S2eTNTGBA8BgRt-oG=H#<>!M6iIPxfIeY$5W'
    '-|s0RU?I;5RLmGtf^dNHB4ZgFOmpz9BoOkIP}OsrbHsneX3E_`05GYA(5rK*tq>U6m8e#Me*hWK_a!_*lD}g!k{1@VQ-m_fU*xWb'
    't>4heY%gdM9H}zw7!ojt2Z0aw?BXQ1&W%W1MJ$SPSS?YS)udA-r0j>TG2srxPDDu{Gb)~YV(<4HBEbnk<6kg)!e0ZcJ;rLmMW1OH'
    '@=SPZG*$YZOosr?ALX0VtiN*4&C=K`2>EfrMvn;e4!I2MlozGBPqZy4Ir)+SedJDm%O%N!k!Auc<;<}yh~H?v;Xc@FD594a8%$&H'
    'C$31&GCUm+XELn%-0I~CE1oxlgXKRLd)s7^PUaMmyb0)%*5Dv-G*3k}lh`$Ch+$z|PkDe(dX~Wc+@E*@QK}7E;CRzWf_Vp;(py-U'
    'z?ra^pu=I&f=0Kc(J-ulD?ZrQQX*9E3K@LR%fcEM_ei9~bat`wz#6udksS@^nFnb5n|F0-p49G#R2YcTBU_*|pmR?14Q2uyeT0=<'
    'QZzFd^kvM=`}vVYS-UBcKG*<8)e{tDx(4zXlr&w3o^BYZJ$5!L(yezlrGHkxr=|4`2LO3D^l=hXfI~2^MxhajI+3~&wY<4?PvPK>'
    'pRtA9?N6?({{~iqJ2Oi|fn^8yDI{{)zed<$)C&-BDfrqI{J4MF%>}cl9}dJD)1Xr3zcKw!VSp^OMI?^*3SQ<QnmxtV%`xC-*r{?;'
    'vK5N3ClJ)Z``4s2Eb$v=DM9PTN|a0)NwSOazD=nbuD0vLXQj($(?F7A8G|#X4@;khBH0QDmu{#VZ{5*%B&B*o7`wJUAUqwC?p2L('
    'Y8a44E{FsXCL#ZvEcxd5ribH>bh}r?N9x^{?2uY`ke>kqT1mg?my)Lr81z%CbFa*|?&wl}l25%pYFI!4iU(za%g*d8xtCx;135Ws'
    '6mO@-*GRR6#0sJ0c=vYB?VNr6^+xYauA6*J;7(cB9J3~+out|UDg?7*w65{#&Ydm2f!aN3*5Dw87ri-z4rFAsR-i0UjrIb>$s{NH'
    '?zo;+dpdr8Jt<+VzfXWp2}nkEtx&r<T$X6|aPvYOLIp*!f#!qawR&HdjVzz`@hxJ8*TqQs1aE;9ZhJjB;r2?vEYv{^GGlFAL!p}>'
    'yru69_|j*2$IbISJKFo-Nt&oq37c?>cd=lEAwwl}uISM)=ZE_yzcE5NcvzGM7V$B6%bJAgojv{ZN5#~ViK4uzNhbC<8DWqC(t^_x'
    'd`XOI7PnuXA{5s89VKkP(}P;^<dXlIUtUL}sDPkQHh>D!@sN*Xg#?hX3GmzN`op^8UCWh^HgoBBU!Kh6?=JQH^{q%hm$}QBN5#}R'
    'QAim9+GEN>0s;ev{xj6t6?Eqhwo**}xgbDTU{*`#L!BJFny3)-#R6~Tvj$_ouRm8O=Yc3M1mopDi`;uGFk3Y~0<T4$#wcezXm}uE'
    'S%d(M8K*qMO@L`i_w1tdB#0=?A&}b~pC;nEq;YAj29;nCiP<aEM0|3Z`ZW6dY3{Z<!072f-=5sJg>+ren2ATM0o)kM4Wjf?F^}L*'
    'kP|4O0p15{_Z4KQ^FEOBxx>Zk?yMpy)yK%aAYdwr0BB@6!hmT*fTFn%e-65L!xX8!ZW~y0Zw^jb;O0?(E%ni5dW)haDpkg;384hU'
    'wcH4=WoQ8X8OBtT{Y>k3!GC`&Sh2}l#A+@8oLztmm?2&;#jL9a{w%UzIt^|d*DZd21^NuC-UF-(a7Ik%AT45Tf;TDcC|Ka|7;#XS'
    'HkToU{R(~DMP?=a%%!F)Yk45WA~ePf8}_SbS|&_y+Twx4g*ul%h5ZhJaPaFkae+PGK7@h;9ffuh@++ffMu%k4@+i3Rl@Z+vP#W%l'
    'nO1&}^qp{es*?s9O-G5e;-K8&nMEB7fx1(Z7w;L~kwuNpz_7G#2M|i!GI6q=AAr~xG9aOu6DdPQdhgurh*XG^8Zd#e|GTDhSGTc9'
    'Qp!>gZ=^rK#R8$usA~cOGBq{98w{jl#0TD&F%K(W!zD!j@Cd3b)bO%sqz#=kSy$na5p9dG49o+{rufltk^IUxLQl&RDs@5&%cB8@'
    '%8&JzDl9-cfDUGU(V-2Z)Nq?(dVyQly5(QDWO}Dl;bTP0#;?OOUiT$182uuH9u(&aC@doN1_5?mT)p=3k8P<ttqHjzfl?Mo8H+uH'
    '7`vLvM5Tw>2++5Y7P@+ExznF%P0z9}(cFUMYdoiVOqN=huR_;JU;wy#x-(9kM}Q$Lw~b~f4DFpeDQbh5q=pH=)WX1(2RTl<ng|PJ'
    'h_O+N_ZCXB-23(0(CQbiS0%NAAwM$;Db$Uc@C;;w^Bwnvj1pu4)(Kw*d0O#uBnf&DkNewCsRTZGiRiUJ%tbyNet(>gNt@FDkkLd<'
    '5`(HsAm!A+b3&;*_P6iq_x*O!RV*5hO@4BZ1zTpdo@tSbJrt!BkXw>2dV@-s+)H*a48dw|-_cnY3fqG+_pvl32TQ%I!OFP&5wbv*'
    '@D$5Zz=-rsS4}e+82dioz8zSLdlbZ%x5w;-e1O_efO6>Q$tADrq%*-sjP4$n9dp<wjmwaVb-<gXR4^q0?8~SoNBio}!k8$$D>?<x'
    '4tbEpV}&;YnS*ZzdJbq(qZzAh2^LL%QYS9G_$muRDYJz$E*)nq5Am2Lz&6$`**41(U_n2+>Qy-wg=~UT7=19BfE1-*>|}v&#EarC'
    '<&;t~<J(^<)h{ike=+L9t@BIC&?bu-t5gE#Lr?;!m@U2%ks+E03t(q3!y4L?sa*ezHWv&6HC>g)79iXVFd}z*>KVMDqB<2kb|hA*'
    '$(1W!6asH*+L~S)(-6oAxTMgTU>1nhtQ(a*qB~R9CbUbxshCT@?O=aEwgKu_oH}MTSb&0B^O7}t6ZItA_hAt#;3C90Dn{TIGq&%`'
    '{&7wh_oPWByK+3}=x8!}f=K~%UU8!HV%v*3KxZ+Lurcx$=4<8BI5KdO{(AIcYVNPUbes<+5ur5hJ4g!A$pjCj2v{df6VNG&>bPzL'
    'i;$-<><X$A+z5PHoCbmjNbTi17v)iCU<WW1y=`hA`7&|2Ktx5yNI9m#R=|J+DSS6Ibc{X<TNn_9F!i-4YS`|Dm?}{J`4Tp#*Imh5'
    'O{yF2EYMnr<;b{_hIFElW;@uHYs3`lpiq>(YTX4{)6*@FlOw|)7KwzE5m_TC$VWk|f~4xug)qO>^rEI_)o;6i=pYihD(z{+r-J|('
    'U`J7rO`539dbF-|m??`aw%aYqamC^nKh?86!KQ3J&JDzkK%d8HVs$HI42myDhz_2~&;V)0NT^Y>G@x$&w(gg+${_T#Vd4>&2k=xT'
    '$;0=Yxm~C~m)Ae`MSGFo)9wrQ=AU5IfWvTY6nyfSnZXDP&4Ge`lr)GoD8t8x0D?<oh9(EOC~10I^gJhABO|>yX?gotDEkLZ)d3EK'
    'S`Oxe$b%e!^h2q(LML(tEH^^s>TmYtZ!@Mzg&tGkspGxBxH_VCT^=#IV9+ppvj@35g3=K`Q47wMTUdyk+pEU50J8YnL$HT*>_q4y'
    'lA+F^s(^o&`0^SRCq?<;+lrS~XVuHbnUO{hA~lVM2IJ#-C&3y}W3U~<at~|Mcio>qUU}skH)tQoI03j27UX3tDy&{^3O6WI88f^<'
    'oLi<fTc~*EC@XL^;6qMJj>(mQ&WQp*>{TqPdS-YB`TZ4^eP*1Pt2R%gQsmWgE%x{m@E>q8Y|&GZ5z*<ARVO{vOw+Wq=sv#6R^;{N'
    'UFGkOKXWE#km8YPVI4>Bj2XaLTr4Gn5T@Z+YSwhIVm_~UTr8rGRdp%Gnlz(Y;bk-$7>i)w@mSt7TpGwljFeVS*819oU!>$^L_<O8'
    'Ow&M2fmwZxQLaOfB*_H$kTp>QaS=ivXNoL~@5?To@S@-w{~AzxdIpe}h?XeSgw~OaP{CLyXaf0nDssZVuey+3s{CTGhl8VUlQc{y'
    'VzQMJGwf9elGr=YM!<#@@35hAWtA1%GPin^KLUR=!zqNa(vs;Z9m3>SzL*?gTz`$3YZqO3G;d-X)NPUj6`wiT7quFh9Ts44E}6pt'
    'dk)1mYEFu3i)#Zlq$v{V-ZpWe&rmy-6t=y9KW<5|R|G7GHR+twz8}@gXV9^JKE>p)ZrufsrC5F`sCy?`GH|@GU7QrVWevm!hFPqY'
    '7)mZNBxtd6?Kf2+DcSX9xd<6Kq{*f9Ecx}~ok**K#F24)=rRn#usBsNo1eZF9J82v2&N6jPCy3TBgYxBRHpq;((6&7BF+UXs9bIv'
    '7Yio$<!YeJ0P3{yH8i^s9zl;~Qi(bN?DDjo>}E*;Yd@!R!)2FVDHpG2^x)~BVZfNQf2o-9`;%WX>TSkk!=0g|AjO_t?ZUsmK41Ta'
    '2H6^F_BASXBP{}clL&f8<+U<k#EVSxTgJ-u&O^vH$7c|Ts}Gnij+69LddCh!r;&NUv&2oL#0Dr%af1{f*RK0Uzb(I71IbQ607jMs'
    'OFkl$F<>oJFhoev*0E}5#zk1Ya%H6A$kI81b&&YcJt>BaN;}%$j5LC2i<}!(V=nq(e_wyU|5E5<F3nmlc&zAW>2ExuX?!)Xsf8IP'
    '&M%`q`r0U=dFus56o*C*$q2H!_z<h%v&Rhp98RPlg{3-&ciq>n_xg0&E^|t+mxYX8k_WA5c@ppftIcZRYyKu+JjTtmYuf7X>22_5'
    'b}V0~`~=V@G$r{$3sTl7D3}DyQo&^pZ!Rzhs%BuH${qaRkX*Gq<BUje@Zy2+i<_$aXocVb=5hNap)mBsn8Z-I{KXd;XZ5Gk=K>la'
    'u?L>CI4Yu(p(}}167?zZnLZq@`vXLFq$-sQ9|Q1G0aOCB=dO*AFoV2M@x1H>J5V0Lz@kD`*tFf61$oBBgA4CK9WL0580vF&XtgoC'
    '$;sQFu!W=!oQ>;nu3lG6DzLl?fEw6PYF)}<plB-uLQca(FdQn7L7~QGX+PFR>F@4EKNwM6|LLe9!e}+igQLusj8GqR9O#s9oKGER'
    '3^~Ep-oa<g7LfcKJjXAE44z<!UzxaBKo6Q%MNY}Q@=TCnJK{~^|4^GtU-~giew7Nc*ItH#<Q}6O|7ciId&|ysA!s5ZB#KfnrrMI_'
    '+~mIgTY09~gJxWZn21EpDV&-yoTLCeT;&@8K*JbUt+;_RbM-z1fyGx52Xjs5Wn=}H1<S*fZB_YWrZ>{KLteIS)pN$PJ?<;?ybK9K'
    '{moBoC7rTj^r$Z|Q$cZ=C^O+|c3t)F#=7jh{`JfU_d7~JT*{Dsa-fz|wFo%S_tCiJ6K8s6s0|~pFAJ3T`XWM0p(6k>o5zYhv7Gow'
    'at2N|wF3PQ^+-Tcvtmo_O>y?ntScEfrOfr}pph-vWrPfk(MA-VMQ%kMgYR&%oNLRKvtgu+L=UdQU7P7hViEHlYnH%56z6UpHJd~t'
    '471QOV<|I06}bEJaDKy|HvAQ9^G$&?GmE=NyBWRWXh9n=bH&EXY9x!wC2APdgJ#XbZ<DGnBS)@(YJ;r0@ulOYf`87>1qqPXL9am;'
    'y~cwR$J=(*`WL7EI_r9wWbx!BzJp0dhto2nN7PrN>7wLi0e!Y9y7m3Eg9{?@Bro#=)-Rw11&>aAZzjZLG(@nzgC`A<N}q($=pLBD'
    'AZ~svaua^qL)F4OX4?B+U>n*RdQMQaIM`~j(j&q#NH)h^=vObSf4e{p!B_)4lZ*uxBPB8>q(Hi~r;tWq0VIMUb8$*{$a#KD)u$%w'
    '9H#wdfKrYUUmQXrWT@0TX_n{q2>V&o^}>oT+ZTi=r9_O<Ntlb*)W}`~3YPMp;TYs49;%|+$Yq<O_r_NKctMFbf+~TgY45sD?2IUr'
    'M>^(I!(`Y1m_XCTCV)`jm6Hj9g2l^*=>%E`3qxi=K}S||B}7_=`sIs<=Iq_DoRx(baPBu1bUmPwSaDM;l6CUy8As3T2Vxl9M?y3p'
    'J(1EB{f3XUsGr^Ufs7AtKl{7wU-i&LwB1e?2^#IyYpg9O2u?CB6CpK%V2H?Be3=bfv!R-yiYS<IXhlFrHIJIeYG?y>A89doGX5kQ'
    'PXJ%0y=yylABksJ6f>C-qro9jb05SF?Vgb=rDIdNW4fZw`ua|m@sBTVTbM^^B9q2w^s5kU6$z*f;BY5qb}}DFR5Z9>Mc<gqR>0R)'
    '`_}m8GI)@=2e?4vQOl4=E)xVzjSvPeZ56a-;?Uqi-NGkTzKHD^N};DvEKO+pdiex9iT-IxPZIqj(PJ_TpXMxSL$uXvFB07I)t(NA'
    'WfTR?!jgq4HrNn`JcJtTRYdNPY8rDjs$d>Cz%xk~YS<N<SV>`;0hzHM(7Z{CGojsBb2X}520_s9-7xJe&s+F$2fx26v#R;|ZDMF@'
    'F9oZduV6mF@8i1{@*ky#RL7iY0&5mu@%7OJp2aF!IG`$F8p)tJg7Vq}E2Uc~0C!rk`npdL87e`D!T~W6rjZ@~jG$0F6bc%RyAFVg'
    'j0!5<^6=2}=7)jt^@E9E<pbAt5`sf3<Be-V4?U*_jruGh2Sfp2z_4}$mlU&V7Ajx_bB}|xZvjdOi9XZHCS?Y2e`fknRPJqYFxE#~'
    'sGmp00kE>Ep@^mdLV^IN4Rn|6%WH~4zl<R<YqwE9i#1DiPrTuOqgIsZ5C|_28S1X6?hI}}gL*W#?cj~2bG_VQ<`%RF7<VL{NT(P@'
    'E1V2^8!8FxY&vy-T@kJM+ZO7&pC|;dI%$1^#mV?nE<k`^AZQi_fu=Png0d+}$^UirpDB)u0ZJkD1~rjG50gd#f+32~A|v-#14%j_'
    '@H_6rKHRm93Z^AoC^HADZE|6n?Yw<xONh1c1~eL?!GvPq+R5CtkLuB^j8~!hnuT3qfq=tPD}(e|DKt$yY{ICEb2qKtj3%^h>PCL)'
    'a=@pJnaOCkCZKVmHn9?`O<K1-)sZ~8xU*O90b<WCJ(k6n;I%w|so7c?&oI1%X=>#0kYO>1K&#$O07FF*#Jd|f%FC{FU(khDiiGNt'
    'M#wBbWYJraOk%OFWU>pcf3}HhL&V#3&8jJaEHf=4iAH9<X`!DiGn+u%(6fwEe}>gx<=Ymjr`5t_%aHARX=$h%?XX<q)IG9<))-y-'
    'zM8jl<37F*hOKfqhYQRoq}*zZb}Kg?uXK`}0um5iW;kye0@}K@n>qLNNiPDNq>ZLk9SR*nOX@-~1M&^f4E9NHFh~N>Xq>ZiP-sc4'
    'Zrz85JM5MWi;Jo_ew1Fj)ojCP8X28Yhc4E%<ERuj+ok&+iv8ga_Hxd!+0m{-fd?lmQ`Jyd$N`^ML*)hM0!1RkM`##)Nnirj+_se('
    '200FfK|>JnyT=QUYmO>3$iN)x3-fxTrfUN$t_@uv^f-H!Iw26Z;EvM;fkjP1Pd%qlN$Z7+j_x^BBWkZ9tc@B!ixxIjz>h~b4?_*S'
    '5SB556}lsMTqFM*bY7vB6Tm^ehLu~XGtA<4U`h;nR2ZrBXi$#N%57!)i+Z246UU)jn``H%?c-;@h1bi4`V2F)AZP%8;VT@}R%P@7'
    '7$V9y12SaA$Yx>$4Gj^7*JfFd0{eEdLRIp+$p?<>wy5SHNYZJh(G09^F%<)gA&Rx6fkd%Z^+@EeYqvrahuGkDuP=NiOD(wH=fWH}'
    '`UrHBNV6axK^}#y&B4H(3bscBxr9Dx7vkE7!i?J8dsoR%eJrScgRECUC3*C48|Z0aDu?GeI5%x#@zdKP%KNWN|Ipl6UdS3V=tk4z'
    'B;nUc6O35t<e~I|zB?e{r>90-$79p4J+ctU*D=Rob&~KjhQdcfLplh18lT3Uk8TlG6JbMinBn$)6iH*u=ivV^<{c9!Q0P{q*DN0w'
    'CYVu+h!Y8IZ1p{&Ev!;Zbn<xydB@<{XpjM(v^*VALQ(Ge1h@;MjOyryeXLMWun33@Zezm5dbsQmo|#e95IHBsl74ajX~GS=sMIph'
    'd!nCA9*oM676ij~`CpW&vr1M>2bfNT_s8lg?JV)zTqJ*`5)BU2jCh|K71WM!8X2}F?lUxVS`<hk&5$54uHC~r5;lb}o-0HPP9`@i'
    ')HkG-jT1+B)JP&I;Cvjb9|X~1aTB_<NXt_eam0gp4Q2v@NG6QRLtr+=G{YH`-8gx}tv(=YCd~)6qF_48ONrnB2MstGr6SC23S~_k'
    '?gzIz{k`mfGpZ0;HT0TBG2%36>9i=}mk`Zy?_!b%N;%n_MXEO1F70g_dD$-^otteNz7$+105G7{>MNCOjyFJo3epX$i=s(0=d(yK'
    '(`_4BcnUQyrXi`s_aTvq<DjJ3Zyrs;q%TvPoCNBwsf%l)#ZK!BTNGmh`2c>%#{zmlXR*=LKv;|1U2K3xI{qV!t1!~-ist86AC*gA'
    'bzMUn^%VpWiq!zRsur%O_OPzm*Qn8?FdoT>%y`>g*0#1WN(6E?A{#c?5Foju4T4N9$r6JzJ<8X+wf?r<oVher8-WuBDTzxBE;yJ*'
    'zktBYTs12nZF*BieE8L`Xc3)W^7BgZDd+-)qNbB-yfREvKMvwT!W?(pym)Z&bVk266@1x-{r8=e!>YU@NyAu21Y5*x=&N}^M!ern'
    'QU$zRnd|0m*~R(2Jf=MsIwf)_gN)(5U~t0V4SbVea!E-B;YR#&@((HL%0njJ-Nq%H;NGE84%=M`b78IycPkAkQlTKV1osUeE~9^t'
    'Awds8%t0H^-1JD^&hiR!4800GJJ3<&MuW<TrxZ`Uk;jqAsfB~yfSs?-+n4S9K%%XNNa4IuOj1;n1JN|2jTg8N87{%)i}sTJ1=$YW'
    'w4FCcb4u*T8rhT;1wqtp>bU_H03%ZfD3trEz`=;<aMRjzH=Usi!?*Ui7)?ZR4F-BBA!uiE9RmSH2_h+i`DkS8+vK&E@?ZClBm;Fg'
    '9ae(Wv+PCofj}{cP&6SD?X@g3;MM`;!mL`GH}ZCTTCi-@d5ncF78AO90EA${;Kc(MB;ZPh@Chn5q-VS%pnWk`XX@8)B;qCd{bBH`'
    '9=D6rK#~2!i5WDlV3G(O{v>Y=!Yuk#KnZ$-K?*cGuH6v-<rsOc>4E_~kVwM7S0576jyA?HSRMzA;h<@n7~&9b)^4PpIINM_j=ry`'
    '_k=kdd*Q!9t68j)AY2Y4*r*ZKMmcc0i_3gqn!95vKw%dOBb;IZ>Igj$UI5a_W}}DHiX2nHAMN<cU0k8|{#0gi)6BYM2LbvtJFIGq'
    'nbv$Kt7}Aoa&yUR4~ptrj)x{umL@Zx8IO>ch!{!cqnea~-@V4ZVYx|4!VGbkdDB`1<ifJuT%@mZ|0$F<khb|2C;4N6Q1&7q!dWpI'
    '%nb&BiLzS7^U7^pRQzwdDH3$(AsBdTLodFe_!!(N7$%URIMmfN3IVpk)4TQCz(H5~Zt}x(opn8IA#8)Sr&*FvU**jXgJ#qKd(JHE'
    'CGa^8?YQ=Eo_WYGsSp}GW7z5T$rP($z7}y4E->~_R<|7Q0{D);Z0v7Zy^aMv2{2_sY)jrDCq*nXEU|!|Ip`!^Q1&;G!moV~i*4E2'
    'qNE1O7C9&LA>#al?+i2R$k=CXidwJL)KBQ=qHUCRu`VKcSpYLhA@PQt<|?BKMn&1fnV~v>#71cgU!}C_ckhhvm(*pxP+{be6Wbn9'
    'Kekbht`fa0TG9r7iX>r(?}P4cU%h&TOB{zAMi3lI%b;bTJ-v7&G(3Gs;UhL0Bvv^U**Slih15qs=4y^m9U83kNs=tbi_CwZ(G8;&'
    'Kbls2Y@3QUzn3uc(Y^bVcLWpufNdhwJLbN$+^`71f+ob%R7S^&GM(=8IMuCK9oVoz#0i_G7=0MLj<{?hK6s4Epy1-N4<gSJc8foB'
    'Im2~1U<aL>5iL{SGXr;q=!_m{nZm*M3;B%Ua58b5t5#IZs#6jmaEDjME#kq_$u>#)MpnWgRwJTdGqki{hN2kxhh=Lb1p{D`{2oUQ'
    '@}WM#BbXtn`m8~Kki5gF0re<aP5!VdoMiQ(3-o6$MJMvSk)<R<+xVQ&JrN@s&4s~QiP=5Hn)QcOD{lxiDW=C$$jK**4l}ZV0XP_C'
    'JvQr%H~`IH#7Yqt{@cP8Go0Y+VlRV}Y?w4@b%Z?xCBuOf3>3-}ZvbsS0K!L0pKI}l9~1V6Q)%8jc`;d#Ms#9S0dmx8CO0@%&^3S$'
    'H*tEPtNh`ONKKjdhiCN+k%hRYZ~sxy9|03EN1j5iA@b9$)L?riT|;#+3L1;^+xW4S?T_nSSd&6PN+$lehDv3EkN*UijprUwf!vog'
    'gd`bnVb$9iSGE<)Uhw|%+UiI$moe$+pd+OHBHR9f*~~bU<pkEuF8Hw4uKfmXS8M^C1D-fEJgOl2Ub0AKlBV1e5M(C_Gm<7%fB02X'
    '^_;Ya2g<|DSlWO5e%$Y_{9^D=__#2QG@JxM-z=YbM2w=H0eqn&%<x1%%yC%dcSsozOPdpv?fuXA$GfM=Qd7aMVxSd}Qoq~@Ox|E%'
    '9TY3nZk-^~k2(381A3XReSFaH&3~N!JYAbH)XpGgw0I*=5HSKJH|g{!Gei8r&=nCm+K;7dgusWlANjr@<HsK-!sMhW(73p8R7q2r'
    '?!b$rM}e)KQyDkNtNYq&;#2GI9u};<(3L_f4#@+%Y3c<!mCQhdwnyban{a^Z4#t2>{D*bZk-X{wK8Jb>m%^1l*<Ai)^WC)IdipYG'
    'fH9O7>@V>WVLTfg2WBvmyNK%m1Op$3fA-NPzW?5X`m%>|AVghFMKA%J8wq?!R`AV3xZg9>f@kk!M#X@=_r4&tTt9jDh41wHe=G!D'
    'Im$CUmI{Ds$RWZ+vTtED;eru}{6<3DxvyC3JY4hizxV$uJuUIzf4bA>0tU;)3O}FkheAkLtk<cGZW)LtfSk8&-!DkdtJ5S2pC2yl'
    '48(~0m$Lj43qp7zC~6fHS_lb2)35N0Cf+lR10f>H*LTUE@2z?HYf14LCF*m68)yaS&<r&D88H)JJ~D5i({%Huu;e+*|FkgZ3e&fl'
    'nhIx*3$B&V5#mNi(gIZst&;pr5Tw94jdklqlHltfY`2^aDn-27pr_Hk#}g0@H#$#bWBB$rqJF$fNqc9#$5-Yk78r`%?9>$nZ{)fp'
    '6GVmv>x}Ln5(`W&hz)RO=eqSUNIR8=j*c3YgyA1Qh|%V7mU+G!(?J1ACMfG#4TKFJ9?7tMI2#=tKYiY2%+0~=&U4#d_JwGG6C9FM'
    'd=;^cMWqbpEk8Iy5|})gB1~n15@<!m(psy`iD0xnGvP4qmOm&~9XKok${@|9dDS^7m@rEn-qlb2ZNb9=B$te_B`yq*j~n@xV5W>3'
    '7aA^NSj=H5++f8vNL!jzvEu7Xk(p0v*g-%C^qfU?p)E&T@73C86L=_KOGYI%xsO(hNe0`{o4=9Za{7;Q>nfhfUhZGWAV__fi3+eX'
    'B2eL8f$BX-YK{V!H)~d{%GiW$p=R=OWv3&7WRxYjH7LP5*=T4s6TA*4$qlAStClTZU_ml|`c{ytlejAwC^#r!vQ+|TwPMC;YKK{~'
    '=(!fZew&~+66`NGUxq_)VBxS(F@mHaJSOplw@RP$!!QeP=wUe?5C41x=E&RgfaZ#qOF9n?6Sr=FUU{L&85O<;Y8NU-Iaf;O5I%m&'
    'AFW(N6G6Cus|^u>IE&>THw(ruq=E8Dk>Um0W!$UU)xY|4DKOEG9L3*<`AQ&?-i$;AP@g)kQEDXj9}2c<?ZOpvYpD@vpHR7}u>cQ+'
    'Ukx{BTtFU(j?81BL5B<8hf5!iujv5-4B5+K-}rKJCAk6@cFPyUol3?8NvoBE0G~DwoWyLv1+9_y@m#fL`HrJq0G+z$=RjuY<(|xw'
    ')(lEY3Z}r3b#noc3s)^ybHxF<!pCHS3)9v!cDlqX&Jy|u`X(R&o<5PqRcNYQ@Knk?q4uGU#p53}j$Hkjh03$UaZRU~r%4}CVC?wO'
    'dKZl0oMTtyMC_egg$sr|Jj;e0a}z)g%6#HK9}oNxDviEsxfiZ)iowEgg?7>VLDNDe&!}EGTr~VWbE7Z<SNJtD&Yh}Oe9s-=r#R1?'
    'mx*5h4V&?RfcOycjbOlDTuLbsvoK{}wb*$SP=N%6RBG0+W=x+)m=vJdVEELwFelKIDXZms{qQtg;`-ZPYv%fiG>yhWSn4d!ESESP'
    '3al4ESt-hd_p%o^eY_<3&sOpDVfkE+Z{{Hds~9t>wauHOEx~8PL*$3^KQItt-^e(IPuH$qwLA`kc97FZYGw>E;zx}7UVfgC>k;yG'
    'IvW_dBHUWPG)?`u&(}HZC`L7KTFzQ@2sQW(5B-h^0W8OdhS0z-s_OdHkqQ2B6y@;cwZH*o$QY3pVjtepJ$_e_s*u+U@s9+Jh7ckU'
    'MwZvFT#=rQxU>qVry8U)LaQLF_LQOki*3bVwh%(IVolch=TkwlO<j@UuUPNor43Mo`wJ-ww^}dDT8dOuU-Q~UFS7B%;3ilQpvj0e'
    'R4tJ(c=dx&<ca)*g(`Op$;`ZBab*mZW5j57BW)uCmj@EPiea44tc!oH2hK!s+$3N&n)=1T9_b97+*#Q5XCZYVSpoJ0YxE2VW+(+1'
    '1ouD^$reZnFRD=n7P)@;-OIC9J~BJCFv||ZAJ=Gfn}~P}>k<pi%O;U~0U8`_2EYf-SpC|U+vqH<D*(W#Krmi%4EZ6aV9us#Nu3~i'
    'S<Tp)IslkSVygPZ_2--K3H!FhogIV)2>a-CyhXwsuxG%TvQ@!{{~Gc-Go<?U<xiQP2rO^G?O|bQe!7IXw?F-K7UzDtqzl`NSan<1'
    'W>Z2*t_!&fnp3Ov9+Z_CS3E_y3$PgxO>p7a|Nd?N)o`xd`Uu*L#uYRVjs^T9FDQ{5osI{5W!yR_nYhHdimjhrFh2;UKiSBWG1AX9'
    'Al`btcrY>X1Z@YBbLo3E@QMp$s`<pFGD4@hbQ~(`uq3B#&JPtPm<6*r9jz9J8jUc@Im5`e<(SpPv}&-8T7<i(VT>+`m&~pyCp3<Y'
    'OiX@(SWhQe+<thZG=noSfZ=+;#FrPfUoXivo<{%%5)465wQy7*v;|RlX&rr7VV>QD9=wPl?oji)@G7O#NJw@QKrBTLxutqzRui5n'
    '_(aC1gYsd1emp$-P3dQi8j>#72cv0l#U~1opf@yaa1G-Ap~Z}WL+U;}SQ1=4oWb>kIqs*p&CBq_)3(szBypw7gbNxPA301So0Ksa'
    'Z45yO40k2L1BPyE7cM4q4AmlkAZ6m$s28Qi)7S}mrp$q#fJ@P0-CMihPc`%PIwWZ9H05}lF)N4rft(|0^iq&4&uRz~pK2IuS1!Uo'
    'fP|7qP-2Ou%aH_RCs*Y{xAOQiDr58e7QoAb%UW-iGoRejJSn)8f~`|qF`!Lc`c{$*VA>>fn5e^|C^qn4`uJo0c}ZgHTX*p~%#J7?'
    'q7>9*Jhvt^TAKcd)dm(cqJB^psR?K67X7Y3zJ4l^bT*n|4&IHkj7Zortpw`_499~^no4}0T-}-#PzwbX^*JVDqO_<P1HeUY#7DHC'
    '-@t41(4dReEhq%~S<$W_6TswcnPR{vtI?`flcid@HHyqjgPI)ueJ=caYc4$En#LQwLCPFH9!%WOBFqxi(}v>f0qEh*!t@p%)4Md)'
    'E9({pC!jIV{3gEOgo2%-4o8v+Obv|)Y8q1WnL2)4w<H|p?e%g;I!nwqsipNaXK`GBO?k0oWm3bo8dBM(mCL?mHHE4N{yrXw6wQ;U'
    ';y4Lol1)^k1rQkF1e;xBw=0iL5g0-CO>Kq!Ri|Et)RbU&S$?_$+;q)DgMwy!^=d`J5C8!hRwG?6j}(}23}lax!r*&||D|C!%nj~W'
    't@z&Lo}VFi?8P;xN609V5Kdns?k3Yk8I=sx4xJv4*wih0B>nXJ>oY2W>=+t2iC(4;cxfZRtroQzN|^2$QX)6!RV!|as562gMk6IS'
    'R{{G{xYIKA$0>z07YiMrJYd=R{UMcwWvke#^in}S@JAsXgNH?@)jDM`sD_wErIFK^zV{z@tlwXL(OeW*Xw(}(d;p1fJ*r0yav-Ns'
    'DmH?ZRgmIO$93zT6%B=o5j21pMGj4TVk#13L%dGVNKwOS;<cVf+f|;{a~cYV^P)$(p3OJI;&twn8v^zb9Fa{xs-aB8@RZqOhEY|y'
    '@*owXzb0=W_>GE#L<9zm@Od#Yhp!9Ros`!uTEf45(Es&6{tqB;BA)'
)


class ShippingPolicyTests(unittest.TestCase):
    def trusted_main_projection(self, root, raw, source):
        """Authenticate fixture fields; never call this native D evidence."""
        payload=zlib.decompress(base64.b85decode(_MAIN_PROJECTION_B85))
        self.assertEqual(hashlib.sha256(payload).hexdigest(),_MAIN_PROJECTION_SHA256)
        tree=json.loads(payload)
        self.assertEqual(len(tree),502)
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
