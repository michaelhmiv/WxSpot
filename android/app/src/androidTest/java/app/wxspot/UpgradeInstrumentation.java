package app.wxspot;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.KeyStore;
import java.security.MessageDigest;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** Platform-only driver: shared Kotlin/AndroidX test code may be removed by target R8. */
public final class UpgradeInstrumentation extends Instrumentation {
    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        try {
            verifyUpgrade();
            result.putString("stream", "\nPASS: retained encrypted identity, draft, places, camera, "
                    + "units, restored UI and real credential renewal.\nOK (1 test)\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            // Never include an HTTP body, encrypted session or credential in diagnostics.
            StringBuilder details = new StringBuilder("\nFAILURES: ")
                    .append(error.getClass().getSimpleName());
            if (error instanceof AssertionError) details.append(": ").append(error.getMessage());
            for (StackTraceElement frame : error.getStackTrace()) {
                details.append("\n  at ").append(frame);
            }
            result.putString("stream", details.append('\n').toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    @SuppressWarnings("deprecation")
    private void verifyUpgrade() throws Exception {
        Context context = getTargetContext();
        SharedPreferences expected = context.getSharedPreferences("upgrade_acceptance", 0);
        PackageInfo info = context.getPackageManager().getPackageInfo(
                context.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
        require(info.getLongVersionCode() == expected.getInt("version", -1) + 1L,
                "Replacement APK must increment versionCode");
        require(info.signingInfo != null && info.signingInfo.getApkContentsSigners().length == 1,
                "Replacement APK must have one signing certificate");
        same(expected.getString("certificate", null),
                digest(info.signingInfo.getApkContentsSigners()[0].toByteArray()),
                "Replacement APK certificate changed");

        JSONObject session = readSession(context);
        verifyIdentity(expected, session);
        same(expected.getString("token", null), digest(session.getString("token")),
                "Encrypted session token was not retained");
        same(expected.getString("draft", null), digest(Files.readAllBytes(
                new File(context.getFilesDir(), "annotation-draft.json").toPath())),
                "Saved draft changed during APK replacement");
        SharedPreferences places = context.getSharedPreferences("wxspot_places", 0);
        same(expected.getString("places", null), places.getString("saved_places", null),
                "Saved places changed during APK replacement");
        same(expected.getString("camera", null), places.getString("last_camera", null),
                "Saved camera changed during APK replacement");
        require(places.getBoolean("metric_units", false), "Metric preference was not retained");

        startActivitySync(new Intent(Intent.ACTION_MAIN)
                .setClassName(context.getPackageName(), "app.wxspot.MainActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        waitForIdleSync();
        awaitText("Continue your annotation?");
        screenshot("19-upgraded-draft-resume.png");
        clickText("Continue editing");
        awaitText("Describe & publish · 1 marks");
        screenshot("20-upgraded-draft-editor.png");
        clickText("More");
        awaitText("Use metric units");
        require(hasCheckedSwitch(getUiAutomation().getRootInActiveWindow()),
                "Restored unit preference is not checked in the UI");
        clickText("Saved places · 2");
        awaitText("Home acceptance");
        awaitText("Away acceptance");
        screenshot("21-upgraded-saved-places.png");

        // The retained Android Keystore credential must still resume the same real profile.
        renewProfile(expected, session.getString("resumeKey"));
        verifyIdentity(expected, readSession(context));
        same(expected.getString("draft", null), digest(Files.readAllBytes(
                new File(context.getFilesDir(), "annotation-draft.json").toPath())),
                "Viewing the restored UI modified or removed the saved draft");
    }

    private static JSONObject readSession(Context context) throws Exception {
        String encrypted = context.getSharedPreferences("identity", 0).getString("session", null);
        require(encrypted != null, "Encrypted device profile is missing");
        String[] parts = encrypted.split(":", -1);
        require(parts.length == 2, "Encrypted device profile format changed");
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        SecretKey key = (SecretKey) store.getKey("wxspot.session", null);
        require(key != null, "Original Android Keystore key is missing");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new JSONObject(new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)),
                StandardCharsets.UTF_8));
    }

    private static void verifyIdentity(SharedPreferences expected, JSONObject session)
            throws Exception {
        same(expected.getString("profile", null), digest(session.getString("userId")),
                "Original device profile was not retained");
        same(expected.getString("credential", null), digest(session.getString("resumeKey")),
                "Original resume credential was not retained");
    }

    private static void renewProfile(SharedPreferences expected, String credential) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection) new URL(
                "https://wxspotapi-production.up.railway.app/auth/guest").openConnection();
        try {
            connection.setConnectTimeout(30_000);
            connection.setReadTimeout(30_000);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            byte[] body = new JSONObject().put("resume_key", credential).toString()
                    .getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            require(connection.getResponseCode() == 200, "Retained credential could not renew");
            JSONObject renewed;
            try (InputStream input = connection.getInputStream()) {
                renewed = new JSONObject(new String(readBytes(input), StandardCharsets.UTF_8));
            }
            same(expected.getString("profile", null), digest(renewed.getString("user_id")),
                    "Credential renewal created a different profile");
            same(expected.getString("credential", null), digest(renewed.getString("resume_key")),
                    "Credential renewal replaced the retained credential");
            require(!renewed.getString("access_token").isEmpty(), "Renewal returned no token");
        } finally {
            connection.disconnect();
        }
    }

    private void awaitText(String text) {
        long deadline = SystemClock.uptimeMillis() + 90_000;
        while (SystemClock.uptimeMillis() < deadline) {
            if (findText(text) != null) return;
            SystemClock.sleep(200);
        }
        throw new AssertionError("Restored UI did not show: " + text);
    }

    private AccessibilityNodeInfo findText(String text) {
        return findText(getUiAutomation().getRootInActiveWindow(), text);
    }

    private static AccessibilityNodeInfo findText(AccessibilityNodeInfo node, String text) {
        if (node == null) return null;
        if ((node.getText() != null && text.contentEquals(node.getText()))
                || (node.getContentDescription() != null
                && text.contentEquals(node.getContentDescription()))) return node;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo found = findText(node.getChild(i), text);
            if (found != null) return found;
        }
        return null;
    }

    private void clickText(String text) {
        awaitText(text);
        AccessibilityNodeInfo node = findText(text);
        while (node != null) {
            if (node.isClickable() && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                waitForIdleSync();
                return;
            }
            node = node.getParent();
        }
        throw new AssertionError("Restored UI control was not clickable: " + text);
    }

    private static boolean hasCheckedSwitch(AccessibilityNodeInfo node) {
        if (node == null) return false;
        if (node.isCheckable() && node.isChecked()) return true;
        for (int i = 0; i < node.getChildCount(); i++) {
            if (hasCheckedSwitch(node.getChild(i))) return true;
        }
        return false;
    }

    private void screenshot(String name) throws Exception {
        for (String command : new String[] {"mkdir -p /sdcard/wxspot-acceptance",
                "screencap -p /sdcard/wxspot-acceptance/" + name}) {
            try (InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(
                    getUiAutomation().executeShellCommand(command))) {
                readBytes(input);
            }
        }
    }

    private static byte[] readBytes(InputStream input) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
        return bytes.toByteArray();
    }

    private static String digest(String value) throws Exception {
        return digest(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String digest(byte[] value) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(value);
        char[] hex = "0123456789abcdef".toCharArray();
        StringBuilder result = new StringBuilder(64);
        for (byte item : hash) result.append(hex[(item & 255) >>> 4]).append(hex[item & 15]);
        return result.toString();
    }

    private static void same(String expected, String actual, String message) {
        require(expected != null && expected.equals(actual), message);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
