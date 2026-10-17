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
# 0e20867dc40010781f74ff485eb1edec6122ecb6 / tree 0f4eb111038684f24102a940efd4d11d2c0d5bd9.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'e467533279c70a9c70b6c0ca58eabd9fc499be3ba53265d2ad12f0e136efe5d6'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*c%V+o#ac(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNecq}`row<ZFa86NKDX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xTC+TZ@|x8rBW-?n3Hl4*t<<J>j<Y+`b59@?CnG1}l$vST|L{eL)pd(nS^'
    'f7<)s{_EeqFY8$-e13S@KW)Re!fM`k(U>6(^Vmd}!ZeH{Yc$Q+<Zke>$>U&MGkv_;iwj@eV|w^wfB2H0_J2G)CVs6uZTGulVe!-r'
    'UEB6{8glF6*qVNb)}^s&C)>>-+OhN9=;x0YKctuaaeLYyzCDD`DSRod*ase74knCd(gRK@&AGR^v2o^y&Xem}oBWlBdrHUC!|`={'
    'N)Iu;q+LwAuuY|PZ8HvY9&GD}W)5>2$FUtoKV@$kJ2YW-L&_$^nsrNSHKy<VY{$urd^X-{<*A?ADNOBb`s_y2&2Drbul4pSkG$MN'
    '+MOQ$`Rbmwc^j6u`j2nVPam&7#5Q)eP1X+`&v$5srnS8>{TNL*_14F}jWLZ?s~`5ir*L}EZ$DmNcADG9%_fa=m{Qw^&W6V2n4%j@'
    '6G!8QwrAP7X4$`gR9BZC^T@gBGLL;S$p=2%VeZ<-I2TNuLLA39TbuvBv_G&Mks&;7dCH%{_S5fa_hq{~etL9z&oAFTUey>EtPg<~'
    'Z0+b<JH;WiX6#e!Cmwk2lNmWlYgT>Xm-E7}uWR$zC7sf#^Gz7rI5m0lo(Ju7I})U(CZ!P8t-JTvSIsVu4KH;xncvqovuoOp=wLZZ'
    'lMQ2b!Sz#T)~tGX-CbQX7&{C@%x?B}8u@u{?l`@Z@m=z%wb3_Y%6ZkA`jR){^I`v-Hpj4kx&Es;E=|Leb*38zzUz=?*LQAg`gY=M'
    '^&!r2GV7l8vV)y_PDcWF+8mO5+3p^%ZX-^7y<tfGV2PT^*wmT1wbliq*<gBW2V+fG{~&fR&zrE{<?Z$LM`zM7b^S0*#u?(6;o4|='
    'Ke&lA-8O7)WRKnI^>r`D&7WVhzq-EXJ8P_seLr$Z^bJp<cXJb3Zb-h!j;GM1&b!s?^96EMUR^td+)a*<*>mu?3&R+UHyyF9x52e$'
    'BG?X1#cx+c`NMttv`Z&Ny3Jw#dP<wPb&tFK@w5%sqYbyQcT=*a4}G${{&`BtadkHRK-3G-x6brtUcHUi_;PjOb{YqhOv{bIfseDE'
    'K06tL$+6`iWY3q#by~gf`NO-cz9eS)1W)PD)Aaz<bJ)k^+OF@Wu1nff&pqz@$Z4EYFpXE1R@}#vBQHGdpSR(Gu=jO)<VNKHesZsI'
    'd)i!XJl(QaPh{UGXJhNg2D?l&jM2{AF_U7V8G5}8p3HdjZkAK2!|~)^$tABxsd4B6xBf6&-p3G~CvMK<8ac<YYqBw^A=zqf-^?rN'
    '<n>4ygELcThbcEbzuonr9l07fCZv1)lzSI#*CuoG9=@c*E<J6Qw{&$UbL)8^aU8h!NnW#U+U#RH^vcHakmhmZ`)%{hJ9&0H((Sk*'
    '$LCW%eA|599+j(H-BqKDYshx;O$vmOG4)(#+@j<PrelZAXn9Jv?`rS)m%bK)*$}!MP3S$*()xBB`FdT~#E$eS@dXjb2L039ckyzm'
    'JlxZAst+!lt_QX$+Nm9FJ5gXw15v&2yD`Lxe38$(wapw;JNfzMEs;~@r|skCQ+2Ez#x9dlHO}^)t0i&H4Y~Y8{Lur7T|>>5M}Nnb'
    'O6e94pl`y|j8vfAK(*N_>mtkIk<7fkX6mM?YvavZAnk|*yX{vF_U8K|x}F8_tvKJznfi@q&`sk+-1h^)mnzB-X9Dr3x&5&mPn@gk'
    'AIr?AF=}Z)cT)&lLV4!94Lqoka&jE|Ztm|mMJIQ7Ox3qQCgE*dh-4pm;2TLCY-7isk7U#n8psdkCf)v)&e`hQRp9rpyXXpmhR=iw'
    'tRX$;wKRqzXo&pZeh9WTez1)*)Co5IqCHhyPaTEz+|Qnx%ywyxeQ11+!5F^eDe@UB;)LAXxufNd+Ej(X(38Knh6|I6acY5gV)7GT'
    'HdT)6x{mTalV;ud-qP;t_ORbQ^DmxX-Sx7r70xr~)OFtbJ`7wD9#8`GAi2r6JTq?e*xk3M>RWVjc61$8#W?shfzd=ubxQ(9dFjc0'
    '2M#<tvcGOSn=MJ;<N5X|WP;vLd{E$3p&<}^UY4JSFi%_-9e0{fxn;ZeZSAI8-j4uUB*c8<c^(s4NKl;!Hev#~h|RWhaSp#|YhnMq'
    ';3TC7He{E&nMB^shCr$JIgvCIzS->%jnCY(Qx|{Du8!$z+7+s5O4d2_dVv&?1b~L;H8qCoqwUfJ8rl)a-F^G1iUg#GcJ2f*#FW7W'
    '2gi-;nt{U~0A$U;3pJFvcW&i}tmt`L^Nr8B>6`$DE&<{J-GvcI(RdK8#O}J*B@>;^_w8$aYQ%eU<c#1Tz3&8bWxz#ihSu_l58c$V'
    'L)&D3@4m>7HsO%Kc28UPbS$6)lw8)fT(r~dN!xPfVJRmto@Cc_!IL`0`R+Z{qy!z8KOYYN2eil;!<i?m2GR$)>861K)wnUX?R}fM'
    'A$uc-^w|t%7&u{+&8`PEO=F*}NzQQPwA_QH4fk#AxPLtWYK8sh1a2L!XLGC<8;T;wlM%|6VmA+_v$INo9OlSF3qVYFZb@0?rlN!e'
    'VIp4x>}$uK$}D^CnHJO~c5R=)Jqb@!^KRc~{dTh3KD`!z-pNiOxzxMH_Abyc8Od!OIZJ4HOrh(hnFflv^SeGhzvS&x`d+PFKmH?^'
    '{?Iw9GvFX1<^U|iWAWs>jUZV%J8eJQ`E{QTug4QN$(Qu)P=ZD|^W>MDZ|jrco1S?`VFoB|yy2rtQ?_wR_f!NcHlr-N>C6Zw+Rjtv'
    '?d6sjZmn-PVZqz3pTQ#PuKx>2efcNXZ;RN02J%^ej*dO|1qFRWCfgg|lgNV6_Vk{nx(xgAbqROr@Vq@9mmcEPWX#Vq{RlNW@|1i8'
    '(-=vkedDbgZJKBTMPg3fPyW2u+u!d?0bdt1^~B`n(FPks-xAuW&nIs1*q8_$$1$l}^PIL^51nQXEeEfo{SlQ#0emL|zy)lQxpU~N'
    'v4>cfKkc~uzow0g&)e%a37rj+58|Kk?J&^&0F{V2&|~ZPe;ojqrC_Km2rjGEfQe1RB~DqU0%;5>3>5a36Aua^_$W}W5eDkMr5{gH'
    'b&e4_lUh%aPkpGWl@3s}wD!m~IP6Uu{R{|SSug(B@2NRTW2CmQU5p(le?M9k_-Q74?l{VP*3{C}W^r7x__;6*`$O9N&h@xU*J}uc'
    'R)QIQ4ofqB9EK5;d2Up>&orY3>QonUB}Vt-4xaa4(^8Cb1r@GB11>qXZEpP3Il;K3H6)$78^Oh9s`in_!|dw!ur8{Ez!Psej&(!p'
    'tE17?dy_jFx}3Dc1(cu)gxS}xUm03V%+!vPQ>_h-GESU0A#Q4&a}e!Bcqi}f>K8u8mx^aj4a9q=ncH%GwT4qTkxP5}=rmqH0I1wz'
    'Pyci6(tnk(*Y6M-*$rurBXt!PGPY#)6AvChzu|Qoa1s)-eEag3ZeMtLz5X0HcLt^ef67~j7DAoDO*ViMbI;LFm_`~c^9>uRTffUa'
    'O-@7BN3)aUi!3#B9=eu4m>lQ=l#bY}{{%?b7cK`!!5yw+LEdwdw(7ESs{}$`-?OIxt%8p*5gaEnjTrsSTc~>yBhR1p8k*h?vH|1`'
    '2it&$@2HOxH#^ByPo8nZHol!c?{{^8rapd(1VEi>p<zK0N<D-R>V!1WW1>3ddD$Bt#vwg|=}@S|%^wH%@>0sOf^R5)Gam(^Ko}U8'
    'qwgI(VJdPMV|*{*J2!k7087`Ku){!|Hn14!T(oK}0u5%mZLL>`1mz{|OO?gjg@90-5X_^ST_<u$rWui9!;NG?w=Bs)>^)sZQDE|l'
    '`{<^ufc`>H(|h3g^OHTSIJ%v|2?})V1nyi2LswA^oqzemcK7mn`ovp*y0EGq$nYQjNF?6CYE(p5cSEmERVr_N`Thc#J*6Vhng9{t'
    '?#yFp`-&{-r`@pnLy96k{kSoe9vgSkqbmbPjw+EfjT%IxFUMB_warnMjF#GiK5^1lTLF%Kw6PLtCvyUnKk-;vVGUfNF;1E4W2E)j'
    '`;ZA>Qw3#axvbyFjn|hXRpZ-Kc1p9Ch@cL*rxqL2<bkVu2Tx>lxpK)jXiTwk!+UUt=lx;x%D-30TKblQz#U1)1w1SaLFFG%>pYFd'
    'WN2cBVw5mmyN`3_`EcP%d^#S&|7-F{d1L?A=p-L+<;*Ejfwg3s1w51VcA6sH7h~X_T2d}IfM)=dbAEX?4sz%?-LaiF0AbnI^{m(W'
    'v4u()0x^}4%K4?{u<$1`=`i~s`OFZGZrsd5;yi!dkV)OK`tykc=an=twLnpA;x-PjOn7V5-Y)k15n19;LBA^Q%fD`);u-&`1zd@2'
    '6GWia%|T4w&_sd&>|P-tU}UsgI`K2j{hPaBc0W9}0uO~_r{_gT2=FyQ>Kb)}X)?gb8Co$OOq%We8{5(bI=sEq3+enivOu4zg*`XX'
    'EjRFTqEWY_qhZ{_r-NSz;oMB~FWA|RJL`$2hda>fyZ)6WBD4pKrfW^A2X;>Mq|Fbc<e|n;^U^k+df(r_t8>yrjQF8Ld;L=N4wBah'
    'xX8O}2vm^+8D~B<zBt&npaP)&lfQp!YhqU<&*0nV!-qdl{B9?j{t%oLN@*ag>p{Kde!;Q4r0d(~rILO1FQ479z>bDAIS}UAUZ9Q@'
    'nm~r+0E{63P~vjoh_vm0!8dlk3ajAjkv=C;0&FL=0EpwXK&BbWcr&y?B(;_Y*QEP5b=*EK?1(K=5Gvn_L)il?av4(e0ccx5T%-xp'
    '#9^Ry6-ab>VBo9izhQ4nrc=>&pHeil+G~(sXTCkEVJe~o7TQxH!bVCF^!XPYf;S<+_3dQ($FM+wWJzs+h9+R40Zqq1Ms5U1(=X*l'
    'xN$pgd-$~Os-)k~qV)c{=ml3z+)QwkAxc2q@}L%=wr0HfEq>qCa#0poH-fGpXLBDq;*{kml6Zq-f$RFVlTZO-^WD$q65_8zIuaRm'
    '9ajz)GE@i<R`@K$cpwC#I<)c`wA1$Y?xo_GwJ>T#>VuLof-=I}rPJ=ohfz0xZU#p-N<VwNdn=dv;pf9vhyabsr99F(aUO`h>kynl'
    '`bV~8J6@PNDgfa3Zf(Vu00jYjh>GyF(DTp|rOYD#Gp&O&h1O;iJl<TXCgb)X0nue=sZDRKhy{>!;Z(+gGu@or1iGP=wo{muPt6So'
    '#L$6>gOgL%xUpNahf)zsl|~WLPW?!EKtX^auM?M<wo*ijK|whpm8<{Vm5nC)y$xyxo9V?v7wQn5%+&CZElAlQP#d}sW`6JE<oa{F'
    'TtY2UOM@R0ms3$p?;kXgABJctKzi|f{SrNf_ZXaUAE?F2GTqas4OIOfBw8E&vqHa)W%+<Rn7+Etk_W%)QIzm?*`f1dig%++*OwLL'
    '@H!?l#|-V9zQB}7giuw&przvW(ys8$bObzlS>5$z&I!-*p9{U-x%0hX7N7eOaT}ycl4y#yjxLp=e?l}9-}zC3ztT>q_$PNbZBb5<'
    'C@)NxQ-MQHb{=8gfd+GxAjfG;pjXr@Ef%e^&9sYXmt9?Q`BF&C`THWB&8QZjp%39Vz>#X;v&II<ZAcXEQ|RYGG2p#B_HPTGi6Pg&'
    '6DMS^?;2QY0KOw_#sLBpUp#6_j={Mu4u#)$^!w+{S8nZCPHBKKXKL!6qYXF$#t-!itOkK5M9|)o8Ac!H_nOz|Y$c|zTfIf<yO)zz'
    'uSxV8i4&la2(aY9CoMLi>Y~i&lJxN3n@H2sl@^We<s|LQ5@G(fB2VwH=gL!Sc#UwQCQw}O=rYm221_7}j-w=!P`AcZx8m`;s``bZ'
    ';QJq64{WVEs-c<qbm?gz+JU?Rgl^cu2m`pGvC{eAZrs7k%l7qoQ?rpEwl>|QG%ju2E+IEYoZ2fnQ>=#;428k<D>qX05a7!UwAVcG'
    ')`}=P0tU2@Bgj8oJNPg;)DB1u*RCD*Puws2a|(Z<J(j<HB*H?OP_xaRqs<M|(!2m(7n2V`3O(kDEI+Q@%>o#29up1sQp*vd7ZhX3'
    'q=N{>R{0o=20Nu8BcBFI27{w2tKP!$9aOywC<RE9yG%e6)eHqZh`yB4YX5^7@gBgm+Uj@l|HnI^bMahQ5|ZsiS^*=mL0-%6j0%7w'
    'p_X<!Rq+VBfYxhQyJSqqFLbXq`|$d-{j=)X1FLFj`c^<E11S$Q9!haKC$oiK4wnf66WPg)TX=kV-F${0`IL?YSd*S&q<HKNs%==='
    'qp=-{36M^w-dYRCj<=DTU$75I(OmCP-3vS;S~Nrjh+}X_hn&^+iz=DKMX<=pQP*^x`869_0H%s&w7~FQx{WU6HbgqVs3m$-$Ve5E'
    'USSgNsvB<H6&LpbX2fy(g};6KyQ_&8RS?va*^&dzq$Yq&BOO^3nQ@}q6(x(Nh0xx(pECmCzC97pR3oMBM_266kZJ?*m+Yv?L*J`A'
    '-$Nlu*mzjw?;|aH)205_W3_reru77lfOe#vW@-soG^iwaW|114kQzw7yLVkh-rvvjK76S<+-_12hoXAy%m7yh{tj1~g#6M(Ww92>'
    '{Bx*X_);zU?JkzsmsF}!h7rtyL6^=q3JDa#QXGVx8G<V!)G$<^=a+5R+fRA>=Sisl0)AePYtrnH(2+;bdsJC0x&Y~<P!Et}Y7nxH'
    'aay<jUzDlpYlSl1iEc{s2-cYT)YQusCl?Esh~DTZb{|05x{VxUwQ{K61TrQ{A=-*!2LRDI54b9`8zeD^WXyyB72u_I6a2S|sIlUX'
    'w@Rs^RLFo}vxh>&rAqqA_lc|`C%6Q`QIg)cgLA%9{XC@Tpvo1@g$S4;o<2Cl5prUDeh|ZT7E;S(tMB@+d;WH_SQ@EXEkq~Ms)p`e'
    'M+ESqur*5gS(LB@ofHL*ScT=aedU5Pho6rQy4HZU4+06;8gOWDk!AUiz(Tn&P~4OjL@@L1KT?(Sik>?tgAP2`6)!r^(m1tX4g)tl'
    'nVtc?rvFe{a*?9F)#U}9@GJ$zOpn+k`u(;^FsASXkeSm&1DC%97)qspQ>T-r^91f>0NmkLwCY$>eIo)QYYE`*{aL#mZ0%ypFWq0-'
    '!TOJz^S?o6@Kn)u6==$*8>!f_!5AUFK<ely*LnDGlla(L2p_SzWjouQ8ozKZ{A<RpYxDBz-?%W>_e99&@&&{NodCWIfIX4U-8A8B'
    'g{ng^o`;)%*Pf(qLobz{xRy%HHB3vSMHqk=fbM{$0(5SCf>7TB({#PqYwkTuq!s)5p?yPokke`VeEpi@4urvueuT0Yb+B$LB!HX_'
    'I=&nrY0Sufqq}8SPdpvEy{QzMc?*r2^ubWyVdTSuGO&awLTJTFa0g%k9%63U!}HP(q$N?>16E){UqE;Om`ESN^SH42X8KwCAr?dX'
    '_3@TH$lixN9Ad?@NZd@F6i>LG@udK_!;XP-f+Ye{hBzQ+0FVgdE&HG~s%re@l^%T6$3e|KQwgIq;AlfJgxN^SkFy6mqFpp)-CDzZ'
    ')5o!ZHJkIjbw1hG-%rEcJWvmky~5t|0?B}K;VeN3fB_iv)uh`_57_+v003~=%|D-?3Zy!c8RR7p5V=n<1ft%t_<vEQL0Tf@bDL7M'
    '$6v4&{n>TQ0E?Ajq+gvDP8ohgJQiXM#8{Z)W159?PjR??FJfgL9Un^py%CBD`fa31K@<YE#hU`YC7&Uqnea7%UXs!+8#%h?7c^-{'
    '@q^E;{StAXzX4CA!ouTV4#~G<`<aS|7MkxN1;VK2qe(Z#{*#pHv7!R7syTp-Mtb6S&cPQq^dT_7quhcKh~;3mV1WLXO`JcE@I)bY'
    'eGl-*Bom2XM|>s-;3VK5L4JXJXqE%6!@C>nk4^aOPH!?AcPgG0@q|IL#ZjiaOsWm80?^IP0vVO_i*%Wy-Peb+?<S8I>nI@H&jo}4'
    'LIMC+qTe&Zw^G}Hb|vfuBrVu9@i+vjO!YzROoBb%E_*MvB+XP2)!a)VNrL(bZJYFymU|y2IyHD+kQ%9hN=&6D?@+*3Z$vRXd<#$M'
    'lDCDx2~qxb`n<RSJf(77CLJ=AgrOmHaoN#N1O$aFpxXx$2faX$0potro+^yJAdTRohX`NJhJ;z9{{h&`>Q84XXaFA=hSM+EP~76W'
    'cPcR6TO{m(UK)*FFPpDHM5}=PYl1z*rv>XOtBm_4J36F)zLsJ>WM+LjL^%AsFnLr`i6amP%Bp=kA-P2uW5;_p^t6B6?y9hsfi@Xe'
    'VA2JR)g@mxXtgE#7h4v4N^VFi&da?!0{u8jqp=IA>SF@k5Q4k(5$Trl#%426sL(_7kt9L_W^SdspA-$p@2ct2o_IgJ9cmI<P9uSk'
    'E)yLe5ic8Mc<_5ODMgC+?&+9L+*FTXyF2%C{Jbyh3em2GD+sbnzjKhIir!)**R*0-L=nWHX#cWZy}mr{-F2ur3x%hE$4V47FFqiY'
    'A`o*j#AiCuLh2zj*`d96PpAEtw7bw|uP0kzxMIZy>J`_MjUzlH8bQZF{xo+8-dk<Y-@Kt14?^P)De2$X6*+=jTa=BcU!c5z=D|Ci'
    'WM_w22%N^rVzCQ_{N_-}KTxA$^Z9gosR~SlMEa)f!mGfmfnZ=^eL_g!et~0&3)O&ks~PUy&@mjgFEv*`T`fOg7YY*5Q(vM{CHVt{'
    '#VeHZ8+Q<?NGUn**ie~fN{__Ifq;rKwq(XsvQ*dDBOuYjH<HT*5moPRKJan>?1<CL_3@Y2_w{&f_)Z<l7+AQ<i583;VI|xf=&vM9'
    '*i6XS>CP=ZZ6&p>K<g+|CYw+-d%_<I8BnYUGK`Vh)RHPrQu7dz?624lRZZHKjDX}|7x8)zTo7a;NZVjv>7ZdE1Hr6SLy*>KbLWO6'
    'XTo2uDncXfgDC;Qr{PS4*-~x+Z^HM1C@=T4NLCG2(cQYGGvny{8T&zTcKy}$aw)U)0Wl$Pq|s<XNA>L~a`4{p$h@ddn_smp{S_)>'
    'g(WK~39n5~R(LqUOop`>Mvy>!!6x1=$RtYcZu&+0%4K^SIYlQBN1~&&L>8{H%<jp&A>t4#K_f@BG<R-Dw`zrzHO4FoM;X?ueEvCg'
    'v?FHq;wV$0=RitQd&u0mn={Mtz@a<AfGjF2V7Wp#B-Ox}UpfJ#S4O;Uszn^;WSxY=1x(XBcXhcxUU!ubi;gY0Ecq>WyQ75dQ8!KS'
    'M1=DI!Nbr8PQa%0)@?oRPkV97Nw_b2D`eXc*(G>QE$VA4mLr5p2o#<IfY#y&Q4YrF&Cy%Pg7~<CEw7(3kM{-{KcSgMtEiPUR=M0b'
    'Y7|X?$+S0VeCJy?^0beOoz>Yq>N?_M<wTBF4+_b=XaKl0pw&?m(e?)0#r{T-`;NV+7`nWqOZcw3N`M`VFl~xgsG7|2=!D3%G$MFa'
    '@+TW9lBiDZ+t?zaj>}04`(i6X2^#4kgbDm?XDGly#BvyShzcp<)Cyg|p<DNKfkpm$Oyw;NW~PEQqmv{Klmx?tEb1<OSw3ZAq&{kM'
    'djZ0#*zH~3UnMwVNnvF=BG``R1kUz2HIJg&BEN^32Gv(&^PAI>-Cm6&p?T=vd158Tui-v}_aDSnOp8!KoPs37!T?-jBxk}4=jQrj'
    'zvPhTatO}sYauG4sKJN<BB_xvnTBpakph8G<1uMULjZhCH{Y;8i~6jo`3c!|NDYvclU1_x-$Vl3acKJM4^Zp{JfJKe*_iS@JGxjy'
    'Y)+r$x_5m$m;pEHQ?M+_qFmBu)~D+S(^Ne#*fA&?Z%&OaB^h-P(GkL7nRFm+E@vI~J($%@!i|D~PY1boOZT89n;dCs+<cEMH)*W9'
    'J6djb+5(uh;h0bUO0Eb<O-r6`Hr85nzA!sM_Hz4PmOCD4N9}1xlxWHEc{fyrHh_KLKaS{w${MXF9Srgh=6wuz?&#}tg~5lsLqJ^^'
    '{M4ovoO&XMhN(SxY^61BC6ZXXaC08?byDK`RcKl%y=UYVAlfX*y3^PTmY!q}$(^O@8h>fZq}koElk}(f@@iOD+m5pM%w!=99z49E'
    '2)RVnAwze#S@~BHDg?~#?%C9Kc{-`~G0g_~c91JF#2TnA^1y>}g+-i|K@1p(3|YGQz8&o=>M_RsC@T|lmq{cM{;Z*p?obiPs0hBf'
    'BI0;E<f)yUgfZ+71<IjSvfjznVT8PmcP6q&;xqHoQroIB%#r}!v5yNGFqHI$(ClCq<5LEPk7W=RzJcZs_HkX5DGEm(C9O~QY~}ks'
    'MFcG5If059V@ePXP+nv#LxX7!zLf+*z7nc>ZgY<Kuh>kvI|u+KwGeuBPW31RhIS>YRp1{$2K0RiPmtvA*o@?b1??1}O!61G>tXBH'
    'cQV@xngmCx3_FGd%;7=c!#%q=$*prE5?2w6q8wIBlx8*Q6bUK&p=(UI1F;iP63C2-=bqU6J%>neLeTgZ%%1Sqz-o`NT5!>48iqU*'
    '-Wp96Ysqv7(EL%pInDYj_uMRv&4Q307i{#1K<|*tz)pEln)^iCf|8Rj8PG@W^tW7+JQ!&vz*5c}+k*Iw)*J4FRznfJyx3qGgFkUa'
    'a+cxgfH;$3)#p|(PgwE185}JCx!Bt#lXNnth~!N`m$U|Zd82tMs+q*DQ9}$1<9f;ieA2T7_UHb@8;DYE&;rMsMiR_B&=h7iLfj$Q'
    'nxP_KJ_|z-HXatRE8vO`_O+A<)w@ClAM~=Y2F5)SDKVX0tUR!WZDnLf!+GWbj`rqVU79Dg`ymwuqV&iX=nUwb(|m)O07oBTC6^S<'
    '3<iA}bMt<FWKq^`ilh%VfKl}XMVYRFJO(9A*P*8y25OI;&5CsE-A(DA)$eI(eZv7j-VJ@6#1!BV%&SpoM50clZbU6_ZrxKjxZ`JR'
    'A$R+eE9<|3mEg|I(okU80e%XJT=uUKb{O>n1Y8Qfb_GA~Uv_iBEb4~?@y0Z$l=*K=|5F$s3vCgJ<Gq5HIf$mE*t$6e{0uu)Zc4U7'
    '5%vUvI(Yw@l!hgK!z?9e-B^i|DI-aCG2XW+Rm0VGefX?&`D_|Uax7zT#`Iz7(@-Rj!oj5*>V{i)^c_j5-VnyFtq%xK`=onSW1JcW'
    'q>&3EL4--jKPOAR`Mv4kxFg-}74eaJw<SBI7VhO|z<^fLFZ!kAsXYe$)au+T^Q}9&l%M2Nua6oQP=Mk=nc%WB`%3O5SkORD&Kkwr'
    'sqr;XZ6UEjC^_7{opU>9Uw^&Pdz0%X9}~D!)-}hhNogmkc7O`O>=IlQpYGh*(i^DVlV%O}Qh3puL+C(8Mr#Gi0@bJ$AWkMZjqi@@'
    'S+%F*=hu@G#`^mN=#+qDWY-F{tHWi9W)C+n#358r6dPzhC|;}gb=k=BX&>JrW_VqUq)+e`Na42ElM`;Q1k6Gm#2_=)#x)eW3Bp_Y'
    '&VVmA%R6qK@7dAb|4!0Gl}gxzTfB<}BMccTp>su#hB-gnH~Ebb%E7~;G_Z(|xm(sGOz-UJr#~vDmP{1oO-(Yf$H@qT43HL_mf%Zb'
    'RI|AK@)V)4*6%1``<))tiYJ%+*ZlH28bt*Jg_1ehy>vX}BUvE<WNZTb_PYMC?s(U7<)h79`rVf&bNRbVJ%4>G($8h?GUib+bxssg'
    'Mu1vOSx7)&;Lv}DTDyYo{J~a=sXrG42n)<=>3pb@gI5z3V!l}5t$fyC?A!Wtb#fkv@<K3P{<Fxv#{#oe<0J4|<Y^3Y#)F0jB9=u6'
    'z#t3`5N%~mQ@Uptr6)l|VGe=Z=J+%b*CmZhYc;3@gGkI?p(f&!)6}QY=TCFD)d5CN2m1EpzAdEdg2qfdVh!NNP_7rHmx_4+cY>Ti'
    '2@UYxQ@gJqL!I}5l+PV5R(EF=NvS?Y?gar;Q3OCE%Mk`l8v+!~efV?Gy&I-T<#pS@ntO9_$^ti!`fI6=F4J2SHBqTDW=#ksAg<*`'
    'cr8N%=+7{wn(Sv<zYG5RW5J3|-Xf#s0>Ie?xPTer1yjtrYT(Zz`=!(1hGE^}=U1T5pz1xqssLxigbvao)+Tt9(vE@!4v!HBb!l@M'
    'LTFd$<1R8Q>1QrAU0KTmDHfqIX4tS_J<~E_deasUBreps{3+~r2!y>~w}}hv`Su|c9Ox*tlaOB-Ju^Bai<U>hjjxR8R)ErQ2h6nc'
    'd!+A#(^H)^&}ceJq!kC{4$my=SP0aen!I?=@Qy~*=nM=?>vjO4#4Qsi>-hnQjUfXPnmLg&RHXOL-Hu3wIH>^>82i6#I(Ky&izKBi'
    '1@T7u16(W+>I}LjARtpy6THDdI!1ipeHnAV@-<vS^be1q%0dk<i$>beNt1OI9vRWL2+P1cplpgC4HwC;d?WO<JfTu2w6HuHaH#xP'
    'f2qO(qyy++<`*5>AW99lDW(^=b*)?ebxWpqIu$-fv~2u3JmYm=0)x>nGU!2Zu7JWKQg0Ao*TvOqAOF~vy3?AFD-tMWft0b>Lx{1f'
    'sZ3OQn2i8^8)>1d*Ooi|nb!0y>k`c^NWR8%%3`wA!h99FP67kKZRyT9aUKDNu-rD9q0qN??xd&<Vv-sr08<MCS03az>1rY@lp)4O'
    'E#6xw$+Gq9x1rT9T(3%M1w(#j6jG=gHQ^b^2Io8O3mGNI0<06h4Dz(%<wz3rARhO(pHc~Y@)FT&ftZVYIQ;%NACoqv{~@D^nj{8Q'
    'mq5y?f#-x$cd)nb>i7M2(N!!Ok4=7Zj|E$1wVr8_i#-&j6p&kzE_#DXnA}TtFbu(JZ{N{b7Yf^hGWW4GB?n8rtij5-{1LK1mhcqI'
    'QoxAxO;=4b85sLM-@YAKi+dErm$%34g?xb8P=Ipi=*cCo>!dTmM~v<smmPE1CXLIGinYg^q*O2^0qo1DCP(|~&%&4}yem2d&<=Uf'
    'h{p<V1TqKT4D=k(q((DV+Y&6A{-jP^dht~jgi>Y;XIwhYSRUdrO@M7iw`AKaOMnIa=&D!cSQN4ePGR)HXaZ7{g0YhYz7a2qyOdK('
    '$&7D*sZ_tTnEu763%AZMB}1DmYOGQToDV?>pklW8N<@ZeA}oNN!3=9?Po{GHGum7*2-I{{8e4#HGr)-4?Wt$*hKlM`@Ys=9r6yOd'
    'cu@$vscCC^ZA?QTBjA!kXM$NETC;9Y_K5CGU7OG@{ib3r{kDVs0oewqUvcW#sKEjh)S8#9*_)^*;lB5aPyrVq#!)c>x0tbgU-pl4'
    'y0|AzD%q9eK}ScE(GyGxp!13oofq3)%mF%!iG+=jw=iETm&TESll0f47gKY8{iWl4Fo_7Iao<5wh)yPWC`G_JVVZzWQB=ou8(4%q'
    'g<)4vo!~~`)8aG`L_n&Q>s*vap@AL1Q1rH`edNo;<pL2E9V6wK23r9G5~T3m)X*{dC~Toe6vEWkqNriJ7h<YF{pU;AoL+Y&Z#AiI'
    'xU)cOA(kWKN*dCMMw;zlTdomPsDnaL_NsLkWKB=EJWh@bzh5L0QbuHrq#z#!tqPK=Ll?sQR?~}`npMB;0-}RR=&H1*5uXkMV1OM('
    'MK)=oHtW&4(qX178nNAONscQPzxb)1?Flwz^Kot<ZUp)~P7|wJA!AT{IYM;sOoj$XD@H<%nxz4C^S5=soK<?ErwtR2xIBQTGD#l3'
    '=gjRw{kgpU!4~aBeownE*qeWXRRa#gwNdcNV`c^;EHnoS`ccv#+Mo;{9|8z2kr|pC<f5eMZPD|baE*-g;-uy6W1;NtHB|>V5NbJ?'
    '4<Zk80MZYo+6tY>8L-?4m8-wmm%q)JCKY;2g{O}9{^IJ0+I4xv=z>AR@XhY!?g&ap{6sA{S8ib;a&E60+XBeqYY)L5(y<evi%5n#'
    'gQ^1lUE<4YRGbv$hi@xhTAfud8)rruJ&4pa8XAm`=bZ#=K#jq62+KXJP2Y8Y{&?k;Z``1LAmaq!LRgTOv8b?mxhY()Ol8RM0&#Ac'
    ')@-5TnWL=0)qoE<EjcDv20AAS0I^rGsItuP4)XgeEc?tjF;{J#My1HB<yy4(6Yw8!GHlUPkrC19l2s=?)J)T~wCFy*%2wp{<z40P'
    'k3VxJW{~2MX<;2l?~ED1SzIh7gAk_SSZdaEv0^^2cw8)^k5zRk#+o#vTH$3h8W@XU;PH&SXSg(wix?@bp6uvr7k-hFmk|vGr87+f'
    'F$HGzH3qp3L6RgB;6v6#4a7wVeVi$>EWR(hbi#{*Z~SXO?dcgnULsneP!n25GC~D2Izbc2zf+MD{(aSj>{8_ygFPG^{V_?ygd!%7'
    'a$<(P3PBQk2igeOu;LxoSFWtGVq4}`5AsLgk7hW9P*z$pJ*7jK{K^-TBaG{>F>~#r3y<baY=gQ@a-iZfC;OsSBeTN-49+EUIAG7A'
    '*hbAsQ9a_?Kn-b%M7p<4T<9~@jwOYy74XL`3HFMB1+gZbbK3WVdie}G*3YMy?ANWk;IS0TF9mh)L`w#a7q*L&Vz;b;_`ooW9VLd6'
    'OAHBGtX%s|RY*#9eOWF-Mh<CmDLqSmy?7_msvvP>93Q$2gD@;kmCNR*Zw1FJ<{pA+gRv8kLHEdU1}v3n|C983RH%q^!3rvu+s4I$'
    '$$hyRC^LXMZF~*QZiGkBW0_Q<P5`?+Z6~`~Qo!2J>D+MHrB}+u>lr<GI%pU$ChcD;X8iu-myCLwG1+iuC@Dy>XIH!M@2}6-zoA~X'
    'hMIkiO5I3{fZrs7-a&b-3>fhu)BKj9a=r5qvd!@s1mfxgri<ew{gmFZ!_aA99`G!26DhF)ic{Pm1<1AQzR_>Xuhu}a6A*xrCBc%9'
    '2xSad3l$6zQnYof+L>_?R<B$csW`H9PGB7*ezYaUkWpzz`<szQFl~`@qiW1WKkV=8@AqE{eaxj<%LR`W{Ve^BM>LJE1~#=Y!^HVz'
    'w1=&Y5}LPOP(*QP<dBRYn~M*z8a{j60Knly3Q}0Ab9mRbcD>i9({`Ctdc7=U^pZSiMaz?b7g%jp3t#g$0pl@lrd`uke@}0NKeJ=`'
    'I^`#THlZoW7g~_AMnS<OV3rCldw6q!K~OaV`&91W2Z!XU<r!y0dV?1agkRiL<wq+74=|70FA0UAC&na(%H=P<$T+J%ojw=P0Es>D'
    'q{UGYoeW(`tdgitiO=-maNX}AvLjWgT=*D(mkOW~m_2uGgoGL7g^K5;73@HH00WB(Rbg}N)-1>~E*@NX2kLOaUc^wJvqP(m;Z087'
    '{)8<gb>M7VhjaD1Vp4(SRRGk$hEnTN4g*DxLLlTcOa#NB0vQx)Y?k&zZIu4*Ui5<z)%Bl_8X^p%W_fUw`H~UpgN_58@{RMU<BTCE'
    '*xEbzjM)N`e}m`vrI5iB4Dl-yHw)-N^Qy=xnOB|(GHge@N&FvbbLmSzX34KoLH258C`j%x$nlSc6}7kQTo-~SB0{1l1!Jl$S<X%F'
    '>%Wy}ialt?b%=>b)SSYp8N*2mz{6F(0RYqwan*_&I5Su8Ll9Ve6>%`vbY4bQa9OZCOxaeIKW2IZjXUIJ>sCEyJlo^GLeI;PAk^Rd'
    '#8%R&QH&n-1!gKJE)!)YT+Obl{@qxYo!7sf`QUy>35ZJ>(oYW5a;g>q2l_r5w|wGE&kVI;<n?8N5?^0LXeo3AAZGJeu_u-jA4yKn'
    '$);AI|DhfUNNQGWsl6%A9-4I}1E-X^UL7>DCA*A}p)uNsqO-`YsAKRQPL^|RxpFp)l#%GcRk&+29Z4)=zGKZ2Scu}>&4Xr>NQ7Y)'
    'T4pR|2B-pee;&?n_|t~JVr{-DkY;9a_h>hxR~$yr2FzTs@ftOfMdcDT4C+C%X5qI<RhN+?*FUvhR^9m0aZ|xR=jVb1$m_srkcHKF'
    'aN>B|u3G=%)L&;^FOw{uyu^1f$>?y7%;*vI)o8jXd09Z8ZHjJvKkeXxNIc2Q{DAcfXhFfF6W^N&aTyH}tnc7SL!{CtVKll2rZ9+`'
    'ABx<BpY~9-Fprt`z8BbrwuYV)R4op+TCDVla14^oaTo0Bh4pV2s390@fM=4iz+$9C#)K3|m-ZCW2rPg^Fk~)H=?*#1kE#09WSzsb'
    '-waU7QR0h3NQ4ZPdMC~D+#X;*i@IJ|@n!ph5T%reQ9228@tPWGHK1TA{~3-!UgDuDs*PN>IeKqw<&PJXcq6D1XqsBrbz)~knLN@l'
    'ry3^12EYWGE;a$q77EKJyY%PJZJ+CS8nu{JBc6W4LJVM1J#0rI^7zbyCee){!7Ykbk93Nk-S@eO4{xM|@9ulmvkQ?}J2@3-!j{!^'
    'S-=PkU0Mb+Y7#&nQI+^IDYa%pHM0#75@VE#j*X%kQO~H^36x)Cr@*?{glI|tw3YU*?bJ<?^vrBxG%}hns2u9C1AHN&Gg60iY)YZN'
    'E6Sa(?_`<6_~N#Ov4AEr@QZ%C>cLhAk`x^(bz*cTV`{_*gMwAGZ@Fv*m|G=ijeRZi{}?}j88cR~%vvO-qbq7u=zB?=U=I@xdKc;z'
    'KB)jj^UiDtJ%wV0K=;+luGdL>PiJ_N_8z4i15)@jXDJNgSiSb5ggxJ|>2O#kLeR4-If>#%4R6Q8Yr*A291Dq;@i?Ox<$;6$lKUV^'
    'U9pLkOrjaA7Z(7HeO%_$<6f`mK>^VV35IrtcV>C)!H+xm{Z$E0&ChQWvrDanq%xp_fB?;o?_L0Wlq^w=YfSyuEWYCFqZd1i+_O+I'
    'RY^2bBXb00c?V=k(@r?*v|{yjpCD>bf)M#TnjX9xJ8TjGgLo*^6`DF7!1kEfQ@U)SgXhf;bKC3Z13``lHSMIwhTX***Pt9)KMhjx'
    'S$Yck^`LQK?FKHHUd?nUIdH%=QC5p;rdy7_7cNhB4>bZsO_F(|y>ScmW1%<zqugSsW$8n3PeUyOWF-mm8fIXZX&`3pHtI*BW{Ka4'
    'H~eozgYy2FG^ZY*lSrg;ucHof#o<sN?BI<obG_<d^cCy`h;QV6D43WCE4T`l8Da%oWjZxtT@f_-+ZO7YkP!889BF-mOvw~dE<o^C'
    'kYE-D2&O|Qp0Ft@y8m_cpP7b>4@n^d&PtesX`^$)SOO~m%!LN^aU`b!M&nMj;jV2|5FVi<8O{a6$be<p5{9K{yLbVEh*JX^MWLpX'
    'xoaQQ6H=LSLJ>3zLc)mvqor0p<+CzbdTF?IQJ&_asq5c2qd}>gy2)F*9I#7cbTJaD351%cO{~Q6k`Ah+NRc%bclPQ%z^~b*$Fc?z'
    '*p%llQCTbh7iNes)C^}}IH~wFAQ|r_@R=eP;oS`!Whqy>FKC7<MMC^YKVp_Gu~;TaUadGtGGGPsy|IaFL&V#V%c^01EHf=yg+`va'
    'X<>mZqmux>kd+J)VTRRT<=YmjhsHuE%W&SUBrTM0W4~PEfCh4A)-+q%uNr%E<37I6XRR_Chmy-gqTFhlbt_XGuXK`}0xk~CUZ`i9'
    '#o4;Gn>n}ENiPD_ppAw`74A~VeHfhMPe;oPe|n4$qsZ`N*_x{C986Xct6TS>84J55!{VYUP64ImJ!-^YG>!bmEWp{Y7>p{#&EwJp'
    '55+d^2YWeZ*z9OmA%ue(m8ohdEM!E_tD*9O`hYMH{vm7#z9dTX(cHF`8X`AFf<dzgv7N_~j%$u8G{{FB1`1<yqlR3A?yU`70Oc5L'
    'l^PQ8r=W1tjDXBcLQg%XP)P@bi;gBXj2~*RKCF!zKWhgzRrrfXzYb9h*bcHUx)GWbSWTnC>vdjXcoV<{T&&zmoo^Ml1H)R7g+dIa'
    'Rf2$fR&FczT}1SpojCN}+FUz7Z681LExcYX)Mp5q1ziDBdcMM5-AyJC0OcV-Ge|T?5u+L0Kwm+;-L+ZPqcFFf97&b@Zt{WSx-E(-'
    '2$D2>>Gy(ek9d25#Sq0>(m<kEt9m5z*R@+Aio-8(yVn;!lcg5i?{i_C8gM>M9nvf~KyWzWOmi?WiGp;|!1176*@d|Fp)e|T_uf_V'
    'Q#%R9T`vbzz(F28g$J!Ayxp)K2X3ZYE1Gy4)>a@t^ca>Gvc{9S(NH%j=`~pdKU5lO2yS4}_9*FTZ4uY8y7X(0EIjUY1a8QcBs`6w'
    '@X_p!4&I!mm~rPLAM7=!K8Tgl-@cC`cZ)F@{2!*R<D~=`+=_deWv9X*F=`P}6Jc+yzDKl$Rl<c%cFO?Z_$(XE6Tljlrz2)20$QJF'
    'i$Lt6I=W#WD})Rz0wROymvAu)r5xTdqk<YD=cHI-7ZaW)+^~yENdYY&+PdVyi2djUF!PrGMVUIQWJUYWkRU8LR#$0frQPPDyepMx'
    'P?2Ud^wg-Jc7)T&%qvllVSCdlK$&Rz1dnj-9@cT8DTJ{;AzE-UxmjVLp?GYZsJeqD1Hr`R<5>M5hz^UX&!tmY9(IT^9R%n;$|spj'
    '7_o)GY>H`SBq+OavS?d<K-LU=59$a(IFzLk!GWd&a592H2-FnH8vJW}w>tg3?0_?>5Lz{Rntm-BG1%dB3ZZ!r%`wqppaz09xs64t'
    'Hk1hMZ5w&nFCm?qZ5zH6%pU+SV7KZkm3oagK!FO<4Y`V<Nu%GhxG2+Y8(HWAH7}+isl<LEk%?nuq!DZ$X~3i}Q`DFQ>aO93Yoo<Z'
    '>kC^HaRL@Uw#0>|6ki7ujiE0<9^~#~1N5`80by!{k$hHcJHPs<T-uxK`pSr);Av2-2GCV?QpI?O{LH=vO$dc}NJeCa+xD`y!;D`c'
    'kh2lzufYuf<r{4f)M81_6rAZn_S)^}Z`;k8(o(e%s9A7>xYVFzgK5|W1YX9Qjk2?*H)TXiU;T;}?dK&wuhf8oE>I|HNT{Y9L-_PV'
    'FG?Z=ZpY1w6&6ot@M}}Smu=X8-$^;F%CeC(jCI6wMN@{%nFnM<zwM+Lz*3d*YVMX@oZri1+T&zX;%G8Y82Sl5Bh0_Rz6e5<1YPi6'
    'MDr&9kf5zR>*3vPT*3(^8k(rE-IXvG#@leW(vTt*3KA`F-|*owfd@4ZEDbajwDHVMkL2wvui&WAtH3$~IYVwVFN}Cf@nnsxhD=T^'
    'RPYAue0AQwZ083qYc)g)^^9VYqM96trWtL#z<tP!2QFVEknAtW{pY6bycvsAVn0@?mnd-YYeRAnFoVyiq)>Q31tnJpc0t4hVO^f='
    'w`}G@w5@$EMuSOQgO4481lpNg$3Q?)x<ra#J{q~}HhJx({MY>>=6)Schoc|$EPIiQA5aWh5DjWX0xjnXC~g3`5S-TLjl3P77A#wJ'
    '9@CkN#e}XN03paISmNNu6EFuue*_~M?lBe)u&<bIGuibUiCB7me;B-~$L%8cFOqOLF};QcOwxiwW8|&DTSZ0+C_!&9NC-9#Yd6Gy'
    'IewaJx?lhgB$5!})rW*Tqm40>mB#^bH)yCOzBI&}wHvAD?`kr&qwgyQJYf#wTxe)$?iR-)c#k~^Hll#FQ4XB$V)h;ws_ro7FYH2L'
    '1g4_^b@UeK9{_3Oc46U`qKZ`TN5Z{w7grdzKb4u>G_!8mUVuK$j!`wnOl!WA<22elnX2Tq2SxQQ$3p`lO9K*+ZpWV9JBl88fNEd`'
    'w)2|4hVvyU38TCr$W3bzkPF#$b5Wqmgr`v2z@6q>oMcl4LTSYVgtKBa9~%q+FJrZe*T&I{nEq`yMS>1J1Ot7nx1#-tkHMXSZvh#K'
    'L*z`O5MUcTy<5KxjBF*dCO<saS=YlB`ZCCK8tDiFRTk+mXa>!Z=gh)h0-xj14r>qRnGXDt3ZcO>4V`YEyr~+-ToE^+<l@3aVkGl#'
    'SitJbMtjrhb!6m8fGLAoTk;MW8sc0r5)0^=gHF-~Wq%VX{Mz@hxQCscLTaFFk#jO1A_hFzzc4zEjD6OosP$S6--HD&+D2&?>mrhu'
    '6E6b|5^vaPyfNZj#Ecfs4AlW7HcDIgDy3DwTUdO*q%LEA3X_MNNbhLtac^>TmFQ*Bk~Z*Dq|8DCA9Q#7>eVaE+Bn=Wf*^8^%sU3!'
    '(~C#R!qbPFJ>X{1Q{ty0JLfOYj{4}wc*_B*LxZC|Nz%yiBJ=NQbVDq~7N!*~dQ3&P-AkDH=-&Ow!hu11z%~*74dYi@Zdi0!L4(?9'
    'DkCRFAWrvrnCe!n4s5s)Vn|I>j6MvOLtHknfe>NI#DmK|$VrT_Tl}HR8LrC#J6P3BN|~%>6zvS(7+KCT41@0%@)<MQ<fS%Ot*Dq)'
    'N9adq4zG+`#Dk@iZIbj2tb|XiCN;rkXlcLnMNRMz%hp5+=CCB$E)JTfLw$l(FSAPZS%UzfJcm&O>QQuj{9#o%$?8L2hn*0qFgKP{'
    'Y2@t4>@+?n<VVDaM&ns<IAVlOv1a{Y)yf+JX^62{`#9NEQUAcs?}396xZ`%tqyf+jCY=;<;lC|hF-i%pE-o(^x`s&uPY2jTP%<1y'
    'K~JGP@dhZs01!S}`do`Y{FtymoJwQg$&1N?G$|9m2#}*zqp`uUg02DVu!++>UF8pNL~6>sKRl~vh&sbPefy7s3<#Kjaqbjy4UwO2'
    'rRK{sa2l$EQP5Zn*oKcCWq(}n!kQEUQu5Nryi;Ni?DQwVY^?8y3go_|AtcFI{Hos0n4_&&_Ja49*H%Z8@rX%B2RR?@7rE#6j7Y{P'
    'EGMvLcEN|WcI`KCyJ8FA9Pq@U;ZX(A_mWd711)7*fG#>oACWXL`opi9s^_FVJWw8Hro;Z@_v3zd<rjm0!pDVaq!}UT>NKn#^OYpp'
    '8Ne5Ez6?+F!yJcIeutFtu(UZr+1~$*f4qB|EKw8eD&|T7DcR*tU;qYl<Dgg}I_m_He$2_&IL^zE>*IrFVE*Iu=jqz0pLPZ@qs1F}'
    'f`}0)xk;x7c?x3Fg}jHz(SEEbBLqIY{mAzP89)9wx(@80J_M~>CP-2}QB{M<P+!9|$EztwRP^zzDy=3ywf^p5!P*O5DJ0vFJaB!c'
    'UZ7LSC_-p^R1UNWd${gk44AclST`NXs~+HUsJCz_T=|pD<xe)>y#ubNFTLgnLutW<5=#%Jq``4u6e78cxDG%t@NxKOA8q3M?>(q5'
    'dngA&kS!{L3E<pFXG5|Ar5OFZWwr!0yOSprbMD^zg4A;T<lPs()9?SW5Oihi&J0&70IDH}782$B2%`xzia_Ky(!<WSVy*Lx%hUhf'
    '|F874#Do9oPM-@HEZ++Jd=hR7Az`szr!u-_E}Z~!-uC!@L3&=DCQ11GaA9Yl3EaPwRggFV!V^K*s-Vz9NC+B2g>5tOo}n1%0TH0S'
    'Oa6Rs&C6d4<v;W6ustNsWw9Qdns`*+@YSKc#({E=bhWXCCC^#@r-eaR7=q34QaE#5aINfy&=@+B7N}xqm1Hv_R{HcV;o_b3B1!P|'
    '54KxQ2bCh0Y0%SX-($^(lp47uQ%teXZ$$lgmy-6*dXKM+Gb}I^yV<EL3f{<d$-~2C64n{rKO`1-O%NO4&dzn~;Zt@h&HfxTu?Pto'
    'KZptAaF%(#nwFv0>Af6eHJ3GfcqGI2;p{hX{PcO7@fZiUJC9F$*%zV#hHNN9u{XrM6|pc~Y1y(7lECD_6k#e8lt3#gmeyKjP6QL?'
    '8O?@&wro0a%)sanPzHr8&8yBy!GvdN|E_-OZwnq4Ai3mEjhzpEC<DAs6n%IaBZ`HFizXG1Rth&*u?^CeCRMEX`ch=(QyO*<&;dPX'
    'QC(=u5!bC+`)q<P1MXl{Qj_~=wV32{4ZZmr2`;DqDATOsnY1$DLIy$V!)Q`~l>vbY_X<?+UW#voxV%}jYE`BeYzsA$mpM8e36z^G'
    '$*n;N-pS2EBa+~CFwm_xO<J{V@d67{)6=(tRGq|K!N<T!1B0SpVi+;wG(5wsS@c|sU%yRI8wvK8sV*}bIIwV7s2D-g(EpOEz+0uy'
    '*?hDtyrGBXcs%^`6__J$&vTM1UM}f8G)zph0eWRgB7;)+8mL{U7$sMg&LMpKls{Uzh9-h=0dpB50&y1SJGdeEuaE}Hu0)C#+>bGl'
    'YFGd2&!xabKXMR%ALc88NP0686+nIJxJIdwOn4~RrnL*#jE@DtpO{UJ&kYqR96oq+$hsx?VJK(^MTqk~gpYso@%Wk^Ai$8lEG~*K'
    'Cs&dy^bnr;g1A%3m>_Aj67utD^T0{Wdd$cgSrE@vYnJag+6B<5tsC)2;8!^fz!Azp&C1mZq|<T%kqcKXS98Syxsuc~NQI&28CP54'
    '6=w<k1AP;a08gGjV(v3lE_f<so>2REjacoY#*w)`BT0Fd7@z4B^EBxr3XB~-TJM4}oOA4ooQS=1t8l?^hiAEg<1qrrL77kdr;7_e'
    'gi6C!E%(CpO)*%QaRApL0zx*LGseVR8BH|&J>#43<5u`J@~@q$R(wyS|5Kc2+{(l+fQHSKK0thk_(m|G6_*l^XxNQl%D!r`^F*Ek'
    '2@0vyteMGpFO%2;HF_|7YFn5SXvz@c!ciMOJPnt){`S|J@p>Xnqp=W{I*T*QB~FI|2Lw=7iZbE7?8QwVFG>EhRXlxIK9}R0heyG&'
    '#Y}2#^X6zv@R{%s`QiKz{D^29`M2=tj;mKKPo<z8<TM$YQ9n%D5u@J9RughPLcUIC13y)STkDsmsUP?GI)@#_sOCP);EE2R=C5I8'
    'Pr-s&E*4{qKmu!)s=9u4WP*PjMLB$VEpR{y=0sYEeONqOY^NesA+Hw}2niYuAw(cd4zFLiB0U>0OBGH}HArWKRzX(nDMbNJ*NVYx'
    'A$)wJyt5|j{PU?G*`}_5&H|$1WN8ghgb52N3P_-pb1X$Fs;_zNq8HhCVSW-U2+(B28mg8^7`*yHDDp&p!pW37hGb@5vA8mZ%4uG7'
    'f<(<Q6ySWy0Tq#a>JV+<%fs;|4r5x^u6e~^k93Ak?kw#3vyi%wtN?q0HG1asG8+O6f_or|WDBH(CDb4Ti(J3_?&Vo49~og<7%7ME'
    'j%zeQO+-9qW{HL7<yOeO01b{d1K<N^tbXmwZFH8_6#!sVAow3SX6=wuFz(W{aLgfkjT&_`bpSAv#8mZ*>(4je6ZUP1JKGBj;K@US'
    ';dqOL*<;UuL1e3f4;wV(b*4}C>&qrGKM`2og4@Hw()@G@ac_V6=`7CubV(Ps7qRNLuFb}rJ-YJ=au+nGR_Q$`E2E}(if|WTGa{Pc'
    '!W;klxBXYcxpM0RXfqmD&^$O6@Q=KpL~?XaAADupIw+aA#JY;DpUo&g2&O-|xsx%{&ov<4dc9a7F?a-R2a<E?do_283uLPK#HBJq'
    'r@3?-D(bK#!)wkD6(*PkBQhPW7Ka**Fv>Z@Pq*cm)x@-Fu#J8NcTvMMTM{pMPE$^3DjJ!XZ2NG4PI8+4@JMMCW?~M)^?->zE^0q3'
    '$u<)=01PA;f}lFWQGw7FMCGM*^kId0b`yH=B8Ip_&F{i8luje;H8%moQsj_Zsy8-j&@u&|$oO<nKFrULhey9D{j5Q=%EkI%LJa2g'
    'L;(_X5K+t;XwUJ5GAITK(1!<0f~$u!xSsH+{S>!(nPGU^7CM|Hu5_6&BSYgOqeo<u^5??UR1g9)R!Q)Hq1)Pp%gJ1iKv*`GwEe7n'
    'q`6-)mrk${*oY>L17rG+G17ls@TZ#jdL0rp{h4w+&Ul8y{Xou<Gyy3{mN#k^5ua)pYF949KbHO_wGR#tcma{C(_p~YAdHf3d;KYF'
    'kKTXyY?rm(EN4EsrFl{?3+2C++KM@8;?lR0WUzxIbeO1vTph&*{!1T!tUoVFY<=r4UWeHc#Y2?Bz!}f235}M9Fk-cV1&yd5)J1B-'
    'jdhEDS0G<Ml}I`p4HF0Np3r&HFqd~ESU+Gm9%Rx~;`8L{)~tY9g#U8xF$5P2U6qHvR0u@4S&=GB<zYo6ty@qC^s}N}K_-yrVHqaC'
    'C#wmkqXs;+GEEejmj*RC`ukk?_tso^#5IjKdV`cXd_0)Ap+%S_s;3Rb*8|YQorU)-Jf?SPs#n%6AX#V(G)7710tGuo9gZXum>L=p'
    ')HI~#Gj;s1Zb>-G+w1wabe81W)Y5vIvp6omrX;;&Wm3boniXl&%4OfOnu1js2G!6k_}R(^-~mG{VICa=QzdsJci=EPTltiWzzDK$'
    'YAfuoI`uN7rUb*wvbF8urfV!26g1<jS1S^R<XOTuG>h5F;AV;`=GtUw7m(>=2n5BF$~_OOR(x-O&d-oL1(W9GFx`(w+rjB;#NA}b'
    'CliaI+66u3k0JM;7d?`G`u+7$kwA9L?wdp}(+9k?5#Uyf+6*O3_Y5hKoAas_H$~JLa|ca3Ru_R%ZIWLKNU&bvqzP!`4V;{Lw(FOz'
    'VylYjz|;+d$+!kVt`~QaX*$wz)8>S12XaZ=nAR=7Xf6sYH0li?K7d5L9@V23-i_fW6&t}yref+`59`)FD;f&^4lPy^BrR~kEGE6Y'
    'SIZ0`ZgeQy1PenYOGBsj!&=f%IGh(f()Db<=@-j!r`!;*kKl-G0#XfSBEF-H05dvSm9M%O{WSms!EaO?<a1)q2f_gc*D(46*qxMj'
    'T(pFL`=I~pfBYY%miyf'
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
