package app.wxspot.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable data class Session(val token: String, val userId: String, val displayName: String)

/** Tokens are encrypted with a device-bound Android Keystore key; no passwords are retained. */
interface SessionStore {
    val current: Session?

    fun save(value: Session?)
}

class SessionVault(context: Context, private val json: Json) : SessionStore {
    private val preferences = context.getSharedPreferences("identity", Context.MODE_PRIVATE)
    private val keyAlias = "wxspot.session"
    @Volatile
    override var current: Session? = read()
        private set

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(keyAlias, null) as? SecretKey)?.let {
            return it
        }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply {
                init(
                    KeyGenParameterSpec.Builder(
                            keyAlias,
                            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                        )
                        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .build()
                )
            }
            .generateKey()
    }

    private fun read(): Session? =
        runCatching {
                val value = preferences.getString("session", null) ?: return@runCatching null
                val parts = value.split(":")
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(
                    Cipher.DECRYPT_MODE,
                    key(),
                    GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)),
                )
                json.decodeFromString<Session>(
                    cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)).decodeToString()
                )
            }
            .getOrNull()

    override fun save(value: Session?) {
        current = value
        if (value == null) {
            preferences.edit().remove("session").apply()
            return
        }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
        val data =
            Base64.encodeToString(
                cipher.doFinal(json.encodeToString(value).encodeToByteArray()),
                Base64.NO_WRAP,
            )
        preferences.edit().putString("session", "$iv:$data").apply()
    }
}
