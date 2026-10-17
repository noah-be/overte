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
# a558db9e96519a9f8ed1d2b9c7b74d117e37836b / tree 61063bbfa36dcb8380fe76223caa5241e9030f75.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '90cec3d6aab8f3ce723f53d65295389f1d4d1265c90227833da296e3ea020685'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*c%V+o#ac(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNfHN~@k`w<ZFaksj{mX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xTC+TZ@|x8rBW-?n3Hl4*t<<J>j<Y+`b59@?CnG1}l$vST|L{eL)pd(nS^'
    'f7<)s{_EeqFY8$-e13S@KW)Re!fM`k(U>6(^Vmd}!ZeH{Yc$Q+<Zke>$>U&MGkv_;iwj@eV|w^wfB2H0_J2G)CVs6uZTGulVeuT|'
    '&<<{H+pf(%4nv%yZDZfrdA75gyD)|1eEad@hxD>PZcqEew}<dKg)gNQ`@qA?!GzIFdcY~AIrla<HqQLed2(HAlfUwCPw9AiIKFOA'
    '=^>_<w2NsMwyCu4I5(ZQt?AOx^y6Sy#<YHNxpgy-+ndhjaU9y3bxUhCrtkf1$H|Nw8*j&9&Qm|NQ<&P>^x2K3o89O>UhC~u9(lQk'
    'v^zcg^VL0V^ENDR^&j7!pFUoFh;8g_o2(x?p6}2MO>28&`Z1br>aCA`8)F))RzK{2PvP{S-+sKl>@>HHn@t+$Fr~H+oeho4F-13+'
    'CXU7pZO^iE&9Z+#R9BZC^T>D8Wgh!vk`FVddhXiBI2TNuLLA39TbuvBv_G&Mks&;7dCH%{_S5fa_hq{~etL9z&oAFTUey>EtPg<~'
    'Z0+b<JH;WiX6#e!Cmwk2lNraRU9;*7znm9-eO(S}m#j<U)cGciZJe4sdC!CPxg7~oQ<G8%>(<@->#Js$$A*_Wn#}KOo7pvOH}Xk^'
    'IZZZ<*#*~6omsQ$;dOU)&0y?6NXl;Zb{hG41f-#vC*!;1Q){Dd#+37_HFc6V;qzhtoHoa>f4Tmv`COWYC+kc%44mtbX4iLaZ2ETM'
    '+v)@Hax&|l^|FJVdrn6JciJ41d)e+DuWlnwoZc{`ey~K%WNhlp+*<2`=kqqbwS%!HtbY)@m*-8`@ACHg`lB;xn7V!#CgTio%nW>9'
    'y&v4fH{CXDZe)+$>h*Om$IYK#v%k8&=bSax#=al9B>ILY(Yv_`EjJ`5vg0W<sq=32`kX+n%ByRqkh{qdGJ8I}ZuDUchTDSJ*4yA('
    'GZAcursB6NqWs~$ecGjyBHiY&e?6s5+`7lz{&?Dk>(Qp;mU2_FrVo9xy#9Gg$#Hcy{Xo<U(YMa@W?sFG*Z6XE;dbJ-Os3_=;De8|'
    'o<2Jng2}PvL&%<!n8vYs;q$?}tiB{>I)bP4=jnO?>iO8m<l3(9rjBczP4#mceINN6=M+rim8BK;@#M%0Py6R>cp&V3-5$A7`2at;'
    '*SI}xE;pWT*{fe<-zR5d>&OPXOf-y9DU+QP6V1@;W$<Lin|HH(mHIfI+$*`{^(ZwCUEtOqX3P5+qVvSfnOr01ICf1oCN(5m&F!0c'
    'C7rw;DPwSE3hglErsuc2KC~lO1D^@$UO(mDMccK>+`NY`>99*ro8>KC-N{T^Hx6+exc7ZGX4@#WZHHdjSRT?mj-1~%-@KD&w<Fz-'
    '8*+S(^5NU&^Y*A*<?5~)U0g%9lW$TWjEt%0GUFB{S1?Mxo6+)=Zr|13^DliZ1hXM@IhxRWqNVliIC6Sj*F^ICE^&g0V}t(b?Ynrn'
    'R37eW`Kk{toURA9DcY$WZ97q5O_U-{-*;n(6Zs;?y0y(5Q#<+j<}Hy^<)`iA=Tmj89mXz`Q8mu?o~tGCof~rbiTI-j6uX9+Esy?='
    'EtS$O9zfrOsTrw2yMb!6Rn|q8#Uq({d(G5MQ`g3uw?Ntv33l7BeAt`skLY?9z*%v=nKShp&!C&eiMa0vf^YW55N87Mr@8&H98Y{#'
    '*AL6g(HOO~pSvjpE}=YgZUYZ$q?{bbzMK0yzM_*mJf`YfAd~PmE=01AJa9%5AGWb$&mkH0ga-11xk<ObrE|9Wb`|*j>n^%Npy8NM'
    'fi<M(yq3mL1Pzh@(+`2_*AKRFhC0EfU$m!+>#0lG%>C@C$!wSA*oVgF7>wa0PmyD+h!b*i=Z=;;YEu;kLr?zR8ZJyO#;FC~iOEl#'
    'Y^ogBbsgn<Ce6C@y`|mP?P0%r=3hL&y6a_KE1YM}sq4J=eHgeRyc@uphU6yS^31r=V|U-4s&CQB+0k`W731L31V$4r)h!7a<)tV0'
    '9r)nck^Obs*=$JyAJ4Z(Artg|;y}f*4Gn?V^RoOrgn8n!=(y8-$}QWyZ)-Q*@_q!+A|d9C=Xp$IAwhK_*oX<_A~xI3#X0<<t%d#b'
    'f|HaU*pOZ7W)gWj8v>=?=S0#>_-405G(L0BPF?&pyE>+?X;-MKDOu;x>jhFo5&#;W*VGuUkG4w_XlO?uclYh5DiV+$+PM?N5L2GR'
    'JUDJ#*9?680YKIayih}#d*@bu$cmn~HD`RzP3HtKbO{g-=q`*vipGOzC3e@fE}7_TzHeXaQzPD+BWDB$>3t`dD+4ZCGqjc?K6F#d'
    '4sDbDz560R+Jr*_+dXaF)3JaKP;yz@a?wt+CvD4_hozjrc#>Vy1yAY}=eze*lM-}X{u~_s2eil;!#7V>4Wtip(@g^fs&Qj%+xs?i'
    'L-s}v>9ZNkFz|&@HoG3wG>v_>CON~E({c}*Hr%(d<Noyks1^2~6S#G_p3SjdY$%ExPev$PirqW_#Lp@La+o6zEdVjyxg}+ln~D+^'
    'go%6&u&*6^DzoglXIfB~*tLBE_ar<`&AWY{_1npA`}A4>dMB&qOX^)?dlzV!jO4bCoF%k8rqFfMOasN-d9F{-FM0cvzE^A4KmU<S'
    'f9M?58E_C0a{!j%v3T;`MvyF>owgtDJl&_m>+!@*@+Eycl%P?*dGbrXZ|jrcOwYWdFawk}-f*bWlx>{SJr%)<%_z%mIx~Waw)2#E'
    'd$}csTk9LXu;6Xi&uX((ZRP?}U;fGU+ah+LfgB6a(Xr>gprCKaWP9U#5?L_Xp5D_`mtjA?F5xa6p0~&2(nGwOjQM${AE8D^o|2DX'
    '8Y5}6Z@hJ*O%qL^NX)7G$)ERn`}=(<;Ol~>o|xP`+F)boTS6Q4`NRz#8xw)!_)O~7Jf|(!L#LTT%ZJy|{)oz=0KSs}-~u+u+&T2s'
    '*h8$#pLSgSU(?3L=k4{Igw6)Z2l3DNb{Ob>fJ($1=&^PD-wuGwQZQ5&1eaB7z{IBE5~nOvfi#8`1`2!27Y_;|_$W}W5eDkc(vM$K'
    'b&e4_lUh%aPkpGWl@3s}wD!m~_}H5^`WX<uvR?eL-&6A`jgi{Ib}@FK{QYQE;HR1Fx#LsjSW`<=o5gX(;^)FN><?-4JJ;hbU9TY&'
    'S_x+KIqVRr{)Q2hd2Up>&orY3>QonUB}Vt-4xaa4(^8Cb1r@GB11>qXZEpP3Il;K3H6)$78^Oh9s`in_!|dw!ur8{Ez!PseKI?|o'
    'S4X3(_a=8VbotT}7f^yK5N2P$er0GeF;hE23*hj9ql^<@oDes)&iN4SM0h9f?&=pl$Crv{P7TC+r<vPweYK_$JHc5`ADzYv2mqBE'
    '#EhX?yYycr?Dac@Ms`Em<49eFg^Vqk{ltR@&~JF%2AqV1EZ@HTrP~)?Uavm~zB>a`f<NW0LkpqK;3gYDiMi+KCrl%amidN_)UDs;'
    'o+hUu>!aC8@<o=K`5rnbGSlQh7oc>+X8jQ$VPCi$d<yPx9SiahQevwvE4NA@<n=v!3eYMzgo)rdk!i%}Z{9-PlNfpatk=-=c90Dq'
    'Z#dWnJbXueoVeLZu6pu}8@BQ7^m)Il12lE`DG~s6riF$DMJV+UKByDYM30H;nCE40co>KD2&O}!5;uPw+{;TT%L=}s{LLH+LV++a'
    'E=S)xdcsuXFvd79;5#=Q41lHUP1s?eP8(Q^bS_%87J&vc-L}>%M1t~?_NB_=?Lt7PO$g@E&8`!<B-4yYvEfFtpj(#YAoiXvqbM+W'
    '#eH;BRzQEDr|CWL{Q1cqRvg{V-~<Iab^>=UgrTdbhR(nIVY_>IJ$>S>KV4W=4`lcce<TubU^ObDtGl6Brz(}VzMQ{6W>2XIv?f3V'
    'xI6P$+P)%7`e`?;{*a=GPd{!<rN_pd^ytdKk)ui^O``@8>C15{0$(p>$!MuP=o2TM+6r*=qm7kFJDD#)`4f+&71qEN8sn6yK1N!f'
    'y$_iHHdRn&mdpB$+<1LSQZ>$|vQwJ9L<DufJ+;`FCJ$WQJ9r|a%au#ML1T)Q8{UIEJns*iSN^?1*3!3p2;7l$T)@M^5LEsFwa(LM'
    'Ook?AC`Jk6wfi_%o(~tU#HZsS{J$oTlsEQ&jZX6MR?eIf6<ABAS->+%Z>K5JeK7{^sU_ud19%2NIo~hO#tm@nraQLt1|Tfkx}Nn~'
    'KekW_Lm;LSQu%(VIV}8%OghXyNIo-!qZ>D~kT}n$8#1XoRv(`@@V$}-rWPowP29!-mI-f-+S|pRKO##UD(F|mefihzQ#|88wSX&;'
    'ZGs3S8n0>SQ8keuFpi@T5HK>@EuHw8=KjrHFuNZfTY-ndXQ$^yNC@yXLFyWHgK09r$QfEO9!#3;{TtiT20FaG)C=kSI<i2Ys)ao_'
    '(JeRda-vbUqoZNm!l#2@2;tmJ^Do%hjyvm#riVMw>bri*5)s;iMbot=)dM>xdeY_xQu0t^sCj7{PrdK&-_<$kAx8Yrp}l^odI!mC'
    '1YG3ZH3X{22N`FM8Yd36EvNvf|K#uA+M3uE$ul_n9DMlm#P4>Z=?}q4p_B%)x*pVP?iYNPmvnvmyi~HU{^hef7TD2{CI`Yi+Y8jO'
    'LKDc49Dp$d07_gg9FeyDFF0f8tFQ{b9_e!uCBSw<3xGII3uKz1j5k9YL{e*ca80^@Q^)P&!j9M?1)=h-_$YgTMJ_{%J^*bCh&yFJ'
    'O?(Wrt^$cJ4-9-Y{Wt7w$#g2(?o*0pR(lQd>&)4s8m1yjV4*!FB5b4-L7#uYNAM;DxW1iC{}>i1kSwVU(9i@dgqVf8VD60oY5Jwy'
    '2sdu$Z4aN;U6u6vS(M&i7ro%BiJJ+IGDHceTOQN`)YgnQzs2vnS}w{0>qgKO<ZSLkN1U>JiX`6PSm3(8?Icuy*nIc%xrF%ZkWSaO'
    '6iZw=T*y!%Kv?0k5aWRmi0aVFXV6aD-@BKJ&#Z+}BT^rfj1iO(-Y%VXPd<#g0dzAsvQhfk<K0`i)DJ&@Y=sEWs9ee;ofGGQ*t-tF'
    '8KnQrzt!==)KLKdzjtdZwge~$;6qe|uZ5n6mMCQw`JZVWoGG+6qu}x8N;Mg`2MLHSJ4<bPYeg)8tP7_y7M$tk<R;J!rL>*GtbA&2'
    'Kp=(=OdOn?vc`?wnmv??SgJINkap@v$^!}l6nUMv%(RsvQVa^p(ey+8@2+e#(eG_gGuTWo9=cG6=wzmbhipO027%hpg)sAbhm-5i'
    '?Q#jVNNC<f;&LjA>HUKy^1~1<1xPQR(=X9uc#pvu_kmiREYm%G+CbI+L87(MKP&X>Se66a!SvOAmOS`XkD`RrWrxm-Dc+4PU0+s|'
    '!|RyL95b|Y`T|oT5kgf7gO-ZhOS{6E=?HlAvbyWboD-hqKNotvbLV@(EIuPBY@rOIg&HZ^I=WPf{t3}ceCJ0A{z^Nc;-B2%v_&~Z'
    'qP#F&P6ZA**?EL{2O7*(f*hwYfnHIsv{<ytHq$PmU3PWJ<)o09^Y=wMn^7%5Lm$F#fFsqwXN?Vz+mI;Sr_j%XV!(TM?B5nV6GN__'
    '6DMS^?;2QY0KOw_#sLBpCmyvVpTW5<4u#)$^!w+{S8nZCPHBKKk%gL`PaALqj34S3SPcSAh@ibEGmJjY?=`Q_*-A`bw|a}zcP}Tc'
    'UX$oG5+^_-5n#y&pS0M7s*5t8OVY!CZ_wZluC!=$FDGedmI(8=6?uApJy)Ju!)t^aHG$%KN0*8IHCO^+bQ~p-gt|4Rx)qP#Rn;#P'
    '1>gVpdSGkSQ4P(+(WR$>Xb18N5V~OpBMjh%#!BadyKx6EFWcAWP0dDv*xGcH(zvv7yMzuHacZyROtBtXFcb#YuiQx0Lx3+c&|dSz'
    'TPva{lH}Avjv)VV?cl@YP&*(sT)TGIKXJe8&nf(c_E<jqNQ8wlp=O&spEfs4OY;JFT}(a%DfE~pvi!JqHw$3Ac}z6iOD#u;UQmoB'
    'lMW&jTjgUg8tjyYjC>j-84Ql9ta=N}IjDLUPzsPHcbR}Ds#$L#TV*Mw)&2)F;yr+Awbk$9|BrV-=i<4rBqZC3v;szAgS?jC85ICW'
    'LM`ods^SrL0j<}rcFCBIU+7+K_Tlwu`)Ad&2UgY6^sRtS22vhqJe1;ePG$?e94-?CCbE+oxA6G#y7>%0@+ln)uqHjlNb%SkRNJt!'
    'M`Jq@6Cj;Vy|osO9d9EwzhEDbqPgCox)*pxv}lM55Xaz<4mqps7gaKei(rwHqps;X^J_M=08AClXo2CqbQ@jBZHRP!QA_lwkdZ1R'
    'y}~5kRX5zYD=zK>%!uRm3xE6ecUKcHsvxK-vn2<bNlgHmMmn-6GUG(ID@qnk3!%MnKW7BOeS0FHsYXiMkFMCCA=L)rFWFI(hrU;L'
    'zK24Ru<@|U-$z>ZSWon~epajZgSQ2NBcL5=r<qy;77Z#1o>`;@C!_|F@9te!k@xrWyboWhK5jRuheJ_4c4mO91Am7rO+tQYqOw>E'
    'Wd1qSE_|sL{dN~i>`N+DDZ>b6!Jtd$j6wp1u!O}4*qI@?B0>#A_4oX;4SV}3Z~r_A^<Tix>v2t*9TGb72zrkyi$xb8ofPT;a!d_E'
    ')-g`&*8ht#Reh~craRG1X&%8EQ=gi8*>+Hg;1bar9mVbgC|kFYgRE8#^_xJ(L@7jDQS1O9I&5TMRP!fDVi3ug2>~j=OYJ83ZxvBv'
    '#T{>zQbnnd0l{Vug@{X)^po?6tRg441i?{~-nfHvzEk}?r0Af^70iVQm?EA&IK&ZhVtjrO!*v!?%VewX`mcNbcC%O-sah>WC(^2h'
    '?p;R&@S?CaO8HroumqhH1&&yS<+Xj~f-@gKhYq^dfVK|;3D_ENXm62a`H;XuxiC=NlomuV^X)%UmGp|9J1B!bc&;m6be^SgYQY=^'
    'Zg?_11A0yWp|s>8MSH8u3p(Lh3W}K?u}Sp%ZIfV3;Rzr!r-=qGe+e*@N&%-%Cr#%G+{pmA!>wr5v8MV)1Vq*nz~B3`c01VG#g<>X'
    'zqEt(A2;WJgUsNmqU|csl%pG|*s;MFA-+KB=qT5D_;8arY%PS3*xa(6?M{tfI2ZmkW7oBLdG&8xnCp8Y<a7A~;(|^9-vz*)Nat>v'
    'MpQTGD}nJm-2A)tBy}5lsr1CPRAR1SS|TmN0K5Qn2P_q!bK?_)`W~33>&0Gk?^z<P*v}8`8`6WEPTS|}*A#ak40iM*l)b2fbz30;'
    '<m;g0%LgQl8ToH?x9sYPr$e_ll|nObp;41Q80tHWe0Wd>mJme<tvCtp04%^m%q@F(UfO}QBuaZ|!LdMJKzIO{NFTxTxUe}h{jB{E'
    'i=qAcc*`DS@53GrvEo@IZl+F(CtS}sDZuTpW8j=%iGY+L4#*h*B*J*hK4^`q8h?4E2VZqKsJUk<VUz}Z+E5H(Hj?t=?7@y`7fo5W'
    ')-d06I2N#GbH2CEU-tF)({MKr)PrQNu(!NGGN4>IOHcw}00y0!blcYhHordr09<zS&*!HCsg7g@c?kqW?h_1wsCO*>UsP$3mI(RW'
    'rWEb*7i>j;b{#XoVr3ZVSEq$jh941+g%|@d7UuYvX5rjZ9B$u>SeZx1VJV<DLNP(VjWj8ULcq3oQ^2?6Gh{Rqz9!I1Qo3a$NB8`K'
    'ChaJG@VT{LBJT4y;E7aNcpS_j`Ic-yQ}NJ3^F5?M7}Xq_bW`j<NtqriDgdjR1K4P!CywVFd~rh`0s}nCEf|3#RyY<6(BHC&^YI8z'
    '6k^x+0Dnv}kqCCgF+l()0sjc{3*<wy9B>`p-B|zGgwO8uCZlnu;<wW9xN)*fp!gH!LtHNWjaTujL>%@E078V?Q@#FolgEp76cFy`'
    '0zv>G0e~yf?-}7+sck^J67~X;7Hpb$9D-D)`XF{D!JcoIy_Z^&W~zv4?xm0<LH&fbP5Md8y$=(e8ayvZjnqITrc#r4DB!C%q8J{&'
    'g{O4M+d|+AQT}%Nytn~8rE*;+9Ws=Jp&@i}+0jn~1cfZ1+XoT{y+Duw<9^YeDvZ4#jo_n)2w%>IgjuBj0ocpxPvt@i-~+>O`Xw8R'
    'TU_@}1;%@eggwwpqtWYS^EHTQ6|jFzu!lHWu&%PoxL>lPL;B}yDdt0F*3lut;pc_PqmoJ-fnaxAwQnaRw+LhGc<+Xu_K(|L71lD)'
    'CgTcBx}dST<Ya?ZTe5$#WwEE^hP2|m+`A*tkE1jiyO6356X=Ez+@+65x0E+Fn}I@w9-@yV5fU(SE8YF1XgGdXO_%n>`{C_SlhAS+'
    'r<QQk((w`TvQdTyzc-Uoq<HV1j_Jfr^$51Rb1%ow`@*ge?OM2kAiMNC2RW+fEk<%pD~3fBK^%(qFWc4Y%hTRnhnllccnWx|L}Byd'
    '141bRF(*TOrV}ls9zv5H+I#nO+J8yA3vKp#vIT}KR&1bNaXr~M!b74FbR6VQbBEx))%N_&8;bEDH2#p1{*7IcBgnNy*@*fD$_r>7'
    'ywgc`c9@00X`Cz;yHLn)4wd`^H7YirPp6lvz(h!-Z`v-r3cMN!1{T&QgaqyvIF`6j4S2Vj;oc1$!(sbUbM@2J@&k6EAQ3(FB^p(d'
    'KR{T#LMgv-2a$?&%IzH+D$`8qkr+7;P*KK~%$Q1+>Kc0lBwF}Ja=9R)>ix|heB3`f;`DNT{N?q1Jzg8msY4k93s*VOf{`PvgnI-1'
    'm4peK2^l-xxuvJAq_!1k9c9X76RKuBxibnGP^<_tjFH;Z0zynu^AM5juh<V&P1=@>faG8o@p=zj5M&}q+hAYmL&HP{f?2DEAg$Bp'
    '&J9V<guh%>ght#4Qv!ld!#53POSuKS3Eu~zyxh|wB3ZDC?$#}x8Asp0u^$v?*I!*PmoiHlj|qVzjYbnXs&7w`gZG9<=0$bd{Hkr~'
    'uTU8)ELllOcx`gB!ovw>GOWcgf&}6VHt}{rCQ)*C(=XarF5BD4DLR2T5*?)_vT&7Uc2DLF5r<d_8abk+xpPChRV%ElF=kOX%CKHR'
    'LpjhB?TA^uILcJ$Igpan9x`|C=FD<D@X?)MKo*r1uv{S=l4@9#tmp)gUK#Pa5f|eyC+j2}E?}D8xvR_l@w%&gSafW`Wyx>3+a0{K'
    '9(B_MPeeEm5IhWh-~?<+Z{618{<IgToP_(bw?eiJkzIn<)S|w&VmU&ngh1gb0B9{TxS)qIdUNy^vLHULV9V>@n8$mAjGxd<qgB*O'
    '8mnAxd}<U;fXTEsX?*8fH}bTPi=EZkJnA~)W93ASRu2lvyl4QpG@#W{6Vdht+r|Dyk^7Fls2IAuq)Yg&x=Mf@j4*AASE!nRA)OGp'
    'mPQ1xO8#UcMH1D?eH&Xu)N%RJ!oJvwP=ZE!2w?(0+ZhUQ5V0J_9il>tIJH6-aOl=OU0{*F9#eTsgPEyd&FCbF10}(5A&a_8UzVdx'
    'jMSkvw-+F+irwDj{Z)b^mK0W|BZBQ{PT*{hQ}ZaQE%JMqX;6JdHorM7+3nRh5}JqpohMde{2J~vc>h6M#k2?&#3@KJEDXRkMsg;+'
    'aBi+Y_Dc?VE{EXEz80b)iW-a<Ad(sxlWFJ%6e$o0H6D|uGz7rMbn^`hw5VfE%}>a#Lu!DmoUD?i|0WXPjziO5e}G~y-~nYhWMj(r'
    '?C4?*u{nK~>)!S4U<TZ%Pr<Szi*iYuS)Z;SOjGr|V8@_nyg4<xlw{OFL`MjRWzvDPxqR!e@4>8Q5^fX>93AA|E!~5bY;vTjaq~U4'
    '+@!JY?r6E$X$xT1hGRbYE4d;dH7$9%*;s4Q`NHf3*~{&FS?+kG9kpLOqC`uM&%2>2v;pixqmZVa${MXF9Srgh=6wuz?&#}tg~5ls'
    'LqJ^^{M4ovoO&XMhN(SxY^61BC6ZXXaC08?byDK`RcKl%y=UYVAlfX*y3^PTmY!q}$(^O@8h>fZq}koElk}(f@@iOD+m5pM%w!=9'
    '9z49E2)RVnAwze#S@~BHDg?~#?%C9Kc{-`~G11+CXdqW)h&51K<bem{3X3=^gBUOn8M1WqeLLD$)MJeMQC24AE|W+i{8>XG-Jv3o'
    'Q4xG|Ma1!T$WuEx31iqF3Y0^uWWAHC!w7jB?@VNm#AoKErM6XNm?Z(cV;>hXU?}Mgq1nMK#-|JnAIl&td;`rN?Blv9QxraVl(atG'
    'vz71n6cMnH=L9Ndj444lKzWg|3=O6^_*N1KIVDu}+~$1ZzhX1x?jQh|)I#Xh`Km`DFtjUCtpfi5GNA8Ec!DH<$7UoiENG_)Ws<+h'
    'T@PEozLVKr&?GogW!Nz!U=9xgAMV-3Np77Rk+_Oj6y>m5qBN^Xr$|WI4_#xz9f+NXl0aruJom)j?>R(*6N1LSVD^N+23C8F)q;yY'
    '(=g<j@YZOmSWBiufaZ_#&1u$Ox#wnSY!-z4xL~741bT;D26oDe(%dK77L=TvWI!Le)8BGQ@?fNy082S@YzyKyT5q@yS`9_?@?wK&'
    '4F1FwsquYO!Z2mx3fSr82`ipAgM;Ni7kk@el1}Cnk-Q1$lGb1^Z!}LuHIvviYKUQBTu*s`PkNTX{@kB<15v6CTHtuoNP>9>nqo&-'
    'm%y2@n4rU9(Sk;|rP0u@fGa-O*HR)>?+O`w(96Oa823n|#B_GC^1vFlm606{=a~mM+M9QEX`a;Xhg2Ad(j!}-GobIB<{J_`IQj@H'
    'xuj@jFzCyeoA>i0i?Vi8Bz>>}jH)Ln%5)9nF(_%eK6<)gp!V3=tVp-s-IV@W{hpTAHyi-u-O$HLOaTtTyc&f@B<e)!M%41=);)!T'
    'JATF%a<@OZvi=)b3GU1+4F#4R;HQwtW&avshfyy;z@^}8SMcNhWj7bhqJB6KZ%l(qng7Q0KZOCZ&=!$6-Ya;SgJ@cct(#-O&#+VF'
    'rerG=VNW2agZHmVX;|Vn%u<5Zjg=^wGLmE$<9(Y_HC%1ihtEov&!&MS$1(<IOdq_Th9Y?s4ldnLH{80T??_7ZhA?(*eL#5HC*7+W'
    '<J2%9ja(23B1}U5Ia%_}?@bTK9qD$jh>z5}E!iQpa4$at2DFlX(Jv)W?J?-5R_9)sZ{5+Q{3M@xeblgk0u&F*1ecxJS8^}Gf(CMO'
    ')+pXijjw@f3yBp%$>HwpoZC73`s<C}n_M?JOyEvg*BrAZrJbbO0V)KuOK?$qx^rhsZ=iNhnl;!<;YDu_p#vEitraK>RHIgaIGN-$'
    'zB{gG)t-)@Ur$OH>+chwQv#BaT`SbC4wogGJ>0wyhfqOLY@qp|c&*;oWh2YcKE6fF@VXdDpWrQ!!fmf7C){2Mn1wosL1wItYbbOR'
    'gtzpa0bgvEcicSRv!lKLour8>m9Po7coz#s7&25s=ZYQ;bAGsQ@*5+RgNH?FU=bg4x2#E+-r3Vne^g8@nJCJenq*>+lMx0PAT2m8'
    ';dPBs&EodUQ-s1=zoUfhcY07Oo?P-@^ULdK6crE@$_7wDIv(<otdIaQHUWNnU4K}2ylc7g(Pl3F?#q+8{N1IVFXSREo=$Q-5rTkC'
    '0Ui<L-D29pO$T>@_XfN3?yZ#G4@XwMDYW2d0{Two)Y3__1HLP~j3!NiO)Fy1$$22k3&D8#&m#983(QuHkHBk@#Cec29yB}<u`EIW'
    '24Qf3Xe(=)(mlH<JqaQTa|q-%$I*n-n=~%1)u0j#A~Ab~nut$MQ=dkkkLGTx4;Vci=-ZR~wvet18Z(;MUIVx>l<P(5rD7hyoggPr'
    'LIb?_)b1<DQ0ILh<#UIN)!kV|QmT)UdqKcd6amo4a)bfXh5$u#AO0M4?}jN-dEGX!=H48fvcS!w{#xpz%k&mSO;oCkSrbADh-<kK'
    'Udzw``ZJ8FCi|Jz?}GpSSg>M~x5%iu0C08zE?|au!4$Ku8u+uwe(5y0VOY2L`4#9GRJ{jS72u4R&_P<n+5~S>+EK8;;W6T%E^RJD'
    '2<-}e+(l+3{miAND{FZm#UeDu3>)^VXIds9g0^@daiPxTPnq5cfw1@MHgSPH-wr~-fsR5u3Hg=LGowSYXn7Re_{xZG1t<-7z)UO8'
    'BYh{Fp6aB5M$=IutvD!mcxF+@LZI%{<i&f2cQm3#XJA-bw*v?zZkae)&ksOs3>lE?fiF^qiuB&O+YzY{CpBOKWB+$e=dNyJk))KR'
    'Al^uSfQtn}9jZda4+JKdEWLb%I!1ipeHnAV@-<vS^be1q%0dk<i$>beNt1OI9vRWL2+P1cplpgC4HwC;d?WO<JfTuwXkmFY;86Lo'
    '{!)bnNC(it%r82$L6jN<aF|};*0pZ=*Daae=~Ot3XxaF6c*g6#1O}sDWYB}+Tmgkeq~0LFu8XVJKK`*Sb*D8US0qr%0x4s$hY({|'
    'Q<<prFdG5-Hqt^@uPt}_Gp*@a)+L%-kbI5jl*MGJh50IU9fS~o+tQtJ;yeNjVYzKIL!oc)+({{QApB9hQ8vNAl?ORax|#?JWr(p+'
    'i}w~vvTXhOZD{oi*Q=6R!H}OBg%s*WO?U>f!TFB+LPiO)0PBP=gFLNxIg$iDh{yfyr&I!;yhQX`Am$<;4!=LXk4c--|B}%}O%j8u'
    'OCaT|f#-x$cd)nb>i7M2(N!!Ok4=7Zj|E$1wVr8_i#-&j6p&kzE_#DXnA}TtFbu(JZ{N{b7Yf^hGWW4GB?n8rtij5-{1LK1mhcqI'
    'QoxAxO;=4b85sLM-@YAKi+dErm$%34g?xb8P=Ipi=*cCo>!dTmM~v<smmPE1CXLIGinYg^q*SFO0qo1DCP(|~&%&4}yem2d&<=Uf'
    'h{p<V1TqI_26_%?QllBGZ3z}le^Mtdz4$5%LMgL_GcFxxED!ORCcrkMTe5AICBTAybk(c!SroDfzQX8((FCL@1!E@*d?Q{IcPU>f'
    'B{RPLrBeOUV)_@OF5Ei5lniaMsIf{Va6SYjfQs4TD-ju@iLd~61~aUoJ(<e&&uDYOAW+j)X>0+)%>W~Ex2K-L8!D<(!DB~am6}|+'
    ';zc3wrlzgwwJ{BWjDSlDoe5@vXwAAo*(16$b!|es^qY#g^xF>h2V@(de#NO{qXr8E*J)m|W^baNg!|qvLIqre7)Qkj++xP|ec3<G'
    '>EfO=sbp7<2OS+vMo%y)fX*vUbY5(GF$d@@CK5JA-okvXTpC9PzNEh%y_lN&>n|PWgGodvjr$IgLUc00Ln#8*3DX30ilREM+rT2^'
    'DGa-U>I63epBATqAOcdYT<4-Z3JvT4hN8Dk?IT|%E*FTX=ol%-G}sDEg&>9RriPAzudsz4Q3z9Ci=u|@UWlmz^`9?cb9&vCyw#+-'
    ';m!iBg;<V^D``k48fmtJZMjBFp$-Z~*{jxFkTpHs@;Es%{C<&0NEwkel7f8HMoor64^8tNMyD$~#4M|R+XX}ik<e9XPa{4Z1i%10'
    'ii&K~L~Yiib)}D)vS`G1yCpfUSp4FrdbTInl+DMvfw&Rq^EgecW;m<V?*PD%8OW`m0n&<*P@`sPK;8Up-7jaAUg&AV#3L>b;HgZK'
    'hwnLayHI~FuYa&bdy(JM?hE$jpJ3I1!*FdBeDau?!3Yb@fr5UNG>A4R!^ejJf=gtECLeN9()70Ic}}=SMtX75^7gS%_V=2q0~`po'
    '9Lxui2RQ)ghf-~YPUH+&ZiLF!-|WlZW=xX`J*L7_2d7<J9Z|b3j~HDrXc)fPz1$r^>4=}G1?S2wEJV)jRbyKyZ}{3nu!nT)MCc-t'
    'q0XSHfPa@bd5wybqWth}#Y?NR>Sg21NTUalnnpu|@$tNqU=64-*bZU2hqdXu?#~~uyz-43v=3yQ09*(Q@-h|`RxdY&>y@bt8D1dH'
    'Ez_DUR6KK(6}TF3kkgW5%FdyOD>{k2iba)WhIf$PUt!s2#)-LV^E4_&UM<(6#h-xxfRka1o{Ef!PM54Y>7iztrlm#q@m01WuP^T^'
    'e}DX$Gckh{k4y{eIC^Ky0M6oKDH((?4aZWmri&HxdBx*m5q+$xOEK1@8Py6eL%z;f1Oty}<UPZsfn3B$Y4v1BU%T*&l)Q{+C@7t2'
    '8i*;tPxJUTlJY^4Bop8uYoZ3?B7{E96j>JEmt8vHMZq`zHK6wN3?MHNEm5cmts@zsf*GBl3FP0Y$O-?x>Oyv@@{7S94vzkqq+vo4'
    'lSer*!(N3TiM<1D1Z-IG4(lsdR#~wvbE^mWBk)HvoI)roEt#IuAxwVdi^(U9>#s3$?V<~h=1pvax=nJR;xi}vqE;ib!vYM>CA}-y'
    'b11e^b5c}~xHeEjnj(?zZ4(#z47FoPVQU5aaZ7@|B49zRN#~sQ{h(exgO2s{DJJ`M>n?aK#qvu*-8<2ef#XFhaZ>D-H4q03v)EB$'
    'D7nOtpvB6y-&BR9WY?GFB4p%{CYNGFC}$ixQ_`v+abz4Hx(tIbEKZfn=BIB3$1LU^f@y=X6Ocjo$Z-ZNm1+Nz^m<gNh;zXTDwo^F'
    '#e&Iwxf&=lfI4k_4b5(ZN6=%LRH9A*yF6_tyIE4e+T(O?xa`s^<>K{>9y}d13>Xuw9ThWvfAUL4z0H_xxHFU#vK(@?3;+K5eEkgd'
    'vNhD~YgFn+S_J$i5%dnqYh}QQ7n$a_43+DhhmdWK&ma(2A23}UC+Vm3jva<h1M`4qiJM4?4N#oo1}Q+UUH6TCTYj|$lAVA6j4TP3'
    '93qr4U@cTIL`c!rv1(_=MOeLZWu)ShrE>!7An~IuDTa(nJKEojG=gc1oEueRF8X1AUw^;<Qs`qY%~~#atmtRyZ#<%Dd^NDCg&8K!'
    'FQYwdZIsZw^@1Xbk46s32(r2O5Ub&{#|;1+PNX1(r8<XqZEM$ieL8KIIi=UjLPjsigI2UW33!3kX0`A&e-khs<7V15ZS{G28~m9a'
    '%hxGC0kjECNxsm6lr;(pCIPclaM{C~3k-s)8Q7<C2R}F@S1r#tBhnkZcp&`ZrYb*LA$Wj!+<r+Y3_UR>F;p&p@kPd2{ps|%fCfnH'
    'fhR4Fis)qMN@A5neM)?$4<|MWM0TVql?xvO@KOO(0<-6?jgT;dyioDHw1OQd4`5(Xp(<>S-I@h?#>Ed8-hnz?uop4Z=i8yx#_%R5'
    'Z-2rTk~(lUuEV){T`{S^@+tsoU_+^ODTjfgM<Eb$8YY6_P=O2zH8xB8p*Bi?cQ5+Ei0b-JM-35%QL{YwlsU-=^+CshPC4Tob!bd-'
    'f~~!S&zLPB`8RluUkVvK!4SVPakGFPG_Q)Bl6mEsAj5XVo5cU2HkZEiW0w3X6=bhghJxfC1M}nvBRK3i*|{zRO+<u5Q3}RXTe6&+'
    '+}D3A&lG#mjO!2+k*GO^Q!|E>6o7}Td;<WeAL6PNH*jXI-iIKt_$uOHuIapttl+X>d6=@TDt}071C2Z6W$RWwXFS{EzCzE7fg<W}'
    'eqt->)F?)e`T{c*6qkuI6Ru|0RsU|R%g*ax&wOydqXfjI4CyBy)bdp=0uJ<jG;TTKOwSCpVdV8?ff8R|L})2=1R!SfSg|LT6CX)V'
    '&zDWDK>tHM5|Gra*iw5_oINz_N(R1C=6ZF|$d>FfLWag@BZ|%<x1x^0cP%z$wdKm$Fj7XM2Up>)&2%KOh&jiaC9n|1xtj;gCXook'
    'EVRs6$_!8i?*2TS-|(jmf5qB-Qy|UE;_lIIMz1)GpbeP0V&gSxB#X)=Y8cdmX3fHHld3KwN3I{WURK?ZEV-%RpYwA;0_1gIHORth'
    'JUDT@ZC9;-aq6$Lu9ry`PhR3Xm}GP~M`rYh`f4;?l)NmU&o)K3zMpn*K_s5!Wq!c=1+<{x(TVTPgt&}`2-bJ-q#;u2NEnUofhi2)'
    '=7%CT;io-REzD!4z3&CKp{=3k1XYU<TP;?4L^uY?=C})X^}_nM3)B#dHNZ2;SYR<yB4a`dq)U4WX#^HPA{a6kr*wy$=f_kXHCg8{'
    '?KcCI@+ooR5E3CnrQS)iJhunf&!VmuR(#pMAVeu8Vw6t8T)d`6S`8>z%72Dqke7I<ifSX5ZI0d>TlwP!CEf_C1e&JSb)DE5Q6`Uc'
    '%&CUSumLcEri)F0vxUNPWS9Q@x$RSs*T8@vwHY8E2D#c&q+;vDpAxZ^iD;5B_93OEk93Nk-S@eO4{xM|@9ulmvkQ?}J2@3-!j{!^'
    'S+U63A%ht;380UtN_?4=TC<^=*@g&-F-k?pMp2EZXVmNj$}h50U|noNG$jDqN_*FK>ZV9~W;QVz8BG{e4)xdpzL3xvsY5z8rBL4$'
    '<<8f4vP@xoaofUJK!Z;-Fx*lPw)!AR(V<c&MrSgnMvO2hSVjAm%T|E7Rf5*o*E0W)@dKDKV-?G+MPfR-qDF<jm&6J7FyWwgm8bQj'
    '0u;?Vvmx{piWLIgS1-F>C+$6*;Yr$ilyVG6;b@Y^S<XiF+KUqQe8Z;0VVMX)&#vSoiW@b&9S^SsmlJU;BwohjjAE1r4*pB-gD7>y'
    'CRQ?uX0Tpd05tY-nNyE@z0({>sJcRep`GEKSsr`v;|_j*Rf1FV^V`JiQY#^;45%O=K(piA3xJQ3C8}|assEbASDZe2v9riM3l&q9'
    'L?bmapP(%7fGla+2}hk)tiJ9Dq6Q@hk-wwq!Mm};CJ``*heBPUsnY>$kBL2{%N9C#-uy7Py?#Cr<akiiPI_$EUA%D(%AxhsAQhjb'
    'r=VXC8W+}X;F9UpOox&K2V4_nwWwyg<<s}V<;m`$MxdxkGH<juZlQiG6d%ASw-{<!`VidHP|E;WNrJqF8Q5hSh*`Uh`jMzv;&<W='
    '|1Y9JdH+nBQxDKdBvQH8Q3tu=aHtP<@J5!oUUe|~3U&g-H*!A|OsJ^@SHUtvtbnUbr$($Rf+m04LR}LQqCSoztxu3CnL^412>uEZ'
    '%)$V{bO^;0Hbq7Ezpnl>({S-2DP+Ka7c$CW;3s%2d<{BPq~Pk~NKONc#+_)xUE8Q2JVHq_d>0HO1D0h=7?z^#;sp#MP7P=jg_=(0'
    'u6<NbNM*_iMbIn=2`2)KmRk9g&&p)!rQy~^d76u+u7BT*2BmK5CU5C-z%Gr^#Ym_o5Ne_}u@c8iI;fT+Mb=o{*{k;ezh;*n%Nj^v'
    'Q=Y#>Wv%>Q5Ii!}3};|CsrWP?8Sf_WnIaeA-3=UNDOb8LXof3AVyq1Ph*`G8Vwog)wc;SjfECR5nEA0bM7#~TtQzLWGSi|}Xyloj'
    '78b}dItkzlSqZb)&|I%Rm2X?99vTawEW>%XlC)61js0?s0~*MgS<`H3ziRBwjr;gMpS8+p97-+|iE^uH)~!r&ywXW>3b;5ld!e3b'
    '7H8|$Zsy!tC%p(zgEkr(Rk%wb_hE33KOHSI{OK`1jH&_2vNcuNIhd>@R=4g$GZuDBhQ&oyoB~SAd(?=*Xd3yAS%9-)F&I^fo5!UI'
    '9*S++5B74-u-VbBLI?*nDpS=^SjdQ;S3~6m^#NfZ{6p9foFq!~(cHF`8X`AFf<dzgv7N_~j%$u8G{{FB1`1<yqlR3A?yU`70Oc5L'
    'l^PQ8r=W1tjDXBcLQg%XP)P@bi;gBXj2~*RKCF!zKWhgzRrrfXzYb9h*bcHUx)GWbSWTnC>-D|D@Fsu*KJ_cNQs-O6?ZB`WWT6m4'
    'X_X-0o|W6meHRfu-%cF*Zf&lepSF*mISa3s3-uX-W<giLC|XWoukI!j2!Qespcy2ZqlnQAZlJFq-tO8g>rt57PL8BXemD8R=ejM5'
    'DhQG^eChXsZjX3-fyEHTTGBwGSgU#@^4GOnA&SE<aJ$zRj>%FB?)SMcP7OGprVeQq93VKHaHjb%Fo}Y6(ZKPbUD<`W_MtE;cK6;@'
    '@>4qr#$7K5RKP(VJ%tCYCA{6R9tUowTPvD)8`f4JKlB)u7qZ5axzSKJDd{y?1V2<7Y6xy%(e^0mX>AeLv0U(LKUsL(>j>PCD@k}7'
    'L*b*@9UZ(mO)=xnM?TnVPJIw7rN4b2MeY`3GWZ{+t>dKx7~G0`nq{ZLATeqYQ4?Wrt-eRJg;m0ZPIk)x;P@;X%@e>HmZu|TCIVWY'
    'Xp2DXqB^=^A1j0mECM2f>6dUZ3#A<1F{6SSBIl%7ViyyhCfu-#N=X4NAlka*!HE3;n3;LY|3jHNt7Jv{&yXPJ#?@8YS!uVqDDO%o'
    '8dRhi4Lvm~s2$-nGV@9lWZ2$x3Q#7RKEWegyN7jLXbNGxO^Fs7ug5Q^O$Y1UiK;tjG7wB`4#(;TL3CJ5eJ-8K@~}gU=^#M&Q9j9J'
    '!iX&dW>ZWvBSG1XlSSL=4`j{2_n?jtghN>x5ged`0Vg9Egg{N9tiivwcdOIi%MSQP6+)|KPt&hOBL+L1P9Zc8qB$m74AeldCbzLj'
    ')rJzGy=@~e`z54vvu(qdg82gg2JBXyQmNN?0~Dwr-H@v&nl$=7i;FVdwvmM{Q1fCMl1l6s5}7zgMjFB9kp@gUnWDxdP<IVKTpKNR'
    'T3^_rh!e2*u_Znh&;uHLjfVF@9^~#~1N5`80by!{k$hHcJHPr<xwJRe^_3Ap!PB5v4WO&)q>Awl`I&tUnh*-{kc`L-x9w$ZhZ(;@'
    'AZH`aUxOO}$~W2|sKt_;Dfp%b*=x6>zil^XN=wy7pk~1h;!=Z>4W?li5O^7HHp<SL-joq7ef29^w4ay!yix-Sx<H|*A)%Ub4B^uc'
    'y(ozgxE(hyR#-e8Tzyt<<z*Z8-*-|DtFmk)4PzbgT+x&vbLIgV(Qi8`2C!6RyqddZ7w7l#nD#i?lsKBq6NY|*&j|A`urGp8B|#Uw'
    '7ty@QKO|@?&w6-w8<%i`iH0UBY<DHhh4D7rtu&-ag@Qy2+&3ItCh(vJf~A3`f;OJH>5;sB%PTl4^eV8<K+cdG%?l%*Qao8Bt09vU'
    'ZErXmh@|Z;+xdaZS`CpxJ)@YUs3r%ZX+|3_a33<`fy);OB>M|;|G8;9Z^q)3*pF4}B?{aO$&f8!2A@$$q40nTO0Ev<f`|#ix;)u$'
    '+02D#Tl-v$29vl3A3FpIv@^Mmfq<fPi4?&c8oBE>dF`eA*Zm{rejQGSqaXDwdy$JDPz+iS4QfOJE$0d-ZUDIuoYv-zyd9qwEL(LR'
    ')0vCKgsvU{A;>6L;^4*;Fb6|_1S1;mF%}N6ub6H#+4UQVSbBbc7`&>-?IQRul5qH9dJPSjqy>k@$XkOgf{YYUg5F?|5NsUQZixSK'
    '{502e!2ljeBq7494+(ch8)GIbj|1Xv&`?W!X^1y#H&V~v)nsZ%-&YKH!W_oA(9qD_EsjO7XnGQCL;-7~95~&@>^(44-C@pO*oDFf'
    'Oh*Cg=q=Dc0Mf|q!on>@6{+BlgnQ*Kt}twWDl@rhX5F&A0DYPrqiT$q)_f<&X|#DVRmp2V6xFwU9vTQ)8jyf=JNES6QS`_IR0Aup'
    'o!9g=oG(d9808H?Zd!|gT*$7Qivm?9JcZH*?lfm{l1&u|r4<hl&Wh1|Y%l=4jMXY$8%Hl<`nTN_2|Dx;4D_+yiuNZy26qa+1!O1='
    'ku!}#fNk*fZv8eevX#u5{P0|7T@PF6%OKBbq$3PeS){|D!AGyvHw$|Se2$NHSo?9F>A)|k5E?ww(CPNco2p^V6>$?vE-p+YMl%0~'
    '1+2bov^T9@M@F6mm@=rfCGU`-A<h*ev4EaA=p<cG_BWBjuYC`Td)V12qz1|sIVW=vG2p@eh0$?j?6WpSt=DS!CM<B#HcGo#7m>W2'
    'co}Grc*9QPjS=S}X0&i-s16{pQQE>+DXse5!s7cSbs6(hm^|b}dPiH2dy}K9L@$e$w1J-@WfmIvpu5{wuU=u+#>WjK2qNdmyknp}'
    'y?B%?Jbk#?18x>QC4MThbN=$|sE>Y(w;Z54G&tImB#nGtWd1#kZiuDW!nC4AkF-!qOP|BcNB8be77h&B1Gb6qZy3MQa>Js-3L4Z-'
    'QyDoa0&%*}!&J9obzsAd5JPI3V)S9K9OANB7^;m-Jh<$GoWuyb#UHwS!*w}e2dkP%DU-E~qMc#MBFkBZVQ_vSpE09NUTSmIii%lv'
    'gno49@XEMFJXku}CQ0AGO8B&DQWI>3mi9|u)CB*qY)zzK4oi~l;-Gmt)F)W=GOJX_8UzUCIgA=mkD}w_539mSRv-F0?1V^#xv_ke'
    'M$V4RPUAQsKO#mn8qb2m5hHYpHR}(nR^AXuLyX1R$H}gW`UiG?4;+lZ9k+8P4S;4a>7<AY|83!lQA%)iae2YeHB1_KI=~)+lHouK'
    'dJ5%<H$VXffbh}M=UV*X$AtaiR2utEUQ8CGNtyUXfE=|NjSY?!bPX`5jX2%YRsQfsq^8XK!?SvZs59KtxBn=}fPe`Y=T0Hl5c%m='
    'YQ8)Jr=dC+1&zgkZTQ$x_Q&-utVtmtB`<x<J0<qOPJaT-#`=z^K<-N#LXwQduj=iLIogV4FL-}>ZFM9WkC^o7Am^j~BKQ2B5y=>Z'
    '<pkEuE;v|g*M0-HE4Bd60Z$wn9#s&1FFBPm&{C!a=%SPK5lI81KRne`Jtytqf$}gj9rho;ANRW}zZm=zJ}yin%?LqPr(yM&uO!jV'
    '0KSm(Wq6_=<~XeKJEV+<rOgS-_Wm*c@$PA|L`|@(m@5UOWS2XE0T|4UgJOl~tP@1~F(+T+I4?u4j}MxG`H$0|r)#5r+8M-*7H{MU'
    'B1WL(CY>JSDTqxM@*W~b`>~>o5cu%+Bi|Qf{P^SOI<SBG5VUTYAW8K^RShOXeGStbucjbT(Z{o@w3_(T`n!h(YcF)AkZeQp!1bAW'
    'flei(2%+s!InXBT;ktt{VAlR&-E<_cdVtTN-omAD<xe)3KiPcu4!EAa^qM0Kr3DvCEIn}LhvUE~L~<8#9e`lq<M7Wu+Qj$Ydr)8Y'
    'P!5D3TT}!Sz`2pmhGYdwG5UGSYzb<1Cr>Em+`V^#)N=jg-51X3_y1T3x-xcWhAR~S)sRCAiE@5~(S#WVqY-F(@nUCNvDSIU<>`O#'
    '|5tii;=%uPr_Tipma_sspM;x2NLZ}bR~g+hmrejVZ+m>dAU&^6lO%k8xUe(O1nytTDoC6F;fWw@RZwUlBm@ni!nT=s&rl5XfCy0E'
    'C4auR=H;)2@}GHj*d7w+vRDsJO*|@Z`0CJJ<3PDby4u*nlIJY{)54%Dm@#mJ$<xvb1(QrmpG}reGROyaJ18Xy<5;&|BniHLV7uk('
    'pi;y#4SE{wd#w48QX{w2PC896j>Ef@w0G8fd}W+rfuY#VPF+#(My^X99xjux&glLjvA}DB*Z_BSu3HbEvQugH=b(v2`0nw8m@p1!'
    '8TGKHW$1N!F9%u8Wep#Gl41LB_8T~U`n=6}jDy>q$EUsQ3(){WHk6^*8{*!ISeUM~Y}p7&VDey!FqH{PpcNHMYppUTf(i4CX2U;Q'
    'Hk~+TU~~v5gF=?(Rp+E&!n3r0S3mW)1rH05T=J*J&Idn~0bVEeA$S@iiiL)YCKZoX3O87>4bqk-Rjl~>Qe@^+8g>xS0X=6?U1-Y@'
    '*R5LnY=SNW?qF0>lly43nB;Q}z4;pnE?@sqrdh>r(#nJj83d^hqe%f)1_UbHD^R_ADZUZn@@CDdRheF}E!0e2A3Yrjl$$Kctw9Oi'
    '$<0C|lHheP(5*L3TD5HP0t-^p)3<_Doy1+i$G}MggQ8zz7%}5CJj1M6^jwQyzfDjZDd5Reml+Lwuy9zY7(vp||B|Y}Tcyw0e6%dQ'
    'p@-%3c=+clFh|~==OotzT>6J_04OBHTj45e9grR@D(p&Rkl!Xvt^4>+`Do=Dnh3%L%w>oO#95s0;D+G8LK-N$5-DDAKgL9=UHz*+'
    'mjctE$%%ZUu#TaNlc*6Kpo37cO8iOvNT&mQ(XL&%W_&Ey*u-pVd~T>n;qbwmL)I<94|iS%MTqZv2p|9E<MA~;K!728SzHufPOc<Z'
    '=pj6Ff+!lvm>_Aj67qAjdEg{wJ!WK$EQsf-HOqG#?E>i3){Xch@T;5#;0WcQX60%H(rLMX$c3wxtGVK^2Y?ZPOqT|kas=8%PCgiv'
    'h&U(ZrDX&|V5(g3RLVS|_VF6A+DDBebA3jV@+>hv(^t&Xq>m^tcKB$$3&wEHvCE$*7CDfW=-ooqZ?oLM@fgt|jmlZ*;=&K1(y&#_'
    'y>NX~3>Ib_z;%d#kPuF1%qF6YCK~>p@lE(~EBqSy*G^R{z9-WEDb6!)g~&tlqbYrW_z>}pU_dJ_B_7eR8^M%))ney~JOvUIQmI)p'
    'lkr|Au?1@MVECP4AMz27Cp||H(2v%;#Pzqo){NH^X&Q}%u+&+cSuSxp6gVJ&vT9TskCwfBd_XZD-XFJ$rw_|<Ilg&#6dYU3q}DcX'
    'j<y8Hgonrv=YQcxMBB)}g`+#JUbQ@xf(b9J24`X>M(jb~&!vgHn(50>>R~ZKY@Z4HH!Mw4Kkjob#8{Ffo-Mr>{sA~PrWweQ2Icg)'
    '$r5LwWwb8TuZ~RckE1AuFRuj-D8Zaa3$YK2XN&Drq$=d~!U7>dqalO{gvsIcE0@CqAC7!@sRYT57<w^l&;^zT$ZI4NouYVty`5LA'
    '$vXdhDv0()LRyGN(w=$BPdxg?w{1`=GtrjuMf}gWcF~J$ykM-IMb^+KV`S_B9LIS^q#GMLG(b2`qY05|)-SG%p>moRVgyJDUUMnY'
    '`~jbUj5T8A^MTU=YjrnpxJ~`yV2}J)o!nX2^=AQUCP9-eE#d=kPm(806L1CKRns6+Rvsx5rnKU>?_Qp@@{tjyg^_aj?l9Vs32GwZ'
    'F*8dnG%vS8?geOYv>5;&fWGV3zT8G<Y2Ee3Wl4eVTIReW=5Rf6>GupeL8}ghH8@#QPCnHyu0P*=PuRC5?rbkCfK&<^44=11m_7Ck'
    '7(})z_^?4kUT69h>&qrGKM`2og4@Hw()@G@ac_V6=`7CubV(Ps7qRNLuFb}rJ-YJ=*aVsrzko5yNu#DZh_+a?@u5&t<$nC{-}YY('
    '=gO@Qpv`DpLG$2Pz(4YW62WNbco5XNPAHkU#JY;DpUo&g2&O-|xev5BaQg=F*6YOziNPaiJCK}9->bP(*iTJ0M_ei+bec=Yp&Z5A'
    'B*SaIA1X{R3r1v8gmK(~gm5TAe??xzXI2x%tHCz<72HJ)(`-q+<T*__p{ZzOVzTYS0XoTP_Csh$qc9V55UvMI>~T^1SxL5;xB*}w'
    '!4L%15snIkwje4mt)ma?__LePgBLNx9cq3TmZ5YSVXwIfAeJJBD^k6&QG=F2o<zo{gYsdFJRTnXru4H0%_<k`g9$O1(-Q?q&_P5o'
    'YoI;H31v_W5}*%1ED5e2&ft2&qxMtW=4FQAX<O)UlDKlyU`B?<M@EknJM!nk)l?7yGge9PfT7#kg^S4?Hjj*fgY_*hMWVeF-cZs^'
    'E2j`HT?mpuKyj{J@TZ#j`ehe1{dwZ2&3J~x{Xou<Gyy3{mN#k^5l1x)wJVn!xdcS8;BlF`1k)Q408$pJI`}Re7?O8rvSat*<-V--'
    'W;yf8EzOgHStz_MYAfcXiA&!~k^xMcgbovRkgKEEz<=rE!}{}*#MZa&;?-Bm_XsRZn88VruLO3fMgehyVf0K<LS3XL+*r5hcLj1m'
    'OG#}tXc`(c3j#QRB0xdb94CYg>eb`&JiTiq_|BRYP>b+izIzP8#X^VFL1Td{k24jhrn6KYRz%Xe1%*IAE7}!o8L(ZIgPHO}#wTKp'
    '0TY5pN=XfAO;ebm%YB@T|I3;SkGQ7sMsJWY(;Oa5+|VM-64ld&;`9LYaA)B?3y<ktn(CEx3sn{x1C3GQ1Sb^i6a+YuFbtf+8j2vg'
    'J519WKdf64j`FtfOF<wsdj#1B4Za{-La;12+mqVWWQPFZB!w%NeamVJ{Zx`|ph1za=)qwag=-io6+9apD1&~qhAH^EwTr+AvTw!('
    'VSm-BmmxJJ7+#jGZBGiUv1CxtO#Ny_!jL>mI773Ttqg8PxIl`XrCmU#k0B5gON=e@uxiEk2I%|@x#RM!c{xn?L!8#Z>1)K@WXLBI'
    'i=o<~(<35R#@r+6r{7;66$xa=?7m6#G9BQhjR3b=)MhAQx@Sm<+?-dfxGAH~{I^pfL;I2@#Y&)RIlM+=1OX`kEYQ9|BwD|06<bwI'
    'hgS7cLthngy|{}^(~*vwHYa2|kW1pmv~KxDb5UTSQEve85f1TsRF7JCH-?|I%n4R96;tPWShwz3(NOSrXt9!js{|L!V$#cdwagHr'
    'H3(&!63$S`3bv?Rcu7Oya9;FC1y>wcNt|ZJy3u|`BY?93+nMG?iX_Drk#g!PKiy*V*8mIzzd$jVeRH^Itk6M0M&mRwf|Pe$w1j^<'
    '(Es&6{tw%b_>c'
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
            'a66799656e1f6f64e4f48fee32cb1897786a3735e7d15c254652b48447afd08d')

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
