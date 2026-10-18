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
# 10f36d86f11be97908a320ae4d11cbe618cd7d2c / tree 20278584d16633647ab3a47951b25a411badd2dc.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'f04851d4d379fe2b7e9b2e5e0273c92af8e9ba3bc9612eea5d4816f5d81540ca'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*emU+^5jd(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNecq}`row<ZFaksj{mX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xS{?|=KZ-;SRhf7{yFB-4yJ#<^>T*~H}BJhnMEHuk}%)Z2D4`u}kH_M-m+'
    '|FrkN{nx*JU)Hlw`26s)f7*s`h1I<8qA_C{XWK-V!ZcdT8ck!H+>Jgq*^a$yrjJ*9ap8-5Ob>tT4`1@r{*Q;p#IJRy?S6MGEFP!U'
    'J3G5HBs02frXjeg8%@`B&WCxJ?J$SrhmRLOq?i41d)gnqJ%rCGd?~Fs1Rh=vCRj7+0jHGaJoLHg<IE48C)c%o@>d@2DIHG_$JgyC'
    'J;d~qb}{Y3HkH<Go6!tYpKUgc8BOp$cKy)CIJnmGGxO-I@7i3mZfPx-yWr=c9qnj%y#r4+nzr$M+xAWLa|*$`<ju!xy}imKFZYmk'
    'r-y&Ox~Fa4hUKmP<J<Go$E%OA<)^i&_hZNN9h<Rf`@xvOM$=70@1uTpvQ?`e_P?iadeCn_USD>a+s4f%**Q$99YWWKhTol{8%-0f'
    'abr8M>|C?#-w)N*rERu+H(fTvFqy=;4RM^iwlU5H6Q>ZZjdS0>^KSit<%kU7Y0Fdo6t<s!PrEPM-SN|-(|dmT_VKF5xX}9$THp7*'
    '^=&`JF|@`GDRR&Tlli8sZQ3=fzVOR=;n&yY5O=9}$xfYbf^Fl}<cag_MxR?tkeZsr5nH$J-d|reyKEa?sx_J4*EX|j+Rk>q4|AIO'
    'V6zKum^!m&)x+!V>YBmy<2c6bX5UYipXcUoZ05=MF8S2<(Kj~bylPFI<W2Z|*gvPuG3;Ni|7t#$rs2st(~TqNI;7bRowLo*PJCNK'
    'h;y9Gx@W!YVCSCGk-(ichvZ(iyT_~Bh!dwbjA<BqqGmFE>df5sy$gO+T<iPM^d_u-5WAP>P1x`9_WJtPnKVuWvT-ubv{Nu6pV#0='
    'H}Ork4V$y<v0J^q?&Y}o^K153*Y}*Wrtjl05UR(a;Ykc`ZbHiq$%*WE3Qg*~TfIIfkgM|Q+9~92a)iu*53jR6*kHWrh;2h3Tx%wR'
    '?buZOc14sw+_z7=bW)_-9QLoLw252yxZ593+i*SFbTfCxlzKCSA@#iec}mG~bvDCD)C<wK&J1Q=y^YuSa&_T$;ucG$<;LKHkF%aW'
    'I~jw?vE@U^o|BlYtzP(i@Gh$_iJ6YzDgAl69)JcucAH$=4c*jrNt+txWc?8N8o5(V<CUcq_wnS&3s3v!ZFnH;ecc|pQTYHrx!1To'
    'Z7w&SZrQ6}<S-=H$JUVzcA01xV?T4pOp1wS9P~1HGWO=(EMKKQjwkm@E_ppl*|7`U`s3X5KE~)gadV#9Ip=7*CL5C)lC9?U&AgIM'
    'UXPS9I5UNIoN_bp+uaaa%hkYVLb^9hd2q4s+GK9t!<Tf}rKipEmagt(Zaohq+L3$TcQ*G;n|*A@!Pt4sW16ky{I>b#ojki8>2}<Z'
    '<8zb`-!`AON98J4ch%_P8goDSCI!NXO#_!1w<x)SA@AfW>v>AI?`rS)m%bK)*%&%f(J*+TW$#;SIlZoHVn_OvI6=g*QUCPzUA$Z>'
    '5BIcu)dv?&*8|%W`>C~kJ5gXwBT;=AIve6dzR0mAVV+}ZCqLi3C333#w0-=1s*bgz?J^lv<NCpKwIsfCGZ{M(fAoN2*HE)%>+jf7'
    'Dc#}$3{99CO9k4ERGY1`F0w2h$;{hprf!<LHr~7i(vC>5+kWN4-h6*V*Ruf5iu28!so!`8-DD@?z8?v`*&9Qg3B;e~_Q!HO@m*a%'
    'EHg*LYH2@rQwUr_dFI>(9+ah=w07v`;f}B9<PMLi`WDC}yp0Qy>?4nyk;I2>dOL7Pte((FelR!b_P2D-R^P4yzkl6DR|qs56DqKV'
    '^qkkyQ0%%f@_&ah^sVt@-#9~^(5GLtr;6*TOW6P=cxtk~OLH7T<8utgaFVCUF;>J0xw&&k%N@0;3WH%Fe{T&JCKuz>0`J7+Cr&n1'
    'jsyD`2A@f@?tE`)_jP;N@1FS=&#&%!S=S2ZnRDto@BI))t_bf&u%<D&$par`ZuHpQx2Nh`baK6Q9aV)LeVV{%Vo!BT0!Df1$$dvY'
    'cy`qPy6tSXB!Q3T+oO;PdOvZXqHRM%Aojd0KaXLaxGXyEG@o+IcJJHTO}D(a09qu(obf!{L>3ZMCxVTDICZwqedppFe$m##{&~Sk'
    'N)K$zE_E}Bd_NlkrQYX6(oFbfw_`LubI(p){588ermtyNsH!Ph=P>96QbZB}8lKnG7_N`DOA}~lM<93i?WZadkRJAPCx{`YJck(+'
    'aPC|)^6>`%Su^rNK}M%LxAH?)^t`P(<8y90CxD?#fOtT6!47^l9z-j#yRLP~MAzs0_O(7W;=MU?MsSb;U=x@t11|PvY<rIQ*a=Q{'
    'eUtsY`yxNughK+`J#F37v49Rxa`k=7MLW%&v@K^ImU05)Np=ljEU8nR@7_~QO3-onb8z@SpheCYzIn20AbpUVZW<|2jkB?B@7v4`'
    '*&8{e&miC9$QMT0>;_QN1n}LP<bbJt%ROk?aNov``_}`YR@i?|;MU=KHphCgp(vu|FbQQ#v76~V^s`EU9OlSFqaQKcxg}+ln~D+^'
    'go%6&u&=cPm09-OGcBk~?AjrLdlH_e=H0%}`t4-5eR?eby;DDhL~F)1{on!(6H9LE$XP<mV+vh2%`{NVo#*=W{F1j%>3g+y{qwh6'
    '`eWy)&VYl6m?N+ZkHwSkHiBg7?6kvp=jlEjUXLekk}v7op#+Wc&68j9efK^Y&h*SXqH#r@>kWr0O}UR#x~C#ou^DCAO=m2aXgg1t'
    'x0hRDc;EYmFD&@J8)mSGy6gV}QeXbb_1hwLpn)6<&`~>ZUr^9DWU_<t1Bomc?J$LDs>`q+Uzc!~4$s@;ap@smO~(8@(~nT2BTtE@'
    '8huRCXivAx**;A)fg&-d?k9iV>+SFNrGT#sntEb#v+YA4!_X4isLv;E@Yt9L9LHx;x8^x*xgI*r99llSj`l}X76tH~3;-9fN#@R>'
    'uf`r?UH-J=^8cDPE<SIs-z0Q4NIr;v#<$~0_XAWS=0K0F<NtL4Ts;LtWkGORwFXRV8ZL3lG8ITRq%cz0_k8i7AcBtq<r-n2?kxTI'
    'B~|Abp);xV6#3MLs#@s)#h%t4xdtD5)6zi&gs-d@f9&_vd`dP_Tl8Iw9Vq``dlmR;CVTGqlsVSa($r?ru2}qBn1=l!ZGPu^+@<R^'
    'ghDI9j6O#{MykKjf-=vID)*UY)JUD`LaxN<e%!(H{%cx_QLdoERcOE^ZQJI?Pn{EtOIkzHsk;$eY^G|rG#+MGzlU{EB?O*$)A3n1'
    'w7xnTU4u8dqoK=}mbictRDm%2`t>VAi;0=qadN7)!BOnQ7bnC`t#dxaej>b+cX#y*pW{o#Gp7dPz0=HXxxQM%S2&SNd-~`!UO)h-'
    '+~Pq0bM4Z9m9W?E5E|JHX^$gy6&7M!GW&@K51`-hx(zr930b~<`AfGiyu4n24t#eeOf7%PTZa}xoxx2uf)aDj(NCBxjh6X_jnu8*'
    '<$)%rA?u^rN%BROn)x2OmOq#r=)&0g*sMPSB<u^9gHOR7u46&obCb5}vT~~gLf$a2rvR;jLzoDT6PZSg{^l*zJqgS6XT64|w}Wf|'
    'dBedr;Nd&!<HXHQay5`=+^~&rr_cLc9iXYhPmutqGc7bMC_-s~@IjrBCVEU%$2_n8hKF%Tk6=0!Dsl72!M(hcvaH}6%HPbPAQT7#'
    '<8t%^yrDov4r7e-0={#@!2npg-h>@T>a>x?Natd&)*{egrrXwfg-B3d(!Nw#yj=(gwF$v&-RwG%OES%f6dP`&9(1cGIf#R&%P0y='
    'UU47Yloill7-)LKrE>ga4=avtXK;c79Xo+L7sA+8R72-q{;=J>yq-Ss)}Jn{ss}Rshd&aDH?SHN(be71t5cQATVKv!AhV}b1X>dy'
    '0^FT>EbUN{CH=G;R)0uQ#HSxOrqW~MPI`1@;K)%WlBQ9Ei1g(+6@jmpvc&e(9`uQmPHhD^`q9Qpq@Bzcp!|u)(h6(f3XO5fR3Dbs'
    '=ioyofK3&YndP#6BR5`Ol2nbesqB<yFA+f<a8E5})8v7x2MBqib-8lMH)u?;a>ILYhv)ra^UA+h$XbS$4}m+9jth8L7=y|`pw@Y^'
    '#$;$>hGLX3Ub~NT<@s>oN_;vV!vAaXNO@!b*XSf4Z{^G>QGvB&ngu+Q^mdw{XYz{Rp7x|%ZUoN&DChg-*|-so-E_xx-T;JUTi3JR'
    '-rE)`VF<)jLMq=cHAfGBB9jiY50Xzfy79)%EF{kJ>4r?|j@8E}j(o4AfvE+GY7@6{fMvp4qxN=j;E%`>#|rvYabNy*`xMXkPc7g|'
    'WSbxYwQhz1M31V81OaQU5D+jj+AW><ndbh@T`;>J9$SHj!e^)FMMwznH9_hcb%SX#z{nX}F&<2s`};Sxr44j=d#M-F`E_K0K2-~Q'
    'ZlYUm;N?W4ZbwJMxP?y#zYxN?ndV=xvmJNV6HO0ypw)N%lqDjx2aBd_O{xcWPV}VB52WOw#!&OpHl7AQ+`p@H(nE~+p+kH9QuPj!'
    'mjztp-8BTN$Ojo`jv6Npwk@atsQ={e-`bkk70EL=`y71u^Th9VqUjI8NuiVmvbrABYwj0(mX~yW`@B@Lum0t;I~Lf{kS0gMJlhM@'
    'u|gBbkQ{(91OQ50E*z1z{VzCU=c}*^zP9u^i4tHtp#?y+(*l`hDC5o829eZS9$b^|-_&vYxUeI(NI|H4D?Z8rV3Es^q7Oj32gIGS'
    'pC&#AT33NYmj?#En*JO1wq!aLZTBffGpoG@`E};(Q4LcOC9u$e5)n31ilEQG;3Iew0$krtrhg0z6iAlT254vk78<3wAR{*dr0JJ('
    'Biy*1w>^AXcU98wXHj~8UG##hCT=D;$`B=>Zh24(P+Mbfev99CwOo`1){USm$l2V7jyToxDUx`DV}a}Xwv$i+V)Nb4=Mv(tLpojC'
    'QY>-ha3Mp50AYpCLW~DOAgV(vpFunO;oiMed}b|-8j<>-WLQu}c)N7kJ^3)|2GGrbF2~W&ws&vkQa}9su@xdfqjD)*Iw#Hpv3DJU'
    'Gf4lLf2-q#siOh_e(%;+Yza^hz=x;^Ukg1CEm6uW@;}o$I8$hCtl;tHN;Mg`2MLHSJ4<bPYeg)8tP7_y7M$tk<R;J!rL>*GtbA&2'
    'Kp@5rOdOn?vc}nN%^pfcEL9psNIMOd@_>Q>MP4T^Gi{}a6oZ1&nqjQ}-Ia|d`n?TmhCb7ahc471I+>~AAzP5LL7+BtA<X>V;pF;r'
    'yIevoQcHs$5|>j^Oz$5wkspR=DL{JhoPLQO!+Q+QxDV9gWSQ>i(*~;k4-&17{#l`4$FdyY4yLc}v*f|A1{5Wnu72#inBtvv>H4yw'
    '9A3v{=9r<K(-)W$i4dwv7_?N}UfLDTOh>?@m(^Wg=A7^>|GCiXojX4WX7PEjh}$4ll0;Lqb#$o|{S%^@_|A_K{FQb>#Xq^jX^V1-'
    'M0sJloC+LrvhxV@4m6mn1UXJ)0==R^X|ZUPZKhpByX@+c%Sj<I=kJSjHltdAhCYPf07t5U&l(#bw=q$;Phprx#enzj*uO1!CWc%;'
    'Cr-%T&^55s0DLWN#t{M(C%&7h28MH8916eh==aZ?uiV<PoYDYe&eYTcpElqK7(di6u$t^3TEj9VGmJjY?=`Q_*-A`bw|a}zcP}Tc'
    'UX$oG5+^_-5n#y&pS0M7s*5t8OVY!CZz4@kS6Vc>my@(JON9B`iafm^^r+NMyhgZD6DY2CbeZU1gC!6~t(8O)>XuD)D;~eAs$VDy'
    'zW?#{z}Bjx8k&itOHTvQ4&)Uebi)oT4B&>wO6P;SaR)Ci+t=q!%|?RQ+H{kWUD~)^LT-#Wbx?AqSPv~23WFO~ZlvlVz?T_muX*Ba'
    'FQTXg3}_)okbk&#^kH(S9grHXT|4ZbxL@|?6#hbcET4TO!a|u)v(27Qn;WL3c>%mGCLe+nddw49eq6ho1u)(`CK~RgmLo(jD8_sX'
    'bn^*oz49>_4gHkHJogqP84Ql9ta=N}IjDLUPzsPHcbR}Ds@c#(w#rgUtNjmV#CrhKYOCMH{~zyw&c$<KNl3N`{6TrhcTLalj0%93'
    'P)j?Vs@TFVp!M3-E*aDD3*D>DKD<6{|EzlUz^YoBz7^2PNXi3^hf<u*$=pLPhsy+kiR|RYEj+%wZa%}0d`iaxtVvHXQala@)i$hb'
    'Yx<7F1W2b-Z>@!6$J<EFFW3j9Xs&mt?ggF^EgGT%#4$LeW6o;(MU_nABJ{|~QP*^x`869_0H%s&w7~E|x{WU6HbgqVs3ite$Ve5E'
    'USSgNsvB?I6&LpbX2fy(g};6KyQ_&8RS?vaxhDt0WFZ4GSvs;PGUG(ID@qnk3!%MnKW7BOeS0FHsYXiMkFMCCA=L)rFWFI($6-)+'
    'et<%fu<_`Xzgt@Nrc1-EpVjL9nAQ_G0@{&wnyDpV(V&vxnMG=FLTVuS?%s73d4E68`|zde<93sJI26^kGb3Cb_&Z!_67owEmBm^h'
    '^UtAn;Y+pXx4T$kUs9<`8AdP*7@6pdLIQ=b6h~oahTw__HH_8Y^UF5u`%iiM=Sisl0)AePYtrnH(2+;bdsJC0x&Y~<P!Et}Y7nvx'
    'JFQ#)FUnN)wL+QhL^q{*1ZzxvYU<^_gGvOKh~B6byAPmj-9`?wS~=8j0vQvf5N$=V1Ayq92V9le4U!l{GG;=63h+|93I1C})L3!H'
    '_e!avRLFo}vxh>&rAqqA`9xNc6I_DeC`oVJ!8zZlejZYEP~{5dLIg|^PahoO2str6KZxOQqoG~hSKswt_x$Z<u{2V(T8K`hRSn&{'
    'jtJmIVQZA~vnXK+Iw=Yqu?ov;`^p7pK7I}zbgdC>9|RJxHQ>;pN0#M70t@BBKyg!A5W&p1|43ERD|+sr4Eo@?u6WUTmd2?Ca~Qed'
    '$@C29HT{Rul8Y4Wtu8O<gl8!zW_rXX(eLk@1Y-(M0GT;WG;sM#fT2_hICVN{I#1wE2EZL|MXQcA)i)v_vX%h;KAg4Np|4$R`K9|y'
    'J6Qj5bN)BT44x|5t^!Rtx{-<<8w?Ba1yV;xxz59fo5W#jA$-K<mhEhJYW%{v@UI!WuFcD<f8)Yj-xDF9%NGzAbOQJ;0QN*Wchh81'
    '-Jq|uvVDr}U3-$c4ZT!);#w*(*Dx)S7GVTl0J;N~3edUn2||4jOw$cwuetXukyh;IhxQHWK~AUb^Yv?rI}ipt`Vq=r)WN!~kO1;^'
    '(DCI1lE#euH@aJP^~BSm+nY+EnYYlWNgwd!qUMP_C<9A~B7|0)1a|-y;34LgJv=Y%Kw1)|J+$Chpf4ai08FHh;CWowoS9+Peu%};'
    'eto=U53=`R4~JOsEU;H&Nfb}Go^euu+hNDRIl&SEDMK8QGXO{gd&@p(jj9@dd8G$mbvUTGXDVTo27KC33}H5s^5g8mj%XK6S+~|W'
    '-*h+@ux4|<x6WVo_4m_oH;>eVWUsKdyg)LbTsTWm0$>0Jotkvp*8?`cKL7w+cJt5Yrvj;tWCnQ&1Vru=41uV3di=kr(jYAn^0`eZ'
    '+T$<SivH|6W`M=YXz5p{g;Rzf5s!r!12GonxJ|Qg?kSG9??tT4qvNm?&>Nwcpx;KC6ht9lTf8aYTk;t)nh9SM=p`xLvXP^EenFFV'
    '6hHXf+Ak6J`5W*=Dl9w>WLemf?Pn?;T4;WN6bPf5Lz8Zb{U<5YV?_nftL6YUvh>99oP#fJ=tE$DN4W(f&|-ztg8}+mHgP^4;fX@*'
    '`X1nqNhT7(jyNU=;3VL;AiqF9G|K_k;oaH#&nA3!r#BgmI~Bhb@q|IL#ZjiaOsWm80?^IP0vVO>7wIxZyRQ#t-%TDb)=@yXp9=^9'
    'gaiOCOf5SL-%4!*+Lf>ukhEaa#N!a8GSvsMGYR&5yX?Kxk~C9ARC6zdBnj##v~AK)TJA%b=+xkOL29H1DlwIsyh8zBy%ELm@GU&0'
    'OWqa&Ux@Oz)91wv;3<{sGU<?^B#aHAi_4CFA|NPa0o^{3IOqj}3>f!|_Ecf)1!)8yJw*6&HYCg<{SR60oc!rb1r6W>!*Kc~8;V<8'
    '_f7@Idy9lU&`YDy>t*vbif9$Ee@(E5I9jl-vdXw$vZF)#=W8kELuS^|A;RJ3g~_9mN*saspnA1$CnUEBV|sh<hMxA1+g%mbGSVjF'
    '3QW47vAX1BgI4!s|6<ExPst70i}P~tjzB+-(rD~Lsya-d8$xiGJ|f*x-q>tL3Ke>YK9WR8z|5_5_miUG_+2$!+7s`Gw?j=r%gGW5'
    '=`zvr5%IE7h6lellTxI3@1Bn7#7*@Gw!3pL$Itu1t`P0^a0Nkj>35EDRMA_E<eI%07EuIoDB8blSFbNmdv_gb&O+fS;IR^g&5I8R'
    'r3l2F4Dp#xw2*oTP5s#3yQkCsOWIv%v)7X?FkG=>1NDj<$i@*K5{;naAb*-W1n;f3=WpInj0d6dhm`bh?1~&gt}V(&)Gtt8K=a_8'
    'PO`JZECf#D)MK#=h5Y7F$v;q|V)OZQdZ`LbghcwL?ZT_TtASw9!}^4f!2JTp5*Mlw?^ZM3yP;z^Y+q`we!5zI#4Z#hVxYc6qe}7z'
    '2#Z%J<u~piQjt<}-m#%F&6FOAkplr0Wo*fesbs0Hu}46ng>NL63nHq)-~7SH{j(!ZFW1LkUf<W_wc(sPlrgYyl@l!(Il@Y~H_%^6'
    'n6R0UvD2MfdfG~ATY=V5rc8Z8)r={2Mj-==6+wnEQkz;*#Yt)&B2xb=_Cr;Zwk0DVIoL(K-UAl|nF!K0*jM_{Fp+^^)~X>$>$JIZ'
    'Ly|M$FIN?z5%<BAfZ)^cO@rA|ZUJw?_kk!c_q0e>4OY?Jx}`JY==(SJgW~M^s~hA}*3$>XguszTqY1U@+f(G=z2T90QJprwYFqj%'
    'RK^NRR#FmPo1CohaDtf(YcW`mKzzX_-Y&=_O73p@Mf=KSdmA}LCmGE*(gIQsqpd)6Mdl3=hgb<3Y0=W$xgp)E6;{?5vnU*8Sg)X='
    '9O#L5#H?N%Wh(R>NJ(lBnLBrLW;q`C=uR*oi^>XEt`H7MHF}h+=md~n8S%QQ7IB!9brKF2Fir2=)#d(p-Bms;I=0}l<hR`I3_<|h'
    '0DgieBAf>Z9)><}0yd?$ZtHP>+KW?8!hP9WA=`$?F2QSRQD66BIYOv}K;bC>Xf0ZZaxg}3j^08R#K#qEdHoyncyEyL6PjtXidsoy'
    'mCKD!jiL!Knf4})?|kb<p7wFEvpSncT}OO+Igz8)gF-Sd8UQX0Xm!*?w7tQ0vA<E|zGE*chAuDZ627ah5?}`-Oq=2rswQ(hIw5i`'
    'jR;<q{K+gu64l9l8(T!warx51zSxRTf<}4>VFEwf847R^u^h%7qC$!|wL%wg=+-@5V3EHbQ+Z3HnW<onb&|w^l3=)yMct(@%TXpq'
    '>QI~83lLVtZtwE`D#4MS6jr7qg6(Kd;B1dmvlZ1A`8~`usJ<eb-<+20_G%mn%|rjr6Du)(4fh$m{~)enT7(MX6eJlI2H+YaITKzu'
    'H`gEgC5JqhLvUta3sDh84Mq$QNsWxjG;{-s6bOVGk4aM+0^no1`Gy5r)Ul@KCuG+lH9%HQR>{(T6A5s~q3N$bK(QC_fa*D9HsyPE'
    'bg_omoIcBS@A`Hy18&r(U|EtyxungkPuCBosd`?pV^B2SoElw9GU_0rBZR{;=|I|CzIE95U{*5;Hwp%h4s!37?m<g7$%LQz=6h_p'
    'Nn_pJ(Q>oX7Qn0x$9(cvaz#LDTJm(WvDTvVh1m(Rm)rNU-0?^|YQJ_wi9I<!?}n<d4`3hok0bh^vPSDk2ZQ{Bc^~7QJNo)uVeldE'
    '5KtEeKeed^r=G~6VQP;aTWO73i6qu8+?)q}os_tK6`EE`?-_Xoh&Btd?lks-r6<`#a%ZW!#$TE;X?Az)B>gGAyc*WkwxcXQGg%0O'
    '2M=#3LM~Bt$j}{bR{m9l3IVgbdp5OQo=&QLOtV409ps7(u?A|3Jn&##VG-BMAO;LXhAiED-;VYb^%&!Rl$D9O%OsKrf7Vb)cc=(t'
    'R0Q8#5z*cbd1@yoVGR32fpXX@S?}cPU?Fegor&y`_{_Yt)V8V&vm}6b?BhZP3?;oGG&`8Z_>_U+V;O{nZ=m^ueOwo1ioz$4lGdkt'
    'w(|X+A_5ljoIu5lF(n8GC@(UWvB5M4-%0`@r-Z7W+ni7QS8S%-9RvWAS_r*5U$qqiL%R~yD)0{=1Ny#%CrI*lY)10Jf_92fCi#op'
    '^|19DI+^VSO@bp;h8;r!=I|i!;htTb<kq<niK~c3Q4XsmO0$}DiiDK?&^0F9f!K*C31mjab5HF3o<k%!A!z&yW>5HQV713sEx712'
    '4MUy@Z;hr(-;?POp!uVGbDH&6?zveSn*||1F4*W1f!-mPft~WAH1~<N1tljZ8PG@W^tW7+JQ!&vz*5c}+k*Iw)*J4Fy@n!sd9lGX'
    '27ls;<XeWP1L91ERi9hEJYmK2W^l0l=VEW0Ow!4mB9b=&UD6sH<c;R3sAdwoMh!76jO!^6@JY`S*q{3oZy-vwK?@vj8c8tkKvQ}P'
    '>k>E<787(hELza$wlo@s6>!A|`&vqb>Rlm&4|-Wx1LGcvl$g#gRvuWxwlcD#;XLyIZGZEwF3pqL{g4U+QF>$xbO!XD(|m)O07oBT'
    'C6^S<3<iA}bMt<FWKq^`ilh%VfKl}XMVYRFJO(9A*GEq`4AdSwn-%HSyPMKKtKZYo`i295yc_yBi7CJ#m{+6Fh(w)8-H2M=+`6Z5'
    'aL3QsLhkk_SJr<6E5V(arJ=yG1N;;cx$Iw=U5W`2GkIi3+OFWo{mX7Hm__|?Al{e;l`{X0>3<3XWT7o0alBXXG6&J@DYkBo0YAe|'
    'm79{SP=q~!pbp-@CZ%DC-!MxFS~pgrWXedAU5xi_O4V?+T^~LxT|S!zk{rtzoH2b^`ZN^DRyeqHL*01mj=m!))f>Xtwe<nv>5z1<'
    'YK&9EfHZPJB#1Bx`R8QGH@`PM9CxJKy&^tR@3v%z)WU=O3>eT#`bEE#JaxdJpIV)JWxjPsm-3T*>h)2>0t!$(C=*<EW?#v@1PdC-'
    '$yuX#J2k#Wsx2f|2qnk6w{vdi?CY;LdT(;w<S>CdWnFX3nv`~uY6qwg%r3!2@#)T;Exm!-J!#h9AcYsbIfM>mWVBYGEKrU10>sHA'
    'C;RTWo>hA~ettbEVXVJTfKCZWMs}@GyE<H!X!daPLL5Q`MX`bAgW|P%Uzd$6NBj5|F~jR(Bz=OnKnl0Lo}6gDG%yQw5QEHE8`n_i'
    'CJ1loJ8KGamUrAd-?O8=|DB|XDwVJaw|Ex|Mi??wLg$Je4Re0DZ}J->l!J#wX<!i_bGNKXnBLjbPk&TQEtx3Fo0?=|kCPDw86Yh<'
    'Ey0(>sAh5d<taj8t>00?_B%bO6;CetuleP5G>Qrc3S|SRARQ0+NLEMy8Pj}luj>!%j(06rKHAKs-+g&9m%qEz^Vhc`{Tws9Nfp5{'
    'J5fj(0or5ALIMH<hyF9v+7)!?54KWF{kb4OSYTF5=R=(wyqc&G^Th&h<+BE3zpwwUPR;{SUI@m^e-^p-SYWnld<0&LJdIJ#c+l`b'
    '#Igth7=*zAqOGiHO84xd^dyKV%ps8597hvzUDCL;R)b0~h{Ws_Y9c;4O??`DKAO9&K4A28pl?s^+d{f7Xw1YT)&On{<pxoDshCG_'
    'C&&qu&;aiPwfhP()OjCB`P|`Rb$3>gl<H&TUJx)9MF2Fi9AUt;AwbdGhd&41yJ3n{UbhXbxi<%=EO7Ivzn1#wGQCAn6O}4s)`U<3'
    ';#zKm*D^GK{tRQP$$qBwyWqb+7OdFhEn+nn0M0JJ1<VjHm}1sd1Ai9TFP#QAj_VdbzXBbDs`mh^0-O;OI!KFHo8V1KI|>#!JVqSU'
    'rOjmsVZTBjcad31KXa++%32;su?USZ!-oCpnU)FDo3?l$aiPxTPhr19ARPR<O<Z8lw}Vh{prg=ELVjiR%;=CTS{?;AzA~a)0ZPLi'
    'Fw@HONZ$#kr#fk%(R7qZD-OyXo>|nf5U4vfdGVg%9a+@q3=B)_b^xKoEfXi}`2mQHAp;Vc`66YgNbjAy9gzxgQUfM1_J7xO?&>xc'
    'NlIA?;*InNxL6?68FfuSK&GZ9c!Pm-jQGI&GUj3BYq*5yA09!Kg&JNKjkKYYChICZGNNq}mVtRd*%Ut-E|OpQM(AmILZ!aY!t!Xq'
    'q4Hz>r3wp>4xodXUvy}LC^g)sm|o!4wQl*>Et%fwR5*-i+4yyM#_PTW2BTkO(1YS!0fj}R-XOrPi>uc@{;@4}r!^s0Bv8r%DPysR'
    '5Mx(UnW*$I8v*(@(n43SEqD4et?60TC7N51e2wQ+kI7OC^Hu0N2@C*tPj|+N^9V46<+jlbg`vH3Cq-=#lhiN)m|7UP@*u}aR}*2O'
    '3^6up@!mp7mV3W`8(RIs^{S*+Fyv=OA%(h86P|%=aK7WdkWqpxz&hc}AWth^jwC@3;&FfbDV4w{FA=>Kh`Gpz!|#vpW74MdKV&pf'
    'lf<Cv5=i-K;5nhx9sApN_4|Ii=qeVC$0k3y$AT@hTF<n|#U6@M3dk)<7rj9xOztH+7=~cAx9{kz3x(}Lnfq9pl7ppQ)?j5^{s>th'
    'OL&T9DPTnUrmLoz42*rBZ{H5A#XSn*%iCl2LOwukC_p)M^yHG)b<&yOBSv?R%Z@p0lg4F8#X8_kQYx5|0QO~6lcRn0XJJef-W8n!'
    'Xooz=;<3UTfy}{~ft~}J)M&<PTY^Q?pVWy<FTToxP|9rKj7!HE%R@Y-39yZIOSa9j1X$3Iu6k8Ii$XTRR~UUTnt&9gVC-apZ^Vn@'
    'F6AqwWX89@RH|QEO#fokg<I#BlA%o&HCCwv&WE4`P%&G4B_cyK5f;GCV1_lcCsVop8Eq~Y1Zuh}jV(a98DK>2_S7?YLq&Bec<e~5'
    'Qj;rJyeI_T)U-9dHl`tv5pYSNGr=qntywoJdqj7pu1#o{ep4}*e%rzRfNTTQuQ+wgYOnwWwdN&j_9p5{xbMRvRKP`uaa4@JEoN-r'
    'm;K|MF78Q_N_ORV(9zLk^aPUv=)B@Y=f$=cbAZlbB4K0XEzH--rEz57OZw~4i>bN4{?c(im_&rqxbGk-L?;tGlp<iAFik+GD5~SS'
    '4J<;Q!mul-PH-deX>l3|A|SPw>s*vap@AL1Q1rH`edNo;<pL2E9V6wK23r9G5~T3m)X*{dC~RRs6vEWkqNriJ7h<YF{pU;AoL+Y&'
    'Z#AiIxU)cOA(kWKN*dCMMw;zlTdomPsDnaL_NsLkWKB=EJWh@be^?|EQbuHrq#z#!tqPK=Ll?sQR?~}`npMB;0-}RR=&H1*5uXkM'
    'V1OM(MK)=oHtW&4(#K3$WU<|DNscQPzxb)1?Flwz^Kot<ZUp)~P7|wJA!AT{`Gn};nG6k(R*ZxiHA@5P=5OnMIjampPa7s4ad`kw'
    'Ws*F6&zakW`g3{xV_&ov`91BvU~m2jRt-1|*G9o7kC_>au+SVR=toI|XoE6*d<Y=8L}qC6Ar~c0Z;PJigllA^7bh)m9}8vwps6~*'
    'fl$lAd=Pn%1CV|w)mG?4&Vc1cs9gQczWi;*G^x;IDm-<(_ZL@3)UL}TMi&ekhHv&DcSle<;wNgsxpE5&k#l?1*cLz*Uwa7lkdB=Q'
    'T|_d}8B`VU?-D1kQE^g~AHJ=4X?0e;Y@8Ws^dM5xXlO7#o_7+g0W}8OAuRW>HhtIq`Qw#WzHx*0fs7M?3t>TC#-hUN<)(0hGL<pI'
    '3&go)TC;_UXO6N0R|5`mT5?RT40KKu0AjCVQPnfUJIL>^u<SGA#9Xy`8kHiimTR%cpMd{>lVOXVij0U(m#jMJp=O$<rA7DgRkk9p'
    'FYhXUfBcy<F@qG3ObhEcdS}c4&f;Pz8H6wm$5OMVixu;E#p7ZTeXOcWG1jCR)e0}8(ZE;)1CPh@p5f9!E@Gs#da~BnF8m@TFC!WX'
    'N@tn|VhYUaYm9Oof+R^Mz(LkT4a7wVeVi$>EWR(hbi#{*Z~SXO?dcgnULsneP!n25GC~DoouCQi->Jw6|Gw%%cB%4<!5$8dzD?3F'
    'p@_*=PRy`ZAxL8HKpO!YR=mT8%9T}CY|Gs0QT_=0(F~^$%1TS7r*sIDU-@G43FG=}%v`(Z!lQW;+n{cf9H{ur$-b!7$n3BHgLBCo'
    '4%l-jwo!9ZR9jpds3A>}NcXmh3w?&#v81r=1^jVKg1sVOL99vVoc8^wUOt14_46qvhjr^Ncr3;8OF`W`(UO7Vh3(>`*ez=y4j5*!'
    'R$?f*#E_uH%C+BAg`{NHm*pa4<d7zp(zE2(i+3We3KB=g@uABw2*cu3xom#=R&dN>?je{q7&`$ObdMZo#8R2|KS{4gg^D;Ate|qa'
    'ZCosv+?T6?G6Sg7#@Ep7MtB50mPsY*1hC7~cCwo#1*|<z=Z4EJy;3e-&*;I^LBoJCY5!6&<M$`OWYpV?$%Z>aNkNJ|yV`|+e|^4w'
    'h6dRhYW6iMbt5eTev=4#N9DCLV8n||^IOKs_0B`cHpgcWh^r5nE{>D*Q+me^L#L5>z_Y|nq{Id&PH}@2AlI(@M!zk;S_8>WKmbOT'
    '1WOJP${4T~Di|W9XzN(DGvgwxUb!+-@yXITfpw7h(LE`Kj7mG&-;6YZX^Wg2RbwvtVSitLzyDI`V=m2FE_kfyXX$S|qG^0Ju&IR^'
    'CeAOTJ^I=xp?T{CMHC;69Fh@abMYZo!)K2h063gTK?+NC4)40JUGMejv|Z+uUM~w7y(AA>(efnV1y-BY!q@ywz<7+CY1g#X=jm<m'
    'XLc-Kr~CxaCNw4aLJLyXC@7c&%u>N+4{t6o2&!gapUNHl;E-IkJmZW=Z}8%Q@Qa(O{Ah*X0p@Z0C803%#F)fTx%|Z!8E5sU)8_&j'
    'Ah8FYv^XlFlc6h#RTA|n@tHmxuKNQ-cBCqm3m*gUQUO!~v*)gjkT8S1Q1QI%1v^k4z`&wHRoJxMngw~r#Sa(WfjV5U7ctc5+o9FQ'
    '@Fpj3f5H}$I&e0w!?}80F{!}vDgbI=L#cHshk>H45C}O96Txt(Kn8^xo2C6&8>PRy7yV#Fb^WKKh6tn8EDt_qPBKD$&~czs&NxRM'
    'XAC*P*51Kq%odRR8$8D^g$$lxh+mnwSwIh(S4B?Ayz)$tVLReY;{Q;aOJDjiOMaCKve#aQg5(~f9RFxoQG3hIbs=aXA|#4ZFs9m)'
    '<=o`H{#$vb*n?(VhnR>&%_*FkF`T3TJY3})06@bSSFN~#GjsJm1cAj@5eIWk=VfFCmj%nilx<b{W2QIKxI<pHZq;+fvpw!B^t=oS'
    'LjBE8Y$cttV)UplFjGNsnJ6>iYIa@q@5Z|9y#Dpf2lqQlKwQd@e)2&rU)3VuK;K8>mLtye%upLfUSAd{@%2T7mO@7WVm6Nzdty29'
    'k>m_~+0+X3Khz@uNzIBawKv7tL$j`A;45XWR|k!3$u1*gXpA<Z=qz$8>KJ^7ljU4nuAB`cWh8oV74F(hM-q#ebF5hc3sIcAdDLtY'
    'i7?DU%Z#PW09D}b&%^l*f7<X@tj#wC(#$OG9_?oIilYT>z|0jJFRPI(Dwn8XP!F0l3%^aOx{MsTe$)n8b>mCNO$Gm)p9>NouY+EL'
    'EP9OxCyux6s`W2U{dLy$GRfk}OMC~Dj1H$|MvthkM$<*f%L4jrQ*`V5X$KcX;z?fS2drN}3kn{c_})y2%V>yTeFsk(B9)GW(dZtS'
    '!XR#bEOHZm+C$aCJZ9SaUSJ#A8hTDpwfL~rVx>ofV~}i)yU?#*SpRl`8iKI~cqSPOEJjLXOh|!rX-^@Izye4FL+0X??vV5Rn5v^D'
    '>l~*2W`I&YB~BbdB4nu4J872Z_6Yk~)b+xOFWVP{D5XS<(n*+$*VM>f0}7V%pWztfB_67x+Q?;_qxZ&E{&+!&H-ajGrfKiGPV9^*'
    'lSew{RKsN00GL42#U{YnLSZ?wOMm{{_PLIyG4xQ>6e>kdh!>Zg!m!hjGhqLShK<?=p>OGF9_bW6yYF)mAKpj_-`)4BXBQ%|c5*7v'
    'gsooFWdS2FbZHsPs7U}rL{;L;q|}-X)yy_TNQ_Y`IyQ=GL_Jos6DYsPPJwl?3DJ}QXe;eq+o_u(>6zKYXk;{DP&w3N2lzrlXQU44'
    '*pxzjSCl(n-^ntC@x^TmV*xoZa7Wxy54QRsNztKFCr%GzYQzYGf>pF{xoicPTP0|XeJ%6<7(aj+Ggh(8S|p~UD{55edr6#N4-*as'
    '7wQ&1sQ^Xu&TI%hg<^$3_tnd;*GYR%XLyqK9;F-uQaGBk6b8{&ue~T?&o^v39F~a?^z2GbqPS7R+wt&Pa5)jjLgHmS&L~EC;NZXH'
    'K8R9RY+@yoXa?)W1wdmTmpS#g*E`LDgsLkf7}^=$ndPwuKknf7S0y+#Kfg`PF6|{Gl>rq51ZZ}gdjarKvP3nmG4)@w_=?j<FLoBW'
    'XQ5)Ml4ztx<`b0V9grnWJK?C)iq+R0LDZlGA@X-LJ$N^E*dzi5@ldEMG<7<F?J=>ZblE}&&zm3Sw%5-Gf*cQO+DVTMyNfrjK{>R3'
    '8l>X0^c3{#LF2;O4O}w4s*$8%0*oIHlAr~c8RXjx4V!d9L&2G82T?$`#raepZJ~ZF6d!<<TMV@<eF*MpsAYhxBtc%o4Ekjnh*`Uh'
    '`jMzv;&<W={~OVuyniOmsR!sJ5~<wlsDoT_IMfF_cq7YPuR0ig1v`PPf!q%T6BA(tSHUtvtbnUbr$($Rf+m04LR}LQqCSoztxu3C'
    'nL^412>uEZ%)$V{bO^;0Hbq7Ezpnl>({S-2DP+Ka7c$CW;3s%2d<{BPq~Pk~NKONc#+}%QyS7n5c!ZK<=0MR)N=nb0w-0*=%`_H$'
    'Mzbs!6bx!QnY;E;Jt37TClo=mAS9d!Fj{KmQ$8z`rI&_V7v*X0rq!F#pwvy><Skte*rhSL7zxz`LQT{rR^oU`2eqe2ku?@~_Ub*r'
    'ui2%?vIY{^l;<x|Su6h+W{5D<3};|CsrWP?8Sf_WnIaeA-3=UNDOb8LXof3ALi|WSVwNqjSSCqctvE<BU<LC%+r+gY;%&%f)i6Jn'
    'nHH@=BhTElut1j4NdRBSN=At=!|GG{wuS1Uu@K5KocCUm7Rom}EY~=oft;B&&6f77#@^hxkMHwYtBl5><T8;cx0+_%$`r>dog}A#'
    'i$k*)>X~M7wr=fa&aHLQivTrfqoGlULZi--x=_pjK!f)JLDHfNV&XTNs_Yz0RuZdQ_n{dJyCuWoqAE@SrR8lkVlbLUeq%kr*|->t'
    'D#guqX@ZAhoA!gfoHJ~8w5t%pL5<2(H53*yqUY66c|m<Z7zqCmHUuY$(%hQcwo*gn#z-(|79qCtSkiILQH2Kih{Hf(Y;M$$YtX&5'
    'p$niKgRN3S0{#>fZkiF0nMvrW=M*aGfN;^##D?)h?KOn8QR8Rrz@`d+@#xnfiUHd}_C+^BlLD)0RCt5FR~X&|aKNWw<yPu^tGFE)'
    ')`Bb)VkoT=1l+T7Te<HdqUYO*<It_mwe!>V@iS-P^>U#;L(nYf3Xsxs3I}yJnLq%PhXBnW(X=8)Gq{1if_S@Yv#dv9ZaX=WD*4^y'
    '1E1@*D5@Yx((t9<3%YIb_5zC`inXMHM6p)&NaU|;w?Y($U*LAHFC3Gl7ToW1VVoLpK206cEI2@LIN?n5VPFyk>7s$-LA$aGaqUB4'
    'RP64(tK_G45{$b+4yb^GJbEYww3hI8!+IRJnQpCU;%yOZ{nw>`=rJrWWQ`|tqoHn6(rdB^eyB9m5Zu6`9Z=HK+9IxFb?MiBvhcXq'
    '5x5~&lJGQ!!bh_^I(T!MV#b}1d~nd5`XE-yaQi-r+%3jr@PC-Lj+YW(a4YU<mYoWN#Hd9?O@zI*`X131RtXn6*)0Qr<FjluPXKFJ'
    'o{pHA2xxtxEdsHN>ga}jtPnD=2#5@(U&6(DDCO{u85PtJIVZ)Eelg)`!VSBqloZecqOD6FjM$G(05fm-UzDk{N>;T03<<)5V|A5w'
    'R@!YY%DYmD1{G;WLr;wgYDYK)*bbr~!}g|AfHKhx2_E6vJ*?wGQwU>yLbTw^<Yt9|hT^etqUw&C3<MLK!?F575FHj%pG&8*JnRrq'
    '9|AO(2?!#YFk%aV*%Z^vNKkg;WYM<z16echJ*XoD;ZT-F1P7>Kz{y6f29oih!N2|BR;Rz09q^4RgjUU-reBLj40br3LTDaDb4;`t'
    'sDWTjZex+E4JAT*+eTjYOGxKt+lDU%^9KM7*sVIHQm^p_C{RJVAy-i}Y4m#*7iGF_BMV)i=EXE5mDn#NGI5NIG=j||4VZK?MU6?I'
    '?izl$Hd^eozOY3RCt&eoOI&D5aXOf241EFeAa@rVpr4Hm2vZ}B<g;Si`PHAwrM<bXuZ#!^o(9Eg09{olRg8DY&+Kc|giwfwWJG4X'
    'Z7*v(%=i@oIU8~Q8r%R-zR?CjEtcd=!8bk1Uc0saw%wd5Ema$VngutAOASgkm`1;Vz{_|uD?4j?Q%1D()vsvLeqQqPN)0IJ0)?W6'
    'glft$gik*Xq9j7#cHF#JVexcEzcv+o*@pf1os`3>EE`F~SVufpG-b$~c|b<=+fIrBEL9n==5E==`Mo@*Jx(?yjwbVjp`YM0!u$*D'
    'iy%}<&;{>BG;i_`3EIlD9^T!?C7fWQp@|CHT?unxybX6N4JlHgAkhN%4F{JAJg9+SX`rc~jc0CpByZpH3XTfB3am4bGvr3|!ic97'
    'PrZ@Vkjbfq3f_R7ug=?-?fk%Ht%gXUo>5FvRFebIG^33dxDT1}z~zeslKlm_|J<~lH)C;1?8h4Q5?O#<7}V5r15$M+mk>}W_f>&|'
    '5z*nMwdZd7hAu?g+UH_4n8Y>s*da)uoym0!1Qex9qzLBF$X&O|YcJ)$?jJGt>u@?8{itWzi(LGGV$gzUP$Lp(Iafe&1IUHov^H<#'
    '?fA4{*{buH&Ri@eboBrTK}Nw62REL8IT-pQ7}0Q#v2cKW#dMpgU%!!vrRVpD!K-@QE`t9e35PFc(9nQMT5xELyft{M$VdSt=nV!5'
    '!R)wpL;RQHr@5vJ2Jk>42@zg>NVqfF7&BRU91wSdhFU^vA>ORrNIid7lc^njUoqeba~S7BLql`7I2OTs97wPc1+0y7;B*(W_rOqf'
    'hdF;?7YZYM#RAmPTcCdcq><Z254RLmq=G*Z?v=Z^!m$0R%;ct-b;}L{^l5fj)fh9a`A&}0X!B&MlGlDHs&Dx`G!U{hAOY!i9O%8H'
    '=#dAg23BA@ujy+zUy_nA${T{*v=#xmkX<(y1*%MV3Z)I)Y0ly#n<@~>UOYfJD@OCN!2s|wR;zekxs8jM{%to!f(|_d1AT1hMf(#U'
    'gF6M^0x}eb$eBhVz&3b#w|*NK*-B<jet534u7@r3Wsv7I(h&x#EYe}njG80QHw$|Se2$NHT>EjJ>A)|k5E?ww(CPNco2p^V6>$?v'
    'E-p+~w;b;R_>R78>~C7Vj*L7BFlA6{OWq+vL!2utv4EaA=p<cG_BWBjuYC`Td)V12qz1|sIVW=vG2p@eh0$?j?6WpSt=DS!CM<B#'
    'HcGo#7m>W2co}Grc*9QPjS=S}X6)h2P#r*GqqK#uQd;%9g~j(v>N4i1FnP#{^p3V3_a;YIiCz{hX#+n+$}BYSL3g*WUcJJsjgK2f'
    '5JXPPyknp}y?B%?Jbk#?BW@NXRyh^fIe&R})JH$YTaHj28XWCOk}RJWng2ke8)7N8Fs*3OHWl4=FJb1Rd-o>`2L|l{+eD~$j9+QF'
    'VbNg)4Qi*UjGPpKINj%Qs#~!-u;E6CAvH}g`Y>1yaoI%d=$KeR!Np}C<RnJeE&kBu8?MU%J6P3BN}2keQM5CBV`MqYFbvKw<TGZp'
    '$xCgnT2V2pj?j<J99|i>hzCn2+a&3Omx~SMGN}nRLreQ*C~AU#ShgloFoz|{c5&1^9qJRTdYM(KV+{g?@*GADs7KN9@rPC6B&!d7'
    '9d<&b!rWNCN+V}SW~XtSkRK5v8jWYc;fN7B#hUepRV!}@q#>rq+Q-SRiVidE`~f%^fje&JOd0^qVA4qu7yjGA6{D2k>f-W(p=+2l'
    '@N|Sd1SP|P6bux~6K?>CJpjT-OP_1;haVI6hf`_nJ9#l#kS1l~7XfnAYBV-DR?szo9X4@#psW1hjYv(I_lIZo3{hver*HpJkO2V`'
    'FwUJqt|9W%t<-#Z22MkDFbW!r0o(YoqwJ6CU09PsKuTWvn0HF-ft~&Yn2q%vQGwi-G=wA>i(l2-8FRE1%U<yQ^4jW1G9EGM(?QNh'
    '`$g{g10#|#3d;$snO$(O)~@{qZdYspoCBUXG(4&x`d)G>WuT=@3(!R;=_8T`Mt^v!sd`S@!vp1EW;*OYen0MaSAH@0CwyF(Mw$_V'
    'u1>@1F<(idodJ9y=gaU!Kg@Ah<#$LK4@;X9l<oav{NvrzWQm$!S20%#NU2}$1O{L*Hx7ywqO(pA>BpRWjpMuwxjsH<2IfCbf1a+5'
    '`e|nnGg`cnCx{q<lACmTl&2szUC4Wg9PP)7GD6_P+mC!-kn!V>qwB!_=|j-EWr8Ht6IC?>`lzpAn&Z_JBr5uNR+Uy0pIU$Suwd<l'
    't`w4ONFKO8Q!mh|WE3H^Jt_y<gacf6Fb2%pKdhUM<W&#wIn-OY6t4Wq=JF?-@7@8|)0aVWgrT(HLW!jZQ_|o#Fba{}MO+6U82C8+'
    'vyV3M{r4W!mpzmNAtGlgf(hW<NM}Q`f_)wO`JUMl)a*{4P|Ue|?*ysk`pLU5oYU|Bu@H1+?9L2VDgde>hZYj$yoJ$(8ATxS8|h)^'
    'zGAKOjLXyi-v6)kw8Vq|=}w;u7%XQ6em)5|g^;jVudgz?WiFina^ALmzaTxYPLm{jez>qR&;;&Z$|^{l0O5%sY*kQbAtVG1p~AMA'
    'c+XG_^neIZ-z9&(x8~)qCE;b1w$AB;p%s9C9R)a_3d6%-J~H;8(~$9|u;e+*|FkgZ3PZ3NUJ7T93$B&j5E?^A(gIZst&(g;5Tw94'
    'jdklqlHgN8rlqfgN)gL6=xMa?vF1Zcjogwcrr75<qJF$fNqc9#$5+M~78r`%?9>$nZ{)fp6U1c_)*0PDBo=s05F6mm&UNeIQ+6uN'
    '{v0*22;V(^5EI7XEc1LdErSA*Oi&K8n#&qK{3OHn;p{hX{PcO7@fZiUJC9F$*%zV#hHNN9u{XrM6|pdww`|!6Nnr9|iZGQ4N}v@L'
    'OKYt%CxQv{jAp|>TQ;3IW?*y(D1$<l=2hpUV8XL>cvnC5w*?OikX-Vo#?A*nlo4Jh_91v0BZ`HFizXG1Rth&*u?^CeCRMEX`ch=('
    'QyO*<&;dPXQC(=u5!ZXQ_Spnh2DpP!Nlosf)nby*HT33hB)EM2N10|7zsX)ET*x3ueNZd{tc(a$xL2Th4^n(1#O2MJRjV?+U|Xn}'
    'yv)(*NTA$gNp1~F@J?<P8j%FAgMn^?Y0|1?ix*gsnx4KDr0OK@3O)u73YgrD09vh>aT=as)+~Ci#joEcsEq{s%T$*c4ScY0Sg065'
    '($N2ss=!;N&-r1Pg*WuDd>#+~d<Evn+w+{{ikC||4-FI3Y=B-_lE|PGz6NR+Dn=PdO6L$he##%MTtgE<xPZ9~5rH_1^Bp$}{wt(`'
    'vMZ6|1@~i2q}tWL`g18Tae=}3O_Dp(_cwew0l#0eB?NX@XyTYj{fe9W+J!5|#|osB=ZePI;(Q01Pe}^OPabS&tr&nkrVqc18J?Fu'
    '9$(V~1Q@cH#YOSu<Vtb{F6@>Q#GOjU1WBuvke{Q?11B*XFe7VZK|EKjS-#_F7eJ@(oy8vkVSv*B9HAW4tX!=?IxQCvxp38THCG&v'
    'D@i?rR2X`makV90@hzc$pl<>a;K}nX<~~#9f~QjE3AGP(EUytYj?DELNy@Xt_)K3hPm?~Pz}OGp;RRzj=hziF5qsxW;ez1~&vFCD'
    'V+4?cGN1TQ7Z-jAl}2B++zZz?#b9B^LA&Vv_zIXa#>8A1O*H&H<D2l~R`@mYubrw^d{3nRQ=Dhq%ET{#hRu{dz7L4_MlfJ6E~S)+'
    'S(vh~TI@WLr$B;2Dm80nGTzH0ObXC!FnnrTm=kEql+|)xKl~alasBPDHRJU}nnq(GEOi!VmP?!t1r7+HtQ2L!d)bSdK3<aiXRCPn'
    'upF1;n}<iivBgYkZS&@6OK?nhi2QK=2L?jy8~L|zbnWU@%Tp;Jm610S&zPG>LJebv;7XWb>=jPPd@x+DAUf^(rD^KNeZJ0NM=`3o'
    '&oa28L#X*{SlM?(2w*u58bSlVsH*E%M<)2kQIx}%*8&HWSzkn2h<(^Q^w>^CszP2b#6J==8bS*6U8rBVB0U>1OBGH}HArWKRzX(n'
    'DMbNJ*NVYxA%tednymBBr-Edgx*{7PDo&Qx07aOvkfMMD_HvG;NJaHEuU+&a8!yaHf&~GZj95d}5($G>KL|yh$WJ(#a>tO&%qtdG'
    '#!xxUi)x7~O|54{Rh^M^ghA{;lSB~`HqCyMk?x9D4ED%ZadKy2*PjK1Wt8?5`*;L8OfRw;B8DF%!)jYiI;QHuWUc?W;Q0IUyO(FJ'
    'd}M@aVWb?sJFd|LH4*WcnI#sQms=tC0yH?<41f=OWA$raZlklbt}wog#v6$d7H(>pXr#M3ae}02l+pbqzOlPCAw_?_`JS+EOWfH('
    'Sb(sPPM^0(m;?3<7(})z_^?4kUT20C4_-Er`H8^t7Tg{dmgc8Rh<p3fPiJxNr%Sr9y@*w}b!|50?9rW1kh`EcwMy?nSs69OA%VL9'
    'n-S3j7oPp^-}YY(=gO^*pv`DpLG$2Pz(4YW62WNbc)(Z2t%H(@ORTHd`q_-~gJAlTn>!gJ{agd$t=Eec5`#z3b|5*IzE^XnxIm_w'
    'BQBK@I?biyP*H~^8D8`KP+@{uFe1|tXdG%Z!YJRF?omFonwVA%w$ZQPE^3%&OX4NZY03#rMI#fFZ66NMNlvpLeo`8RnV5sHE93$_'
    'YQJ8RZ6<C27)US#LDj-hfzTF2<)wA>VTE~i6MFC>hPXq`@4_;aP9y9!Hvz;_<d9pcH)b_xnV>B)J{^<~^Yi23(QisWYt*cAu|Aj('
    'gE>7>fCRmvX@hGJ_YW;*3>;GT;fE!`)x#NFPk7XRirc)*Fg$Gw9ZnKgx=fgnq4AN?BeF^PbKz<#2!R=^BzVBkZSBIvWRBTZ<PW4w'
    '{2KM5)OZ>@LC=&q@Dp$;S{!t17yPMazFvm}O@E&FX)~VTa6gc9BuzjHlI2;=BI2lqv3BJm`~yfRc?2bvXu5oofb2-QAwybO?HQG^'
    '`F$teWx-{wH_Mq%ZfTwr%tFD|sjZlkCN6y|Nd_=&5;{!OVNnzt_%D5YSbtuU*!tF8ybiM?iiapg-h$`Wghoq47_r*Gf=1L2>LNAa'
    'Y~7;Y70B1WN)V4m!^FY6ah4GYTi%gi{ea<kkV#XC&y%ZLvjS=n{>yidA-GuRkUA3MUo8Y8+^k5IrSj-SB&}Oe2=ud}T|p+0=W!V('
    'z>(F2Q>y__txOX|=A}VRj{ZIu{=GF99&t_Mjou(-4u=O5H?#<|MD?_xI6VM8+*x?f!ee@urg~-F!u$d>1{$Np2~H^30X%RdnNX9X'
    '5kXBuYCcoPkL#9%qrAPI2TEs&2PU<&p5`o$3$Q6VezG#DVO!0L?9<9+-?EwlOxwsx7k>-96mW&Xu^UdBlWd$mIqGP3Kt)u!b`cms'
    '_DyYt{Z*%4hSZc`cv-f#1K_2`l0iW;zIwGHVMv}OoS|9FR@!<LQ_Qu2eMc>g5gN0K@z~{<jjL9CZ-CCvkUK8lnwP_LKg4MroW4ff'
    'O@@3ju^6fyKmr$!say0&`sw%AM@0hJF}rUPy-WvqX(Pa`7PT2lnC=-;A~)w%D{hLYGv*GOcC0P}t)WSNDHEJVUg4w(XygriIrH4F'
    'U$%;^Dy9QdHxMS{8U(ps+(oA8NXJc^6S5s=m$)&lTYk}86j*4~8$f&jiFiG#M-6fy!%te~1S_i`#h;Gr);%j43jPj!sv}$_xL`dd'
    'y}Z{RaG%y7lx>0qxW8;&YY*0vhQi^z=#j2x^UbhWjyvUsDpuh}BgqA*fi(_Kh$E*jtMXMBqrV1V&^w5VgB&O3d>|ZPa196?usbQQ'
    'U9^OMJJA32KmHF^p8Fy'
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
        accepted={'npm-consumers-sync-ci-v1','npm-consumers-sync-ci-budget-v1','android-owned-npm5-sync-ci-v1',
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
            'npm-consumers-sync-ci-v1','npm-consumers-sync-ci-budget-v1','android-owned-npm5-sync-ci-v1'}]
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
