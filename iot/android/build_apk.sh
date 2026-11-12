#!/bin/bash
# Builds SmartFarm.apk with the Android SDK command-line tools only (no Gradle needed).
#   ./build_apk.sh            -> build/SmartFarm.apk
# Needs: Android SDK (platform android-34, build-tools 35) and a JDK 11+.
# Signing key: ~/.android/smartfarm-release.jks (created on first run). Keep a backup of
# it - phones only accept updates signed with the same key.
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BT="$SDK/build-tools/35.0.0"
JAR="$SDK/platforms/android-34/android.jar"
if [ -z "${JAVA_HOME:-}" ]; then
  for j in "/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
           "/Applications/Android Studio.app/Contents/jre/Contents/Home"; do
    [ -x "$j/bin/javac" ] && JAVA_HOME="$j" && break
  done
fi
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
KS="${SMARTFARM_KEYSTORE:-$HOME/.android/smartfarm-release.jks}"
KS_PASS="${SMARTFARM_KEYSTORE_PASS:-smartfarm}"

SRC=app/src/main
OUT=build
rm -rf "$OUT"; mkdir -p "$OUT/res" "$OUT/classes" "$OUT/dex"

echo "1/5 resources"
"$BT/aapt2" compile --dir "$SRC/res" -o "$OUT/res/res.zip"
"$BT/aapt2" link -I "$JAR" --manifest "$SRC/AndroidManifest.xml" \
  --java "$OUT/gen" -o "$OUT/unsigned.apk" "$OUT/res/res.zip" --auto-add-overlay

echo "2/5 java"
javac -nowarn -source 8 -target 8 -encoding UTF-8 -bootclasspath "$JAR:$BT/core-lambda-stubs.jar" -classpath "$JAR" \
  -d "$OUT/classes" $(find "$SRC/java" "$OUT/gen" -name '*.java') 2>&1 | grep -v "bootstrap classpath" || true
[ -n "$(find "$OUT/classes" -name '*.class')" ] || { echo "javac failed"; exit 1; }

echo "3/5 dex"
"$BT/d8" --release --min-api 26 --lib "$JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
(cd "$OUT/dex" && zip -q ../unsigned.apk classes.dex)

echo "4/5 align"
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

echo "5/5 sign"
if [ ! -f "$KS" ]; then
  mkdir -p "$(dirname "$KS")"
  keytool -genkeypair -keystore "$KS" -storepass "$KS_PASS" -keypass "$KS_PASS" -alias smartfarm \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Smart Farm" >/dev/null
  echo "   created signing key $KS (back it up)"
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass "pass:$KS_PASS" --ks-key-alias smartfarm \
  --out "$OUT/SmartFarm.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$OUT/SmartFarm.apk"
ls -lh "$OUT/SmartFarm.apk"
