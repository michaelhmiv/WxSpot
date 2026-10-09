#!/usr/bin/env bash
set -u
cd android
./gradlew :app:connectedDebugAndroidTest -Pwxspot.beta=true -Pwxspot.versionCode=4 \
  -Pwxspot.versionName=0.3.0-beta.1-acceptance.4 -Pwxspot.apiUrl=http://10.0.2.2:8000 \
  -Pandroid.testInstrumentationRunnerArguments.notClass=app.wxspot.UpgradeAcceptanceTest --no-daemon
result=$?
adb pull /sdcard/Android/data/app.wxspot.beta/files/wxspot-hunt-acceptance /tmp/wxspot-hunt-screenshots || true
adb logcat -d > /tmp/wxspot-device.log
if [ "$result" -ne 0 ]; then
  python3 - <<'PY'
import pathlib
for path in pathlib.Path('app/build/outputs/androidTest-results').rglob('*.xml'):
    print(path.read_text())
PY
fi
exit "$result"
