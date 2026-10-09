package app.wxspot;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Verifies the encrypted guest session and game shell survive a beta APK update. */
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
            result.putString("stream", "\nPASS: retained encrypted guest identity and game shell.\nOK (1 test)\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            // Do not include credentials, encrypted session data, or HTTP response bodies.
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
                "Encrypted session token changed during APK replacement");

        startActivitySync(new Intent(Intent.ACTION_MAIN)
                .setClassName(context.getPackageName(), "app.wxspot.MainActivity")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        waitForIdleSync();
        awaitText("WXspot");
        awaitText("Home");
        verifyIdentity(expected, readSession(context));
        same(expected.getString("token", null), digest(readSession(context).getString("token")),
                "Launching Sounding Hunt changed the encrypted session token");
    }

    private static JSONObject readSession(Context context) throws Exception {
        String encrypted = context.getSharedPreferences("identity", 0).getString("session", null);
        require(encrypted != null, "Encrypted guest session is missing");
        String[] parts = encrypted.split(":", -1);
        require(parts.length == 2, "Encrypted guest session format changed");
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        SecretKey key = (SecretKey) store.getKey("wxspot.session", null);
        require(key != null, "Original Android Keystore key is missing");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new JSONObject(new String(
                cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8));
    }

    private static void verifyIdentity(SharedPreferences expected, JSONObject session)
            throws Exception {
        same(expected.getString("profile", null), digest(session.getString("userId")),
                "Original guest profile was not retained");
        same(expected.getString("credential", null), digest(session.getString("resumeKey")),
                "Original resume credential was not retained");
    }

    private void awaitText(String text) {
        long deadline = SystemClock.uptimeMillis() + 90_000;
        while (SystemClock.uptimeMillis() < deadline) {
            if (findText(getUiAutomation().getRootInActiveWindow(), text)) return;
            SystemClock.sleep(200);
        }
        throw new AssertionError("Sounding Hunt did not show the expected game UI");
    }

    private static boolean findText(AccessibilityNodeInfo node, String text) {
        if (node == null) return false;
        if ((node.getText() != null && text.contentEquals(node.getText()))
                || (node.getContentDescription() != null
                && text.contentEquals(node.getContentDescription()))) return true;
        for (int i = 0; i < node.getChildCount(); i++) {
            if (findText(node.getChild(i), text)) return true;
        }
        return false;
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
