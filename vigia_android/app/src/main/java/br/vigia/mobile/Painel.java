package br.vigia.mobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public final class Painel extends Activity {
    private static final int ESCOLHER_VIDEO = 41;
    private WebView painel;
    private ValueCallback<Uri[]> arquivoPendente;

    @Override public void onCreate(Bundle estado) {
        super.onCreate(estado);
        getWindow().setStatusBarColor(0xff171b23);
        getWindow().setNavigationBarColor(0xff171b23);
        painel = new WebView(this);
        painel.getSettings().setJavaScriptEnabled(true);
        painel.getSettings().setDomStorageEnabled(true);
        painel.getSettings().setAllowFileAccess(false);
        painel.getSettings().setAllowContentAccess(true);
        painel.getSettings().setBlockNetworkLoads(true);
        painel.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                if (r.isForMainFrame() && "vigia:camera".equals(r.getUrl().toString())) {
                    startActivity(new Intent(Painel.this, CameraLocal.class));
                }
                return true;
            }
        });
        painel.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback,
                                                       FileChooserParams params) {
                devolverArquivo(null);
                arquivoPendente = callback;
                Intent abrir = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                abrir.addCategory(Intent.CATEGORY_OPENABLE);
                abrir.setType("video/*");
                try { startActivityForResult(abrir, ESCOLHER_VIDEO); }
                catch (ActivityNotFoundException e) { devolverArquivo(null); }
                return true;
            }
        });
        setContentView(painel);
        painel.loadUrl("file:///android_asset/painel.html");
    }
    private void devolverArquivo(Uri uri) {
        if (arquivoPendente != null) {
            ValueCallback<Uri[]> retorno = arquivoPendente;
            arquivoPendente = null;
            retorno.onReceiveValue(uri == null ? null : new Uri[]{uri});
        }
    }
    @Override protected void onActivityResult(int pedido, int resultado, Intent dados) {
        super.onActivityResult(pedido, resultado, dados);
        if (pedido == ESCOLHER_VIDEO) {
            Uri uri = resultado == RESULT_OK && dados != null ? dados.getData() : null;
            devolverArquivo(uri != null && "content".equals(uri.getScheme()) ? uri : null);
        }
    }
    @Override protected void onPause() {
        painel.evaluateJavascript("window.pausar && window.pausar()", null);
        painel.onPause();
        super.onPause();
    }
    @Override protected void onResume() {
        super.onResume();
        painel.onResume();
    }
    @Override protected void onDestroy() {
        devolverArquivo(null);
        painel.destroy();
        super.onDestroy();
    }
}
