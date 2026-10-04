// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Window 2.2
import BrowserNativeInput 1.0

Window {
    width: 640; height: 480; visible: true
    NativeInput { id: nativeInput }
    TextInput { id: plain; maximumLength: 65536; objectName: "plain"; width: 600; height: 40; y: 0 }
    TextEdit { id: rich; width: 600; height: 100; y: 50; textFormat: TextEdit.RichText }
    TextInput { id: validated; width: 200; height: 40; y: 170; validator: IntValidator { bottom: 100; top: 999 } }
    TextInput { id: limited; width: 200; height: 40; y: 220; maximumLength: 5 }
    TextInput { id: masked; width: 200; height: 40; y: 270; inputMask: "0000" }
    function verify(condition,message) { if(!condition)throw new Error(message); }
    function runTests() {
        plain.forceActiveFocus();plain.text="old selected value";plain.selectAll();
        verify(nativeInput.commitText(plain,"Überte 世界 👋"),"Unicode commit must be accepted");
        verify(plain.text==="Überte 世界 👋","Atomic Unicode selection replacement must preserve all code points");
        plain.undo();verify(plain.text==="old selected value","One undo must restore the whole replacement");
        plain.redo();verify(plain.text==="Überte 世界 👋","One redo must restore the whole commit");
        plain.selectAll();verify(nativeInput.cutSelection(plain)&&plain.text==="","Native atomic cut must remove selected Unicode");
        plain.undo();verify(plain.text==="Überte 世界 👋","One undo must restore selected Unicode after cut");
        plain.text="before 世界 👋 after";plain.select(7,12);
        verify(nativeInput.cutSelection(plain)&&plain.text==="before  after","Native cut must remove only the middle selected Unicode substring");
        plain.undo();verify(plain.text==="before 世界 👋 after","One undo must restore a middle Unicode cut without changing surrounding text");
        plain.text="Überte 世界 👋";
        plain.readOnly=true;plain.selectAll();verify(!nativeInput.commitText(plain,"changed"),"Readonly commit must be refused");
        verify(!nativeInput.cutSelection(plain),"Readonly cut must be refused");
        verify(plain.text==="Überte 世界 👋","Readonly text must remain unchanged");plain.readOnly=false;
        plain.enabled=false;verify(!nativeInput.commitText(plain,"changed"),"Disabled commit must be refused");plain.enabled=true;
        rich.forceActiveFocus();rich.text="<b>Existing</b>";rich.selectAll();
        verify(nativeInput.commitText(rich,"<b>literal & 世界</b>"),"Rich editor plaintext commit must be accepted");
        verify(rich.getText(0,rich.length)==="<b>literal & 世界</b>","Visitor markup must remain literal text in a rich editor");
        verify(rich.textFormat===TextEdit.RichText,"The native editor text format must remain unchanged");
        validated.forceActiveFocus();validated.text="123";validated.selectAll();nativeInput.commitText(validated,"invalid");
        verify(validated.text==="123"&&validated.selectedText==="123","Rejected native validator replacement must preserve original selection and text");
        verify(nativeInput.commitText(validated,"456")&&validated.text==="456"&&validated.acceptableInput,"Valid replacement must honor the native validator");
        limited.forceActiveFocus();limited.text="";verify(nativeInput.commitText(limited,"abcdefg")&&limited.text==="abcde","Native maximumLength must be preserved");
        var originalMask=masked.inputMask;masked.forceActiveFocus();masked.text="1234";masked.selectAll();nativeInput.commitText(masked,"ab12");
        verify(masked.text==="12"&&masked.inputMask===originalMask,"Native input mask must reject nonnumeric characters without changing its configuration");
        plain.forceActiveFocus();plain.text="";verify(!nativeInput.commitText(plain,"a\u0000b"),"Control-character policy must reject NUL");
        verify(!nativeInput.commitText(plain,new Array(65538).join("a")),"Oversized native commits must be refused");
        verify(nativeInput.commitText(plain,new Array(65533).join("a")+"👋")&&plain.text.length===65534,"Exactly 64 KiB of UTF-8 text must be accepted");
        plain.text="unchanged";rich.forceActiveFocus();verify(!nativeInput.commitText(plain,"changed")&&plain.text==="unchanged","Unfocused items must be refused");
        plain.forceActiveFocus();plain.text="unchanged";
        verify(!nativeInput.commitWebPasswordText(plain,plain,"A")&&plain.text==="unchanged","Ordinary Qt editors must not use the delegated password route");
        verify(!nativeInput.commitWebPasswordText(plain,plain,"\ud800"),"Lone high surrogate must be refused");
        verify(!nativeInput.commitWebPasswordText(plain,plain,"\udc00"),"Lone low surrogate must be refused");
        verify(!nativeInput.commitWebPasswordText(plain,plain,"ab"),"Ordinary editors cannot use the delegated whole-password route");
        verify(!nativeInput.commitWebPasswordText(plain,plain,"\u0000"),"Password text policy must refuse NUL");
        verify(!nativeInput.commitWebPasswordText(plain,null,"👋"),"Missing owned root must be refused");
        return true;
    }
}
