package br.vigia.mobile;

import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Keeps the password encryption key outside the app's preferences. */
final class CameraLogin {
    private static final String ALIAS = "vigia.camera.login";
    private final SharedPreferences prefs;

    CameraLogin(SharedPreferences prefs) { this.prefs = prefs; }

    private SecretKey key(boolean create) throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        SecretKey key = (SecretKey) store.getKey(ALIAS, null);
        if (key != null || !create) return key;
        KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    String[] load() throws GeneralSecurityException, IOException {
        if (!prefs.contains("secret")) return null;
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(false),
            new GCMParameterSpec(128, Base64.getDecoder().decode(prefs.getString("iv", ""))));
        byte[] clear = cipher.doFinal(Base64.getDecoder().decode(prefs.getString("secret", "")));
        return new String[]{prefs.getString("address", ""), prefs.getString("user", ""),
            new String(clear, StandardCharsets.UTF_8)};
    }

    void save(String address, String user, String password) throws GeneralSecurityException, IOException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key(true));
        String secret = Base64.getEncoder().encodeToString(cipher.doFinal(password.getBytes(StandardCharsets.UTF_8)));
        prefs.edit().putString("address", address).putString("user", user)
            .putString("iv", Base64.getEncoder().encodeToString(cipher.getIV()))
            .putString("secret", secret).apply();
    }

    void forget() { prefs.edit().clear().apply(); }
}
