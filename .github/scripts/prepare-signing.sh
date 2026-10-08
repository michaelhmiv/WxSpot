#!/usr/bin/env bash
set -euo pipefail
umask 077
# A fresh acceptance signer is never distributed automatically. Only a verified APK and
# its recipient-encrypted recovery bundle can be selected as the retained beta lineage.
export WXSPOT_KEYSTORE_PATH="$RUNNER_TEMP/wxspot-acceptance.jks"
export WXSPOT_KEY_ALIAS=wxspot-acceptance
export WXSPOT_KEYSTORE_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export WXSPOT_KEY_PASSWORD="$WXSPOT_KEYSTORE_PASSWORD"
echo "::add-mask::$WXSPOT_KEYSTORE_PASSWORD"
keytool -genkeypair -keystore "$WXSPOT_KEYSTORE_PATH" -storetype PKCS12 \
  -storepass:env WXSPOT_KEYSTORE_PASSWORD -keypass:env WXSPOT_KEY_PASSWORD \
  -alias "$WXSPOT_KEY_ALIAS" -keyalg RSA -keysize 3072 -validity 10000 \
  -dname 'CN=WxSpot Beta acceptance' >/dev/null 2>&1
for name in WXSPOT_KEYSTORE_PATH WXSPOT_KEY_ALIAS WXSPOT_KEYSTORE_PASSWORD WXSPOT_KEY_PASSWORD; do
  printf '%s=%s\n' "$name" "${!name}" >> "$GITHUB_ENV"
done
