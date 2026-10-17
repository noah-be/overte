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
# 458e859c7b1a4c5d9f8112c683cb0c3af7565efe / tree 4edbb8a91e20229706b62beda4988e5c9eeb94b6.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '6b71471f0eaff7dc51e127e8527693f726206242bd38db47de10f45c264a4d18'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*c%V+o#ac(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNecq}`row<ZFaksj{mX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xTC+TZ@|x8rBW-?n3Hl4*t<<J>j<Y+`b59@?CnG1}l$vST|L{eL)pd(nS^'
    'f7<)s{_EeqFY8$-e13S@KW)Re!fM`k(U>6(^Vmd}!ZeH{Yc$Q+<Zke>$>U&MGkv_;iwj@eV|w^wfB2H0_J2G)CVs6uZTGulVe!-r'
    'UEB6{8glF6*qVNb)}^s&C)>>-+OhN9=;x0YKctuaaeLYyzCDD`DSRod*ase74knCd(gRK@&AGR^v2o^y&Xem}oBWlBdrHUC!|`={'
    'N)Iu;q+LwAuuY|P$GPdeZB3VkrXL5xGN$#D<9E+IZf`o9$8l(D)-A2on7;S39Vat#Y`h(ZIZyr6PGM?i(`PrDZg!*lc&)crdF16D'
    '((d%|&sX=f&D*fN)qi|@e)@RzA-1uzZL)soc)mk3G_CE8>Bnfgskc7%ZH#HGTK%y9J%!VQe*5wIveVo)ZZ>J0!<5=SbT%|D#}wUQ'
    'nm8Iav^~qtHOv0}P+eVm%p>1TmwD`yNj`9Jhq-GT<6JOt3UM6cY;FGg(*D45M27IR<tcv(+fToz-Iwj|`03H<J->YWcvWLuus#G{'
    'u(hLa?G%U5nz2u@pLpQ8PiEvxTC?g4znm9-eO(S}m-LlRoo~X}#;M7Z_dIBy+mRqOH7SL#Zr#1VzG`-PY<Q`o$^5>ynO)O%L<bw@'
    'G}$m_7hFGeX3eUH*WJ}MgR#Rf#O!8or;(rM=5A=_$@nh$)Y|BqG3C5!O`YUT_<Yzur_C|!U#|aZK9{E9$vV>w1Lr!V+4Y?po4%d+'
    'w)zm~IGJ_NdfCCwJ*OjqJ8cfhy=-@nSGN%-PHz}eKUkt>GB$N)Zmo5}^Ld-z+QC>8)<1~d%kw7ecX@k#{n42;OkF<=lW~SPX1F$*'
    '-Vbi#n{FF6H?qfW_4>M(<L1w=*<W4XbIuxTW8aTl5`Dvy=-u3emK%~2+3^&b)OojheNG@(<<+%Q$lc@!nLQsKcVQTV;kF>Q^)|TH'
    'Oa$AZsrc=RD1W$bpLXe_NVhrcUr%Whx9)MbKc2SXdbHs-_HIhn^r26d*FR4wIj+v8ABcJ(`qr7=%&WKY8egt1+)mt<$+X-UeDHDB'
    '(`P3`Fgdn-2-$NI(>PWyd_H)W)tAIfNAQ&XJY5e!Js<m+T-){C)NzfoseVqQ?;~I1oPue*vb5qpo*a4MY5%+p4}`t1+aotBAK)kV'
    '8n>s-<;K%3d-aR#`{ZnF9ob-)iH0%SnLB1uOf*BUm%)=6Z{E%FRqEq-a<Al)*Q3-pbb(ucm@V&Ph|Uu?XL604<JdLXnADJLHMei('
    'm2~oYq>RCtDYV0so1Wk9`p}MC4SXh~d;OGq7j4%jbMqd)q{A*fZI-umbtf}v-8jT?;NB;B&9-T?kL}Pa8_PqQ$C2~f=9_o&>~^Hv'
    'aYK&JQ9gXzeBK_Ft6bexql;_EcJfUMgpo1zTxQ&&<O-%^hs|htO1JN7@A;R$7J}Ijx*SdDJ<-zob{sjqu4`gP`jj|9#IZsD^!8o6'
    'Tq+Ouw0zYE7f#m$+Z658j<%gBu%>~i-uK-Y;zYj4v2JZM$J9=KzIjXJRQYN9`1w>FYlpGRWK@l_z2|C4eCLK-ej@(p0mZJNX3L|$'
    'V@suUiwDp*VQNMy&~BjGY?XD9W${R6-d;0x)6})`<}HwRM1tM+D<Age`y;xZ1#niJZ{|$>#xv-qaU$;ff#93HF~pfb{Aq4~EXNby'
    ')%C+Nb2LUR?dNU^flDaQoZG;I8Yw5ovG3;oj<4wC4v(q&7RV&LjSG?NBM+RB#D{I{*mFomJ)wd8U~bawZ|R(^zFh@=|GJB=5NJ3i'
    'RA3G1Ij^NL6hTAe|Mo+m`t^ftoS{yz=@;#(;(F>*Hgi9FYBJlUIrgFPIR;}m$y4MQE8>LQ+_|IWj@nd(!O)Yxw}uOoi*ag!cVhAr'
    'Cz~qAbzMjKo=LOrd~a#@b$i(Fp7|HgukLzT*9zyEbLu+peIEv{2=4~4rXjh>w>&d$^w{0Er|MgDa&~kbRmC{?G=b4XOLa>EMtSMU'
    'eFr{xc4U9ub~am*z{m6LQOE?npEyw9RiPmedtR2GhcHiE79Dq*Pq}5g_igQ_Ti%ZVS|r4r@jQ=-EF`E-1RF7dT*PMExj2Vkw6(B*'
    'UT~7q0~@kS-Ap2HXG5UW`<zIc3E%8?h{k8`*{O@aW>?4bHSG#jH6`mDdc8o3NCH5^^O_pN_0e`|0uAj5<nF%xR7C>PLpyhZ7-GtE'
    'm<Pv=>zaX&KLE&@ffs5hbMM^B4_VRkw&sk_x#^q$hAsi(0o{cWNYQu@t;FuS)+H02&G+qVeQLyebL5QRAieJdb7jCqYlhZx#D{Kb'
    '*`aN+zjt5cN1Jd+V7sTSdpZ`-0ZJ}wTQ1sZ_M~k&^RSc?7*Dcmy5LEj;(Yg>YEpuZ%b$b8{{by>#_-LPRRigR+;r1Gfoj|s+xEWA'
    '+>pJIL;7q6GYouTl+CUOHBDomtx3*s<+R*`rVaOP?6`kD0BVK(=LBvYu4i+s7aNKq$CDAtmSQ&#0P(X*fE?z?LkmDmcWy~p<))&9'
    '1z{pz1MF+Zp2{qH?wJ<UC3bC}z&#01Q}b@$XZ?1v+djP(fZoYYA-UAM#`Z4IFd4~h9XU&Ac}$_}rkMtcx$|6~o?r6zDSfZju7Ca`'
    'm;TT>sx#mqBIW=r!(;K}yNw`OIy-GY+<CfBhu7nYo8(LSb|^ukeDma&eBah5!<n9WM_~piZM@-7r77DurF$xZ6`N6(-E?LI6K&@y'
    '^Y(H}47b)dd||=cuAjjo>aPC_NPYPy*Kdp1fd+CcKu5=(`+|bLA(QQm?@46AXnT53Q(cDr__~C<ba>t#k4q2nYBJ{MnSO*C9eGMV'
    'f@zGT(Z2E4jW$g*fg&-d?k9iV>+SFNrGT#sntEb#^Js&Op>GLo)aMg7cx+4rj^i__Tl1W@To0XQ4lN&ENBbixivsvg27n9LBy;D`'
    'S7Q&cE`Qo_`F~9t7oWG+ZxT8iBp<{-<J)1N`vEEubD+o8@&7siE=$2sSrA-StpO98hD)5XOa;;yQWz-gEnhq+h~T3@xkebMJ4-))'
    'N!2+<=uB!oMLzYRs#ZEc(bC!@*WhDs+URFM_{w_m$9_-Er!+=t3){umf%5mGRe_&ovgeLZnPW{YO>Gv(6^ow>)386J&F@@~yL7#V'
    'P-rEX(dV!<<HunbL7C@9mHSLHYM@SaAy;B_Kkndp|1~YeC|6M7Dm37dW83D&Pn{EtOIkzHsk;$eY^G`-X*|rXeh=%SN(emhrsK12'
    'Xnl1wx_WPNM?;q{EpY)Qr~+a3_3KxL785hIBeVbxA2`Z5@x=*oQ|p`$(N2VS^6svF;d6Ycc;?hVymy+pE!S6T8nF|c_4Ltcynp~u'
    'xy7FT=h~(JDq*kRAvCfZ(jG_ZDlBAd$?PW{Jb-?~>o(vdBxL#a<uBd7@bY^7Iq=;Xm=gRcZyj0)bp|)t07}d~M?Ya2X|&8YY@}}e'
    'F84G!4Ot(}PLeOO)XewLwfw>4Ko_8N#Af{wAYos)9DEAya2*Ts5K>~RE-SZ6AmsHudkWAhIE0DdIFV_@=x^Ra-IEx3{;b!~^mdR9'
    'Aa6L>20VO6eVn-2Nv?YGj2pJ`?euxSs{=H3_$d+qb*6=e1w|<J5I(3A(nODm>X_$cZ+IAo^a!Ryp%OQL9Nf!GDa#7Jq5RDp3POP}'
    'FfK>mJ9@%Y<S@oKFW@^j91MV^>rL2UpiUcDjC3wqwHAQ}Gu^h<D@20wlJ=#_;_X5}s7(mw(ao+Cxg^t!NU`BYvY=a*<RJE*E~6+g'
    'dBuHnQ&vEKp{MCR@cjA79#$OP&fo+EI(7ngE`*`0sD{qJ{9(I$c|CpNtv_8@RS#tN4}T;QZ(ublqN}^1SEnkKx4xXeKxR*=2(%_Z'
    '1h_l%SlYfKOZsUytp1Rqh)+LmOr^)ho%HC+z>%X$Bu%3R5$VfuDgs|GWyxr%J?IlBo!Sa;^rMZHNIRJ?K=~7or4`n|6&mA|sXj(p'
    'pS=&605(-nW|qtPjof&BNm4b=rm|C-y+j0cz&*9tm?jTg-8*<9qsx^`zCmM(l^foJJ3Q|Xn^*q5Le|o^d<fi;bX>s0!Vpyc0kzK4'
    'XiSDCW++Ap<F)%ZSDp_SuEeL~A^g84kCZp|e~nJ^@m9{95*1iWrdhx<NpGhq(tR-o?x`i^aszk<Ksnzp&&CaK?4~=m^9CR++q$0h'
    'T0gc>2}2;J5>okosW~kCiA*}oK1e<@grgfbvyeE?ryDY<J60c`IPkra2BsD$s!iO+0hS4GjoRDAo<AZ>94hEn#eMnL?NdDCKed1>'
    'k!^wqBpR=2=utJ1ATW-j5D+jj+AW><ndbh@T`;>J9$SHj!e^)FMMwznH9_hcb%SX#z{nX|F&<2s?fo0u(gr%bz0?co{5rBgpQ?pD'
    'H_<IO@N%M2x1*zB+`^}WUkKscO!F_;*^WEwiKd4;(CWK>$`TRUgGJM|Ce;HwCwkK62U7A-W2kv)8&AFO@88uq=^;k^(4oD4sd@*='
    'YXn^6-8BTN$Ojo`jv6Npwk@atsQ={e-`bkk70EL=`y71u^Th9VqUjI8NuiVmvbrABYwj0(mX~yW`@B@Lum0t;I~Lf{kR}JhJlhM@'
    'u|gBbkQ{(91OQ50E*z1z{VzCU=c}*^z8>jw5+%TPLJNR6P77q3p^P^}8$?oTd2mg-e^bZp<HC;EA_bxHt@tQ=fJH7tiar2s3y3>q'
    'KTUiLw5|e)E)NWRHT^g2ZOL>h+U`?|W>$L*^6SjmqZ+0nN?@TqB_eF36hWVV!AI~W1h~GPO#c`bD3C0v4bad8EHtzOb-~;l0n+qK'
    'xe;#M&f6Y7t-C7e_p>Oyzb<;gRTDQ89A$_SP`5m&1*okVZ+?s4cePxU1=fwAE6Ca0hmJU9`4maK!Lh(~ecMT>0I~V*=W_}1*C8E='
    'jJl31hYJ}h1PCj97GgXQ0#O}W`3%}=`+N6N@tL(SYDDUTk}-lZ!rP_O?#YKyH-K&iM>a}7d%Sxqm-^x7kF5{^8kI|Vq;ujt5PR1l'
    'ID_<``L{Y=m^vx|;P-BA#g+gC0epyx@U_tM&=RH0BL6e3gENKJW)wW$T&X7G_8<Y#WoM~PZ>@+0kagiy#)325oZJMup_H~$n3Ye>'
    '4G6^0fr*2YQ`We#TeF8!5lfXu5z<cmNO?d(fFiFGmzlOwM2bN{IU<#-|J{|1Ci=Y%Y6hF>#X}eB5S`4_@Q^J?*&t9Gx)5f5?{ISc'
    'xm_-y775LpNL)@uF};7#M1B~er2y&0bNVHE4DT^G<33P}lV!T6PaCNEKS;DT`e%iH9m{fnJD9$@&yokf>QR(%y6n(-F~z&lrR&Rz'
    'a(Eq+nPY}_PG4Y3BtobvVbD@>dudlVGaUhsURHN~nRCLk{O3ZickX;In8jxVg)Njpv``~OTSu2l(LW)YiSPU<!Cz@7RQ!`WoVF;Z'
    'NR$_*%c;O2Cp(WY??8jON|56;CeSPDl@^Ou*=E{Bw9Bq8xttUdbN;?aXEUk=Xy`-u4RE9y_^h!3avKtb`xN?lPz-qQj{Vz$XJW|p'
    'bK->T^<4u?4ZwG#%{V}S;>4qt<TE(e#i8)~j(-2V`O2*w%P9>oCbCe|^JxQ)fbm290;@rw2@$mSWQNhl`Mu`#Ia`V8>sD`(`tIeV'
    ')oT*HM&bl$Bmyk?;FA`cP<2t}b4hym?@grX=}L=6_i~bUW{EI=Tal;t*K_5mHM~Z+Q4=VxcXXNPUxOtOM#oVSNvK<6s$22+T~+-;'
    'QSkkbuLrhP9o5iG99?=Eh;|^a0HGUpFv0+CXsmQTxEpuy^0Iw>-qdU)h^<XGDUC}Tw@c`N5vTS_&J^pR1w&zQ{mPA0Jp}kN1MM|W'
    'ytN{VB1ujy<OuQ)*A6~R4z&YP!?kON{S)`g{+z;JXpiNyk3?7~6Kb~E^J#O#v@|b(*Tv*RkV21nBFm3!ce4P-o5w`Mz0`7q=mo`C'
    'GU*^fu~j|>qrpyT$jGNblEL7p%Br`poP(-&0i^(Ga+e8cqMD(A2ho>OTJ3)@Bi;j;R$Kip{{MIfbS|C?OG2`pNGo6@HppxFolyaB'
    'B-GMQrz##{7tng`YL|@Z_=WD(W*=UkwtrSVdtg;9P2URWWFX~%#zQGi=VZ3f%i%IXU?MxYaSM+xuba>CBcIZ-0Bh1yj1-T(LA4Dl'
    'do;EqF#*!))LU!e*zq<}^9%L?DVpmYs(XQFM2m)~0C5Zs>5#M9eo-ZpxCj<GIqI6OGrwj-3&2#-j20N)OSjR5+=fW!7qvu>3K^+F'
    '(ko2jU3J5ayW-+Lz>GL<zwozje|I(Uq6&hVGFx(>nbZW3X`~~IA~Q~OyP{;#v=G`G_j5)d+_xtJnrfu9{pgDQ8B%Q^{*oOvdFXp}'
    '=X)q52^$Zq{C%WlkM%@<>u0rkKX_XZI0D*{cABXrV9}tG;F(2ga6)Pz`R?9z6?uO@&-?JD>f?5kdN>r-V`m1qI`DV6(j?@UCMt`y'
    'K<1xA?ZTI8(QkLL#J;3bl`@QA77V&{&L|{M2upDgc4i2!h)}~&{XM^I!`^<%+dof2{TJ}_dR&uchlGwig5IObV$lUiCxv=|98-gk'
    'b&S)x_5Y$wRbMNV=}vT0nn$q4)TgFiwm7+1xJ2|uN3r_=%GPb<Agh%_{U(qxQ3}yk6gvQj&UwI9ncX0XK_p`)1gHQnwVU9-RYZ*y'
    'cf3_f6{SK31e-k+A}&?ZPtGT@ik#pQ1V>4F;||XGPWAJUqJt_|Fc%_Vig^0q5J$*~@%cdv*I7s{ldZn%zwY_l&0=Y!YPArZNUIvU'
    'cO4PHi^A3@<!4dC5_D1&IARr+*Y=eQ&V2kFI_O#h+CB&*U~9mky+xMgLjnus!a#9TS`fj^xBp00(kpuIpbYxpxvqH8d6veh1#=j<'
    ';mPz2=r#R^(vpi5?X4~^=!9n}C}w)ZCeiP=O@c9nCxFbHCK|Z>CBRTB1)MsaG@U1KCj;OPx1v?Yn(7-75LrtAfA7!Q?O<ycTYl;O'
    '(hk;t+?@XnGJ~gzwyQu>j&7u4#|C4B_yVb;qg?0V!%gC_wGcjHbIW$NJ2igcT=>_FUDxL2)xU9JuJ4JE&*ck<3pxRO7XW)Aox5qm'
    '*$P#MU_1{u|E@hr-G*K&J#j6Sm}{7pNQ*E4F96*EO9klM_ynQ82d3$IvDe&tmPjl1^F#ZF^dP6x_WAlX#T^KP9sLMpFX~|3R!9K('
    'I_UWF0ZC&<{u|vbyL#g3(Ctm7(9BzC)T9rF`VJ!>9+ZJ4L=i$OPJ%lC3-Azg%O0MWb|5W@(jHoHEYKGa9snlNNANr@Y|czSYd^$d'
    'Xum$*vIp7wu!lpecovD9sgvRf*E3EEa69Z6I44*lAZ3UHas~j2Fy68cTBEAQUta0KR~-&&?wLv$r2(Hd6hoMer2II0up`<<Q`W6D'
    '%r_m51+3Ye@2&Hfef|A3+|2{^AlWPIEiaG^C>PEWlmHljL8m6&_Vs|x?+*X~m)-pH`KdsvBbh;70s)cx1VbR|9gF`LRT`uvLO!=C'
    'MSJ`OThX6g#|*Go8AkfmY2lRNN5o?x#z2gPIX<RYIQJBX+xH??=FxFj3h0ecOwey5O$wqAur1yc@Gbca8O?;R3G|YbZrRAuJ-?ty'
    'JBlBCZta(d`}_@fA{7=M2XjciCEL$bJhae!4=E5vHHRkM6#Gw7rpJm3z^di|HX7-P<2eUk+|Y->0FQDDM&O7Qjs*ksw`}5kJi-%&'
    '*!4ZYACpWZf*o;85Wq>mKZ5)M`Oqu}T!(iz)_*qPvpc=XXxypztu#DtoGcS4{)G7umkWR6Rs1Ruhdl#;5TW)|um9cT@nRhXg!{RG'
    '5I{%(;7as+M)+208_=$Vy?~?zn<gHIAeE^;h@DBW=i6oPrIw_bDx#WuDI`fyKcQ`te$sO9!$hYB&kIr`HBgDE)Z`rs`09-)hKFzA'
    'DP8im5coorznwlWZU9fIT$f3Q3?*S`2whxu^b-L=Aq(jCfy6;C5M;o(U$mzRV=qV}_~;?Rm$M;Z7U_Qg_OklZnF<=f2ZrJFOEwg@'
    'xbB?_jQ17^d!Uy_qu0ykYY@>YVE>w64{@|$U1gPVzhp;;^v~B)%!kaZqeFzl&kK`BC6zb=!S1$d-%dzw5ysf@-VHtNAGf<ItYx50'
    '#ub=!L1T5v$p)>qWdCBzVo%8pX~lWDcSoQfM`<*6AypkF&<!EDOCOPLDQ|2x1BD7bL?1~aBw*%Ny8B7daQv>CF71i;!`q=Iq2)AA'
    'E#au8<0Il_qYMvzZziQk@!mZh(}|nv5o~woUXGvlg<T=qwQvPNcIkHxa#Yb<jO3bD42vj&I27$)wyW2dr@gxlHD{sl6!2Jy!sf*X'
    'gi-`zPKNkQCt657geE(*_wMPm|B`kW+U)gY3k+AR*g(DFda`kZheRXjILM#o4#9h??fIKG6yrf?{2?X%8@nP$kZX&w5%mj{7tlO-'
    'r<3gLFbjdxI9V)qp^)DkD)|R$RBS$<PA^q~iI7O&v|V@=cr_3VEUZrm3EVGmEODV4@NPB3y&F1)!}g`->Zhya2kb&YB6{jeG^!+j'
    'fUtOlQhwtOA{FVB+dDQ?rkT<sF>)ZFqKqw>F_kRUHTDQdwD67OazRAZ`<p-bxPNxU>E-(P%j^4kyf&OuhcX5hu5zLUBS%;X_Xhea'
    '2@^IGGIqLiOHW%#Z7a|^%9P0_RLyvDXB0A^SP^6xBekgogqWn}AtKpdu^+0Mv@IC{$-yq-^&Yq&$V8B~!M@UmhKURWvsMj3TBpsO'
    '8<Ly}f4Qm%jkph{1O%UkZyL;&atnA9z7Irsxu-=$vS1b6ty?-Xj=q0mKPb+wzq(#7WtKD^69PvXjV5$d-<~1|?+uU4i|VxbRol{E'
    'p)yujvXYYU+T>(~hZD?XSc_o<3B(s{;_ZS=qU7$TU$n1WwzrW}bOLcCI!a4q;VR4Qp3EB}4zUt6azsmW=Z18vR#;hM%%X6VVZF-d'
    'pRbN~#H?N%Wh(R>NJ(lBnLBrLW;q`C=uR*oi^>XEt`H7MH7rV2bOK1PjCkFMi*cBfbrKF2Fir2=)#d(p-Bms;I=0}l<hR`I4&GUh'
    'x@m$ZBAf>Z9)><}0yd?$ZtHP>+KW?8!hP9WA=`$?F2QSRQD0lJ93fOfpzss`v=$j$(8CzLIeH6O5Fb~t<@ImO<Gn$~PiUsmDrzN-'
    'RW3I^HHs#{WZIiFzVodcdD_Rt&gyI)bsh1saw12o2Zdx_Gyq&0(CVm(XnTY0Vt=E^eaBu@3|(H*C45(1CBP0wm^Q^LR87E;PKaDf'
    'BZ5~Yf3lGxiR$FOjV&VTxO{10Uu;DvK_fkcFoB=#3<WrdSPtV3Q6WW~TA>R#bnBiju*hGJsl27Z%v7*ubdtn@l3=)yMct(@%TXpq'
    '>QI~83lLVtZtwE`D!~y;3M<nQ!FDt!aJI*(c@)(a`8~`usJ<eb-<+20_G%mn%|rjr6Du)(4fh$m{~)enT7(MX6eJlI2H+YaITKzu'
    'H`gEgC5JqhLvUta3sDh84Mq$QNsWxjG;{-s6bOVGk4aM+0^no1`Gy5r)Ul@KCuG+lH9%HQR>{(T6A5s~q3N$bK(QC_fU+F2G39%9'
    'bg_omoIcBS@A`Hy18&r(U|EtyxungkPuCBosd`?pV^B2SoElw9GU_0rBZR{;=|I|CzIE95U{*5;Hwp%h4s!37?m<g7Inva)`5s$t'
    '(pYzQwA}2p1u$#FF`xXEToI6(mOR~TthMNTVRnM-<@UWScRbRL+OHi^q9w=Y-B1<U0QQ0ZIHC_KYqXwpFvvfc_c7eLqp!~u1|RYc'
    '0d-;UQ=3|F>WLg0ruN{mmDaeGNMh~6&3Vw*Nr~%Mp=qV`o{?98XtN;ePGc`vdXhaPcb2Ma{G}<AW_QO<(x2kXt6^PjJIdlSlZ7yN'
    '@bHEr<Puef4Bg>o<zGdp5HP#DXH(nd>7?4nM0W$Cfn1Rx)<A8M2Of+oEaI#TV!%LT$kNUC?Py<7k1_5?S(%u-Od^T!XAOmPhl)T('
    'MexlP5y#shPwnI+jA4H$P!6q<^-iu1BjjzoGm$+KpP84I+E$femIUyQeO$<Zp`<s2W(TtvpE59fEQ7G{4K#nSkL#jLQTXIh()x7I'
    'R=(d;M8HCx6R4OmrUc;t<weFaG??b#TS*|~lu*@koAZhPip`X}g8*Ps3!zu%s~&~G(5^(a3j71efW9x`36lIBn~}V*pq(O=N&X^t'
    'J#78@PG);Sli)~|VaJewIXnn_xMvq9xpi(t;woZMl*4L?(yS((A|Yizbd3pjAa){30+~_q+!K4h=MV`_2pa!_*%SU6SnV-Z3oiOh'
    '!;ojfTcfFBEtw7hnm@`nr&)jHo|~nySrGE$f{h*#=pAwy*eNecbDwBiP;zpT0e$37f6FDwgOO$eEal9xEr{P}z2QD+H5Adyiw&kR'
    '_!C#8#`jSP!<30DV5gTSta#oG4wnC1>}``tI+;^M@+P25T7$j3(L5E^Ok&rlA%=x<J>>yD=~)8%bARFuM5#7tf#Xdh3FaMW3Nsra'
    '?vQNFP!TYng&_zV4-428aK#7vT1tfKT_J-HdRbTl;~t5Wn9eR%9$3S+GP0xLJo5lYd-JX?&6C>wkO~7)dSnZ92K1fNd_#f<M;~D&'
    'mlVwm27MWG^L~D0QPysXqz^WLQS}5xnXZ961|?0`M^85l)E+yV73tQyo6<k4-_z3ih68}S8~QkjDZn9^SEJB~M4d?8h+5v<x~Fh('
    '$IsY8?)E2F)_(&l!JV0<p}?{O{1g(o>|Z17FzN*exD<Tt3Vz(b?B;@5)DH*ZjcHIR^WT{Mr!YVk+9DFidj&6Z5KT+5b#n~(8Fs4N'
    'lx&3}><I*Q@cuO^4NLrnSxV5lu@WUyMw0Aeyl+#ghO6!R@LB2d*))*kSjOOt>4W#vP$ZAS!KEAOhFf>^9Z9L)5XP>p4+u~Dq<d9k'
    'oEiqCkqaV0gh|LhCriHhz3Jh&Bi-&5@sWDBB|D@R?&W8|fL78k`laNlJqG>M>f9^ytvkAupX5`oj~W(GfZ{=!;IcFOO710C&_GVk'
    '8pYeG@ikCwA+bUzIo!RSb312Wf4$Lrlj|mj3EU~`nq$_aw3AdjK!sp-2`-9HckXQI4b<*Qvj%%9yy(p#bRZ+6wE|^<YSao4CzG7U'
    'cgOXt+SBp#>q!Y?{e1#-N<cEQYlYg?;j%=thnpAT5Gp8&4KyDVuhsjyY-Bmw$G3<XUKb<j6TAgdxb5}igxf0tvrq>y$c(jd4TWxk'
    '@Rq(a;ET=jj+^IucC`1ulQdDK5;ox$?_$9SLxxJ|T+yRp&JXuZeq)4k@USQiEaGGCmNf~}JA3-+kBX@!6GeGblT7S!GQuDOqy?uX'
    'ysj~-S=@ekicnbVca*UGP7i9ulS}?<et8{@q5^_K*#Ig?$3s4n6%s(kCctm6>ksRWcP&>w+RUZjeR(pMzq{1)g<Pb?(@Cx;LJ+Vi'
    'z$1dZTTENH>EJH#-e7m$y_M4Y;mFE2g%%u5K;OxnS~_WVz;}h0(WEJ`X+;b=IS)j6As8?JS>)bhf!V6@5qK?<I1h5hgN6qpmPH7_'
    'APf!=ZDmbUx@Q-qCqYDE4uRa}IGS*Jlg6dB8dQQoBxbKr6Y<Gu>eJ}+(cEqI0i&k_eS31>7SeS=V@4C(YXCQfa=j?MRLldo6XXO+'
    'Xn^;g+I<BX>bwu6eC}|ux;v{#O7$^vF9?{5A^;j$jxb=_5TI!8!=Hoh-7rNeuiFOJ+?#__7PxuTUrT*-nckwPiAt3*YeFaiaV<B('
    'YZ)3qe}*yDWIxmTUGU!@3s!9M78x}c0M0JJ1<VjHm}1sd1Ai9TFP#QA4C@v@zXBbDs`mh^0-O;OI!KFHo8V1KI|>#!JVqSUrOjms'
    'p<SVmyU47hpSjd@Wi1b+ScJxyVZ(m)Ov@xh&=wCQF4VdFDbqV45cYoECN8k&+d(Ke&{1e7A-^(uW^_mvEsug5Um4M@0Hxs$m}%vC'
    'r0;~&Q=K%>XgW%y6$j-G&n)U#2-KaLym-&>jz-kz3=B)_b^xKoEfXi}`2mQHAp>$f@I}f{k={FZJ0cb0qy|i2?EkLm+|_L?l9aL('
    '#2e`kaIrwBLsf|QfxrZlrI)Wz$A}NSFJtakzJ^PP{^1c+S*YP<(MTIQX|k@uBO}@tVHubQluhxY;Uf8!Z-kzfCsgVSEi8`)94bH7'
    'U#hSG=>R&I`9+5|h*E<94$}+Vy4EfKx+T*)oeGB$EgQcM&v@OJz+m)?40=$UE1<B5)EflYb#e9D$3M2E?zAT4iUdkoAZ0A}5Mu0V'
    'Dif6+W+On~Mq23VwdGEKrZqjwx<qpelCSZcvY0HjFkgkPgAf96Te>q&oJW8mEVqqjDD>@}J1M0Ogg=Tm$|e}N@*u}aR}*2O3^6up'
    '@!mp7maSjE4Xu9RdR0;@81gftkV4(43C}<_INxz!$S6S;V4d(~kf#+dN0Oii@wmVJluF=}mxx{q#9ZXV;rGY)F=<o!A2OP#Nn%iS'
    '38Z{A@SITU4)*q4{l4EWx{5{PvB^*Fv0%%r)-x?~v4^6R0&+{zMQ>0ElY7Yyh9Ow(?K?W_LScJQ=029D<Y1|nHCP#!KSCDB5}smN'
    '3K)^T>8fca17qLk+qVO2agT!d^7fd$kPlEB3Q!ImJ-Os{opdJnh|%5SvSSY0q;VNivG#bAl&X{@fPER&<Y-_0Sr`+AcSWZF+93}b'
    '@mS%FK<41gK+ge9YBXcDEy1GcPwK>_7hh#TC}p;A#--zo<slx^1lVSDOSa9j1X$3Iu6k8Ii$XTRR~UUTnt&9gVC-apZ^Vn@F6Aqw'
    'WX89@RH|QEO#fokg<I#BlA%o&HCCwv&WE4`P%&G4B_cyK5f;GCV1_lcCsVop8Eq~Y1Zuh}jV(a98DK>2_S7?YLq&Bec<e~5Qj;rJ'
    'yeI_T)U-9dHl`tv5pYSNGr=qntywoHdqj7pu1#o{ep4}*e%rzRfNTTQuQ+vV)L?<&I?YSg>`l~@aNqkysDO(Q<ER*cTg=$LFZ;(i'
    'UEGr<mF&v#prfP7=m{nT(0Rp)&Wmj?<^Y|=M8d|%TbQqvOXJAEm-N@87gKY8{iWl4Fo_7Iao<5wh)yPWC`G_JVVZzWQB=ou8(4%q'
    'g<)4vo!~~`)8aG`L_n&Q>s*vap@AL1Q1rH`edNo;<pL2E9V6wK23vut5Tx+k)X*{T6}HeL3SsJNQPi;A3o%uo{_`blPOrO?x0+Np'
    '+*zQt5X+HqB@O9BBh7ZOE!T)C)Ip&rd)2xNvZkk79w$eJ-!BpgDI>B*Qjm|@sL3$sp=qAO=yYX=m}S*(yMX8*61pnwX~d_402p9L'
    'QISoWsLgt`uJkce7LC|$w<O0Ei(mXy&-MhHviUeS5H|vS9;b=b3}==49RL_I1GyD6Kw2>pYSb(ZsGGm7`{k_C3q5U^c*NxaJe5iE'
    '@I7a47wXUD^$)gaFY<fZeZk)R6Ra9=7_N<iPaZQf7-69~P|%N(2GIs(`1lY&aEZ*&<U=k>n%)*Y&k5JaNH0!W-aZz}{$5jcfCHhH'
    'gZUuxAO|4*P^zuaiJSq;jZnGzn|=A)jA>G#$5eRg;IxaYBWl;>5u*zR4Z}CPm%Ae<9q|*j;9R+dg~++RYHSPT4PSc*_K=R92wg-n'
    ')EQJ2@b3~QuTgPQlpnsWcxiQ3y=<HrY4jjc(`aZgKAv|HtN}F!+aWCXur__y{rTgSSH5wB_JNEOfD2(kUdE!r>gA?zy)u;{!wbZ@'
    'Wm>a^if4|p0#^eLa$0gs**WxZMJKUWv8b}l@DB3(D=hoWI5Agko<^m}tL0j>_!ICSa58MsQ;`wT>5^3^J=9Fow6y3xzRFhQ_2pgV'
    '?~gxoCT5W0k!fKaNAHXoz*$@@C4&&A;aF<cbg^PSuXtQ6qK{Q|DaM*Kqgvr*$k!Q*VBqnLyl1#Hkc${8t)A@YYZrczl9v$;1*J1h'
    '12F~oX&&E3Qa(tMWC9#yP1HbKgwV&CBFp0YvP&ntDEP*|2GpLO0pum3B?>j6btEHHFryPRf&4oaIpN<|UC1s~elgg?!O<U+G)yRB'
    '@+c=}*sBmEv3H=2fDJ3&VSVMwDl4{SZuKC41pa7-QwU|HCDT(ngvqabG5LgX{WWH;U3B5myoqg4w@D6EeCA|d)M{jQSb)K~q;~~-'
    '4#hTVPKxRg*9K}xQzX*8ZQ??op>`}OY^{JlZb`6L1T2U(>73KPAJofd(6N3##bm#3-35=OSbiy}dnZ~laJ*<GPKw>K2I7EW7CTA|'
    'C6^cyv{<?Jo2rnM?E11?gp3^0<Wh_X<%~mTN?H{pj*R0&mthcw#i?@H{PeBhn8n;fFl{h)0y5|xInIEkGVOnoUXKbDaV}Uv<#OA&'
    'STMOSR|91RP^XQrq1lb_2zo4&O4JEpm#6JyH%kgwdz{V<mtA_LT)dvqgQtUr0b`=IqhiMIPkza$w;7WScZQNemP4*~;oo1Mub-h_'
    'wuYL0jY{1}i-6xGg5E)Stqd6PBGdeqp>n<R5VFnj83f|$1E!1PB>j}$vBS`5U>@)+aT6)A0g6-HAO*;^>%P%%%dgfzvJ()1ktM;B'
    'LxeI0tc41O2r1e+R_)BV2&-4Fj8uHGbWUI$B!09d#gI{HNBf(RMlfxWbE9g^ML+EC>+knp3VqC_S<3~F75yyzjYl+%uLd@?FvG<8'
    'WweK_jS`x-UQk5w(a0egK{gj3Vl{mBxB-B}i4>%;ROj%nZS8umPp9oNr}TPR$mk_`(2ABP0WYxHtQNlJZvw_++)TTstv*k0gFmxl'
    '`8wq%fHt8i$roCXvPMC{Bw&^bE_--$fk99;1N&6&;0K4~s^uAHM0$f44}@RbROLr21P?He+b;=)p(n;9hRWqHzQ{PMKb<}o&;W@&'
    '@TA325uFTONvx8nPl?a;;lw6^$c|K{a^YhDUMhe}VD{X#5fWyQ7b>2YR<Hx*0SqiERE5p4TeBd~xcK41J5YxU_9BM*d^@z-7~bUM'
    '?N8W3QU}h)bvReAD<&0KUIjo6Y$&xZ<uFk6C<H=I!$dF~Dv&{;#%5_h)JEy=?nOTsQC<J(s3F2IYL*9|GA9|KKIk~mDQBFc4vk4p'
    'u(fya8M6f>{|3+TOCf_N7~)qZZWhpk=2ekXGOs)nWY~^)llVW>=F*pb%#vTFg6!4GP>|eXV4fUd1cyB*JJ*GviHMLWO2L?FOO|t!'
    '`}%L?nPLx`aUEhJ5;doAYQ}Jq0`PE^ZvX)GLtM4u2F}dY`w#>cUqu|uHJz7{6<ii94^y^P<qt`1pmB%1Y~8BojAwh?SLk^$P(=OB'
    'Pi!Tf8pY^QUtp$!;xbWY!qx1$>feoZ*?IlznGf!Flz_ODA^qfoTE419z=6Jx#w|yj>6xK6jJ&=qP~z*02rY$<0K{w_EB3^4;v>oF'
    '`Ld}M=zpk30+N~)TWW8LvxjC~$-r02T(1rq*^*sG$j}&VMA2E~R@5>0uEnOTwp=+IM#@O^;40j;nT{kDG3Qvb1Qwz=ck`gxBobkm'
    'g_aphnE|T6-Jgf^8~(K6uUMOJ3Z$7?+&$XO=oN<%v;i|$Y`jK|WKp?94TE~ntXcSNQq^VT$n~Sv%c>iaB{voPbAB#JfV>W@23c5*'
    '2PclV?W*-JPW^S(^)kug$xD0(lZ+1M$c!FQUyY`Vl9vVa*{0~$_tOq8h{Th;%nw+<fEE-yI`O@k5SP&q!TJuKG(;*L38T?HFoi+f'
    '{7~d3{IrLvg?Y@h_r1V2v^Dgcplb19tHnx>2*)7V9CyL4UReKjff|Cb26!eJ3oJ%TWK2kbbZJi^jlcp(1ViTHl<tu8{FthvChHug'
    '{bqntJ|#{ZLLy|S)H`XG=k@^mS=9ByiZ9z2geav%jM7P%i`Udhs{sW|`Ok0+@)8eKQElY1&Cz>fD}TJ8#2Z1CK-1K^t`j>W%H)xb'
    'In^*3HUK8jbg>C=woq7(?9!h<w|xro8W<3yHUs3tAXi(8RBWC2QzEu95lu42KBTntkxucm`#u-(;f<8=-F>fmb|DgLC#M2U*s_`~'
    'D;7CBWH6&90rU}7i7%5<Yc^Cf+Yli!Mycr7D5??ljGCQ5`9*dLtcy*ErUXD+Y46%j-4sdB%qB)7qX~n`p&mQH7ZN%nbx6mi6zaR8'
    '-1+)WmMM%cZd(`&Xz+;!hFj{vRv#oOI#lY!=uF1ch!F+_t7zYH*$ObXO3)hnTIT;TegHFOtYVq9NK8jp)Tq$+k~qO0CLHvx^0b~*'
    'fTDS4HiVu+u|lBx>SfpKq`jvzJV|?xQjP&B98J<V%h{-2dr`ukZ`gD=EE6H<*_E6`aifN}<Kea7aw3j}#LIY`QH=7y!GFnp5T&lz'
    '#7ZX74AzSafW|&9bLw%gcbWqURaZzbv@^Uj%VQ6I+`;d!N^oj^ew&zGY9%C<0Tl!UXm*@?0q{|>L^ZB4^<T62iql6gb{4s3p<=3%'
    'XrxBw6O`p0kR?q!;i%J!)z=+C)Sv_*@^>^ncsF*~BmxHUP^c?3bvl6UF|ns~*+K`;n;+)3*Utxn91m*RNskS?i#M)8IkbKnq~f#m'
    '6!hys<HFhvTr$0y=}>aufNP?x7S&9*eEMFvJlQ?e2oyC*=8g8oE!2;N;sY4v7DFvdAA)-tY8fCaNs!kt1G`KEF>AL`KN2-d{7$^#'
    'e<K={_s^s`^#GkjB9(g`b&x9#hx%X#Z)BP4RR^Q5U?)I)BlknWgqlil6)ZEv3b@L2YQ(xCX!5r$)HNX?>f<=l`UIJhDWqJ0;IAOT'
    'EDR7#hfq9WQ&e>S>*_x<4HqAhLIw<YA)_1yeuBrs*Pv5H3a&nm<TSu&+=({awT%kGBa|e=cfl|+U|F_=VJX@!UceyY)PP1&sOe<x'
    '+DG+-RHmFz1kHkwa3a8Hsg+OptW1_(8g5;br@3hA`uELfQ0k^`@|G?K?9v!rjD%_ep(bh*D{;J}gK8;KWR1n0y?PJuYj)|etbqhJ'
    '<@rlg*2@0{!6QS>a0Z5xicbTQ@ooa2DRL3s-M~?na;5u%X1G!$#>&u-m}N^WmPwLVD-MzjSiyXcnICII#M_X|s$qUCGc8($MxME8'
    'VSy~8lK{Sul`xA9&GqV2`L>1Xp|KFkGMslSNekuM*e};Opn;s3HO-dxtH$2kxR3AiS*wi3q2w}=D7Tts-O3clE1e{#fQv)37wVa2'
    'akg&lX3nj3(u)8!XrrM~g}W4T9|q_6)6p`+pC04Gs2Y$gTT_*tgUL!_b?ZJfV_~;sSX@-aDWJ5xM~xVarjg&61vncPgHffpd0d*{'
    'q1dMVU@zwkn;q>cgm6%!GF1(Qg^cKVHB??u9}ot@KZFgzNuo3#&23w$A#!6R7&MCz+j%VMxaO!rgM7qcpfEN!YREO{-rCRwP>#V?'
    'sUZP>3JN#P2*}JN^we_-m2^P3=xAcY_@Vad!`i6vvvy!pg}-?8>k!3&?I8Q28=*;o)if%+Uf(MWZvr^rQ@?U6b-q>H4h(BS778(x'
    'RtW;`S-Gv;cM;L^?Zlz)*5=yzY5Vw@v+#PkP@f@a7IX!SqU99!>TWWD04NUunn9vDiWtq{2Kox(?XJzT9)-E><VdRIcasl%uG^xh'
    'f*?u5mwqqk_K3F^SPW6DB@HBswW>!Ve_gv3qB#5lw|jlzm@Kv6exD2D)PVD8>X2r^0fNH`XPOTKlPE|R4IB^Jm0gHy9}1&lckf*#'
    'Kedx!-1Txm1svqjQ+Uu?!rKk&ao}dUwW5i)VQmHSLyuv3A!|ID8x3`nl3tTV@I$4chTsMkZI6<k))sLc%LTvolZD5<j=&AMl7y!*'
    '6h4~W(ZQS36f^F8<b%ED)CaLr`rG$W<Zdx0ga5;{b-a`SgIjS=v+PtDBt|VFY9j2d)%S?Duu8bl$!-|{9G_*Qc>-9&@^r+^L_q5k'
    'Z4roFR7W@LV}+1`ML=XQ{Sq!_p_IcrW>io^<eU^s>|(;xgd28IDJh@@L|d0U7_lD!Gc#}bUzDk{N>;T03<+{>TwSG|m3Etp@~%{('
    'K}DL;&{Ly=+7V78Gp|HJhV4zK0A-@-6FkDTdsxSXrVz&4lxU&xdi-+Qbg<r?sJeqD1Hr`RaIAh1M2E%H=hCSx4?Dz|4gz!^<&#V%'
    'jMze8HpMhE5|rIIS+uSGK-LU=59$a(IFzLk!2v25a592H2-FnH8vJW}w>tg3?0|1nA+&1tH2qpMVz9&M6hiYLnq#8HKn(<IavO_O'
    'Z731i+cxsDUqU)J+ctbDm_Gnuz;4wkm3oagK!FO<4Y`V<Nu%GhxG2+Y8(HWAH7}+isl<LEk%?nuq!DZ$X~3kDDQZjtb=UC2wb5dy'
    '^@S~pI01_vTjFB@J)ptYXm}swLGCU#KtCHB5T-^L$!Ep3^Q%9VOM7!&Ul|b;JPnG~0J^G9su=H(pV`--384@V$%xEw+g{donDHwF'
    'ayH`pHMjwwe4`D5S}e(#f^T||y>>hL+jeuNv{Y>bY8KoeE;T6GU>bG-ftT@SqwK8dO&QVBSHGe~`+3RFD>a~?3lxeP5~?Z35I+6T'
    'i;@U|+i~+^g~ijs)o0~aUbbQXeJACxD$7RFFxC;z6-^m3XC9Cd{kD^0083TItGQctaegn4X^)dliKEFpVdy9Lj4=NK`yvQc5_G|P'
    '5zU+YLxQ&QtcQ2EaS11wXlSCsc2~k&7;nSfN<)fNC`h!xeZ#?J0uO2+SQ=<5Xycii9?9Fcyn>@buLA1~<P5pdyfES^#gjF%8ZtT2'
    '_J*^8NZQ`AogcWY)etGvGm1%yYH}c&X0-7F_aQSLxO|a7vcDkrpPRPxW-LyL{aB@5qQK3N4A~N9@EMg93J<8D<m$jKh?pR(%ai?<'
    '&0L7Kwa>+9Fo|pMu|tqRJCo}e2q;RIND<7Tk-Kh_*Ivqh-9KXP*Wq+H`ccoa7rFQW#h?YzphhIna;|{l29OKEX>H!f+wp0^vQ_6X'
    'ow-;{=;{Fwf{cPC4sJXFb1?KrFrwieW8nb%is?3!UB8itrRVpD!K-@QE`t9e35PGH*U*4TT5xELyfxS&$VdSt=nV!5!Ny_jhWIbX'
    'PjgKd4B&x85+c0%kZ@<TF=n#zI3Vr@4YkCVhIq4fBlY}UO{RAAeZ_z$%we1h4GqoR;#dTWrYFHh6tFhRfzw^g-UCC`9p?OnT_}ve'
    'bQGYD-U9stAdTEEEZkC5kqZ7uxL5At3d8oNGLxHT)-Br$(5Klks>YaU&3AH~Mw=&7mAv*tQGLtjp@ER40SQRAV^8lLMUOl{HLwEP'
    'c}-u#`I3}`QQi>brnLyjh3vYyC{Sg>Qz&iVPIDF~*;Ij0TJZqktQgJ51_Qv$Sgqo<ar7dlf7?xwphFMAKp*R^Xn*2kaHrr~K!)NF'
    'InyWv*alDU)^7tNTgj}+56^Yh^{|D$4Dy^tI>JDeMLG-`eDqp<v#^)I=lE!cwIAo14*Ze|p}{i^oo=7JsT#&y5jUaa;=)8?B=c`r'
    '!0O9Jd(-N5WaLSJDT7*D@(vjq;#@Hj3+S1HPSOQse-kPE+V`-yhn<~5YM^Y9b20}J10L*O7#&B(K5J9ddaZ_U!U7j<qqK{45y{Jm'
    'mw^U}H|#Xt7;!FQMhj<#>HrcOr7e7w(yHGrEWTe-moYzu$wN-0ceM4mH#xdW^s;D48~7<wW}$%(y1RY#>J?^feB3aCAaah(I|ka*'
    'i$}@A(}$Zq;AYWN;-?}z=P%EW`sl}a%K@rGgQGo3(#YpU=HJukhFFR%Oe<RSNDHO3^f}CYbnpIT;lQ9hV4Dd4hVd&cH!M1=ph4|4'
    'm64Mo5U2Y*Om!<(2R7UYF{Gv`Mjr;tAugMRq1wpAgUde1NsO>t{GrP?T$clOu&SAqGFi(g+8LHCvYcfY2Im*@88h1Cr8ZZssF+np'
    '=tpM`uZ&y7gQb&glJpI%gios`HNj?RX}|PEP4ExP)<g>Cuq4?o4w|P!eS%dlvr2WWL4Z)6!>9rEC^|m=uqvEn^`WoBPKZ>P8_QQ|'
    '<m|}oG>#MUBVt6O@hmtTF+!(Uv;MGZ<qd%}#8|9-ob0Noe_-eLz`+RIaXV+y0B8o2PKvnj-xjVIr36<Omlq6O!=!<y1MDFv84jeN'
    'r%;}F0~BBY2p=tduEigIOxPbzrLphi#biO6l!;#i$Wg1&*x*<}*8qdsh|@h?<qvN}YRbGnJgaAjI>SAE`;USQ2$+Cz?i6wjk)Lj*'
    '=F2m18mfa)&{z!EhL0U(e_ZdvniK+3^3un=Q(_P7^e4b<tnY{l<i4aKB*|F(s@~3+qpeu>g7=r#R!5TYh)JIgaz5HGa?kG>k&IDT'
    'PGHUKf`heo?Kg0{Vhi9L@Wi3vQ3cWWl2a)IEoEAOE;>mcku)&+!&6PwbJ89jC=WB!VgK>_algCri@`tP<H9u3j1Y8n8di__N)qi1'
    ';0rllh9~-Aj>9UyL&|tq+MJ+l?;qnI@17=0)C9YVxl%w%cDWN6fWh22C{~EhIzgl#bMiHg^D^Z6_@Eh>|2X}5x;E;kok7fK@kX8?'
    'VgyQV(&<5-g4lE+?;&!uA1lfTfe&v#@_j+Zk3WvC1N)~BLF<+Yl2lJr)nGEz*D%fTY6=n+eLSm5tBFsozk67)_Ci+*$u=YpT%V~I'
    '=u|R_5ZWG<18u?{t~(e5X6+x=O-J&o2lyQ7EnEs${$z9clg)SUfa~c?uQ|d{T5zGn(gRn1I1Y?LBzF<l0SE>@4*%?<O?>~o2lZtS'
    '<v<9sMMW?HoEzzENLHW}qo23TmY`;L@`Pf}-FqiUE!R)pec_yb|Br>BD`R(NxKaU74LP)sDCb8QO_)(I8iBSKFLt&SYn^9Yp8og#'
    'f2F4-9{f*t`dq+ZIV<q<Nw_J5gvEM&mC-G8=>(ATw#WAi((~#xNy6uc3p)c%;Qpnog2V|Bo(RHL1%(zuLeLN@Y@3Pq48=eXhye9n'
    '^5=VNUjAAr|Cwip?ICe4i}m2t#G~?tuMX`s4wQSOtBoxzdCu}bEeyKC5Nw8*!kOcOYh^ct#?X<pKovu)B%2Yj(x-O`7w@bWNrJB*'
    '*lzhcs1&hGgPunF9&0|N)W|KFVv2o!BkISyl(cu&dwgY_VS%C8%}!lW@J6mn9v&`}u+HfIA+f+~g4h6ecCK3wpR!YF_UE99MfmRV'
    'gP1T5XPM`#X&HK*-pfH&b6LZOpJdoRoc#ulpFVFh9^>G4=kaMT`$9CpkPT%h_J+8(A{M4AEn7B15|})gB1~n15@<!m(psy`iD1G!'
    'quKD!mQ5#)85kV`%Ak;?dDS^7nD8v^-_=k3ZNb9=B$xcDvGc(XWq{X-eF&b$h+?7PqDjT0mBI~HY=g9=Nfj%;z7(1Hl!hGybU@Ep'
    'R2SNE#C5CIKAWJ+fIAqK)Z{)|EhhO~LvQ{@g3H%`lxbG+o3t|FLIy$V!)Q`~l>vbY_X<?+UW#voxV%}jYE`BeYzsA$mpM8e36z^G'
    '$*n;N-pS2EBa+~CFwm_xO<J{V@d67{)6=(tRGq|K!N<T!1B0SpVi+;wG(5wsS@c|sU%yRI8wvK8sV*}b_+a6%P%(m}q5maSfwxMZ'
    'v-xOQcta1%=kf5*S7463J<mz5c)6tW&@eI02I!R~i402NYoK<aVw8cTbPnO;r~J{%H8c@~3z*9g5s0%m-@y&Re}yzqb|q50;C_sW'
    'RJ;0De=Y?kiZa?=%lxFkpL3XIy>#5GFij*YO$M&W+?uru*Nl$^z@L~+jn54gDI7j{bI7_S_+cn$2SteQdk7!@=Hu}-JwSjVds$o*'
    'Urw$hSLh);bAq^2$(SH%wG#4kw0YnpW<6$PjVy@gsx`}Z9PI+=)YgsoBk-%72H*(gpl0Q21=4A`fXIcbmaDnqum^w<fJ~PL84XQ{'
    '3J^u-#U=~qq`b6@U<gc=3!X}uC)7S(BUbyUab&K~NK&39#%KD9d7AVQ1;!2^t#`o~&N+5PPJ}TLw+a^wcX*Z?I36Q_9F+OQf4aEv'
    'L#Q-t)p9Rf-xPy|83%A3A|ND$(;2ggD5Hsnzh`_Ce%uPbM*g)^)r#+l^nZ%;j9Z!b1<<gW(g%nS5#I;~wBl0Y5e>T$Oxag0cAm&n'
    'AVDFOnl&>S?`0BOphgddPi+fxV%B$0&k+RlqxCLv{q3(c<Ml+EMq?o?brxrqOPme`4hW#E8kNSQWiKBeP|Sz-$F1V&!*X1XZyp{6'
    '#}+fGwauHOEx|G2A@aldANUc`Hu7)b=#HybEl;JO9pp3_no&PY+7YAP%2pF{Jwm=t-v)lF2)EWRO;bPa^K}k8ic!sdmcbPrLd{>p'
    '%ASG+vs^637=Z-VELC;=>c|BDIEr%k@><}463mIT5c{xrw%ATZszP2bED#bj8bXLbm>gceaz%PJV3sPJo@$WJ2(5yw+Ea=GoURpv'
    '*+TgEMtNsV*7@gCL9$I<0i6Xz#mUkdpa>HdQWTItE9Y2>R8(K{+C?w2@xuHhSP-Deh&5C#kuZ4mgHYs&{DhM!cMQqQykc=>43*Qo'
    'Xmn-Kj3=<(PIlAW;!YMCoqR@VMBywiN2vP6!5--ho!nX2_2;QD3<F$)3mqO2b9$K#0S3W6kVLWtQo<5ykby<6Uw-%Utd)<9FfELf'
    '!*_?#j!aM!5s#T!Vxf7t6>={?gQLv=_`o+-zxL%eI!o&c05B>L{Er;7cE~9#W{E8vbBJD}M%_#u0L&yYRsG`n^Ue2!eOuzr_QC>q'
    '^3Y)TyhXz7v1h;_vQ@!{4I1(~)2I6NWfPg72rO^G?O|bQe!7IXw?F-K7UzDtqzl`NSan<1W@FAC-T4H$3z}1_^d6LzQByocxC^iu'
    '5lwL6jsN}I{;T0!x%C0G8I3Dw9vln!M_y1O7!4f{_{z9-P%?3ebroAbn^ArcOn-87A82vl_6_2#*NYVrgGcztk(^84tGQELAXCi|'
    'm&yp8=F)MfsKb&BulatcFu^Psk?Cl)IMir_QNA<$bXz{NnwVA%w$ZQPE^3%&OX4NZY03#rMI#fFZ66NMNlvpLeo`8RnV5rcJz!#w'
    'i`vghvdzQ|00RkzAgGRTR3NkkQF&<{eOO_h-Gm;zh#~G!^SiJNrPBy|%}oHY6glLU>Wz&Wv`mR7GCm!Y5A*Zm;n8nOKWosea<M*`'
    '5Q8~AQGf&;L=>|I+H;&x2E`x&`tZY&;OgNFt|vTdKgDfcW*DBfg$^f)D_thc$k6!6=#gSa{#>}43PNDUDhVDibX&V{F_{~Xh|%8C'
    '3<X}Ah8fUD=*g^5Yc6(S8pcLHp?1NaYUb;8NYM1>iJvy(84mXYIY-h2q##+|s98iD)iBhqT<%}cwFTssaAlNPDOm;DT(TNQY-xmq'
    ')o|P4;{}(s-YjQ6xutnhFbjpZMQz2LG;!%$Niu+Glh9$J4svxA8$9B+a!F$ATX*p~%#J7?q7(+scy3K-v^0bfs|_q@ME#&HQWI{h'
    'TlBjExuB(_wi+}I4Vnc396%AEAZv~j!Upx~ae1CntXs1JY7zd+caI^sSm>%euwNS?5aDJ;sw|a<6_K=VK_Sr3igwrECJT9u#)c%s'
    'RO)_~pLFJ<VYrZ$<2(b^vFU6o*IanSHH|lVgOoWO9!%WOBFqxilaO+H0D3sac+bLP%Kf@^3rH59g~ljxf)if}MIDYL3<D<}BO^w4'
    'hiO{lhjmNBQQj638aRK8$;Y5caAF^j_{(G%VytFMk)vk+aTDx=W#6)z0t3KHBn4<m>J0}I+Bm)r5R=iO&_kx6mUsA6`IL*m2(oW#'
    'E9|d2^)jTU1jEa+wdGv(8cPNR&G_ooii9C~mT-n<F<TkjOfkh=n=I`DGJOnzpjcA5=V8@~?+wuT8FI(vTk~?5?uR(7gVWcDyUD%6'
    '#A2v+==2aun7T!eq@R9&eN-fn9kcr;(aUszmo@_2YEhe^gz26kC316Kwc@6TI&17NcL}sFX;Q2Ns+N?<XpA6aJHQ~cZxD&rFI&Y{'
    '71M#K8+<3Y20^YDcadp2(s9$~glq?LN!*y$Ex%|k3M@404In;%M7$o=qZZzc;U^Uv!AhoL>Rb=&);%j43jPj6+X1c;Tri7CFYnbd'
    'Lx|R3uNVydFU!`o_Fye(C>+j<9_e~E-}H;+xKnNj*hg?gHUX)IG7;ZVMt~W8S+;KJV)WMl3<SU60Ib2`qOrny$Y`7<Mv(H3i<a<j'
    '2l~JM$NvGhFZ^l'
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
