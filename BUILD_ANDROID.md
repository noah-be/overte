<!--
Copyright 2013-2019 High Fidelity, Inc.
Copyright 2019-2021 Vircadia contributors
Copyright 2021-2022 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Build Android

## Pico 4 (current Linux workflow)

The Pico 4 client has a maintained command-line build workflow for Linux. It
checks the development environment, installs supported prerequisites, downloads
checksum-verified prebuilt Qt and Node packages, builds the APK, and can install
and start it on a USB-connected Pico 4.

For a new development environment, run:

```bash
./android/vr/pico/build.sh bootstrap --with-deps
./android/vr/pico/build.sh
```

The bootstrap may request administrator access for missing system packages and
prompts for Android SDK license acceptance when required. If the Android
command-line tools have not been installed yet, it asks for explicit acceptance
of Google's license terms before downloading and checksum-verifying the
official tools automatically.

To inspect the machine without making changes, use:

```bash
./android/vr/pico/build.sh doctor
```

To build, install, and automatically start the client on an authorized
USB-connected headset, use:

```bash
./android/vr/pico/build.sh deploy
```

See the [complete Pico 4 build guide](android/vr/pico/docs/BUILD.md) for prerequisites,
individual build stages, the source-build fallback, device selection, path
overrides, and troubleshooting information.

## Legacy Quest 1 workflow

*Last Updated on December 15, 2020*
> [!WARNING]  
> The historical Quest 1 workflow below is currently broken due to breaking
> changes in Qt and Gradle. This warning does not apply to the Pico 4 workflow
> documented above.

Please read the [general build guide](BUILD.md) for information on building other platforms. Only Android specific instructions are found in this file. **Note that these instructions apply to building for the Oculus Quest 1.**

## Dependencies

Building is currently supported on Windows, OSX and Linux, but developers intending to do work on the library dependencies are strongly urged to use 64 bit Linux as a build platform.

### OS specific dependencies

Please install the dependencies for your OS using the [Windows](BUILD_WIN.md), [OSX](BUILD_OSX.md) or [Linux](BUILD_LINUX.md) build instructions before attempting to build for Android.

### Android Studio

Download the [Android Studio](https://developer.android.com/studio/index.html) installer and run it. Once installed, click _File_ then _Settings_, expand _Appearance & Behavior_ then expand _System Settings_ and select _Android SDK_. 

From the _SDK Platforms_ tab, select API levels 26 and 28.  

From the _SDK Tools_ tab, select the following

* Android SDK Build-Tools
* GPU Debugging Tools
* LLDB 
* Android SDK Platform-Tools
* Android SDK Tools
* NDK (even if you have the NDK installed separately)

Still in the _SDK Tools_ tab, check off _Show Package Details_ at the bottom.
Select CMake 3.18.1 and NDK 27.3.13750724. Do this even if you have separate
installations.

The legacy graph pins Android Gradle Plugin `4.1.3` and Gradle `6.5`. Bootstrap the reviewed distribution once, then use the dedicated wrapper:

```bash
python3 android/common/tests/legacy-gradle/run_dependency_report.py toolchain --network
./android/common/legacy/gradlew tasks
```

Do not accept an automatic Gradle plugin upgrade: the dedicated wrapper and the
root build file are the reviewed Legacy toolchain authority.

The Interface native graph can reuse the maintained Android Conan packages.
Point the build at their generated CMake files and package roots before building:

```bash
export HIFI_ANDROID_CONAN_GENERATORS=/absolute/path/to/conan/generators
export HIFI_ANDROID_QT_ROOT=/absolute/path/to/the/Qt/package
export HIFI_ANDROID_OPENSSL_ROOT=/absolute/path/to/the/OpenSSL/package
./android/common/legacy/gradlew -PVERSION_CODE=1 -PRELEASE_NUMBER=1.0 \
  -PSUPPRESS_PICO_INTERFACE -PSUPPRESS_QUEST_INTERFACE \
  -PSUPPRESS_FRAME_PLAYER -PSUPPRESS_QUEST_FRAME_PLAYER \
  :interface:assembleDebug
```

These paths must refer to ARM64 Android packages built with the selected NDK.

## Environment

### Create a keystore in Android Studio
Follow the directions [here](https://developer.android.com/studio/publish/app-signing#generate-key) to create a keystore file. You can save it anywhere (preferably not in the `overte` folder).

### Set up machine specific Gradle properties

Create a `gradle.properties` file in the `.gradle` folder (`$HOME/.gradle` on Unix, `Users/<yourname>/.gradle` on Windows). Edit the file to contain the following

```properties
HIFI_ANDROID_PRECOMPILED=<your_home_directory>/Android/hifi_externals
HIFI_ANDROID_KEYSTORE=<key_store_directory>/<keystore_name>.jks
HIFI_ANDROID_KEYSTORE_PASSWORD=<password>
HIFI_ANDROID_KEY_ALIAS=<key_alias>
HIFI_ANDROID_KEY_PASSWORD=<key_passwords>
```

Note, do not use $HOME for the path. It must be a fully qualified path name. Also, be sure to use forward slashes in your path.

#### If you are building for an Android phone

Add these lines to `gradle.properties`

```properties
SUPPRESS_QUEST_INTERFACE
SUPPRESS_QUEST_FRAME_PLAYER
```

#### If you are building for an Oculus Quest

Add these lines to `gradle.properties`

```properties
SUPPRESS_INTERFACE
SUPPRESS_FRAME_PLAYER
```

#### The Frame Player for both Android Phone and Oculus Quest is optional, so if you encounter problems with these during your build, you can skip them by adding these lines to `gradle.properties`

```properties
SUPPRESS_FRAME_PLAYER
SUPPRESS_QUEST_FRAME_PLAYER
```

### Clone the repository

`git clone https://github.com/overte-org/overte.git`

## Building & Running

### Building Modules

* Open Android Studio
* Choose _Open an existing Android Studio project_
* Navigate to the `overte` repository that had you cloned and choose the `android` folder and select _OK_
* Wait for Gradle to sync (this should take around 20 minutes the first time)
* If a dialog pops open saying "Plugin Update Recommeded" dialog, do not click update, just click X on the top right to close.
* In the _Project_ window click on the project you wish to build (i.e. "questInterface") then click _Build_ in the top menu and choose _Make Module 'questInterface'_
* By default this will build the "debug" apk, you can change this by opening the _Build Variants_ window along the left side and select other build types such as "release".
* Your newly build APK should reside in `overte\android\apps\questInterface\release` (if you chose release).

### Running a Module

You are free to use the "adb" command line or other development tools to install (sideload on Quest) your newly built APK, or you can follow the instructions below to load the APK via Android Studio.  

* In the toolbar at the top of Android Studio, next to the green hammer icon, you should see a dropdown menu.
* You may already see a configuration for the module you are trying to build. If so, select it. 
* Otherwise, select _Edit Configurations_.

Your configuration should be as follows

* Type: Android App
* Module: <your module> (you probably want `interface` or `questInterface`)

For the interface modules, you also need to select the activity to launch. 

#### For the Android phone interface

* From the _Launch_ drop down menu, select _Specified Activity_
* In the _Activity_ field directly below, put `io.highfidelity.hifiinterface.PermissionChecker`

#### For the Oculus Quest interface

* From the _Launch_ drop down menu, select _Specified Activity_
* In the _Activity_ field directly below, put `io.highfidelity.questInterface.PermissionsChecker`

Note the 's' in Permission**s**Checker for the Quest.

Now you are able to run your module! Click the green play button in the top toolbar of Android Studio.

## Troubleshooting

To view a more complete debug log,

* Click the icon with the two overlapping squares in the upper left corner of the tab where the sync is running (hover text says _Toggle view_)
* To change verbosity, click _File > Settings_. Under _Build, Execution, Deployment > Compiler_ you can add command-line flags, as per Gradle documentation

If you encounter CMake issues, try adding the following system environment variable:

With your start menu, search for 'Edit the System Environment Variables' and open it.
* Click on 'Advanced' tab, then 'Environment Variables'
* Select 'New' under System variables
* Set "Variable name" to QT_CMAKE_PREFIX_PATH
* Set "Variable value" to the directory that your android build placed the CMake 3.6.4 library CMake directory (i.e. android\qt\lib\cmake).

Some things you can try if you want to do a clean build
 
* Delete the `build` and `.externalNativeBuild` folders from the folder for each module you're building (for example, `overte/android/phone/apps/interface`)
* If you have set your `HIFI_VCPKG_ROOT` environment variable, delete the contents of that directory; otherwise, delete `AppData/Local/Temp/hifi`
* In Android Studio, click _File > Invalidate Caches / Restart_ and select _Invalidate and Restart_

If you see lots of "couldn't acquire lock" errors,
* Open Task Manager and close any running Clang / Gradle processes
