#!/usr/bin/env bash
set -euo pipefail
# Keep app data and Android Keystore intact: no uninstall, pm clear, or UTP between versions.
cd android
mkdir -p /tmp/wxspot-upgrade
capture_upgrade_diagnostics() {
  upgrade_result=$?
  trap - EXIT
  adb logcat -d > /tmp/wxspot-upgrade/logcat.txt || true
  for variant in release releaseAndroidTest; do
    mapping="app/build/outputs/mapping/$variant/mapping.txt"
    if [ -f "$mapping" ]; then cp "$mapping" "/tmp/wxspot-upgrade/$variant-mapping.txt"; fi
  done
  if [ "$upgrade_result" -ne 0 ]; then
    adb logcat -d -s AndroidRuntime:E || true
  fi
  exit "$upgrade_result"
}
trap capture_upgrade_diagnostics EXIT
test -n "${WXSPOT_KEYSTORE_PATH:-}"
# Both APKs use the isolated PostGIS/API services started by device.yml.
common=(-Pwxspot.apiUrl=http://10.0.2.2:8000 -Pwxspot.beta=true --no-daemon)
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest "${common[@]}" \
  -Pwxspot.versionCode=3 -Pwxspot.versionName=0.3.0-beta.1-acceptance.3
cp app/build/outputs/apk/debug/app-debug.apk /tmp/wxspot-upgrade/version-3.apk
apksigner="$ANDROID_HOME/build-tools/36.0.0/apksigner"
"$apksigner" verify --print-certs /tmp/wxspot-upgrade/version-3.apk > /tmp/wxspot-upgrade/version-3-certificate.txt
adb install -r -t /tmp/wxspot-upgrade/version-3.apk
adb install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
instrument() {
  if [ "$1" = seed ]; then
    adb shell am instrument -w -r -e class app.wxspot.UpgradeAcceptanceTest -e upgradeStage seed \
      app.wxspot.beta.test/androidx.test.runner.AndroidJUnitRunner | tee /tmp/wxspot-upgrade/seed.txt
  else
    adb shell am instrument -w -r \
      app.wxspot.beta.test/app.wxspot.UpgradeInstrumentation | tee /tmp/wxspot-upgrade/verify.txt
  fi
  grep -q 'OK (1 test)' "/tmp/wxspot-upgrade/$1.txt"
  if grep -qE 'FAILURES|INSTRUMENTATION_FAILED|Process crashed' "/tmp/wxspot-upgrade/$1.txt"; then return 1; fi
}
instrument seed
adb shell am force-stop app.wxspot.beta
./gradlew :app:assembleRelease :app:assembleReleaseAndroidTest "${common[@]}" \
  -Pwxspot.testBuildType=release -Pwxspot.versionCode=4 \
  -Pwxspot.versionName=0.3.0-beta.1-acceptance.4
cp app/build/outputs/apk/release/app-release.apk /tmp/wxspot-upgrade/version-4.apk
cp app/build/outputs/apk/androidTest/release/app-release-androidTest.apk /tmp/wxspot-upgrade/release-instrumentation.apk
"$apksigner" verify --print-certs /tmp/wxspot-upgrade/version-4.apk > /tmp/wxspot-upgrade/version-4-certificate.txt
diff /tmp/wxspot-upgrade/version-{3,4}-certificate.txt
adb install -r -t /tmp/wxspot-upgrade/version-4.apk
adb install -r -t app/build/outputs/apk/androidTest/release/app-release-androidTest.apk
instrument verify
adb pull /sdcard/wxspot-hunt-acceptance /tmp/wxspot-hunt-screenshots || true
echo 'PASS: app replacement preserved guest recovery state and package identity under the isolated acceptance signer.'
echo 'This emulator check does not verify the production beta signing key or create a distributable release APK.'
