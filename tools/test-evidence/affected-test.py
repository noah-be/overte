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
# 122a8855f94b0a30102f10168d4414060c758ae0 / tree dd0ccfa63eeb5eca83874644096d4b2b4da489f2.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '66ff61a605bf75cb6f81da4fc039f1d511e22bd10273bf656f4e0952cada4d26'
_MAIN_PROJECTION_B85 = (
    'c-qaK-F72MlAQ1L7=68*%E*lT+o#ac(LGN5vd~2m9008D+CBU3`YZvmS<@sU5~!6VX}71VTN8oINDp^&GxPua?H~8s<JTAe#XZIS'
    'ZX54*e>|oA-Er@p4ms`r@%v%-^xMDx=Wma@n11{B-%QgC*8cWyza73h{<a-slT0(@80W6(XA_fi^U&tpjL`<4k{#R0=>Nm<$Fu$m'
    '{KL-w_Fw<@wybBN@b&I__pl8=3afeFMPr6E%wrQ>3ezx-tkE=Mle@vkCXa)4&Gh+d&n|p(_v!AB-TqsC*!^*LpZK-zxZOP+3X7+1'
    '=-Rfo(~w&i$JX>iv@VTJJK1gy(T<((Mn8YP_&z=F4%_2y|Kl!vP2pQ<#Xj)xaxh^ulOAwNY0kaPjg2!ube>$-+T<@h++#W%?+!29'
    'W4ep!IX%Vn6t=0fZrco|pKKnpY0O}P_p!5m8)NU<aUT0TxY2iQu35LVmdjo6bKef*V0gX#;Bqu=<89m8Ci*#r;9c_O^R-@I<$;&G'
    'Pfy3Yf4;bfZQh3Et^VW3<HP5x53%K^waNOS<M|HF(6qKUrXQo}rr!FfpPk04)%UyKQ#jt~w;wJqJI!t5W|PJ_OsVZdXG6p9PSFjf'
    'iKB5t+q3Lkv+Umw)y1X9Jo4Ri+4TKnk`El*VeZ<-I2TNuLLA39Tl>Mg^?Q~hGK7aMPx(vOe)&B;ecL`AzT7*#=jR`vuWF17)`!q~'
    'YwhS;JH;WiX6#esp!FvA$&7qSYgT>cm-E6eugf9slD^WZ^Gz7rI5m0VJiEc?b|gqmP2z~HTX*L#ubN#R8(!*YGQY2FX4kYG(ZPl}'
    'O*V|#1=mlVS+nZ?<>}&@!PsFKVs^8))5y<rb2l{eWPF!=YHjq*m~vjVrcUxEeBJLJ)8-I%&zFBSpG(v5WS!}TfpZ<w?E21)P2Wy@'
    'TYZRgoXomsz3kx0J*ESJJ8kyKJ#U}xFK#1FoZc{`ey~K%WNhlp+*<2`9~9TD9gH<${eyUVe%yrJQ{G-)e{?1d6M<})j5F;N4A(}}'
    '`@v0o({01%M)ugPUSIce-2C}H`-|&)&RJt^?0Z7>&^J7Z-px&Dxgj}`9Z#W2op-C(=LB+9UR*nc+)a*<+4JFX7lttyZ#rUIZ-Z;i'
    'M6ey2ir=n?@`wBJ<tZH%={Eb_%Q0=@*4;nt4##b{9BsIby_=FXedv?r_0LmEj;pij2clkxzICQI^XhH9#OI3(w-dKmGA%a-AAFqk'
    '^x4S}OpYxdLiU`*G>+8^pAO!6^(8UW5j>_pkCy{b&&NI{*LHn3bzRb?`Z<lhk9>{XsiyJD(u(_daO8!@-Qzag5%#`s58SAHfM488'
    '+#WaQ8&9|F#V@k&le4jPWP@EM8pdd6?wCn2(G0y_22W<ZdN<2gsgL8qy^u>@j#A^$1#bOew!DuaI#1l3r*_Ucj$M<DNe#(XbNyys'
    'NGC5x${3uPLOV>k>G|!h5ADd+z-L0b*H5{3(ROVzSMT9l+CQa-&GMEm?qqH~4<wEQ_ddyMwoRLTY=_>A^N@!$k0a-|%~$W_(LIrF'
    '#|=3?M|uBa^L2Yru5xi#jV`Vs+sQX65Jtw-bD43Ak}DYUPOdV`Q@VavJI}xLy%5ZX(2<IU-V-gYZ^x0->$)a(q)&+xL>wFRPp{v_'
    '^SSbH56f4*cj0(BuuaiU?P%MH0&5zG>V4mhAx`9r9BUHhIi_~<^VM4-r^*l8`>)69SUZeeCZlSc?LAjZ;yX8!87Jb89#HHWYPLN3'
    '8@5zRw|D@36Q*XQ0__H>%~n|#Sr(6E=Iu38H%(m|uigS_M<m#7zw=>l-X78AEP%7(d^2b2H=aQ^jT3R-4+P)rjUmni;!kt^V>ul8'
    't}Y*znWHgkX+L*U2wXyW=G+Dz)JQowj(s=xH+)4$x4%!-w?HQ0ZCr?CA9>)6BtC3o$DTtn>In_x2Xm9Ie@mxq_4O+7yO*cv3W0`W'
    'LIu{4p7UB7id{EE{%=17+ZsRE#u@4an|{%rDz2w4Wi$7)rzW#qnqwatpJOnFlRQO^u_8{$&5b)+?x;;w7z{o6duzBbxfrJwcqb-5'
    'ak8m$T-SAd?=xxEjqfczec$ePPmlbIr&o8mtZRky%sF+P_r4DUSA=&1SksW)<be+|H+t-D+f(%|IypPKj;dlDe44;$qNTbe0i(S1'
    '<h}zRJUg<#ZabSTN#OnI_9$e6-cKAT@T$-dh&?aM&qJ6eE{l#k&8OV5-P^Wy)h+Kw04)+?&Ul{3L>3ZMCxVTDICZ1VwsUa~zi4Y='
    '_qgCBr3W@-m%5om-p+<VsrNaNG!wqr?GTO6+_O^`f6cBA>3e!ARMnKMbLjN~DIy5~4bN+84A)27r3o~&Bapk>_EQxJNDuAY31WyT'
    '&tV1yoIBSHeEb1G)(pH*Lz#QyR^DYrkK39vKIf)$0vNgkhzE2R#@^4ygJ>mo*R?L0=xn}iU+YsN-kT$51PAE>Hi5Y^;G#7{YdPXW'
    'H?{20Hre00FY=>J*e9^v<JLVK3g`eOm$fYy?KFGRww!rb$_b1o*)@Q%q)u_Zc~3PdLC59K!Quaa7CB@1=E<so^g(XAX`nzgZj5bv'
    '+h(rF-pC<+2KgQazA(yW*MpiSfNyJ(1E%&Z_n>LRZ5uo6UiN@mVfQtGTZhZp9P7n~qR8=NgtDdB&4cOetP&uHIr7i~5YvrYQdYUC'
    'C}BaE$kzb-+OelH%bt6t1$BvC+b3{O!qe1z*!Nk#o$R&`F9o1?vQtPd^{%nK3p7kda$85v5?UTp=(=g9fnshv*T=`_ynRS-)!OCH'
    'f8^31I!AQ|97Mz%fMs|ro_x0vBui(f?S~sr_i_JnIC7JGOF#A{Xq0cB{F3k6`eZoMGw&$O0HuvL9I7;B8>e(jMX+Ks%Ceizj9{Ye'
    'JZ0WqZi(U6`i3toc-!?eSVZ0Re+H?~|K##*5j)U8js@uG*mGY{&^KhVz41MXEEsJ+g=wnGu<u`%aF_Ov+rwe$Azn<z{5;c-P@^MH'
    'iKZHTOwwpix66$-O*DZbF{kb)f8FWr?{=ktuM3)bVsi6ngN>nY32oHp6E}ElOazYOGpSqil(t+Bon{U#A6`fMBPxpm_)Z3Z3)m!c'
    '=g?PU53w$PdgAi`o;EH%ZZF>?bT&vnh=0bn!$9`~R3hd;kFDeXbpTwJf}ye?IImg*CN>S1IAxg%q%ov0P}p0(cu)|*M}cyUFi>}v'
    '-hWBeIY#JAYCT0h^`WX(IzZ9V+9TKCV{ckIsDSX5_2T<}PtB(^MrsS&#n^%J_oG#TpJuY>j!&6mO)X7r7RMEfp9<5k+o#R%T#rxb'
    'at)!-N-(3(VQI#X!!Uv}&y6bgnP${Lo$5la#OU7d;BogoEyXBTP~j>x;F4q8=EhH*6O2n*L(-|c5nODhY9DDl%&vY9>!L~sJn^RE'
    'vu<d8bu_wqZ*oUNmoF`G0VSvcVfOXwSB4f7GqvO7RBMByj1ym+5I42X`4H_ycqi}f>K8u6mx^aj4a9q=ncH%GwT7>7BA52`(P_MZ'
    '08qKbp8n_BrT;2nFW(_FvK!JKN9rmpWNgXoCmuY2e#7fF;3Onu`TFJ0-M;Yra``#%-I*}8{3&l8S_pLpH`xG6%sodxVH#<)%vWrr'
    'Zv8IzG&v1fAI(mZFS69k_t3Tc!Q?;}hStYs{ShExU$`863T}TH3-X?uv{jdtTO|<k`kp-nXcZj7L~xwQG-C8uZ=vo<j68qVYiN2q'
    '$Oe!%9Bcy~zN0=)-0UP*J$c3z+xT((x_hbvG<EnX5&(6kg@y%1DD@CNs1wpekBRD-=Vh;W82fY&rbD3;H-GHi^K&W73cjKI%^V6s'
    'fiN&GN8iI63RL7U#yBtFJ69YGfThb#*kPbf8(55VE?Tt~fd(_(w$>{|g7T8~rOM*%OhBkj2<Fkvt`oT=(~L;5;YPBcTbAS?_MR@I'
    'C@^`&eRNe;K!2g9=?$04@smBQIJ%v|2?})V1nyi2LswA^oqqY<_UZZM_=UIraAsBAk>TI{kx0CO)u@Or?uK5Ss#M<ka{dCDJ*6Vh'
    'ng9{t?#yFp`-&{-r`@pnU5X+;z2BHhkBvL((UpNCN0msLMhzm;m*Z3fzFx|b(NcTRCr&!G72xP+8!M4^GGBo5Cmu^Htbr>u#wk;M'
    'jI=&`A2I=Ks-Vm)m-Q>T@$!<SYMf1Fr!;$s2<m`)YOyg*9=N)PkT;AjS1$PqjVV@ccn@y>xZ7`D`1cA~OW*P#a7WT{0S^m9Q27Vc'
    'I!~i98Jd`(7$uC??&DN>-krG;Uk>~5|C&5f-q`;&I?3l-IdMu<U@e(u0na48ohIm+ydt=#mXym4;28kre7`&!H^8x*ZrIK%fUs=q'
    'a@K48*g_=?ftX52<@=@Pu<$1`=`i~s`OFZGuH4K*;yj&h$fWL2eSG4;_evU=TA-*laT^C%CcHIjZx?(1h%9lapkEdD<zKcB@r3`>'
    '0<J{12_jJIW*9*9sG3L+7{^fv2pAddmQMUkbNlAbnBBX_R^XxV+39%^5(0cpkh(_QV44gta)wrn2a{%d`^L7kf%dO2^-Mayj4aTn'
    'YGKb!bjuCAoM_bT=x7+X@af<eLO3_m{0nyW#GUm()5Gm)^<6$?i3sh%qUl<b>VcgTJ!$g;DS4<d)V#Efr{4Fs@9LEF5F_4oXfI!?'
    '-a+yj0T+394S_21LB^S*#)*S%3n~EWKl$6YwkCE(@(j*C2Os`C@w=U9`a^J1D5Zg{t_Ss+`vsrnIbGjAE|u(yfBxzY1$H!~$$>D>'
    '_5yXR&;&9h2Ve{VfD)GrN2G243(nZ-Dy)L9NBW#Z39y~e0w9jl0-0tg<IT_pk<?lqT$66!)M0zSup_oeL8yEyKFS_ok;{;x4?x=j'
    ';!fF56CVSut3aa50|Q@8{|$RvGM$RH`;?-Y)n0@AI&=1@hN*}WSZGg)2pcIy(C1(95xfckE^jB(KZXSgBui=oG&BJV4bohYksATh'
    '^h>!BuH4S+9=@!*D(UyLD80Wfdcjo_HxnFXh!Rk@Jg5bztr@R=i*LJHF3JMyM$i@HZ0<uxoU(k1B;Mdy;JUu;BvgRdeDm`;hxp5o'
    'jzmUX$Cbl{3>5-|6+R0w9teS`4y}9!?X>-^d#U)$S{OAV^+CxPK^fug(rNeP!>AiTHv_sHM?ZVKc`N7o;pdO75CIyMOL?So;ye(0'
    '*C9BA^q={+I$oGMDgfZOZf(Vu00jYjh>GyF(DTp|rOYD#Gp&O&h1O;iJl<TWCgXN50nvG9sZFn~hy{>!;aJ9kGu@or1iGP=wo{mu'
    'Pt6So#L$6>gOgL%xUpNahf)zsl|~WLPW?!EKtX^auM?M<wo*ijK|whpm8<{Vm5nC)y$xyxo9V?v7wQn5%+&CZElAlQP#d}sX8!1K'
    'a{aldTtY2UOM@R0ms3$p?;kXgABJctKzi|<eu*B#M-0xm3)JFdneO4s2CDu$iPlE{tkADxSq^Xq(^vOd^59oJiV{wj9Xc<jcsIIq'
    'd09~oFJm%u%+Sv13rvYb2vsEvS}JZY?Fwh6BjC}?>Mk#HN_dw4T<G=Ao$m#+_}q_(+aOhvL{qeNbg2~m6QY^;!H*LBm7au(e{uWc'
    '7UdL)^1^gE7C7W&=Mm-|XfRg^a-7BldPTj`V$mwwOuLA7*~KN7lR{$7-xuj@MzsJ9eF(n+j#LAmH8wzQL!xk>LO&0R0UzD5e_QZG'
    '47q$xoRGb~YhbAX_>Qz02MAD{_->{e=udTVDEz*I-#u==b8E+PN&}2JQ&abR+JGZq{7}EZYO;f94a<<sF#0%u)Vw}rD=~fF>Mc^='
    'Js-7tO`_LGoB)kPfF&P%(qa>;F3Nl^Ne}<Mi8MW3Y0>DOkJ8R85$10z^7P*6QK_AHjc}tTP+afmGSR;VOCXGnqa>10x5iYr;^9qI'
    '{Y+8t_Q#h4TdR(0XeN#>Jq<)VkXL}v4LcZN05>#NIv?DXJ9vKHzC3PfHWI|vrkj+;rH$Jq<i?0odnIRz_0WQ$Ft~o@MyehHe3^mv'
    'nkU{`5k*J9fEIED`G;!<A0~&|0jc5IwZra#`(<}Z;m@?k^4UisER+c~+wA$YxnWwG7r^Uc@*zl}$2^hc$F;jz0OQSlqTya@IYRV;'
    'V$8QdH=nR(m5;$_uu~fHY)6n}FgU8R>Mbnipz2*fDL|UsWdfS0W+>o6^re(m`yb4R_W-8VR=<n?Ki&bIi^sx}kZdQ?3K)qE@>+gp'
    'Q~(?awY1ZzibvQ5v|hW~C1W~#qkFa4g_nozpH<HuSXE2Yw*opDNO_>~P>RzznJx5kxJ(e3$WE@@!u|8h<}3Wjhjb{wn)DPS#ba+!'
    'ZNthQjqONGfOI<b)>=4ryp7cSf_*@W=6Z+fUf>zgq9H0k9D_qT<gB(|RLLYRf<;b_x~A*Qui4N7FjX|81%~(1ZFC{GA=3FpEzzSw'
    'MyinX3X^zO-EifuxVZN)BM#ed{O#-CT}-^Ff}p0%mK+F^g$&3v(vd}x87I13QL<=S2<?^oIUx}4#{&UPHB#DscE$b-sWuRQ$&Q*l'
    '^u4<CJrt6JjfYkKKGL!`UFxs>tXA*Gw4T5b(2lgzOf3P629*TQEK-9LQUl3%_o1uE$NPEQg>O|Kx0}?%p{O1^Gr-k>zr&R#A-^<H'
    'S*!&z{~T%;K39u=`xHy;ODa_<!w6=<piAeBLIQ=b6bE5vhTw__H4N3?^Yb?B?3cX#^C;AR0Y5LtHEDK8=*T1JJ*q4gU4V2_s0YX~'
    'H3(V9IIUa%FUnN)wL+QhL^q{*1ZzxvYU*W+lZ%B*L~nEyyAPmj-A4AZTG`ic0vQvf5N$=V1Ayq92V9le4U!l{GG;=63h+|93I1C}'
    ')L3!HTcuP{Dr7*g*+U`XQYHQ5d?KsJ2`)i!l%!Yg;FRxFKMyH7sB#5!Ap)j|rw<Nsgq#?kAH;CD(a^58)pz~(9e=x7ER9sH7NQer'
    'RYUi#BLa9)*czq$EJ|2{PKp9YtitlzzH-5tkDo&aU28zw2Z01^4LG#7$g+G$V4++XC~is%BAEH{AE`=uMb90SK_5KV6)!r^(m1tX'
    '4g)tlnVtc?rvFe{a*?9F*5w7A@GJ$zOpn+k`u(;^FsASXkeSm&1DC%97)qspQ>T-r^91f>0NmkLwCY$>eIo)QYYE`*{YkqWZ0%yp'
    'FWsHn!TOJz)4xGx@KDiq6==%Qja2N|V2lu7Aa!(<>pXn8NgTEo!bfbb+0OP!jbAty{v~7AwRwK=uUweRdm`j>`2ymCP5|Epz@A9w'
    'ZklkmLe(J{&%@2XX-`tOp_fVzTuUY98m1-EA`HL_KzG1W0XjE6L8$M6X}VtQHTRJv(u)1OYu}I_<aFFVUcRQd17WbEAEE3;9jx05'
    '2_Rnw9bY~mY0Sufqq}BT4?G>Zy{QzMc?*r2^Z`#UYM#i0GO&awLTJTFa0g%k9%8Q9!{gEpq$N?>Lko@t`U1iOz(o28p2vmFndxWk'
    'hgb~l*T-x2AbTJ7u#XkbB5^ZyQas^$#z_HghaCgw1WN>@3~@lt03Z>@YxY5FRMq(N3qAO%!$HkGQwgIq;M0a;2(yutA7>ACM7wCp'
    'y0wP+s>88>HJj7Db^5X|zn_M?d7vI7dxgE_1(E^f!dZe600S`S)THaa9<ce{9suCHn}0q&6i9U>GssIIAab8z2t>VO@&BSqgS14*'
    '=QgEikH26m`m@WJ0TwI6NWVHQoHG1~cr3&ih_Nuo$21G)p5k!*Uc|~gI1Wnzy%CBD`fa31K@<YE#hU`YC7&Uqnea7%UXs!^8#%bg'
    'XEbRC@q<sT{StAXzX4CA!ouTV4#~G<`<aS|7MkxN1;VK2(4?zk|53{HSWy93)f~V^BRz3E=irMQ`Vbi4QEtHq9I?W&V1WLbO`MKL'
    'c%Trwya)JWl8HpHBaR6II0^VikY6Aln&p7&@b1R?&nA3z$5$DRI~Knc@q|IL#ZjiaOsWm80?^IP0vVO>7wIxZyRQ#tZzhjt>nI@H'
    'uLXnvLIMC+qTe&Zw^G}Hb|vfuBrVu9@i+vjO!YzRM1notE;}!^B+XP2)!cI-NrL(bZJYFymU|y2IyHD+kQ%9hN=&6D?@+*3Z$vRX'
    '{0I-}oVSI*7oz;__;qmucu3{COgdyJ2}48Z;<BTk2nY&UK(`Mh4tjwg1IGQLJyjTcK^nnF4-vkc4GFVI|3j8LCx1FqK?C@}Fr0qL'
    'hT<02y<>s#-XdWS^wMbbdf9vpB3cFPUlZ&hjuxz|tTOJG>}a3<`BIAckePLKh;aCMVe+V?5=S6DD697Egya@sj2&;?(8KP2`&5Os'
    '47AC(0+TLitS&j(pw*V_Uu;?IDY+r7I4`&E2=wD1jmA?*Rfh?5LkRBDN2FWI8=K8Qp+XPQN0JB$n7Ng1eo{0X-&E73J@I~cJJck!'
    'oJIm6T_!p{B3?Gi@Zk4mQi>FB-P0i*xvB2KcAwny;p?ujD@3~%t{})R{mwy-Dte2NT+@nS5k(M(qW#Nu_453%bC;p!EEJvs9xGAU'
    'y!e1nia^ZC5TEHp3#o_DWQX?FJso%7($kqXdpX$x!xbwwP_MY2Y#iYs(Fi&Y@~62&@ZM^B{^||IxEC6~Pf7pAQ;{RcwME&8`UT1h'
    'Xdb-NNp^Oag}`Z?EEc;^$gd8S`~x*AHeZj&=c>R&NThGtF1!l78VCj!)+dAn?iV<gxKIsvx0>PB4IRRM`&@JN)7A0=cA+2<J@q9T'
    'RgynISiC|hzi|hVij<P`h7FZzru0aR90;f=V@qaCB};XUJpvLfd?UGB5K;C1>JL8d9vyLdxjz2#`o0{m4d>LMjDdx#oM^$w5mv&z'
    'f&NOugw2GEoo?LH!&Xw;3bc+gWwHrXGp5)Xg$yWG1R2IiZE8ssC#iXeNcLCkhpHxROGZF)u#0%T2QCOQ5u|Ofuk@i|A_Kv!RYQ>0'
    'X>;R-Bxk~3t|~$!?t>`-!KdMy2D7Ey0^Wr015sY?X_2fNtfISiODD$B+c)-3ad!FD^>Qh*^Z_v;aHP>_LPz!ODRS`M@W{NVPMcq~'
    'E&UZLV}&IvDG9GlPF8q0!Ayp=7)Fple8DE(F32QG?r!=;`^sf|8#zTM8O=A+0#Xm7tw3}|<_!^tSP2?AqNTZUL%LNftgJC+Q8>!5'
    'Ugh)8S4TTyRxge+6?zV&B(;akjk`Iq9QS;5M;MSrWd$r(2#2H^79}e>0i;((yl$#R9Oh)5gu?|)(;IhnzCT``DjyadTX0$OTkdv8'
    '3EQJ?n&62D=K+F;p%0vZP3g7Uy5Ajl;*^tcpZ8YCwjr`h@S0lG*H$b?2$c{hJOu!)#Sx+$jM1y3w~z(#aRpmm{>D7s8)W>1W*V)c'
    'R?=AIa^q8@XaY>8y-DLcU%QcqU0m#}PUcaU5g#ija<qC-NajTYz@-7Lj+%(JH`p%rH;UXh>_x@U`6Zphchyw_>|lgxQ@ldeWR6EC'
    'M6RU~!K;!#*+`K@b#mLr77=w^zO=9_wjz|Eksd;rz|VGu0vtpvhjE9fkRnd4&;=a2c28$m<gdq6-qK)ZDp)f*N#a0BFkHx@?$Vd#'
    'C=(-fsLk~S2&-bZcYc4B;D{xKmFb9JJDL+X+vC(cifW7e9%dR;Uy;qPPD`G4Y8(m8L;ubbD=~fz_ZhtZAg*FsgbLymBpDV4;2I-2'
    '6J9u1*B`qjhdh--aAsc$Q4vKAMhp;1jf}}ObOVYM2!tAsNmCjE;A6V_h6P&Gv8LuHWY-}zKvqsx$<lul32?`u>90RPu@~@wvK+E8'
    '<y&@iwuaaozshy*@^&x-Zq%n>S&~J$q|K~P*AJ$tdS0+&P&8hh8l6ir>L8*cgu^oFK-yfsb=db{Rx=4V3I>i2a_^SzK}$9{($u*6'
    '9$RkGSa)}{-0ZXkFl)mxpZt|v5s;deJl$-pwdj0dc7p8X`n@c7JkpNZuN_gMCCBI8P!-w$_JRL6q7N!-w4QV@$Um6(G2FPL?~fG*'
    'AMy?Xbz$&Rn_6({i5wcH_TaIV*0_~OV(r4!dC>PsiR*WvX{Gd@kyn6dvmonEV=q{Gl077Mma1#~r74qUcf(H7pW@4_VO?!I%HlJV'
    'g)n&V@P;Df5><x`-Qi~CUqz@8FuS{DQ`_a~q}s<c8|2$TuE-E;pti^Z55^T1aaIN~U?4JN>E_#Zw5zDc826*BOw3&-kwo~jhC;eS'
    'MIfUh_~wd;<MoiIc5)QPu-g|XhgQjYCs&6N@;2U?$R3H$%u7pctI9A-0(iqd&Sbz)(i=jvgISDE85lm6L0I?(nm^dbby21$eDWx1'
    'eY#~UZ}$`tu#o2jDrSr+K{!Bpk+BR7raAal5(qgZRQ25EeB!@iGv)3e0GQN5=+*hEM<Fn@D^aZi{{S+e?@M@sB!9zZBrhyzrwC<|'
    'zsOw=Tfe@O*<R2jI8tTUF(hCP4+0-<*~L+Aog0z3idYoouv(%tt4XIwNZAivW5OMXorsb^W>h@4#NM|YBEbnk<6kg)!e0ZcJ;rLm'
    'MW1OH@=SPZG*zr6(;-0fNBQbB>#y8%votmfLVjGZ(IW!ALoNe5<wa@k6KxAhPEInQkKF06xg>co(oBG*oH(`x@f)o-+y||OB6@kT'
    '!88Vc;)>*3hNlDKOommTTRlHu#q(-#u>9v@Z<|cg$($mRHvwJJ8tmnb=BcP=61zqXF)WPhDG%^TPZHRl`xCDqO0_`?9B&#)Fz-N9'
    'nAr$%hh%Gpih%hn3_;j<Sir7;D?ZuRQX*9E3K@LR%fcEM_ei9~bat`wz#6udksS@^nFl!9t9Ny7p49G#R2YcTBU_*|pzoaK8_Wba'
    '`Uoqzq-bU^=*yU^_w$}bS-UBcKG*<8)e{tDx(4zXlr&u*J>4)+d+cmhq+1_uO8=~WPfP0?4gm6Q=;I`&0Eb{+jY1<5bs}{mYI$?*'
    'p2FT8zG4gcv^%=8{u@{c?#wI=1(qG)r;x~H{~BS3Q7=HirQmB<@Z<hvH)qVEemD?sOoK|9|Hkw`g#ohA7LhpKD|nfMXj+P`t7E{='
    'uv6uxWGfV5Pavp+_peE5SmHO#Qi9fvl_;4ql4KX-ZJSaxTy58f&q|k1rhz2KG6rW%AC^81Me-;dT)LrdxOPWxNJ{mFFm`QyKzQ0G'
    '-K!eo)G#28To4H&OhW!SS@PBIO%KN%=ytD&kJP&@*&(%XFFykYw32?&FC|ayG3cjO=U$nw-O;)HB%gY@*RX&B6c5S-mz~*HaxcMx'
    '26A%NDBezuuYqa{i4{W0;pXj}+Bv)W>y6%<TsJvP;7(cB9J3~+out|UDg?7ja8Z1^ac4_!pmtB1HP}nxMQ;wF0~r~u6(|c-qgH@8'
    'ndCHnIId^ao(^AMj!GEo?-QU?0+NwkE7YzImnE7#+`JHnP(e{_p!uM9t=`vpBg@e~yhhCMvKUDp;VqEDZ7(M$++GQog*u2qW~_~C'
    'D0CBqxAdJgg*nSRZk})1(a!%)(nOU?*o0gB6bnWeGE_q6iXIJfez<S)8zYp1hec^%5g&86tVx(Y*wascR7@?ID9W3fWMYq#5e69`'
    'EjTT~m&B-Mar@;dLSe1nQNs2+-KiB%F8Qzd<z+OA3J3~i1E?S!5BW$|NB|j|0KdJiKdd`Gv|RaYGv|Ky`N^FB?p)7b-iq{d%<Lvr'
    '1jp<|A!P)p#gv5v1O^WMXQ;I+=+2*PrI`A2L4dHptd`D)IyrbXQ6c7w1>VYM4aUB$|E`YC15us{#>;;ex%W_DwrYF?UW+`9LC$#4'
    '@Ib_}2mu&`!2zPJtZ7QO?4tA}h$ze<klP$b6LDSAxU^P-N-&7T>=kMvJ~>T&8htvNPg{M!=;=V;9^8+GbY0MxiASsf+!)IBqV!TR'
    '58zIa6DXkp-g|2I6=bN>K9KUc{n_g7q#`NR$H=`PU@D3LXk<CUfN4X3qPY)$4!U>46sf#!8(4F1_D)&g=3aj-_0eT|i=rkfRmQ9d'
    'p#;RW+z78_XaM~g##EF2OzU^Se}61kvB_Ix)LZ~Ky8st3L%d*$Syv7GS!BO-8r(3fTm1A2bPTHA1FQ;gMoj1+En;ngH!1BXSm5v&'
    'aZr~wmm!39g+A^qvyy)1T+@}cJdk1$8e@hH`_(fo6Q(z9@j&82oy(uXeuqHV`*oW*!=A4Pq2NGAp`C>M%IKNVAz8FM3T}L5M7IKz'
    'hC5)UmFJPZ6HZTc(m<o>D3Mkilsi1LsAC~ecWUzDJ;OU1QKK_3EUnuCgc7$*oUG>uAU1{!NNDDZl%XQMckXsXD#S?*n84WoL({p7'
    '+gKziWhsa^(jVYrflz1AH30#cnwsDZ2GTL&1Mkb2`<1WZ9HQSnf+`C&yet}NLnlqvRd{4X+afFj^MJA`el%Ppzw(XH)AEE$eW8Wr'
    '(SSqc$NEbZ79br!2Q$Cu&<0UzxJ@y=z^!ZD@-JI5z2mWP7}2uv>+p=%eF+RkzsR5m#km3si%7jefL#|?uYLGqTk1}0Las=llm$}8'
    'Vh<t4uBI|k>0vek^lhYtu3lU2^e0-=qpV9bw;=f%&nb(^QVa7{=sF1u0Jo((<HUIc7{YSfXof=H-nf&ZHi$`Tm;g*I3|x7T<D{#J'
    'uuz5=8?|_Ep(M-Juiu7NKXbh*sTB<QnNdigZq$TlARC<TxG!XsAPcZg_%g`TikBlv(4BbPKYmIj@X1R=uLWW*^5O9N<NKJjDg6%_'
    'P1GbYsJaAFz8ZK=D0K&W{jPrBZ5Lg|qVd?|2X|kvWmfB%7P;6%QAz>1CF!C!sD#PAWCz0#toHgHophnFJt%YUOH*>N)XN&IjLRP('
    '3uFmTu`C6QNZ)kTG?Rg`@ALKBfwj0pL41CD%wEWQs0{@uhmM|H^14ns6MV$z?s3^Mhi%fh45?Uqyh%z0Qxd?wjB0YUul_8IiNd?0'
    'QvmId2aR~F@J1kWaAu(AfF?DXvD%hk(ex*E;?j$+vLKW)TR7v=amMlxk7)vIGrA?)W?2F(=toz*DxXCmo8T*qJ{V0vic&CkvcNau'
    'MRAw%l~OX}+g~cx&n>2ZG3vst^IOT#CW{)YR08KiPy(o!Exr<wA({vaU}rGH8rqYoT>peN7YqV5U6sZbAlwWvB6oZ08N8vQIu$&2'
    'Bvz@(l`EbV0<UV?nqC{z5XcC)q|ljQ7KqlY8<ahwJ5$#tv`fFKm`lIzV7EuM0qR$rIyP#s00p(?C2RI3>Pfio{UTJrMTl`!jKD2s'
    'Y;Vi{aY`3=q)8>aay;nhXfk?&Nda_Taia5L+lx6sXEBkmG4dAXYvs~7GVmq+_2|Xa++BX@I3G+RLTTK0kQAbm2_8xjuuhmJpi>mp'
    'aoq+MAx~l06;vm<5%{z?4FnO8YUMf?<xyy02QU=9ZE7F+GI6;;L`BC)Ii|r@z<>lPd^a_8j6Mom=n;i5^|dH!*zSawDp3FV95%<7'
    'r;@jtR5#pNptTUok#Qvr=|m&VcCanih$+-Tp(uORx(l+Vr&}H;M~2@o5(z0IvPM#nkAhYON!6hXVScOWMNQ4BKb``jgGlJAw5JiD'
    '4gz3+9YsYpX`(jk(Yn&dOj$HyyWNr;S1f+^Q$5)eY|7^2+(6t2^m&{nR<}aNp!o6$(ZMqr8X&D02{me#2Gq?z*8Or;>4ly)Og!T9'
    '0G`SudH9|)w+r>>^7;o`v={k3J$=L8{0poaa2T$Qf=?bZGZ<l^IZ)7#k_OQRW%&3IKyZo7(BwldN}665J<SQ%$Ve|vTHf9l%Klzc'
    'b$|n*mV@~q@*oEw{ZOi{(21M@%Z*UE`m25U>x^kqq5D*L>Ui%ju8yc(mq&~)7&Hvu>|XAUpmfAf)Pi&678WAs_M)*ZfGocD5bPlx'
    'I}y5wWT-Q!D&XHGPF|zpq$odpUGd!Nta{lvGt%fmq^8l(V0=99Bv=D#47Nj9?qO~Eq5JdaE3bUx2JHhGCjb}1g1n4Hh1JVV;d*5%'
    'LxvZKbIY`53l+~CWd*JV9OSg*m|Pj?oG1XqUd5uyGQ&H_@2{}zBjdzewRswqBCnQf(c(|Qf56GGMNdUWM5jwuo%B#MP1Dk%yZ9no'
    'k(cKWmA~(Q=1j~W#Us<gI*#5MGk~+WSV{&VOvAC%tm$IKd|L6aSVSMH>Qam~X-2ie%V;z(7Qw*d8F|leX&@IdQd&LP(bq2gEF~`^'
    '8VX8hng(JD%<5|lavg#sNhZKS)<g}&MF@SIDY7iymR&mGMZq`zHK6wN3?MHNEm5cmts@zsf*GBl3FP0Y$O(U2bs@V{`Nd!l2S<NQ'
    '(lDWj$)lW@VXs1v#NL560yeC8hxL^!tE||Txz&UG5%{ASP9c<)mP}9S5GKF!#pDyl_1BoWcF~1L^D4GM-6lCu@tKo-QLB;JVF3o`'
    'k~ti(=TK~;=A@_|ac!W6G({ra>n6_h8EVIp!qy7-<CX+_MZkhslg>Hq`$4^Y1|93?Q%v^j)?M&eisk2mx_6=_1IG*7#YwSS)<7IE'
    '%wk80q2v-nf)*>+epMBcl3iYwi;$5+np{fHl3y?0iL@$692v)lF2f)Ui&N#Y`Qb;wF^jo}VA^2p1Z2=Xa-0E6W!nEFy&e@R;#{zT'
    '%H_6kv0!rFE(XdBpiUcKL$e#<5%gFlm8cWIE>GLZZk80V_BfpyE>G!&a`AFT51tMh28>Djmx>v`Klvr2-eycT+!;y=Qta8)F8uq;'
    '<K;8d%hph{uTiNRX%X<7M9@1ZuayBKUSyizGE}a28bY=?Jc2-6e86;ZoTQ)9J9Zd44a@_cC2k@mHb8NT8>9facHLL{ZTZz2NOl4O'
    'FtQ|Aa)?mIfVEJ;5Ftfd$Euwf7h(0vm63{1md**RgT#-vq!=<P?Pz~9(g>z4a&A<Ox#)-ew*GGSt<c9@nzdZ;SkceY-*`mR_-bHN'
    '3o}fdUq*Y_+9;uU>jgy=AB`N65oB}mAy&g@j~f6uoJc_mOLY$K+Sac3@^IWPb4o9lg^XU32d!v%67T}6&1&Im{w82N#?7>A+UoQ4'
    'I`}g?makKO0%#MOl6;{BDQgrIOaf-9;IfA|7Z?OpGq6wP4&FH=S1r#tBhnkZcp&`ZrYb*LA$Wj!+<r+Y3_UR>F;p&p_C>~7{o(kv'
    'fCfnHfhR4Fis)qMN@A5neM)?$4~Of150M?IO69_b0K8NHmB8$|Ya=AgATLxrFRfq)$^#f!RHzD@W4C5Oo^kQRg?FG17wkn0_4#&a'
    'wK2TO$=jc>g`^Igjq7l(URO*iu)GR@8rV>3UCLpg=urrSoQ8>DI8-2mLXFMReyEMoZ|+6!jHoXEbkq=G7&Xg-Pnna9P#<(0=#(?g'
    'QO6lWPO!Ci@Cma8B>w@=@mnE-Cm7;aCT<qcgXUF{Q!=kS6J*$qc$4@))aKIXe$0|zrGo6$%21HpW02z?4J&GI*|{zRO+<u5Q3}RX'
    'Te6&*+?RhV&lG#mjO!2+k*GO^Q!|E>6o7}Td;<WeAL6PNH*jVy-iIKt_$uOHuIapttl+X>d6=@TDu2xM1{!zB%hs)W%6PViU4@>P'
    'Awj6W`H8KhQ==F?>I=+NP+TU;Ot_j|SN*%OE<3G%IrG8&juH@;GNhk;P|H`f2sqI9(YWP^Gd(lZhLM-&1xkE*7NMok5rCM@W5u3W'
    'PJAReJzqAp0{sv5NI+7vVoU8!aq`ftD;fAond{X-BU`e|2pJlqjVL;c+=@B|-{E9A*On_M!$=v4?p=kuHq(*BBIX=xmcT+3=WZS}'
    'n?xcEv(PeQDKkJ7`1I%g^oGA|_$$`tn*wQO7I%+!GkV2g1Z}{~6&tTnBUw}~QNy4fG;0=qom6!mIdb`^^|I>5myVkX{y9GvBtTvV'
    'R)Z|8#)A{b+jiCZXQ%!;>w1}F@#H1GgGok*b7V%3sINxTMajzo`fO8l>-%X3XGG#bUgmqOUqA~A9-a8!Oo+>9h+usOPZ}bXj)c+Z'
    '9+<))Zhk0o6Mou5)xtbx+WTH$8`>IrPEfV@u+?IvM}%XLY>vBNS1+u8yFd-WSOYwhj0F}WB{C+YK)ST2kVaquB!VGxaY}c{X?{%A'
    'QImBJ(|$8RDW4K24j~aTRO+2H%X52x{VeKwVa4a|GeVS7B1Y*X%*AVJq}70erTk|&26>5xs;D+{+2-h@v6b&HDDg&6CD1gruIt3k'
    'h%$MkV@@?ph7EuTG+k^0oGcWUBfIqHPi>#ecp5_wMNOen<b-%}*(nS=4LJk$k7(GaZ4mmFp5}p0@uPd2i+J}+N_cbMtDaqm#M;TJ'
    'KohpCrpp3GVCd2^m{F4e`iQE;mr1EL8>*RYh>#egRCH_<)rfjV%}${FB0B}v#U?~k0-&w5H*KeGilk>|6QhyQghAy{j~(C(37wHT'
    'q+?SG^<7c!e0e9!6vk(_EsO=^z`z}GOFh`?gCs?VN}V`8jHwYL3<_4!zU90XU~ZM5HTJd4|6}|BX3SW{GHa2Tj;^Rtq3<Pef;~()'
    '=v}B=_^1LD%{#Lp^c0E}0^L_HyIv>lJ)Pl6+Iy683`pT<&Qch}v3l)A346L>(|*59grH|vauUUj8s3hF*MiH5I2IBw<8ekY$^!@g'
    'CHFy;x?&S6nM5;KFD?KY`?$=h$GzTZ4kT1vA;Hkj@XjocJ$S!^-(QsA)cpK5F}u`CNGby=2nf*ZIQIhJqhyI{Tx06LX7LrLk6!F7'
    'a?e7=R3*_!jm#$~%R3-Tns&lbrxmNOJA$Y|2}0!WXnOE&?664$4C0|sS7_>V0NZ0?PwBFS4xTsf=C;?*2Z9_AYT8MU4ZDjsu0c7p'
    'ej23Wv-A}7>p|nf+6|mDy{eI<U;>OE4w9e+m>J~T3=NxfK|{frX$Mh2x5fEXpKYOjEEFHWD7P4DS^5y%(@@I*SxJJth8fsp8i-lD'
    'jrx(OS>ku%4gVX_puB%3&8Y|IBoe9I>!^cVaX8c`J9s6_T&_A8eFZy#tbyDQ1rrlt1y{i`L#%+SOs7VyD}p9}+d^Fv5~4niBdt%6'
    'DVajb1ql8M63oH?!E^}46E;Of_rI?GGt+SKAt_|QfEO~#Vc;itEPM?*RixnR<48^ejK-a4!%f?$AUr}zGIOBlB_*Zj&D)1Pgk~Cx'
    'KBHL{3<?G{oy<-9sGg9@loN`eSr8IV1Q;!~@+qH{$<j;1t&8$Bchl<4Xi(~=Zt|8c2kg=qU5tck0-+{q6Dx7Nq=RZHQe=(AoxOSw'
    '@N1sZeOUtuY|8VOsH~O$3o}F*YKAi~oK$=okc@W|_)L+D@ZkmyvXm>`7c|3_A|ZaHA2G|8SS*tyuT~r+8L)!+-q^&oA>wt&Wz{f0'
    'mYEi<LL<-Iw6H*y(MbSb$Vvu@FvIFo`MQPbp|KFkGMslSNekuM*e};Opn;s3HO-dxtH$13xsSK`tW`$iP;!|_lv_=+Ze@z&l}?gV'
    'z{R223-wI1I9s=NGpE)%=|zAVw9(M0eW6h|lDbgL06>HH0zuNE3u59onyTy^OjZ)BYxkiU3r|ai#YI(|0!qt!)QG`o8u^V`fU{vS'
    '7*&d!$E67#if!6Y_HxRw+0j#l5DscormCT^kP$tvhRO@-1HwS~hp-_yNtEWJxo#^pL~e`(gJuz8JC7wD*Bn)7kdHVF6vpO84Y>y0'
    'TN}Cn$}!j~H6-9qLE)wu0hyVEo_bE9k`4$L9ZhT)Kh$1*SQ|Bd)(&i{@E4DM9ikYp9b{j0BQz<nnns1!>wAUaO#lac>Q`>1&bNx&'
    'fnhDkLLr9IDnY<KE4P*VE+TrqojCN}+FUz7Z12Bv7GBO5>LUcrg0285J*Ti&casSOKzRtz3=+*z#ApUL&{q&|cWst+FU;*pj-*O{'
    'H+j$Jx-E(-2$D2>>Gy(ek9d25#Sq0>(m<kEt9m5z*R@+Aio-8(PcP3Llcg5i?Q&t98gM>M9nvf~KyWzWO!Hx25(Vj^f#X5DvI}wT'
    'Lt#|x(??gyPwgZacfA}?0S9^XPz-1-;q8X?IB+xFTG7PYBG~$`OTX(eEH7k@Cv&5rZc@@~vIu^tG}I8>z@qI@($m@^u48rS*M73_'
    'xYrT5Ay<;{G={=QvpYI?bDCntosWF5*PQwwR!V>UK8oBe#$@n+n6{3W5@2vE?rD~t3WLO`MMO=6y|wxt(H2$-7dqK31AybRY&1^*'
    'YgnF+n3)J@eWEP_v5V^HihZmQGO!4U45nYg#VnL^c*l$iYKWYZVu@W$c$#p<E-EDjw18;qk_RL9qZ7c)TmBbi>a3C#?LR|;u;5r-'
    'rJa;^o3rw+RH8ven$gfxqk`HIP64)qD9EtA=@g($G<||cxONZgxX={BSf3Cr_%gX!VW6RSY@DdNgC+yP#O83Ueh@^5#nk8AsVomW'
    '1k{HB4Q2v@NG6QfLSQz<G&2&E-8fmat^PpP415pj2thcMr4hjaDj0CGQLBMuJZSK*?cM71_q+qXQH9W|+0*oE(TKqgr&9>cgJ_P4'
    '76Ua9tjTRGQnjH(Xs_GI^KJ?0+-%$MtziBDfC0Nzr&Q`S-T(zENH^pviYASI&*Gv?*KK5>3)H-rhNKevg+wNfk&#BQd87f8PNt|a'
    '3DjM~57$PEC#^4RQN#&Y{MZr~no^t&CK^LufIP_E#RlkSV*|p}2qXEd*mi#Pr*dv@uIno!f`X?(u^K>E)kziO9r82#8Z;pk;vpH4'
    '8Lr#Q+72^*g+R_moWBM)0F-aEK~Re&IaBaW53<*8M}OUJPL!6ajX=$U8^omsB^yk`E+FtS-fWbeHN7b#TKei&v}ixi`FW)V6m)??'
    'QA0vC<ru=JA9_&|A#gixUaYWqI)h)E3O;Yc?rkUKuqw+&(lFK$&lOD>GG`u;5&gE4VgO53#;dt&c5!+y_i2ZdO^Kt)JYnc3_>3_B'
    '0{bEeRT6Z;dlAi>{6m7a@~npsw{Z?9m}qFC!uF|zxiH>_yOo9%sZfw;f%}Go%LE?OK(I8>RM5sVS3Q!~Z+Qhrg<b{L8ORxOqj_P('
    'Q;H{RWHn@RYN3KRVCSpz_GLToxUAI>DbzEHNs4N6Aev^h@dEcDGak5nkwCJ)AoriEw)1K%PKkYAqh2Bl7#9XL^<0lsoyjEx6v};7'
    ';9x{_xM}UVtG=N#(YE%v7!4+I4L)`V5@=^~9RmSH=@Kb|IW%(DZSvYn`LFv&%>6o?4o5%gS@t3qKcE=2AR5$&1X|7&P}~4=Avmqg'
    '8+kiEEm*edJf<@jiwRvl078&au*AWQCtwbS{s=}i++!>pU|%uaX0q!y60!7rdl<Z``|Tq5FOqQhVtNe?n4|@V#>iWPw~CAuP=elI'
    'kPvJf)^3RZa{M&cbin`~NF*V`s}BixMjK-$D~|)>ZqQImXf4E>wHvAD?`kr&qwgyQJYf#wTxe)$?iR-)c#k~^Hll#FQ4XB$Z1x@)'
    's_ro7FYH2Lgs)hDI(iHA4}dgsyRdLeQAH~FBjH}Tiwg|fpUO;bnpwAOFF>DW$EX@(rZwNmaT;x&OjYvQ4@LDYpN9rQmIfps-HtuI'
    'cN9JH0M)<>Z09w74d+Wz5=MDLkek*bAZN1c=Bz-K2~VN4fjiAvoMcl4LTSYVgtKBa9~%q+FJrZe=at(yi|Jo?QzYonLom?CdMnzW'
    '_!!(N_!f|%I7H4g3IVpk)4TQCz{plIYx2WWopm{Ep)Z3xr;&~@P-T%0gJ#eidA?cLOW<>Sw8Pqu^F#-JPKD6mnTAfcPu^4wW3Gss'
    'P;zl$8g<L@E`aao%SL<E>UCt~Nq{MXT3hlC85-hTF%k>tnS)N!1!aE|Dg4^^u(*evoI+}#Y>{&^2N44v>|YoiN5(#DQ`CB`hHt_G'
    '7j2`oi**sn%ZZnP28lQ9G~O6-E@DOtXNKwk5*wv0e3jCwZx$ABm(+R8Phs+q6X_joJ?>48t`fa0TG9r7ij-Ms;DhdNU%h&TSsNcW'
    'j39`dBlC`d_VnUWvheibW)HYokXYqZWas?l*-;<;7;ia1b!c$3CrKLlyvY1}8r={}v4v?xiyl+aZTB2zKD&2+vT$I~9<WV>ddK*c'
    'mKzowR?wh!n##yY5s1@$9;Uh#s{<QugcwrO6r&G=<q(%m#Ey=M6%<@t_CZc!gx%r~UB2PE9I%5`&7_pcT1L^%@Qsn>EW<E3zmU(E'
    '(IzjoxoSnltU5wJI&*ks+#((<ooth&4_+=dl*^<h*bFW0m%gY8ez$B*q+kw9lI`N4c{<c5SoJciRL2?w2<1798c>g-<Kw$k;UudM'
    'eHnH_q{7@-zDgr!M`ovSoRA+8BN~lo!QqGzI>nmx-Kv#01kw;=vG#GYtD?gUJHH1GM&ORyIg<uJGnjNz#D)L1aK$JkxVpH!VCWhq'
    '4LluS4?)RrAO$^z^28fJVh@1u+0v(4{O*0ies?U5eJ3v_3(}-a{31Y(T8+jA#|pXzu)`)!_jHv%y%DJ?^KSpBo+0WC_weIC3Nj#I'
    '0>-&h$TdWMx|NzQ&%kM@4n{#^F<=`$ca(j<-kCKi1f=Apk9nuW9@yzmfZ15z5f#XNNkd4IvG`TJoiRsSvFsV|FR!hRB;yg2J{{zI'
    'v|r?&-!mc^qp+O7n%M;hYwg;v;C96pz&YTFL&KvAqVFZAQU+Sev;bXnl0G77VDzV_nyTlhJ={?qW~Rgb<M+ev>B27t|AdbV(?~Ny'
    '(A8;JJ?1M(v@?J&<a`;P=%+ajtNacr<8Enlg0g*ljNjiqO_rz$b`^7_fRyZVColkmxp7de5S?{`NI&P~YaHi!$o1h)Gcf;g{PTEe'
    ')K5Eun9<^mJVC?=l-#7#gFFSX=|bK^<Y+%vlo0~&UVr4rf{gb+j;;gyrw>8vmI;znPgK<m=%c=dX^vM@kf`YMSyft1d}{sO-Ga3j'
    'x>88CA$j2XOuay-l2L@v_NW|a6ZUZ3!5A=W|Fmv8kXPNo=TL9qT)6TloAaM+-n;`Yr!T$c2t#SXg%V2-rli4fU=$*`i?|LzFz|8s'
    'XP<52?f350m)(~GAtGlgf(hW<NM}Q`f_)wOdCP1GYIY}2DCXRKbb{1!{o>s>&gt8KECgK{yEDU;3V>?Jp@l>_Kf-9jj3N;Ejr6dy'
    'tyt?c<MQ~wcmFFrEb-ufy5rXZ2FqE2pHIR~AtWr;>#K}znM)^toVPuGT#%ktr%4jN-ksSQXaaZ7Wfde&fbc{RwkjyJ5E6ohP+{9l'
    'yk{r|dO!rIACf;mTJ!wZf&~Q1R!%V*dFX|RWNe4tl`i+NSY33$b$}slDlB=*^1mz$y221_hL^&b<AQ5tH-yH}k+eV+L#rg45d<l4'
    'PGjAAktFz7kZI}bpi;y#4SE_s3~N55)W|KFVv2o!BkIS8l(Y}lyMJMvVS%C8%}!lW@J6mnGC^D>VV%+aLt=r~1hE0`>|D1VK4r(!'
    '?9V|Hi}2m!2QgtB&N9ze(=sR^$pqyftGTS<(@!#N?@oRLhc92Z8IN&ryVLlz=UpKhV916t6njJ5TM-L`dCQiKkOU?VrU+A+pafb`'
    'v9#7Ib0U~9&uBLMvt`qXV+KZtfHEj#X<l_s3MM>D`w#U~e_L?B0LdkPYV3UQLmA+8VjqI1F``($6EvxKv{Jaiifxd#G^t|6m**lg'
    'pVF{{fDY(6i|RsKj<{~s+Gi738Q=~^B{jLvR*OkK*U+1Pkl^z5A7q+U{3fkTxR61R`k+_@SQ!wgaIZl1?xpxfh|8Nbt5#)t!M0E{'
    'd6}crkwCf0lH3}U;GNtoG$ILJ2Ls)D)1+0)7B8?MH9dVRNYzQ)6?_aF6fn6P0kn={#%XwlS+nS=7QcL(pf(chFH>D+H1NT~VWDCK'
    'NkjijsseA7K4<gUvharPme1qvpD(~1d3&0ZT=8;A=b>R@nhnq^OA;BB!q-6ULd7TpN$DKI=TG^wm1}4s2p2GyAtDfGalV5ag8vF>'
    'pzKPdc)|S`6RCFful`yJO!OlM@%LfA5{RTXBT?ZVqmFBo8p(u*f^Ay6aK-poY6RLRRBmc4z(e6z!_65MkO!h8V^L_(VMh1q(uc!K'
    'x`O~i_OiGrJ|A64uFykx<^*x4k}*NjY9-|7X!F2H%zDho8d(s}Rcn^-INAl!sVzSTGJ}<gF;7~fASo#r#>Pl_E+BH@s^w~~I3QP&'
    'dIqU5^gQEgOT6M+LjOSD1SG(d=Z~2COqB~BOPMFsKGd;T?W4w#xjrLFd6pQT=_}@G(nk~+JAAg@8Dlu**cCYud*@c+g5eI&as$U>'
    '1dxL=pZL$=fgeJpVXKyV=K7`>EX+7)7rh@eE#{0dF;_+t4S&!0Cj7V+evSNVr>Ye{66yaG=NY#$@e80~Go=p@A0oaH3~0rrloBxu'
    'Q}$JhohI@WNKi<nX3b2-dwGCK0h$elPi+fx0!<l0TsUgOr(eT4uD|}ZX1tzA(`YP&rOx8aa*5NSzySf2m7+{|FMDy*=S!0RY!y%M'
    'mg91G_3$V-wwOt+ZQdMh362R5ksr?gz(9z$k$($EcU-+{c`60%Ag9UDjQU~Hju`b;wwjRZ5%P8VHt<tLxV3(1n)-2<FLT&YjB4()'
    '46f)9YW^Bl_8k!dSdN2+(7-RM>iX4@3I1^q<?#8XzyW2}7m*fXANCFw+o?!Z$m@mpM}kH}2oVUA!|PYBNY4h$Qian~4bmB*RghJC'
    'N>PB*wPG+^2%%ZAChPq3p&;3&uE<7+ij$=^KoKS^q$u2KR?e{$si?l@wTqr*<AwQ2upmH_5o@SgB4P0A2cgIl`3Wae?iiApdBx(&'
    '7%HcE!4?5D;hIKHB}46osu;aW5W5Eb0<CbwJ;tm!TwsrMhK}we?E15ix{#~@dxAB3=JYZf0t|wCAc<rPq=Y5ZAOnkBzx>nlqgFmJ'
    '!n80_4&NQuXo8xEc+AWa3(d=|kb40d9Bl@`2fnfTwa>TFNm^F`fKh?qf8?08Lr%fCOVg4%LG&6m>SpQyU?z#F>KE6aZ{8C2ZHYVE'
    '3k%@MLxbV-774S*o&kf%Rs|n6XvphKpX%3_O=Nx`u)GGhyM?9s<s9N(|MbgAocraRE^N<Y)oopyO$jBrF61r_ZmaYjl$B9aJVm$*'
    'uo)3eaN&*r{oDSl;as`(0kj#7D`*}Z3;0J~P$D@x9S``*xOGr6afx*mTR)jmeiBT7a&sqRq@Qa*y!CpqLSpa;+72Y=()Via6c@-;'
    'bHt@GLZ`WO94hLtB*SaIA1X{R3r1u*S}hJW8ex?03_snL&#We<RfBERBHTp{(`-q+<T*__p{Zz%qMOEWs77K&*=K8N6lP)$!sUR8'
    'JuYfLE6Fw!HvkMI7=oZW!chTT45ISVI{LK2Jh=(oc@ab0zUFsf8A_)S_L`djVkvUSE!7(vHE5ZFPh@;LD4*u%hyA_Zlz!HrS><AV'
    'Fd+tWdZGXcdPCC&*C6g6TFe+Yr0&xXOM<Jr6S$u6sQnVRd6{8&+!i{VB(8LsFe5|bBcn%Tlk(@n)l?7yGge9PfT7#kh0DoYk3d*9'
    'mbCq>e5AQwF_%uT5ZH(&jRRx)&oR<}UGS%x`Enf+H2s-!JkEHA!~H<cku(7*NR~Hh77<4^47Dql;U7!?lG+D{2fTpD)oC!`YY;|B'
    'x4r%pwny(jeYVS5ua+}k+|oQLn1%A+N^QlQG;!%$Nix_$5;{!OL9UKs1OKJZ59`lM5?f!pi<e<`MDY-%peEzFHKEbc5Js#vu%Hq3'
    'gStpfxUp{0HwE(LuM$aTqhaEtO*qSlge~t#uztXBJjkS}#OKM?tyuxJ2><1~#}HgBbX6WYsSt>8vm#ZN%EO9CTDPDO=to7nf=nRK'
    '!!k^OBdZCgqXs;+GEEejmj*RC`o~=OkJemx#5IjKdV`cX93D*E&?3wd)zgOJ^Z@j5XW=~ykLg32>V<U+^9#@zXpEA+3l!`WbvTkt'
    'U}|VYP}7i_&(!h5x+UQ#Z!ecS(plnxNiD6XIg8^0Y)aBgRwgxUt67mYtz7mstGOJH1jXVSNP6FO`iU?hWU@=xg$|4t3j(S*kG^j0'
    'A~1sNo7xKdt4_TPsVTwmvTSX8xak^81_jO3uT~@s$+LtrG>h5F;AV;`=Gwr%qn5@9jakKb>~hS8RV#ipK<8)39hYy-%Mmh4B!tt~'
    'h`Y&<PbL;awL_=Jv=>vi=z;Xp?=Fvu1hQjx-z0jO4)D@O;Pr{x3?)qW3@MSD^Qsj$MbsH{2TeOx7lBf3l3&UMr;%4UX#yH~17FTO'
    '+x5#<u~o%%VCn|oGp<39>&0DUnvQhbv^gQ$fm{+drgh6Nnu`Jpjd}x!4<He*NA;*d4rKUA#YV6i6{PsnVcohXMMJ^gp~Xsqqy;XR'
    '#iW<_YMCL#jSgj-U}30aY3S4*tR)SF!+F*tUC!p4ez6>P$_)Yg2#&}mAk|PN;ycO+FrzQ4@>Lh3zXo6+_>GE#94F>{ARJ(D4WmDR'
    '-AQ@JMN9a%1N~qB<NpBkKm92'
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
