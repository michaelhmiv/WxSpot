#!/usr/bin/env bash
set -u
cd android
./gradlew :app:connectedDebugAndroidTest -Pwxspot.apiUrl=http://10.0.2.2:8000 \
  -Pandroid.testInstrumentationRunnerArguments.notClass=app.wxspot.UpgradeAcceptanceTest --no-daemon
result=$?
adb pull /sdcard/wxspot-acceptance /tmp/wxspot-screenshots || true
adb logcat -d > /tmp/wxspot-device.log
weather_trace=/tmp/wxspot-weather-trace.log
grep 'WxSpotWeather' /tmp/wxspot-device.log | tail -n 100 > "$weather_trace" || true
if [ -s "$weather_trace" ]; then
  cat "$weather_trace"
fi
if [ "$result" -ne 0 ]; then
  grep -E 'WxSpotWeather.*model:|Model capture:' /tmp/wxspot-device.log | tail -n 100 || true
  python3 - <<'PY'
import pathlib
for path in pathlib.Path('app/build/outputs/androidTest-results').rglob('*.xml'):
    print(path.read_text())
PY
fi
if [ "$result" -eq 0 ] && ! grep -q 'state=ready' "$weather_trace"; then
  echo "No successful radar readiness trace was recorded."
  exit 1
fi
exit "$result"
