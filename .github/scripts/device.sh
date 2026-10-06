#!/usr/bin/env bash
set -u
cd android
./gradlew :app:connectedDebugAndroidTest -Pwxspot.apiUrl=http://10.0.2.2:8000 --no-daemon
result=$?
adb pull /sdcard/Android/data/app.wxspot/files/acceptance /tmp/wxspot-screenshots || true
adb logcat -d > /tmp/wxspot-device.log
if [ "$result" -ne 0 ]; then
  python3 - <<'PY'
import pathlib
for path in pathlib.Path('app/build/outputs/androidTest-results').rglob('*.xml'):
    print(path.read_text())
PY
fi
exit "$result"
