#!/usr/bin/env python3
"""Static executable contracts for the hardware-owned Pico audio JNI boundary."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
JAVA = (ROOT / "vr/pico/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInput.java").read_text()
POLICY = (ROOT / "vr/pico/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInputPolicy.java").read_text()
CPP = (ROOT.parent / "libraries/audio-client/src/AudioClient.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}", file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {message}")


source_function = re.search(
    r"static QString picoAndroidAudioSource\(\) \{(?P<body>.*?)\n\}", CPP, re.DOTALL)
require(source_function is not None, "C++ Pico source selector remains present")
cpp_sources = set(re.findall(r'QStringLiteral\("([a-z]+)"\)', source_function.group("body")))
java_sources = set(re.findall(r'requestedSource\.equals\("([a-z]+)"\)', POLICY))
require(cpp_sources == {"mic", "voicecommunication", "voicerecognition", "camcorder"},
        "C++ source allowlist is exact")
require(java_sources == cpp_sources,
        "C++ diagnostic sources and Java policy remain synchronized")

require(re.search(
    r"public static (?:synchronized )?boolean start\(\s*String requestedSource, int sampleRate, "
    r"int channelCount, int framesPerBuffer\)", JAVA) is not None,
    "Java start signature retains String/int/int/int ordering")
require('GetStaticMethodID(\n        inputClass, "start", "(Ljava/lang/String;III)Z")' in CPP,
        "C++ start lookup retains the matching JNI descriptor")
require(re.search(
    r"CallStaticBooleanMethod\(\s*inputClass,\s*startMethod,\s*sourceString,\s*"
    r"static_cast<jint>\(format\.sampleRate\(\)\),\s*"
    r"static_cast<jint>\(format\.channelCount\(\)\),\s*"
    r"static_cast<jint>\(framesPerBuffer\)\)", CPP, re.DOTALL) is not None,
    "sample rate, channels and frames cross JNI without reordering")
require(re.search(
    r"startAndroidAudioInput\(\s*_inputFormat, numFrameSamples, androidAudioSource\)",
    CPP, re.DOTALL) is not None,
    "native frame count is transported from the input callback calculation")

require("AudioFormat.ENCODING_PCM_16BIT" in JAVA and "Short.BYTES" in POLICY,
        "Java allocation and AudioRecord format both use 16-bit PCM")
require("private static native void nativeInitialize();" in JAVA
        and "private static native void nativeOnAudioData(byte[] audio, int bytesRead);" in JAVA,
        "Java native declarations retain their class-loader and byte transport signatures")
require("Java_org_overte_pico_AndroidAudioInput_nativeInitialize" in CPP
        and "Java_org_overte_pico_AndroidAudioInput_nativeOnAudioData" in CPP,
        "C++ exports retain the Java native symbol spellings")
require(re.search(
    r"if \(!data \|\| bytesRead <= 0 \|\| bytesRead > environment->GetArrayLength\(data\)",
    CPP) is not None,
    "native callback rejects null, non-positive and out-of-array lengths")
require(re.search(
    r"QByteArray audio\(bytesRead, Qt::Uninitialized\);.*?GetByteArrayRegion\(\s*"
    r"data, 0, bytesRead", CPP, re.DOTALL) is not None,
    "native callback copies exactly the reported byte count")
require(re.search(
    r"activeRecorder\.read\(.*?final boolean ownsRecorder = recorder == activeRecorder;.*?"
    r"shouldDeliverRead\(bytesRead, running, ownsRecorder\).*?nativeOnAudioData\(audio, bytesRead\)",
    JAVA, re.DOTALL) is not None,
    "blocking reads revalidate running state and recorder ownership before JNI delivery")

print("Pico audio JNI boundary contracts passed; Android/JNI execution remains device-owned.")
