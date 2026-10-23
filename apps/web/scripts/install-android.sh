#!/bin/sh
# Debug build onto a USB-connected Android phone (Git Bash). Tools: Java 21 + Android SDK in %LOCALAPPDATA%\Thandak-tools.
set -e
cd "$(dirname "$0")/.."
T="$LOCALAPPDATA/Thandak-tools"
export JAVA_HOME="$(cygpath -w "$(ls -d "$T"/jdk/jdk-21*)")" ANDROID_HOME="$(cygpath -w "$T/sdk")"
ADB="$T/sdk/platform-tools/adb.exe"
npm run cap:sync
# debug only: let the app call the PC over plain http (adb reverse). Patched into the synced copy, which git ignores,
# so capacitor.config.json itself keeps the release settings.
node -e 'const f="android/app/src/main/assets/capacitor.config.json",fs=require("fs"),c=JSON.parse(fs.readFileSync(f));c.android=Object.assign(c.android||{},{allowMixedContent:true});c.server=Object.assign(c.server||{},{cleartext:true});fs.writeFileSync(f,JSON.stringify(c,null,2))'
(cd android && ./gradlew.bat assembleDebug -q)
"$ADB" install -r android/app/build/outputs/apk/debug/app-debug.apk
"$ADB" reverse tcp:8000 tcp:8000   # the phone's localhost:8000 = this PC's API
"$ADB" shell am force-stop in.thandak.app
"$ADB" shell monkey -p in.thandak.app -c android.intent.category.LAUNCHER 1 >/dev/null
sleep 3
"$ADB" forward tcp:9333 "localabstract:webview_devtools_remote_$("$ADB" shell pidof in.thandak.app | tr -d '\r')"
echo installed
