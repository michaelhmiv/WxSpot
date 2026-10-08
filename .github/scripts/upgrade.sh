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
# Both versions use the production endpoint. This acceptance creates only a device
# profile and local data; all database migrations/cleanup and publishing tests stay local.
common=(-Pwxspot.apiUrl=https://wxspotapi-production.up.railway.app -Pwxspot.beta=true --no-daemon)
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest "${common[@]}" -Pwxspot.versionCode=3
cp app/build/outputs/apk/debug/app-debug.apk /tmp/wxspot-upgrade/version-3.apk
apksigner="$ANDROID_HOME/build-tools/36.0.0/apksigner"
"$apksigner" verify --print-certs /tmp/wxspot-upgrade/version-3.apk > /tmp/wxspot-upgrade/version-3-certificate.txt
adb install -r -t /tmp/wxspot-upgrade/version-3.apk
adb install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
instrument() {
  adb shell am instrument -w -r -e class app.wxspot.UpgradeAcceptanceTest -e upgradeStage "$1" \
    app.wxspot.beta.test/androidx.test.runner.AndroidJUnitRunner | tee "/tmp/wxspot-upgrade/$1.txt"
  grep -q 'OK (1 test)' "/tmp/wxspot-upgrade/$1.txt"
  if grep -qE 'FAILURES|INSTRUMENTATION_FAILED|Process crashed' "/tmp/wxspot-upgrade/$1.txt"; then return 1; fi
}
instrument seed
adb shell am force-stop app.wxspot.beta
./gradlew :app:assembleRelease :app:assembleReleaseAndroidTest "${common[@]}" \
  -Pwxspot.testBuildType=release -Pwxspot.versionCode=4 -Pwxspot.versionName=0.2.0-beta.2
cp app/build/outputs/apk/release/app-release.apk /tmp/wxspot-upgrade/version-4.apk
cp app/build/outputs/apk/androidTest/release/app-release-androidTest.apk /tmp/wxspot-upgrade/release-instrumentation.apk
"$apksigner" verify --print-certs /tmp/wxspot-upgrade/version-4.apk > /tmp/wxspot-upgrade/version-4-certificate.txt
diff /tmp/wxspot-upgrade/version-{3,4}-certificate.txt
adb install -r -t /tmp/wxspot-upgrade/version-4.apk
adb install -r -t app/build/outputs/apk/androidTest/release/app-release-androidTest.apk
instrument verify
adb pull /sdcard/wxspot-acceptance /tmp/wxspot-screenshots || true
echo 'PASS: APK version 3 -> 4 preserved encrypted profile/resume credential, draft, places, camera and units.'
echo 'Signing scope: matching explicit signer; version 4 is the optimized production-endpoint beta.'
keytool -exportcert -rfc -keystore "$WXSPOT_KEYSTORE_PATH" \
  -storepass:env WXSPOT_KEYSTORE_PASSWORD -alias "$WXSPOT_KEY_ALIAS" \
  -file /tmp/wxspot-upgrade/beta-certificate.pem >/dev/null 2>&1
python3 - <<'PY'
import os, pathlib, shlex, zipfile
target=pathlib.Path(os.environ['RUNNER_TEMP'])/'wxspot-signing-export.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    archive.write(os.environ['WXSPOT_KEYSTORE_PATH'],'WxSpot-beta.jks')
    archive.write('/tmp/wxspot-upgrade/beta-certificate.pem','WxSpot-beta-certificate.pem')
    config={'WXSPOT_KEYSTORE_PATH':'./WxSpot-beta.jks', **{
        name:os.environ[name] for name in ('WXSPOT_KEY_ALIAS','WXSPOT_KEYSTORE_PASSWORD','WXSPOT_KEY_PASSWORD')}}
    archive.writestr('signing.env',''.join(f'export {name}={shlex.quote(value)}\n' for name,value in config.items()))
PY
openssl cms -encrypt -binary -aes-256-cbc -in "$RUNNER_TEMP/wxspot-signing-export.zip" \
  -out /tmp/wxspot-upgrade/beta-signing-recovery.der -outform DER \
  -recip ../docs/BETA_RECOVERY_RECIPIENT.pem -keyopt rsa_padding_mode:oaep
rm -f "$RUNNER_TEMP/wxspot-signing-export.zip"
sha256sum /tmp/wxspot-upgrade/version-4.apk > /tmp/wxspot-upgrade/SHA256.txt
