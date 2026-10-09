#!/usr/bin/env bash
set -u
cd android
./gradlew :app:connectedDebugAndroidTest -Pwxspot.beta=true -Pwxspot.versionCode=4 \
  -Pwxspot.versionName=0.3.0-beta.1-acceptance.4 -Pwxspot.apiUrl=http://10.0.2.2:8000 \
  -Pandroid.testInstrumentationRunnerArguments.notClass=app.wxspot.UpgradeAcceptanceTest --no-daemon
result=$?
mkdir -p /tmp/wxspot-hunt-screenshots
adb pull /sdcard/Pictures/WXspotAcceptance/ /tmp/wxspot-hunt-screenshots/
test -f /tmp/wxspot-hunt-screenshots/WXspotAcceptance/01-home.png || test -f /tmp/wxspot-hunt-screenshots/01-home.png
adb logcat -d > /tmp/wxspot-device.log
if [ "$result" -ne 0 ]; then
  python3 - <<'PY'
import pathlib
for path in pathlib.Path('app/build/outputs/androidTest-results').rglob('*.xml'):
    print(path.read_text())
PY
fi
exit "$result"
