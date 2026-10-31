#!/bin/sh
# Signed release APK that talks to the public HTTPS API (Git Bash). Tools and the signing key live in %LOCALAPPDATA%\Thandak-tools.
# Override the server with THANDAK_API_BASE=https://... if needed.
set -e
cd "$(dirname "$0")/.."
T="$LOCALAPPDATA/Thandak-tools"
export JAVA_HOME="$(cygpath -w "$(ls -d "$T"/jdk/jdk-21*)")" ANDROID_HOME="$(cygpath -w "$T/sdk")"
export THANDAK_SIGNING_PROPS="${THANDAK_SIGNING_PROPS:-$(cygpath -m "$T/release/keystore.properties")}"
[ -f "$THANDAK_SIGNING_PROPS" ] || { echo "signing properties not found: $THANDAK_SIGNING_PROPS" >&2; exit 1; }
# Variables already in the environment win over .env.app / .env.app.local, so the release can't pick up a dev address or debug flag.
export VITE_API_BASE="${THANDAK_API_BASE:-https://thandak-india-api.vercel.app}" VITE_DEBUG=""
case "$VITE_API_BASE" in https://*) ;; *) echo "release builds need an https:// API address" >&2; exit 1 ;; esac
npm run cap:sync
if grep -rqE "http://(localhost|127\.0\.0\.1)" dist-app/assets; then echo "a local http:// address is still in the build" >&2; exit 1; fi
(cd android && ./gradlew.bat assembleRelease -q)
APK=android/app/build/outputs/apk/release/app-release.apk
"$(ls -d "$ANDROID_HOME"/build-tools/* | tail -1)/apksigner.bat" verify "$APK"
echo "built $APK"
