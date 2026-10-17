#!/usr/bin/env python3
"""Offline compatibility and trust-boundary tests for staged host receipts."""
from copy import deepcopy
import hashlib
import base64
import zlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

# Immutable historical20/21 and preregistered source23 workflow bytes,
# independent of shallow Git history and without installing any workflow.
_HISTORICAL_WORKFLOW_BYTES = (
    ('d9fefd275d9e3c6977cf9350a1945a6bbe5051b4', 'c-q}s>u=jO5dWUPg6WDn0Ve0Yb{;Y;ON=J#>I8|?p(qMLmd-XCSyD;LiP!dj-|?k~CClz3S<!xq$-Cq6cW<gck&~EByhsqiQZ67MiRa&VBOoJ)fO&$((Qm}_1)ZwD34`}3Wx(-|DTP~P5FQ(WAW0ljf7V`$ya{y3B_uJYB4#t<kHNp;YjM<BBP2<~(3LWP3;CN6F-w5!KOGV$cxqsNFev@xv&bK_IHLc8S%H9xY&-M@5N5y9DF1yMvzuWU-?{<ii6{KAK8;36D$L1*urxxwMtCz$wW|7G0NiIZk$1;ir4bQhAbvbaLJ)wvQ|f~=WB?@RCV~RXB*+VP$RLhG@S=j;p_hiDBXNgp)u0=6$j}QptR=uERLN9|`f(&6LZy+=3)b+bpE3rKKa;y77N?2avd}vkdgt+n4`f8eI32WMiu~=O71~ic82}?6KUx|FL-OfUl}ma7UheRav^4T9^5h9wFVXm8FB$=F4?GTXccXS!P!U4m#5vwLm~BdCs}Gun29mt>KJ`L6q`vaS7HTO$@gg5Whel4qVr2pY>brQLP@9180#A4jk5lG@wyk#4qZG{<2`LcB#U&ANCzM-h4;gk!8oH86-M<K6tDvg9wkz?IL=%rj#m)Z#MRkpoV}OzNR$J3;*?8bv33D=VlyBXM_G}WaAshOVuuuU6C}0l83?VPP^=5oSS!_emw&zIEqd5Ayx-(CGA5GMfdM_uwp-F-W>3hrtgZwua5PDG~Twap~bBw`?JK7DdFjM#<i@rh#+3aOf1b1W_NC#;oQfGI+y}hq<7@Yv(<xFUVsG<A=wTw%}6k{*y#!)!y5E);XaT9I~XQ<mHGVS7uI}V`8l!RWC^WbJq$^p{?6|;rpmLO+|Frua<`Fdr+2?Dd3i{bVTVdD#rDN*Ijroy-wxB<nRF1}WUvMNN<FXfkuRn~FLh1&>gg|aGSH6&`OtHL;lr6Q0fXGC0BOanKs8w<GS39BNOTcbi*71C&pB2kr<MluR8<d*VhlvaqMwJn5>=wlhSG61u_MkX{GjZB|n4%eyCB#bQ;>qz#;Ua;ry@4|uS`3D2<+4jM+-Gjh;`pf>#w!iaiXZPve!25N3uw$g$VqWbOYWPrJp_G>Ml+re(-yJZlT;m)G=?5stYMieE<CF`>N4v>lg`I)z4=f4xHH?E}FVG<$vn@hQ-Y=|3H{@HDMxjE1xlB0N;^479RCaZSa3oQcmB!o|q%;hiQq3+I=@R^SB>Op{QeD<n>B1H>B5Rl`$3%f>Poe1NYQg-5Xqv<S{M7BAzv%W#HW2X*L`9@~NBy%`UH4_Te{^!xKXT7{{cf+XdFsnjB|TGBdUByy9y;WACpX(njN@p}nsaLb=-TVr$t*9h#k(O|`Zsy>`1x7?^!iV?`wCTcFOK@BkL;$SI+Hny-qFjhq|ln@yXV*ai|hWQIa7FnZf&#R7P6_8t}UYo?yzL2_@P!aS^JmQuXQZrvKwpNW5nsO$u!T_hk(t#6F?%jcfTs0iZSGry9RAWGGy^YAqaPPJ2WOvMHQXC3^VEPG7}aZ?X$g0W!)vdlpDVarsMFjmor|S9<AzI1}B{^9tbXd*mA&%Iqa*k(imlkt%w!wNV74EkfVy;JFb$Y>B|beYM!A~i(cDXV<%oDsfX>*!Y0XE#yT681}A7eNd%j!S2qMLo9|X_#!cH&>bdnip>)fph~@gO7xk?pH&<9UgF|b{@KZFsntJ9FOWqnboTlI~9bM<%#uQ@0rZTzQlQ)<PHMoPJ$o%137<HqLzS@IJRfh;vVTN3VMFzYq1`x@1h5}#8FI#P?;G4It<&(66qrsc9lV@||LY)Q+<^;G)Z~-dKdebFpy7f#<b%<(`l=tnX6MulTWKL>uL__gS9kGtQGC>`d%FbffFpQ36to4riL2e~ImQ8X^LRK2(ngpyg%QXp@8|H%8PbavbhJ^?4uhMx9URI);_q8|byq|3ucw754wu15|{~0mOuV!^b_O)y^AZk3`3bhQSTf0+WILD#Kt*_|$C3e%08t=D6PWD!H|F*82*<kMq?Y-xhOsQ4#N=3y5WoHP?%|3z1PK0@?_LvV3nV5X*hxF}bXfKX}DtL=R;j>?en_sT7=_pUrb{;Rxt`GQ>B`3hbBg&V}*Y={XB!)9QLw+ZbFAElDlHpvO-!5MFPtSWN=e_<vmuLO%pRfDf<MWg5;Z8o;sUfc7&#EWGsZM^>m>-XSoQ}P6wT9$Yq0N%pg6}ycP1kE<cBN?CEMyk@kvGeuj?FRVSE+iKwMx#LUoX3kQ+x+-Y<qGap=uwQHAE&ou<!JhdA0cbo)Xc$zwk-N0Y^{#U-z`Gk`T7VVu=5-LVl7S(h%%(PVvE2weJ{hA%3q5)jVe3#zah1fMwqRN)Oz}r`_Wh?q&Dt`tSag_5l(9b#>m;!Ma&A^(v3y<=3%g&xli<wU<1ODNP)CX{0DA`~^>EYySb4lWnp'),
    ('d04a6dc70213d8b549bac30c11cc15eaf0182dea', 'c-oazO>f&U488kT5J7>Q<b1E0feuTDVC`XD&?UPDvdlDEZON0Uq-oLrKFN-gG>5J8!GKBnk?-+IiWiu`#L*fRNx=zWb`OM41ei&RBCV1LV5`mJD%abk;CUVb0NPRM$krbK1rpCV@ugJcp_(wjhUd<=xOjPiUplq1L7^X%e8zZ>5TE@Dudh*5qA8@cQmd+i&{fJNV321~6p%vv09N-?6`T7e2(l;~@ifOHqZ;aos(Ry;Wu76p)G2bTKa9J>DnqhBKOZZka)iF`=slz>mX@%z@xIO9NCt$exPfDP0$<iB9z(Aa0;SP}f-r-EOVto3FA!MmjKG87&W3rp2szsk0n0;u9%KVC?Bj@YF-rNkI~w;#8Nd86>~%$N-0NQsQvR`<_6|5(N$cYpgVw8>;Db-NG{%kR5tlB{mj-`3v=pb@Vr<vEVOKvT_dr0#d9vAQ9F3Khm@t?H_wn4%z4C87DY7Lu7Fk1sd0mkeI>UdK`j%Sfwqvl=R+2WmI%PYDT{KH7cV`<oT1cyW2mW+;-xOtz{(LA-a&zLS!vr!*-neV;umnD_Q`S3LYc&9N3+xB5>qeN)|4&;@%&I*=>*DL}{AO{zoc^5N&6l&u{HE0;Ss-;@aX0xk4HdOPkJ;~w`D`(7oe6S!Lu3$ku;sgh|3PWRyhAf5&>Z#fetF+vxVnP2mjT;vb!#W>=nof(d71'),
    ('55d08b65a987224ce576459cede693cfd49375f6', 'c-rk5YjfMU@w<Kns`Ffun}T{+q#lhs&gIm^J;!!rJ8dU*H6RE|uql!TKsmZ3{q0=<ltk)bD{01;59coyfZfGn-@E()ohve80g_23C__mc&HjP{mPX0UED#A56No00G-8S&B{Hc1{w@(WVU*nA5sR51iYGB5!Guc*znn@;Caj0fXE8-n67j$QR74izjVEaD<445fG*i-{i4ZKZ+n+yIDoNa{pv8T|fXkF9I@X&g$FaW=DxmhzN5O70E?CghOtU{DHA~@UsRWNlpL2{!60ohHbewPst0dJFWe>d<ER(Pik|^>Cy}6o`NktO!i0yc3nnlr212U<0L}4FNMnUdFpGY>8WAdeVV@86n!J9BK+U>$h%0#YzqYy%KsR_8cqLmXX7OUlk76Z=3FyE~J6wN@3F`a25Bavh&+yUl-m*#>C=28@<wimdF#FRyt#~9Qy5==_VaHVpc_=dHd60>$=E%IHy2Tupi&5dJ`#QZmFx*8D7S7L2inV-cf!_AgcZ<!OtCoIVnp71zR4DM^XW}n5=xow`l>klsa!?$mahZp_xi{aq%<fK37p;{(IE#iLdR(Um_$F<u@1SEjr7#zzWgTti@8^<}nFUO4DAh>kllKHC=kwYQ`#tOXTil|YI0SJft!9Hy@nM(+DebTABou(U*w%2OZX`|C<w)cI~t@{o11Ddv-y3<$?yyI%zTdY7LEbO5P;c;OPymQ=}GgaJYLUO4v1q%W@;3NXxz>_3fdD(y&PEo|C44n-SH{fcvpjD8n{`>jGd4G8R`bDo8Mb;d~+Q$6v)$8HK>9740i!*{}Wxk`58y1)0UiV-8vYqzasmeHS`h!>ZFtqTfGS=DU@$qobe|rhWQ9@id@Lcv8SmLJw1<4e`EK5+zQx*~)70%wjN7cQ#psMKLzvw^j>$ppBc=fSW|GbB;u2!MvPu~rC@#x*ai?7Ww8n}C<(XM`4K>+*BNOZ9GbTmdJ<)|uHn#kJTtD}q8mp=oQv(xjVi_^isYFboqP$K?p_3EeBw+IX5Xv1){8lFFY4%_yY>NDWxpd_nx=I0c&`nOY9%5OUbYYUKECtMA;QYy%HL25%77&F8tlS~mmVmb&0HlCR~jOS{og7-agnD_!;upwmegu+S4AoXLYPc%UDYog0h4A?BzKv3OC76B(v<b;Ny)vynVotdmBImG0}bsSQl#oQK?c8xD@PJii_M57CmmB27K{oB!T87i+g%79-J2fz3D_E%ig@eFJ@-k;}|no1IIcbzOTo9Zk<S#6%$vDT!M&I;%lTb*H3*J2Dd4h(>Q<$>h%^5X3BqFTaOy3z6%#wGx9$h5O1_A(4r0isyjtcJVN1xDZC;$Q~`FIOy}Shed-tvaj)S`14VYwhIQ%UA;xwfyt_W#lMbdY#2wAwT0$V8sVTQWhy$Gj*1g5(}IUlgK=lGM;V+UzTOgwM^m_cRPoql%)mfof#!AT`BC@`o^)>I#w&viAc=QpAOKIh>ZxHVL!>hX@e)|)2CH0&`?1_vkCaLVdTk{&;}VYOR+VhLwHu3`gM;INS1CGhV53P+X*^etJ{Iyme=l3uR%<B^PGLBzBRmAf_SP!kS-6a`%a@-eMk@|pm~tk?<t8GSU7C9y4`lY-Ry!eSh(+Yx?Zcrn()tSxy%i8@bA+7j+KLZj~q0)f)tt$%i!;1N*)$Ks3XKU0Z)Q-_(YfT_dn|zs2=(r3q!x|vX<NOn{K`CdZ68I!}IE%A5bq0sULPdqh8l(-}5Z!IHASyGuu`wHpxV(;MLa^p516y*HVsD&@mR?Z632Fw|tEh)@#8mNT66!(4Iq4n4lNbv~IoLfWcdsJZOO;R&whOI6Qv|2Gha$LI(&aU?8PRglFjA1&RnkGowRX7BPIQbnHO4Dqu7sdSozVE~N4)HgOydJR9j?tF*|^)0+{7?l9yd=nVW(G%<iH*R2sRa{v#bH_Z)unz9mb&Bnus%s>lr)6pG|gXFHc#)pRsoGhNSvR8Qd9rNj!K+6{yV0huJa+jO#rpFe!0Umvc!z2orh`?ZVUWqh__Ylk)(E<jn)^|+KisXg^J){9YphD-1d+BP~ZQ5JtVdLRk4-b;Y;H4=Hg4kv{R%!Q=v9f}AqF}hOnMwdfX0mpsjl7r}mR75?JCC7O5h4-bE0}!%B}nvExo?d;;Kx6h|I%t)uTGfKB88vc9KtI>csayMz&V2gg$QT|WTJ%tW$hT20fP9WM^!-vC9loH%b~&lk%%5Hf~&>)BQKcNkJh4?velCvl??kQ?~VqiCvW;Ex@F9ZYOEt-Y0hB6n4C$fAWq#OFi4P<LsF2)BoR<)>S#{YFpEJQQ^=Yy{v1LY5wSd|7wEvSM@tR#qz`prMN%x1M9tSRQ+BSjUZLU%nu0L$nn|;W^;;x{%>wwQV>1J?bTk?0<qJ_4QjzZNFzn7V4z|M*=q49su_jf^hjqFVkVZ(3`k+?q<Q)?{oS|HgYt7HRXPldi$*wz^$-(Ys(*NgK|K&v=3fTTJ{5U$zyQYoA?J}PYe|f+4M>F-!nyJTWjm*UT(Hf(<-0{-Ps(b79`MY&fxx?BK^-}CI(<P({?~4yLpm9BwUZ0+Rv+(|ye*4Fq<O^K;p|tXyyZmEML%w&Xzl4vmBq)9@HFc2|yHMq_jYM~3CZ9e-KmLfGe*0m<vn_3RW;nz|C?3Mzq2H#i=aF{1$voflL*MPNpdL_Y!`=NRX|=mSyWQ!AcBD|hZ=_%(u=@Ege>yJ24Df;>55O;0H;K}{fZ8-*{#2^}Hz=oczA*XP2FRbZrgsO2W)8kAYcmP0ix%~6m8m;ytp?q&fr@(Qj)=H4Q`cWpwKM`yc@MQK{{ur>)>r'),
    ('e1e009f489e2bd126d0546f75977dc73c6450dda', 'c-rk->vI}8693L$q4m1TyV(+841;0IRq@$e>}-M^8|Uuo?uwd+24oL2V@U(1Hv7L{x8@CFY_i#_d+;S@q*hO>)sJ7dCf}3uK+H^E5hWt2m_tI-elRDDOqkDvsd(W3OiWwxx&BQAdyKeX5`N4%TfhQkiV0IB3_NZx>own;u|Bz-ngW@L;GWrvoL$xezh5I{5r_xZ3l?MB^gJ9Og!^HnWc-^DhlR{{m~St~$>MB^5VZ_}w^V}rlWfpot{Hi%PYw<WW6~BpM2Y)k@C5P`6$D-?k0g?L@E0VsmPAciwtK<CKynp`B@scSm`GT%r%=;_+`hvdQ?ae3%2*^C9*3UkZ^;EjDk>}GG-raloH;qSx#>l~ZvWR`$$enSda`i}CkOmwJz-Q|<v@P>ZH0HmhPP#&u~_F`*1@)narHV+82lZ=;_8@Z7|ChO#}cM*Pg$aON?<=C;0_I^fzMXP=7NUY4${#u^cdxVOrCAtc=IOtt(a8lQ)sHGq<rEBf~9Xcc=M+5rap5Hihkp83AFaKPyER9Y9SLdE+yEx7S0ZQ#e6UjFl5uI!J{1sf!>6(6ENuzY)tzmO%-8tiprUAHI1w~o5T8g2)xJW>L6m>k7gDV<ja?oMld(l5FD({Jj#7!HUW*oi@}pvEwNiIlZcWNmQw~kPb^bTYj_lT5}hob20BU6Un48>RYY6udb6!(6rVAmqciRUHN2y<$r*Bk)rSsl9m46tv2JabFRiaOziA-VcosM>zdxf~XM)ix4}dQ*Dp9X9lT5wH0%+2OnkqHIIGmqNnf-tYUrQ5l*iT*<Njx3Q7GRGJ8yCTvw@1#A-EOgtY1$pjJZ^T5TOG&j8tucTeRzD>>K<8UuW217Tozzux&MN(#ln{iG>_Bu#MZ{KljggRovNQooR2agxdgihCjeI5^gw18{$&{nxR{WPrW@#!FEpDYq#jFB7(xBZMlMslQm#>;$5Y6gnBUmitX%pw)g*#NvSQu}X2n6EgqKEs=E-`b9xm62;KY>+c^)ZU?y>s44E%LgacZAo0HJ7`b@ik+Qx%ROrL8a-$gfQ2;N0QxjB&1T2!Egr#fFf*JsWo!L{bWn1E*WBwUBg&H_Q%Z;6$vj!&UcyR}xeuL8nVzz@2{ak@@pn(!pP^2WO+f`S|Q~cz$_)IvT{rAA_X&It(e=d$#!c!|AYkU3KUp<a}^F7@iM?XMY=C-(0;1Hn$}P6|gK{juD=OOE^*gDAhpY8J}om!B;<mwQ5}uO7kt{zbMu2PWJZSU5+m9{xlwZ9t=n0>(kN2UM4%GkkN9I+l$jZ7>fg3K74gIy1pCXOsb5+8~66t6<;DPoEIrlqo&J*sdo1ED|CuNm%KGTd7m){b2cW!7!yOx(}Q(AwjpzzoR9+-vh~3WIkaG9SDyzrqrv#o#}DJt;C3{=xf>1#H+|BGq-c2DYCI~VVR66lIP*|QVCpA8cr6njHD8}Hv>(L48!L%j=GbM9|I^HI3t%e>$+ZrdmC^$oi$WU5)VIuLUE69Jwh0E?ab36DKI|Pk$40w%45MwMdu$tr<}*9cJm?%H!^m)OR6lGTREaZ$cmn6UK^`9{-nQDkUboq8^*|)%9(9g;M!U^g@W*I(SjRyv_w1wNN@<WoL6%mvB=60+xj~G3n0{*+%yq41hqXIxtJP^XI|k^acW4+*!*XoHb#2S-8P!UGDhdj1D~cNgip?S@yR%v3Ul8)JTNd&&*2+r~heZhIOdB>BGn2)H_$3btuq(=<fP_4R6Xaet0{~)%5P{C)vZ!MG{;_J*o|zA<YQpFKy;->eop8k}jv#X-`z)PM#W3oGltxo^T>2?EP~I|$@5FT7xWA%<K9;2d&QKN*5Ke4FKskunlnKi~W-BD3lW3NY5Q$WRkOIzl9*jH#LQ42y4L1}Kj1~h@x3_#AyR4{PD(ImRNaGr1hJjF~<uP*h(@&YgE3Fg3MO+E$P@QTNQG^B-8dG2yf3U4N%g70!<)P?A`*BHor8%AmPa&kx<N;Cwnk!h6By>ssQOF+vL@1!02wEwR3hkIYDu>ygi4Dp*>p&o$Q+>=ZVNh@-hC`)?WFGL%#GC2a(i_(Jm0t=fv>#d(V^pgeI9E=3<`UE^tELv*cY;N0MGAu!<jD50GFI5?f?4*|gh1qJV%XiI>g0o+^^F!K0r@OR-N190@E{~2qV$l&c!_3(Wq}@^)<>vbB`YSdu?0azcWXCsMV(cRW%{q2O!fZ)W57Q%L^`aROMFxtn8Z2)zfjP;t>)nX76{hn$}#z2g1d3~1pFd|gan9Bh(JgkNI><Hd{UiHS`+Z&FU&fNPZ^(vOra{_r;$<^B?=><s0<=mJKPkCyBIid9>A>42qa05tL5h4kzNaoQwHOl!D=`uh5J9>efTiGxVjw`J5<larE-{mO+ex<`A(xxLZ9OL2J0GYA<Xb+M3+S<3$&VYZ$Fc1k9>Ec8=7mxEAfm5<kZ$0==X0JKno^M+N%)|P$REx#o!fT(uyny`naK5#apVkUNV7eNQ}@ACR_&S0ZGPAOATzFV-^G}tUA4S7vs^@FN0y}@+C=Hs}n1S_C2}NH7e0HDimvo$gpq*#3yp|lc0IX{F5m;4Z~A03q+k<W7As|I0dfjacJA??MldoR`3KXbvA`cQ%$)<$OiyGXUKP4T||~HRA9fKKh_JZMp&wV8FElNNK8zrtB?fjY1uH_&LZsTm@=M?b*GD35m>BV*8kpqTw#v~!_SvDSHq8h8urLZQkEuSl=GxqN?XCXF9-xj@ZUPzBbd1PajK_r<U@#<LrFG)whqeW%adlt1^NKk<p;~rB2zjuLn?wmrO!T7ajSj}5zYvp9KfRy_Z*Fp;_8sXU`AXusqHJ~f=s{{3-$}zN7cjCNSK1i7={rla;VjKshrGOZ*Vfa0(U+KIKMH%d`;+iNk!YE(_;SFzFk&{P|GYgqg5cdk9@9@oh9uCeTmj6_Yt0EUg@;%LN73#*cou6LKTvU=`GBq{NcySdN0x|X_{2tT3x$i7-qNIVuoc{uGKkaPSdfW{_7mI%yzfubi2nrx4QP!!W2bK<zFfHzZA6c>dhtvS7yo;3jvF9n^D$cDQeN0W?#Vr48u(XD0O7Gi>U%THHg_F9}2C7Df~iD4DScg`y9}EpLA<+kBDXsUe3NvQ*w>#!M3-2hn-j5c^7a4F#oEX?H5>VaZgyae8VmE3oG-x=-sW{uD81Dt!~j<{SRnn4xX5ew}TpnYM5A!SW>4A7Jl}<5q8MHh_<;R+!UH$dtLYkb=ubN{196ImtXnm;JlXQYFUI&Hvg5$6oDlap9g>c=PqyV^5!mY?(*g?Z|?Hu|4iO2=g7iWF-e`<uT}O3;xw9AOP)+=`J<Zj``U`!tZ7%@{q4RztxB$XZ25ch>oZ)oNU_gwcwLr#X7Mi3?h@@T(Qf<MsMZ8ru`u{wCY!q0`dUA67`>xHl8YU(D$ku=49<QT-wbZ=KBOOUs^I<Y)$j)$J%9XWxhNLl-<gi|1}It~%$D}KSNj(w8>C4'),
    ('2f4aec7f6463801a6deeb443b59977273197ea60', 'c-rk+ZByGw68_Gwm}R;6lGND7*fMsCtFYh=+y!vJ<nHSB$~BTk_JAx2&B)-}?0>)R8OfGxVM9n#_u=+Ku;!(wU!Upj*`LXA7*ANBh>8=bxJx4D+_DiTBOdUWDG>(m2y>K}>fa>hcZrC(gdbDE?_q;t@rWxDg}!iR)vbU{c$f59%z@}#!hGQgNAKMVgYFg~Q6k6qmk>K<fivdPd{HuCB1nI-z>P!U(vqQRoDD>g&lf8qrpA(rQ4q#FqgZ+KruL>faVuL9k0(M(U_&40gn<GEWf$aN?iPGHNenDIGn^g8VG?zLA__qZLeQPxe<vfM#)(~xxi>^{$sd2@hvk^T2p$6Bai5BSMsYX-rNMC?^CjQ932n`WAw8q!B*V2);3qRf_yZ_E<wQ@%Ngyd`k|cH#sDw6})p}FU@L*~v5OVRkcRA<{Kb?IX4tiIE;pO%DdGE4IYKe?%zOZX|%BtBSsNGF`#U<E20Bh^bN=$f|C^`{A0#jYGSJ&g<9MRlThR35ZcWwzRCTh$JoPvHQ6QNRW5{Y!si9q``2Y11y_j~T1(`@h-V@}Iv`}Nj-qvf);)!eN+yZgJ1_MXi;b$d6Zau3?g<O4NuuS?35ZvI1O=%N8!;WEYN;~rPen7TZ|>H1<hkEM``Ix%;FeE~+wO!bJsX|%wxumxo2PNL((guxFKoKJyaaK$K;LWS|H>T-`Iz8ae7T2)HQ`cq}swg;<9PBQ^0gbM^-=<*E<yX4D!ijb<|I5(og(3drIKniFAr#pOQR?Y&4>LoEx<m&uFa&xR)rC^7X{2<VRZHbP`8}2AgT~?#n%A&|;$^(4Fm7ef<^+txlDk%er6T}lb4yCH92ep1x&Rp5r%*W2aU1KnU_z%y8l`p0|i!Jbg%rnCHRs<vJ0$~TKt-5>;6bR`bUiQuh!(T2B&yP+DUX+8fbTufbi?b$V2&F+t6&pzs#$qG_vi%nJ$l4g-Q`UBhl=TeA8iMFGvwmsGc0uOT03wnH=zji;NbZ9)1T~4EKfjR*<`phLH@Fzjvm4FSI1KhO7q30yA+?m^(0qdB30OJ+8Ryzt=n+PBh>`7`52u5Z>tBYw&nQR#aF9x&C7}pF^Ced&hubg){6$G_=f(A)e?2J5eg$`D5|O@UJrfQ>T;pw3i&!;ufYFq1RLv0Mj~pD3ikJ9)r4(@_S4l*TR^D@mw;j7~ISc@z<#}Gax!c)y_pN4UA4Z#2d*88kSvl$$8gz<SftOEZue#f)lnHVUY(bo?;U|C<?;Fidr(JJ1I=~Y5_FDTLtJ&lY_+vF&yyYS?cAUNaQf`n!j+aI`Cx2yA_FWWu1BBn(7WX{6-r~(x({8lt^_B(N?Ce@r-LhTB@;t}(I##(lT>#uz*!s!<MCOwu77JiO`Z@7-+ePs{13o}zVD4-Z#au%RcsQ3Y7FUPS0<=M1LU|IBNJQW@!k^FJ1&_f=r^IG*TsD4lS2pTQ*ex%eK%881xIGA>R1pQ^mkguQNMUp>x-id!KRVylpsLXZv%(l`od+45c(GawDBSx;zjrj~9S{2-56=w>ucNA=sR+wY#W~H85g3$$IQPvVjz2_Nk5sd{y;Bel7ntKAWA$en5HUR@V^?32u_AUNe79DXi);B78y2^7X8B8V=Msi~2E_u1s_nc;*Ya1$H!|<9*B?I)PcE(odDH5&AR~xdHMM+lc64#p|JZ}1{jzt|JMBNdI}>FHcRm-9TJnuW@H$L#(Da<2+RpMB+e8%7nK<D!{O61QrBk~v`d{<=HF@_gxBSg(03Q)3k5v97e+w$4a)uRFFoF~T2tzPoUWtB{kFmMAD&#M(8t=dskYnuTDRar3r2v+S`96Vi#v}yb7R>fJIePnc9<v*O@DT%`B~jRC<DX325GqhbvG%1QIdrtEb-R}wke$neCR{;<(&Gs`L@KCGw$cv>0|ZIHFG=W({FXBS6mOV?Cr}07DMU|lr(Ev%4D0qOZ$X_ir5YPx!lHoF9ES=Y={(egBY&c23n#45D;^3GIJb?GF{;f1luIXlHUm@0vZ;F!xZ!<ci3^M7_?XMEG?o+fp4-lt!Tsp##US0CYAps^tAge^0sd@Bz0h}g?1Kwq%=@^++O%egWNtltt&Zp#%9kY*nAyWs=ENA_Yp9~m%EspUFP+Tvzkx6mMiVT7csUhgsx?H6jv$5<fI>M97b=}_Wv-YB+>THhPmCZgG~iGk$6+k>?E|Wp<dbTB(wcxDf9Lj*u`+(0bA_sepH{ZQDy*>56{Ub<unLj{7AxT)$lyE_xeh0AfA~Vp)&ot}EgNP8h6@7A(DU+3<jLSAJo1w+O9_22Jt6D`+4nJv-eJ+1zZ77tUYWZ{w#iQi`m$JA{57};O&PKEECNq}NjtIOf<S?`N=_*kz2E|U$UflKB0`230dAT&q+JR!g){`D05AO3DfiFhS~vEHZtOv^kCg(Xq*#f>3;&a#dN^q`CWldU7*E2uO8VI2R5?na=lLSwMqUY5ryV}PPMwQE@}tH=VkrV?qrOf*2z8R!x`hD(e?F_`NDZ)w0TK$(J8(>x)ZK}+2+_RZ)jWZO6s~(|W{vW6TPzN3UM(76d&jgThrRR9r<WJ!XOMGllY_J+k+M;|KIKe03JiZw039KKtIz{xDEu(f(=Z7DBc{--8F6=rd<F7g(ddKbDR%6@bu`Nq+Q$)%!%$`40oTnvzFLS(2;|7qG#%BMr*7;}7@RLIo74_ws2~vt#+(C#_EGf|Mzh+*B=3aAi}Zd&n`xfzf?bM<Zn6Kq7OGa#%C-3P;bb_t_*)Okmr7+ZXma}H3GLvUG*c{P3N1nG)vc>tAl38}Xb5E8x?C}lHnSm?>hNVwPlq~n9J)yYk(C%}lTkwRRA%)?u|@bWL7Qa?T2q+J3yhMQ1dJp~D$-4*==1S~yn6LyL+kwh#g_gSwe9m9<*RGnoRd6W`+il;o1^?}@A^)4@DV(6q44I>i!#^6$0+c)0vWQ@ga0N#@tl_Pd^OamXQzX8?>m>h{>9bl;NtS1OEfcgC|^80JzoEKBHY5p>+|8^V9-137nuP^9WsU4v07ffbO5f*)BFk-UwQzk6>Rn-|IWbZ`N*ZwZmv?eu;-fGE=*CexTy21KpnU+Jt=*W+Fp7JKmqh~;bO)(fIb7>X+VKGS4gShP^$g>p$l8(TJLKlE$VS4X09VYWG)etNn)A}-z8Rx?d3$DNwZ?%z1?<Nmc`ob2Dfa>_UzU^ck8YL?dH~AgEiY7x82_Fc;!uUEykud?9zAB=WEUA0P}HtC&R)x37~nZ3$@(SCBhFf;IbKr-7HghQO!D0Gys^t37LNn6#o2ramBr?um7VIpGvZ70J<4njA`-@swEdoZgvg@we{<sm&R<|^VnVVh=<&>IC#`S+GVfrSiH=;_Xv?BOQsws4|Nq{^D&!>x#vAEcS4dhPjY<||LE}i`1JU2(A%8tEMPik)*ts8u=?tWh1`#N^vvf?i*s_x(_E1&DOL{USDqJOnv)fimH5pgIrr7x{C)YQZiM|7XpB_;_3!_C%>TN_q>^R-%gBELw+VZm'),
    ('cff76b696a4afd8658329a02ab33032672f292b9', 'c-rk6+j84B_FZ3rs-7n46uMcYE{%7RrfTA@V>_~)?oQUL0ZC9oOp!DJ%GM^?Z{KqOQX+M+6>lcZL;VsFI5;@>8}dClQ*6vVBBL~MIf=qx{xk7-97J>dL71<2LfmK?2V8NYl2j^yzloA7KZtJVn1?)JN<<-H-c(2lziO3`O?jW3%|n;WSRgzNP)X8|ZrmYzA3hKf#;KAuH%by7nB`BODwQbgSIFYNktbx#lsmyilASTX2`L=ylMe~MPDR4KJ`&A;B5EGP%~B;I9DmAAOe2qP1$8HpaN#S85u@yrcL`4=Ech%49OhnK=4j$1@<qURyfjXOV1$5NsvVE;+nBo`_mRUSAIS;(+;bDoyoa2d@?^Z*g_W2mnf|pxn43v0fvYR1oKW#lEf-J>G!sL<S^+3G1ucf|9FdHZD2?F`Fc-Qs7g{ivqA<~3;35{fJfI?^pq6pMr8ERrD(@plla^uP#%_#7zRlKvb)a0|I7y;V{KuFs0)qKUil&u1X{b`#YS$WVy`#jGN2#Jy5vGd6eJx9`^Kh2i=E>W^@O&_O^ZICXJ~%rc4KI$52g5$8r!uJr!l_>?yY7gvemxBU1rQv9W9h@-aPh*%X-4mh33smuT)J?{jH@WgAPE6u1zIvi)LlFQ2cGSF`)<3%Eyi5SVcmw+ZCM`c*zIP+ZFZZj&c4HX4W~)IC$mniQEM&`-Uv16FTOw`-0zbq6JcQuymQjei7Kx1L<*^>3l;=+AXosjfhS46!r72(N=YDQoSY7c(BNvmz*Uec{{8a&Y%n@|^}Jt<B5Mv~Y$N}B`D%22^7p~9IWq>fQm3Y(D;}2NUJaiAx*d1!ROK_T2g8?l5VY{9@~P8{qodJq@a6)HqjYfHz%$vWV2K|K7$jGO@-!l`h`G;1P}qC-j#T$@K~>4Yf62e!HE54f|MEk-@oA4-UamsttnUWBV0t(3BDdLzChc9~vCAJ<4uJipEI8PEJf0913sOyZ9Lf6L%fs_m7ry|O)04Bq^ONB}>nJMNC?S8cdiCS?*MugdhK5l?H9UR#6qd~`)h9sBK}lBY#OD}L{o64t<+mM!u?0x3Q=vv%F%@LHK(!$ZOgItKX{wkLa14T;iD&u_?YRh5@V>7cCO*R#ObA)9P}uP~q<#wZ2?Dep5?u~MIL$)@g6c-{04RYX$JYd{hJ8rvTxUHgASN%a6OaPU$!#%d*ZA`K<kvw-G+2<V1cu?sZ-+-^sI1;713n}Ue(Uk=Z?vf6IoNQxpXZjkiXw1#OqP_-FiW_+o~L$-nykh1!f{HC&Zw?yDFqt`0>HnrKyq?%etL0UEuC1p(ef9iIsggCwDaZZWf-agM6tG64R@srw7$W`!4CAfOtEmps2vwkbrc0!3`>-vcCzJVtO1ND|7?93IZBtlPeY-IlZwDI;)5b74V0|wI?G6jd$rqXpqX{Kh_{0;%d*;g8HFqEb_Pi)jSJE{)k<8tlHWJ=P0d_eGg^_gfQ6iVcR(Hme9YWAb)poU)_X)geq8kegz_Rcoq|tmLLO}iZIB_;m>M&B25fa)r(wGclBMPQey82+b-k|L?sZ|cZFjn^-DEnv*|q&zV{3Rb2<Z$%5SEA4{aUkCy-yIwpm~tkpDBqDNO;z2_j;X1r_}>taDU(G_Uv|>x8NVUZE?%P;NNriyG9Py9dbZ)1u3-dm%;CB#_kt@j}c-LfhR#ae1xU^-E6%Ftj`>q`@Yk#c-v|_EvwP6Y|w76Y1<9k@m$;YUB~a)TD?}Sa|c_{aYBpZq^7M@e3~Yuf)}qVu-)ub*HVsD&@mSH*34|lEf0~xdM%iG5fn=b+H)uhBl6tUty{l8<iHD;2W?QqN^afZjL0~lU^+DWzyJXS45U;^=$!nkfRPYrW-!F10jJjrV+Xlb9(MzVBZC>YAeGOkj^nUln@9&srH^bsz8X{L4t+6(&cGQ5Qw_Ls-5T;T1;CJd)!MLzm{kJTY}^dk9JC-eZQY2_i*8zLbl9{&$%3VowF2ii+;JxiTE0L71BchjS}t0fm@QHRG&+*{QQ+|;0E5N65+I0uAIuuk!U_0VU(q=$kQ+8|NCST0CYUeo#EY`qw6@U0#?4$0_oAlYr7;YG_+~stX?LPAvVwS`V7Rdviw8w!w6=#vUd#<ktHtatLa0@eBuc<nD8B_INb*KmZ?rt%#~<8zVKk0k$6TRE;isKL*d+)%gV+*q@=Q)xqJ)oQ4cv$M8BF>hoCU?EdTZRtrap3%BN;7`tVg1iI`}s%d|sX8CEq=P?V;VR@X2>XM;Cf)1}Zp6ac&Y8|BQW6SW+}VD^r#&sH<Y;L`F7%KP;F+t0F3&iDZZ9>ZA^IcgR>}%T1fbuwo#mP{FbU`b8O`mq6b$flsiL(8F1#mx8I7LTx!!`add_`@5uSu|Ul#>h-NPqsa7VW@)3r@!P}U$?@yKG0qgSu8X2&l?G8-6LKzH1){zo5V63SYAgncOrr!^5lr`B=4lB2I)kzb=Hnx%Gm=mqGzxfN8i-N@b>Svf-Ylj`6si0><jM>l*IO7mB{L94R#YR26nT*p77O5;wzX0X9z+A~P%s>*Rj~c1u$q@7)J)T0+_31I5LG?%Yb+I|7E(>!sueqV%M;;))fqjmb;tQoAvYOae(h)`2fLfe;2)=h7v}@$a0W;4<M8D8j%Z>&v&VzaZ^-}Zw!c`n{dIb0{Ur0%I_F&ObZKVQy><Ki)7tIKVa*%HQtUFt9z%!s#Y-M&9G@-L$Ln7#ynju<{cDi+8LoX_TKUFZ{%eoRzICU+fY*BF6`#{}U4&v!RJm+p!3~?s$4|%)Kaj^?e%kb8%UmYa6w<tdc;<9m%eGmk)8e*cJHBIex!3SqnA2GME!OVzyiTXv^Uchuao5aAOJMbVIAfg_Vg`7@NO<5EtBXuwv#2(`KzuA!@Eep<+FzJ_eFNl=sOjCoq1%W5dVpr)8y79=-6#{A1XKfd^q`_XxnW6IdUV0(c9ez(D({m{<$rR@cgz'),
)

def historical_workflow_bytes():
    result = {}
    for oid, encoded in _HISTORICAL_WORKFLOW_BYTES:
        raw = zlib.decompress(base64.b85decode(encoded))
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != oid:
            raise ValueError("historical workflow fixture whole hash differs")
        result[oid] = raw
    return result


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("host_receipt_package_policy", ROOT / "tools/repository-checks/package_checks.py")
PACKAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGES)


def blob(data):
    return {"mode": "100644", "type": "blob",
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


class TemporaryGit:
    def temporary(self):
        directory = tempfile.TemporaryDirectory(prefix="overte-host-receipt-")
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def git(self, root, *args):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                                       cwd=root, text=True, stderr=subprocess.PIPE).strip()

    def initialize(self, root):
        self.git(root, "init", "-q", "--initial-branch=main")
        self.git(root, "config", "user.name", "Host receipt fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "maintenance.auto", "false")
        self.git(root, "config", "gc.auto", "0")
        self.git(root, "config", "core.fileMode", "true")

    def write(self, root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class WorkflowGenerationTests(TemporaryGit, unittest.TestCase):
    def setUp(self):
        self.generations = PACKAGES.workflow_generations()
        paths = list((ROOT / "tools/repository-checks/workflows").rglob("*.yml"))
        self.contents = {blob(path.read_bytes())["sha"]: path.read_bytes() for path in paths}
        self.contents.update(historical_workflow_bytes())
        # Immutable historical fixtures must survive later template edits and
        # remain available in shallow source snapshots without Git history.
        for oid in ('93f35c99ec6580b8796420997b1dcc586b7bfd95',
                    '861db7b76a11b9b8772e91cb24ec7cb9d918e339',
                    '6684e18785719813c51f9e3f5481a82ca40f0baf',
                    '84d98cac819755f98eecffba847e0bbcf667a6ca',
                    'c1d3d14a9098de214b6544dca8dcba0072090c6b',
                    'c01ff8a69f1ccbc60196da17e782c9a09defe4e5',
                    '1f8a7c3b4fe400a7c62ec2682de3f77d08dfd70d',
                    'b9022d17b985f93838b92cb42c7e2d873e7cb11f'):
            self.assertIn(oid, self.contents)
            self.assertEqual(blob(self.contents[oid])['sha'], oid)

    def materialize(self, generation):
        root = self.temporary()
        for path, entry in generation["workflows"].items():
            self.write(root, path, self.contents[entry["sha"]])
        return root

    def test_old_and_receipt_generations_each_accept_only_a_complete_tuple(self):
        self.assertTrue({"packages-v1", "packages-v1-direct", "shared-receipt-v1", "shared-receipt-v1-direct"}
                        .issubset({generation["name"] for generation in self.generations}))
        for generation in self.generations:
            with self.subTest(generation=generation["name"]):
                self.assertEqual(PACKAGES.validate_wiring(self.materialize(generation)), generation["name"])
                # Independently enumerated API entries include their own path.
                tree = {path: {"path": path, **entry} for path, entry in generation["workflows"].items()}
                self.assertEqual(PACKAGES.validate_tree_wiring(tree), generation["name"])

    def test_missing_unknown_nonregular_or_modified_workflow_cannot_pass(self):
        original = self.generations[0]["workflows"]
        for path in PACKAGES.WORKFLOW_PATHS:
            for mutation in (None, {"sha": "a" * 40}, {"mode": "100755"}, {"mode": "120000"},
                             {"type": "commit", "mode": "160000"}, {"sha": 1}):
                tree = deepcopy(original)
                if mutation is None:
                    del tree[path]
                else:
                    tree[path].update(mutation)
                with self.subTest(path=path, mutation=mutation), self.assertRaises(ValueError):
                    PACKAGES.validate_tree_wiring(tree)
        for change in ("missing", "modified", "executable", "symlink", "oversized"):
            root = self.materialize(self.generations[0])
            path = root / PACKAGES.WORKFLOW_PATHS[0]
            if change == "missing": path.unlink()
            elif change == "modified": path.write_bytes(path.read_bytes() + b"\n# unapproved\n")
            elif change == "executable": path.chmod(0o755)
            elif change == "symlink": path.unlink(); path.symlink_to(ROOT / PACKAGES.PRODUCER_TEMPLATE)
            else: path.write_bytes(b"x" * 1_000_001)
            with self.subTest(change=change), self.assertRaises(ValueError):
                PACKAGES.validate_wiring(root)

    def test_individually_known_workflows_cannot_be_mixed_between_generations(self):
        policy = self.temporary()
        first = deepcopy(self.generations[0])
        second = deepcopy(first)
        first["name"], second["name"] = "first", "second"
        for path in PACKAGES.WORKFLOW_PATHS[:2]:
            second["workflows"][path]["sha"] = "a" * 40
        manifest = {"schema": 1, "repository": {"full_name": PACKAGES.REPOSITORY, "id": PACKAGES.REPOSITORY_ID},
                    "generations": [first, second]}
        self.write(policy, PACKAGES.GENERATION_MANIFEST, json.dumps(manifest).encode())
        mixed = deepcopy(first["workflows"])
        mixed[PACKAGES.WORKFLOW_PATHS[0]] = second["workflows"][PACKAGES.WORKFLOW_PATHS[0]]
        with patch.object(PACKAGES, "ROOT", policy):
            self.assertEqual(PACKAGES.validate_tree_wiring(first["workflows"]), "first")
            self.assertEqual(PACKAGES.validate_tree_wiring(second["workflows"]), "second")
            with self.assertRaises(ValueError): PACKAGES.validate_tree_wiring(mixed)

    def test_protected_producer_requires_the_complete_new_pair_and_all_five_siblings(self):
        previous = next(g for g in self.generations if g['name'] == 'android-owned-npm5-sync-ci-v1')
        prospective = next(g for g in self.generations if g['name'] == 'protected-shared-producer-v1')
        self.assertEqual(set(prospective['workflows']), set(PACKAGES.CONSUMER_WORKFLOW_PATHS))
        self.assertEqual(len(self.generations), 23)
        self.assertEqual(len([row for row in self.generations
                              if row['name'] != 'npm-consumers-sync-ci-budget-v1']), 22)
        for path in prospective['workflows']:
            if path not in {'.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'}:
                self.assertEqual(prospective['workflows'][path], previous['workflows'][path])
        for path in ('.github/workflows/repository-checks.yml', '.github/workflows/project-tests.yml'):
            mixed = deepcopy(prospective['workflows'])
            mixed[path] = deepcopy(previous['workflows'][path])
            with self.subTest(mixed=path), self.assertRaises(ValueError):
                PACKAGES.validate_tree_wiring(mixed)
        for path in prospective['workflows']:
            for mutation in (None, {'mode': '100755'}, {'mode': '120000'}, {'type': 'commit', 'mode': '160000'}, {'sha': 'a' * 40}):
                mixed = deepcopy(prospective['workflows'])
                if mutation is None: del mixed[path]
                else: mixed[path].update(mutation)
                with self.subTest(path=path, mutation=mutation), self.assertRaises(ValueError):
                    PACKAGES.validate_tree_wiring(mixed)

    def test_candidate_generation_manifest_never_authorizes_its_own_workflows(self):
        root = self.materialize(self.generations[0])
        path = PACKAGES.WORKFLOW_PATHS[0]
        self.write(root, path, b"candidate-controlled owner\n")
        forged = deepcopy(self.generations[0])
        forged["workflows"][path] = blob((root / path).read_bytes())
        self.write(root, PACKAGES.GENERATION_MANIFEST, json.dumps({"schema": 1,
            "repository": {"full_name": PACKAGES.REPOSITORY, "id": PACKAGES.REPOSITORY_ID},
            "generations": [forged]}).encode())
        with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)

    def test_metadata_generation_requires_the_complete_six_ordinary_immutable_entries(self):
        for name in ('protected-producer-metadata-ci-v1', 'protected-producer-seven-target-ci-v1',
                     'protected-producer-original-default-v1'):
            generation = next(row for row in self.generations if row['name'] == name)
            original = generation['workflows']
            self.assertEqual(set(original), set(PACKAGES.METADATA_WORKFLOW_PATHS))
            self.assertEqual(PACKAGES.validate_tree_wiring(original), name)
            for path in original:
                known_other = next(value for row in self.generations for value in row['workflows'].values()
                                   if value != original[path])
                for change in ('missing', 'neighbor', 'mixed-known', 'executable', 'symlink', 'gitlink', 'unknown'):
                    tree = deepcopy(original)
                    if change == 'missing': del tree[path]
                    elif change == 'neighbor': tree[path + '.neighbor.yml'] = tree.pop(path)
                    elif change == 'mixed-known': tree[path] = deepcopy(known_other)
                    elif change == 'executable': tree[path]['mode'] = '100755'
                    elif change == 'symlink': tree[path]['mode'] = '120000'
                    elif change == 'gitlink': tree[path].update(mode='160000', type='commit')
                    else: tree[path]['sha'] = 'a' * 40
                    with self.subTest(generation=name, path=path, change=change), self.assertRaises(ValueError):
                        PACKAGES.validate_tree_wiring(tree)

    def test_original_default_generation_binds_all_canonical_sources_and_retains_metadata_baseline(self):
        generation = next(row for row in self.generations if row['name'] == 'protected-producer-original-default-v1')
        canonical = {
            '.github/workflows/project-tests.yml': 'producers/protected-project-tests-android-platform.yml',
            '.github/workflows/parent-qualification.yml': 'producers/parent-qualification-android-platform.yml',
            '.github/workflows/repository-checks.yml': 'producers/repository-checks.yml',
            '.github/workflows/sync-validation.yml': 'sync-ci-selection.yml',
            '.github/workflows/browser-client.yml': 'npm-consumers/browser-client.yml',
            '.github/workflows/pr-metadata-context.yml': 'metadata-edits/pr-metadata-context.yml',
        }
        expected = {}
        for target, relative in canonical.items():
            path = ROOT / 'tools/repository-checks/workflows' / relative
            self.assertFalse(path.is_symlink())
            self.assertIn(path.stat().st_mode & 0o777, (0o444, 0o644))
            expected[target] = blob(path.read_bytes())
        self.assertEqual(generation['workflows'], expected)
        self.assertEqual(PACKAGES.validate_tree_wiring(expected), generation['name'])
        previous = next(row for row in self.generations if row['name'] == 'protected-producer-metadata-ci-v1')
        for target, filename, oid in (
                ('.github/workflows/project-tests.yml', 'protected-project-tests', 'c01ff8a69f1ccbc60196da17e782c9a09defe4e5'),
                ('.github/workflows/parent-qualification.yml', 'parent-qualification', '1f8a7c3b4fe400a7c62ec2682de3f77d08dfd70d'),
                ('.github/workflows/repository-checks.yml', 'repository-checks', 'b9022d17b985f93838b92cb42c7e2d873e7cb11f')):
            frozen = ROOT / ('tools/repository-checks/workflows/producers/legacy/' + filename + '-metadata-v1.yml')
            self.assertEqual(blob(frozen.read_bytes())['sha'], oid)
            self.assertEqual(previous['workflows'][target], blob(frozen.read_bytes()))
            self.assertNotEqual(expected[target], previous['workflows'][target])
        for target in set(expected) - {'.github/workflows/project-tests.yml', '.github/workflows/parent-qualification.yml',
                                       '.github/workflows/repository-checks.yml', '.github/workflows/sync-validation.yml',
                                       '.github/workflows/pr-metadata-context.yml'}:
            self.assertEqual(expected[target], previous['workflows'][target])

    def test_metadata_candidate_and_immutable_base_cannot_omit_or_alias_the_sixth_workflow(self):
        generation = next(row for row in self.generations if row['name'] == 'protected-producer-metadata-ci-v1')
        helper = '.github/workflows/pr-metadata-context.yml'
        for change in ('valid', 'missing', 'mixed-known', 'executable', 'symlink'):
            root = self.materialize(generation)
            path = root / helper
            if change == 'missing': path.unlink()
            elif change == 'mixed-known': path.write_bytes(self.contents[self.generations[0]['workflows'][PACKAGES.WORKFLOW_PATHS[0]]['sha']])
            elif change == 'executable': path.chmod(0o755)
            elif change == 'symlink': path.unlink(); path.symlink_to(ROOT / PACKAGES.PRODUCER_TEMPLATE)
            with self.subTest(change=change):
                if change == 'valid':
                    self.assertEqual(PACKAGES.validate_wiring(root), generation['name'])
                    self.assertTrue(PACKAGES.consumer_generation(root))
                else:
                    with self.assertRaises(ValueError): PACKAGES.validate_wiring(root)
                    with self.assertRaises(ValueError): PACKAGES.consumer_generation(root)
        root = self.materialize(generation)
        self.initialize(root)
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'Complete six-workflow immutable fixture')
        self.assertTrue(PACKAGES.consumer_base(root, self.git(root, 'rev-parse', 'HEAD')))
        self.git(root, 'rm', helper)
        self.git(root, 'commit', '-qm', 'Missing sixth workflow immutable negative')
        self.assertFalse(PACKAGES.consumer_base(root, self.git(root, 'rev-parse', 'HEAD')))

    def test_unrelated_source_and_sparse_candidate_do_not_change_generation_identity(self):
        root = self.materialize(self.generations[2])
        self.write(root, "unrelated/source.py", b"raise RuntimeError('must never execute')\n")
        self.initialize(root)
        self.git(root, "add", "."); self.git(root, "commit", "-qm", "Approved sparse candidate fixture")
        sparse = self.temporary() / "candidate"
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)], check=True, capture_output=True)
        self.git(sparse, "sparse-checkout", "set", ".github")
        self.git(sparse, "checkout", "-q", "HEAD")
        self.assertFalse((sparse / "unrelated/source.py").exists())
        self.assertEqual(PACKAGES.validate_wiring(sparse), self.generations[2]["name"])


class TrustedGenerationPolicyTests(TemporaryGit, unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / PACKAGES.GENERATION_MANIFEST).read_text())

    def policy(self, document):
        root = self.temporary()
        self.write(root, PACKAGES.GENERATION_MANIFEST, document if isinstance(document, bytes) else json.dumps(document).encode())
        return root

    def test_unknown_foreign_duplicate_partial_and_corrupt_policy_fails_closed(self):
        cases = [b"not-json", b"x" * 64_001, {}, {**self.document, "schema": True},
                 {**self.document, "schema": 2}, {**self.document, "extra": True},
                 {**self.document, "repository": {"full_name": "overte-org/overte", "id": 1}},
                 {**self.document, "generations": []}]
        for change in ("name", "tuple", "path", "mode", "zero", "fields"):
            value = deepcopy(self.document)
            generation = value["generations"][0]
            if change == "name": value["generations"][1]["name"] = generation["name"]
            elif change == "tuple": value["generations"][1]["workflows"] = deepcopy(generation["workflows"])
            elif change == "path": generation["workflows"].pop(PACKAGES.WORKFLOW_PATHS[0])
            elif change == "mode": generation["workflows"][PACKAGES.WORKFLOW_PATHS[0]]["mode"] = "100755"
            elif change == "zero": generation["workflows"][PACKAGES.WORKFLOW_PATHS[0]]["sha"] = "0" * 40
            else: generation["extra"] = True
            cases.append(value)
        cases.append(json.dumps(self.document).replace('"schema": 1', '"schema": 1, "schema": 1').encode())
        for value in cases:
            root = self.policy(value)
            with self.subTest(value=str(value)[:80]), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES.workflow_generations()
        for change in ("missing", "symlink", "directory"):
            root = self.policy(self.document)
            path = root / PACKAGES.GENERATION_MANIFEST
            path.unlink()
            if change == "symlink": path.symlink_to(ROOT / PACKAGES.GENERATION_MANIFEST)
            elif change == "directory": path.mkdir()
            with self.subTest(change=change), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES.workflow_generations()

    def trusted_fixture(self):
        identities = PACKAGES._policy_inputs()
        root = self.temporary()
        for relative in identities:
            self.write(root, relative, (ROOT / relative).read_bytes())
        self.initialize(root)
        self.git(root, "add", "."); self.git(root, "commit", "-qm", "Trusted policy input fixture")
        return root, identities

    def test_complete_trusted_helpers_and_transitive_requirements_are_bound(self):
        root, baseline = self.trusted_fixture()
        required = {PACKAGES.GENERATION_MANIFEST, PACKAGES.PRODUCER_TEMPLATE, ".github/test-suites.json",
                    "tools/test-evidence/run.py", "tests/run-project-tests.py", "tests/platform-profile.json",
                    "tools/sync-test-reuse/qualification.py", "tests/requirements-host.txt",
                    "tests/requirements-repository.txt", "tools/sbom/requirements-validation.txt"}
        self.assertLessEqual(required, set(baseline))
        for relative in required:
            path = root / relative
            previous = path.read_bytes()
            # Preserve valid JSON/pins while changing exact trusted bytes.
            path.write_bytes(previous + b"\n")
            with patch.object(PACKAGES, "ROOT", root):
                self.assertNotEqual(baseline, PACKAGES._policy_inputs(), relative)
            path.write_bytes(previous)

    def test_old_trusted_sparse_layout_has_exactly_the_same_complete_policy_hash(self):
        root, baseline = self.trusted_fixture()
        sparse = self.temporary() / "trusted"
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)], check=True, capture_output=True)
        # The existing outer caller intentionally remains byte-identical.
        self.git(sparse, "sparse-checkout", "set", ".github", "tools/repository-checks", "tools/test-evidence",
                 "tools/native-tests", "tools/ios-build-qualification")
        self.git(sparse, "checkout", "-q", "HEAD")
        self.assertFalse((sparse / "tests/requirements-host.txt").exists())
        self.assertFalse((sparse / "tools/sbom/requirements-validation.txt").exists())
        with patch.object(PACKAGES, "ROOT", sparse):
            self.assertEqual(PACKAGES._policy_inputs(), baseline)
        # Ordinary deletion must not be mistaken for an omitted sparse input.
        (root / "tests/requirements-host.txt").unlink()
        with patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError): PACKAGES._policy_inputs()

    def test_unknown_requirement_graph_fails_closed(self):
        for source in (b"-r ../../outside.txt\n", b"-r absent.txt\n", b"requests>=1\n",
                       b"Thing==1\nthing==2\n", b"x" * 100_001):
            root = self.temporary()
            self.write(root, "tests/requirements-host.txt", source)
            with self.subTest(source=source[:40]), patch.object(PACKAGES, "ROOT", root), self.assertRaises(ValueError):
                PACKAGES._requirement_paths()

    def test_recursive_requirement_additions_and_changes_are_in_the_policy_identity(self):
        root, baseline = self.trusted_fixture()
        host = root / "tests/requirements-host.txt"
        host.write_bytes(host.read_bytes() + b"\n-r ../extra/validation-pins.txt\n")
        path = self.write(root, "extra/validation-pins.txt", b"FixtureDependency==1\n")
        with patch.object(PACKAGES, "ROOT", root):
            added = PACKAGES._policy_inputs()
            self.assertIn("extra/validation-pins.txt", added)
            self.assertNotEqual(added, baseline)
            path.write_bytes(b"FixtureDependency==2\n")
            self.assertNotEqual(added, PACKAGES._policy_inputs())

    def test_symlink_gitlink_and_oversized_trusted_sparse_blobs_cannot_be_hashed(self):
        for change in ("symlink", "gitlink", "oversized"):
            root, _ = self.trusted_fixture()
            relative = "tests/requirements-host.txt"
            path = root / relative
            if change == "symlink":
                path.unlink(); path.symlink_to("requirements-repository.txt")
                self.git(root, "add", relative)
            elif change == "gitlink":
                revision = self.git(root, "rev-parse", "HEAD")
                self.git(root, "rm", "-q", relative)
                self.git(root, "update-index", "--add", "--cacheinfo", "160000," + revision + "," + relative)
            else:
                path.write_bytes(b"x" * 100_001)
                self.git(root, "add", relative)
            self.git(root, "commit", "-qm", "Unproven trusted sparse requirement fixture")
            sparse = self.temporary() / "trusted"
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(root), str(sparse)],
                           check=True, capture_output=True)
            self.git(sparse, "sparse-checkout", "set", ".github", "tools/repository-checks", "tools/test-evidence")
            self.git(sparse, "checkout", "-q", "HEAD")
            self.assertFalse((sparse / relative).exists())
            with self.subTest(change=change), patch.object(PACKAGES, "ROOT", sparse), self.assertRaises(ValueError):
                PACKAGES._policy_inputs()


class ProtectedProducerPermissionTests(unittest.TestCase):
    def test_caller_grants_exact_read_ceiling_only_to_native_owner_roles(self):
        old = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/android-owned/repository-checks.yml').read_text())
        source = (ROOT / 'tools/repository-checks/workflows/producers/repository-checks.yml').read_text()
        prospective = yaml.safe_load(source)
        historical_path = ROOT / 'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml'
        self.assertEqual(blob(historical_path.read_bytes())['sha'], 'b9022d17b985f93838b92cb42c7e2d873e7cb11f')
        historical_raw = historical_workflow_bytes()['d9fefd275d9e3c6977cf9350a1945a6bbe5051b4']
        self.assertEqual(blob(historical_raw)['sha'], 'd9fefd275d9e3c6977cf9350a1945a6bbe5051b4')
        historical = yaml.safe_load(historical_raw)
        permissions = {'contents': 'read', 'actions': 'read', 'pull-requests': 'read', 'checks': 'read'}
        expected = deepcopy(old)
        expected['jobs']['project']['permissions'] = permissions
        expected['jobs']['metadata-source'] = {
            'name': 'Authenticate PR text edit',
            'if': "github.event_name == 'pull_request' && github.base_ref == 'main' && github.event.action == 'edited' && !github.event.changes.base && (github.event.changes.title || github.event.changes.body)",
            'uses': './.github/workflows/pr-metadata-context.yml',
        }
        route = expected['jobs']['route']
        route['needs'] = 'metadata-source'
        route['if'] = "always() && (needs.metadata-source.result == 'success' || needs.metadata-source.result == 'skipped')"
        route['permissions'] = {'contents': 'read', 'actions': 'read', 'pull-requests': 'read'}
        event = next(step for step in route['steps'] if step.get('id') == 'event')
        event['env'] = {'GH_TOKEN': '${{ github.token }}',
                        'NATIVE_METADATA_INTENT': '${{ needs.metadata-source.outputs.metadata_intent }}'}
        docs = expected['jobs']['documentation']
        docs['needs'] = ['route', 'project']
        docs['if'] = "always() && needs.route.result == 'success' && (needs.project.result == 'success' || needs.project.result == 'skipped') && needs.route.outputs.metadata_only != 'true' && needs.project.outputs.documentation_verified != 'true'"
        expected['jobs']['workflow-security']['with'] = {'defer_workflow_contracts': True}
        expected['jobs']['workflow-contracts'] = {
            'needs': ['route', 'project'],
            'if': "always() && needs.route.result == 'success' && (needs.project.result == 'success' || needs.project.result == 'skipped') && needs.route.outputs.metadata_only != 'true' && needs.route.outputs.security == 'true' && needs.project.outputs.workflow_contracts_verified != 'true'",
            'runs-on': 'ubuntu-24.04', 'timeout-minutes': 5,
            'steps': [{'name': 'Check out the exact candidate without credentials',
                'uses': 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                'with': {'ref': '${{ github.sha }}', 'fetch-depth': 2, 'persist-credentials': False}},
                {'name': 'Verify remaining workflow contracts',
                 'run': 'PYTHONDONTWRITEBYTECODE=1 python3 tests/workflow-contract-test.py'}]}
        outer = expected['jobs']['repository-checks']
        outer['permissions'] = permissions
        outer['needs'].insert(outer['needs'].index('native'), 'workflow-contracts')
        candidate = next(step['with'] for step in outer['steps'] if step.get('with', {}).get('path') == 'candidate')
        candidate.update({'sparse-checkout-cone-mode': False,
                          'sparse-checkout': '.github\ntests/platform-profile.json\n'})
        verify = outer['steps'][-1]
        verify['env']['GH_TOKEN'] = '${{ github.token }}'
        verify['run'] = verify['run'].replace(' verify --needs-json', ' verify --event "$GITHUB_EVENT_PATH" --needs-json')
        self.assertEqual(historical, expected)
        # The old21 recipe remains byte-exact above. Current22 has its own
        # complete source tuple and cannot inherit permissions from a mixed pair.
        sources = {
            '.github/workflows/project-tests.yml': 'producers/protected-project-tests-android-platform.yml',
            '.github/workflows/parent-qualification.yml': 'producers/parent-qualification-android-platform.yml',
            '.github/workflows/repository-checks.yml': 'producers/repository-checks.yml',
            '.github/workflows/sync-validation.yml': 'sync-ci-selection.yml',
            '.github/workflows/browser-client.yml': 'npm-consumers/browser-client.yml',
            '.github/workflows/pr-metadata-context.yml': 'metadata-edits/pr-metadata-context.yml',
        }
        tree = {}
        for target, relative in sources.items():
            path = ROOT / 'tools/repository-checks/workflows' / relative
            self.assertFalse(path.is_symlink())
            self.assertIn(path.stat().st_mode & 0o777, (0o444, 0o644))
            tree[target] = blob(path.read_bytes())
        self.assertEqual(PACKAGES.validate_tree_wiring(tree), 'protected-producer-original-default-v1')
        for path in tree:
            for change in ('missing', 'mixed', 'mode'):
                changed = deepcopy(tree)
                if change == 'missing': del changed[path]
                elif change == 'mode': changed[path]['mode'] = '100755'
                else:
                    previous = next(row for row in PACKAGES.workflow_generations()
                                    if row['name'] == 'protected-producer-metadata-ci-v1')
                    other = next(entry for entry in previous['workflows'].values() if entry != tree[path])
                    changed[path] = deepcopy(other)
                with self.subTest(path=path, change=change), self.assertRaises(ValueError):
                    PACKAGES.validate_tree_wiring(changed)
        self.assertEqual(prospective['permissions'], {'contents': 'read'})
        self.assertEqual(prospective['jobs']['project']['uses'], './.github/workflows/project-tests.yml')
        self.assertNotIn('secrets', prospective['jobs']['project'])
        for role in ('metadata-source', 'route', 'project', 'repository-checks'):
            self.assertEqual(prospective['jobs'][role]['permissions'], permissions, role)
        for name, job in prospective['jobs'].items():
            actual = job.get('permissions', prospective['permissions'])
            if name == 'native':
                self.assertEqual(actual, {'contents': 'read', 'packages': 'read'})
            else:
                self.assertTrue(all(value == 'read' and key in permissions for key, value in actual.items()), name)
            self.assertNotIn('secrets', job)
        intent = "github.event_name == 'pull_request' && ((github.event.action == 'edited' && !github.event.changes.base && (github.event.changes.title || github.event.changes.body)) || ((github.event.action == 'labeled' || github.event.action == 'unlabeled') && github.event.label.name != 'android-long-diagnostics'))"
        self.assertEqual(prospective['jobs']['metadata-source']['if'], "github.event_name == 'pull_request'")
        self.assertEqual(prospective['jobs']['metadata-source']['with'], {'nonproducer_intent': '${{ ' + intent + ' }}'})
        self.assertEqual(prospective['run-name'], '${{ (' + intent + ") && 'Overte native metadata nonproducer v2' || 'Overte native ordinary qualification v2' }}")
        for role, condition in (
                ('project', "(needs.route.outputs.package_host_mode == 'full' || needs.route.outputs.package_host_mode == 'tool-dependencies' || needs.route.outputs.package_set != '[]')"),
                ('native', "needs.route.outputs.native != 'skip'"),
                ('android', "needs.route.outputs.android_required == 'true'"),
                ('workflow-security', "needs.route.outputs.security == 'true'")):
            self.assertEqual(prospective['jobs'][role]['if'],
                "always() && !cancelled() && needs.route.result == 'success' && needs.route.outputs.metadata_only != 'true' && " + condition + ' && !(' + intent + ')')
        candidate = next(step['with'] for step in prospective['jobs']['repository-checks']['steps']
                         if step.get('with', {}).get('path') == 'candidate')
        self.assertFalse(candidate['persist-credentials'])
        self.assertFalse(candidate['sparse-checkout-cone-mode'])
        self.assertEqual(candidate['sparse-checkout'], '.github\ntests/platform-profile.json\n')
        future_callee = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml').read_text())
        self.assertEqual(future_callee['permissions'], {'contents': 'read'})
        for name, job in future_callee['jobs'].items():
            actual = job.get('permissions', future_callee['permissions'])
            self.assertEqual(actual, permissions if name in {
                'route', 'project-tests', 'project-results', 'producer-publication', 'platform-tests'}
                else {'contents': 'read'}, name)
            self.assertNotIn('secrets', job)
        callee = yaml.safe_load((ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml').read_text())
        self.assertEqual(callee['permissions'], {'contents': 'read'})
        for name, job in callee['jobs'].items():
            actual = job.get('permissions', callee['permissions'])
            self.assertTrue(all(value == 'read' and permissions.get(key) == 'read' for key, value in actual.items()), name)
            self.assertEqual(actual, permissions if name in {'route', 'project-tests', 'producer-publication'} else {'contents': 'read'}, name)

    def test_callee_retains_permissions_readers_and_exact_historical_baseline(self):
        source = (ROOT / 'tools/repository-checks/workflows/producers/protected-project-tests.yml').read_bytes()
        self.assertEqual(source.count(b'      checks: read\n'), 3)
        self.assertEqual(source.count(b'          tools/branch-policy/check.py\n'), 6)
        self.assertEqual(source.count(b'        sparse-checkout-cone-mode: false\n'), 6)
        historical = (ROOT / 'tools/repository-checks/workflows/producers/legacy/protected-project-tests-postmerge-v1.yml').read_bytes()
        self.assertEqual(blob(historical)['sha'], '861db7b76a11b9b8772e91cb24ec7cb9d918e339')
        previous = historical.replace(b'          tools/branch-policy/check.py\n', b'').replace(
            b'        sparse-checkout-cone-mode: false\n', b'').replace(b'      checks: read\n', b'').replace(
            b'# Prospective protected producer; dormant wiring approved, production guards false.',
            b'# Prospective protected producer; production guards false and no active generation approval.')
        actual = subprocess.check_output(['/usr/bin/git', 'hash-object', '--stdin'], input=previous).decode().strip()
        self.assertEqual(actual, 'cad732c967d4d18b5a341c578b90789a271c02e9')


class ReceiptWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.old = yaml.safe_load((PACKAGES.TEMPLATES / "project-tests.yml").read_text())
        self.new = yaml.safe_load((ROOT / PACKAGES.PRODUCER_TEMPLATE).read_text())

    def test_only_full_host_execution_changes_and_other_owner_jobs_remain_identical(self):
        for key in self.old:
            if key != "jobs": self.assertEqual(self.old[key], self.new[key], key)
        self.assertEqual(set(self.old["jobs"]), set(self.new["jobs"]))
        for name in self.old["jobs"]:
            if name != "project-tests": self.assertEqual(self.old["jobs"][name], self.new["jobs"][name], name)
        previous, current = self.old["jobs"]["project-tests"], self.new["jobs"]["project-tests"]
        for key in previous:
            if key != "steps": self.assertEqual(previous[key], current[key], key)
        before = {step["name"]: step for step in previous["steps"]}
        after = {step["name"]: step for step in current["steps"]}
        for name in ("Set up Python", "Set up Node.js", "Set up Java", "Verify runner prerequisites",
                     "Install QML and portable C++ contract prerequisites"):
            self.assertEqual(before[name], after[name], name)

    def test_exact_candidate_trusted_requirements_controller_and_external_receipt_paths(self):
        steps = self.new["jobs"]["project-tests"]["steps"]
        trusted, candidate = steps[:2]
        self.assertEqual(trusted["with"]["ref"], "${{ github.event.repository.default_branch }}")
        self.assertEqual(trusted["with"]["path"], "trusted")
        self.assertFalse(trusted["with"]["sparse-checkout-cone-mode"])
        self.assertEqual(candidate["with"]["ref"], "${{ github.sha }}")
        self.assertEqual(candidate["with"]["path"], "candidate")
        self.assertEqual(candidate["with"]["fetch-depth"], 2)
        self.assertTrue(all(not step["with"]["persist-credentials"] for step in steps
                            if step.get("uses", "").startswith("actions/checkout@")))
        prepare = next(step for step in steps if step["name"] == "Prepare isolated host evidence validators")
        self.assertIn('-r trusted/tests/requirements-host.txt', prepare["run"])
        self.assertIn('python3 -m venv "$RUNNER_TEMP/overte-shared-host-env"', prepare["run"])
        self.assertIn('unshare --user --map-root-user --net true', prepare["run"])
        execute = next(step for step in steps if step["name"].startswith("Execute the complete trusted"))
        for expected in ('trusted/tools/test-evidence/run.py', '--candidate candidate --include-platform',
                         '--timeout 240 --host-timeout 900', '--junit "$RUNNER_TEMP/', '--receipt "$RUNNER_TEMP/'):
            self.assertIn(expected, execute["run"])
        self.assertNotIn('--suite', execute["run"])
        self.assertNotIn('candidate/tests/run-project-tests.py', execute["run"])
        self.assertEqual(execute["env"], {"GH_TOKEN": "", "GITHUB_TOKEN": ""})
        receipt = next(step for step in steps if step["name"] == "Preserve actual execution receipt for diagnosis")
        self.assertEqual(receipt["if"], "always()")
        self.assertEqual(receipt["with"]["path"], "${{ runner.temp }}/overte-shared-host-results/execution.json")
        self.assertIn('${{ github.run_id }}-attempt-${{ github.run_attempt }}', receipt["with"]["name"])
        self.assertNotIn('continue-on-error', execute)
        self.assertNotIn('descriptor', json.dumps(self.new))

    def test_sparse_controller_contains_actual_runtime_and_recursive_requirement_inputs(self):
        runtime = PACKAGES.load("host_receipt_runtime_contract", "tools/test-evidence/runtime.py")
        _, manifests = runtime._requirement_inventory(ROOT)
        patterns = self.new["jobs"]["project-tests"]["steps"][0]["with"]["sparse-checkout"].splitlines()
        required = {*runtime._TRUSTED_EXECUTION_FILES, *manifests, ".github/test-suites.json", "tests/platform-profile.json"}
        for path in required:
            self.assertTrue(any(path == pattern or path.startswith(pattern + "/") for pattern in patterns), path)


if __name__ == "__main__":
    unittest.main()
