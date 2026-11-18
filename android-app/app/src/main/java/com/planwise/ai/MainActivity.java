package com.planwise.ai;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.ConsoleMessage;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.window.OnBackInvokedDispatcher;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;
import java.util.Locale;
import java.util.concurrent.Executor;

/**
 * PlanWise AI - Android app.
 *
 * Opens the deployed PlanWise AI website in a full-screen WebView and adds
 * what a website alone cannot do well inside an app: a splash while the free
 * server wakes up, an offline screen with retry, location permission & native
 * location bridging for "use my current location", a sensible back button, and
 * opening map / website links in the right external app.
 */
public class MainActivity extends Activity {

    private static final String TAG = "PlanWiseAI";
    private static final int LOCATION_REQUEST = 1001;
    private static final long SLOW_LOAD_HINT_MS = 6000;

    private WebView webView;
    private ProgressBar progressBar;
    private View splash;
    private View errorView;
    private TextView splashMessage;

    private boolean firstPageLoaded = false;
    private boolean mainFrameFailed = false;
    private long lastBackPress = 0;

    // Location management
    private LocationManager locationManager;
    private LocationListener activeLocationListener;

    // Pending website request for the user's location while Android asks for permission
    private String pendingGeoOrigin;
    private GeolocationPermissions.Callback pendingGeoCallback;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Executor mainExecutor = handler::post;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);

        webView = findViewById(R.id.webview);
        progressBar = findViewById(R.id.progress);
        splash = findViewById(R.id.splash);
        errorView = findViewById(R.id.error_view);
        splashMessage = findViewById(R.id.splash_message);

        findViewById(R.id.retry_button).setOnClickListener(v -> reload());
        applySystemBarInsets();

        configureWebView();
        registerBackHandler();

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
            showContent();
        } else {
            loadSite();
        }
    }

    /**
     * Android 15+ draws apps edge-to-edge: keep the site clear of the status
     * bar, navigation bar, camera cutout and the on-screen keyboard.
     */
    private void applySystemBarInsets() {
        if (Build.VERSION.SDK_INT < 30) {
            return; // older versions already lay the app out between the bars
        }
        View root = findViewById(R.id.root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsets.CONSUMED;
        });
        root.requestApplyInsets();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);          // the site remembers location / travellers
        settings.setDatabaseEnabled(true);
        settings.setGeolocationEnabled(true);
        try {
            settings.setGeolocationDatabasePath(getFilesDir().getPath());
        } catch (Throwable ignored) {}
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " PlanWiseAndroid/" + BuildConfig.VERSION_NAME);

        webView.addJavascriptInterface(new WebAppInterface(), "AndroidLocationBridge");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleLink(request.getUrl());
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                mainFrameFailed = false;
                injectGeolocationBridge();
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (!mainFrameFailed) {
                    firstPageLoaded = true;
                    showContent();
                    injectGeolocationBridge();
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                // Only a failed page load means "offline"; a failed image or API call does not
                if (request.isForMainFrame()) {
                    mainFrameFailed = true;
                    showError();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress < 100 && firstPageLoaded ? View.VISIBLE : View.GONE);
                if (newProgress > 20) {
                    injectGeolocationBridge();
                }
            }

            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                if (hasLocationPermission()) {
                    callback.invoke(origin, true, true);
                    requestFreshLocation();
                } else {
                    pendingGeoOrigin = origin;
                    pendingGeoCallback = callback;
                    requestLocationPermissionIfNeeded();
                }
            }

            @Override
            public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
                Log.d("PlanWiseWeb", consoleMessage.message() + " -- Line "
                        + consoleMessage.lineNumber() + " of " + consoleMessage.sourceId());
                return true;
            }
        });
    }

    /** Links to the site stay in the app; everything else opens in its own app. */
    private boolean handleLink(Uri uri) {
        Uri site = Uri.parse(BuildConfig.SITE_URL);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme();
        boolean sameSite = ("https".equals(scheme) || "http".equals(scheme))
                && site.getHost() != null && site.getHost().equalsIgnoreCase(uri.getHost());
        if (sameSite) {
            return false;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, R.string.no_app_for_link, Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    private void loadSite() {
        firstPageLoaded = false;
        splash.setVisibility(View.VISIBLE);
        errorView.setVisibility(View.GONE);
        splashMessage.setText(R.string.loading);
        // The free hosting sleeps when idle; explain the wait if it is slow
        handler.postDelayed(() -> {
            if (!firstPageLoaded && splash.getVisibility() == View.VISIBLE) {
                splashMessage.setText(R.string.loading_slow);
            }
        }, SLOW_LOAD_HINT_MS);
        webView.loadUrl(BuildConfig.SITE_URL);
    }

    private void reload() {
        if (firstPageLoaded && webView.getUrl() != null) {
            errorView.setVisibility(View.GONE);
            webView.reload();
        } else {
            loadSite();
        }
    }

    private void showContent() {
        splash.setVisibility(View.GONE);
        errorView.setVisibility(View.GONE);
    }

    private void showError() {
        splash.setVisibility(View.GONE);
        progressBar.setVisibility(View.GONE);
        errorView.setVisibility(View.VISIBLE);
    }

    // ── Location & Native Bridge ──────────────────────────────────────

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void requestLocationPermissionIfNeeded() {
        if (!hasLocationPermission()) {
            requestPermissions(new String[]{
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
            }, LOCATION_REQUEST);
        }
    }

    @SuppressLint("MissingPermission")
    private Location getBestLastKnownLocation() {
        if (!hasLocationPermission() || locationManager == null) {
            return null;
        }
        Location bestLocation = null;
        long bestTime = 0;
        float bestAccuracy = Float.MAX_VALUE;

        // On Android 12+, check fused provider first
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            try {
                Location fused = locationManager.getLastKnownLocation(LocationManager.FUSED_PROVIDER);
                if (fused != null) {
                    bestLocation = fused;
                    bestTime = fused.getTime();
                    bestAccuracy = fused.hasAccuracy() ? fused.getAccuracy() : Float.MAX_VALUE;
                }
            } catch (Throwable ignored) {}
        }

        List<String> providers = locationManager.getProviders(true);
        if (providers != null) {
            for (String provider : providers) {
                try {
                    Location loc = locationManager.getLastKnownLocation(provider);
                    if (loc == null) continue;

                    long time = loc.getTime();
                    float accuracy = loc.hasAccuracy() ? loc.getAccuracy() : Float.MAX_VALUE;

                    boolean isSignificantlyNewer = (time - bestTime) > 600000L; // 10 minutes
                    boolean isNewer = time > bestTime;
                    boolean isMoreAccurate = accuracy < bestAccuracy;

                    if (bestLocation == null || isSignificantlyNewer || (isNewer && isMoreAccurate)) {
                        bestLocation = loc;
                        bestTime = time;
                        bestAccuracy = accuracy;
                    }
                } catch (Throwable ignored) {}
            }
        }
        return bestLocation;
    }

    @SuppressLint("MissingPermission")
    private void requestFreshLocation() {
        if (!hasLocationPermission() || locationManager == null) {
            return;
        }

        // 1. Immediately send cached location if available
        Location cached = getBestLastKnownLocation();
        if (cached != null) {
            pushLocationToWeb(cached);
        }

        stopLocationUpdates();

        // 2. Modern Android 11+ (API 30+): getCurrentLocation
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                    locationManager.getCurrentLocation(
                            LocationManager.NETWORK_PROVIDER,
                            null,
                            mainExecutor,
                            this::pushLocationToWeb
                    );
                }
                if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                    locationManager.getCurrentLocation(
                            LocationManager.GPS_PROVIDER,
                            null,
                            mainExecutor,
                            this::pushLocationToWeb
                    );
                }
                return;
            } catch (Throwable e) {
                Log.w(TAG, "getCurrentLocation failed, falling back to listener", e);
            }
        }

        // Fallback for API < 30 or if getCurrentLocation fails
        activeLocationListener = new LocationListener() {
            @Override
            public void onLocationChanged(Location location) {
                if (location != null) {
                    pushLocationToWeb(location);
                    stopLocationUpdates();
                }
            }
            @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
            @Override public void onProviderEnabled(String provider) {}
            @Override public void onProviderDisabled(String provider) {}
        };

        boolean requested = false;
        try {
            if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(
                        LocationManager.NETWORK_PROVIDER, 1000L, 1.0f, activeLocationListener, Looper.getMainLooper());
                requested = true;
            }
        } catch (Throwable ignored) {}

        try {
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(
                        LocationManager.GPS_PROVIDER, 1000L, 1.0f, activeLocationListener, Looper.getMainLooper());
                requested = true;
            }
        } catch (Throwable ignored) {}

        if (requested) {
            handler.postDelayed(this::stopLocationUpdates, 20000L);
        }
    }

    private void stopLocationUpdates() {
        if (activeLocationListener != null && locationManager != null) {
            try {
                locationManager.removeUpdates(activeLocationListener);
            } catch (Throwable ignored) {}
            activeLocationListener = null;
        }
    }

    private void pushLocationToWeb(Location loc) {
        if (loc == null || webView == null) return;
        handler.post(() -> {
            String script = String.format(Locale.US,
                    "(function(){" +
                            "  if (typeof window.onNativeLocationReceived === 'function') {" +
                            "    window.onNativeLocationReceived(%.7f, %.7f, %.1f);" +
                            "  } else if (typeof detectCurrentLocation === 'function') {" +
                            "    detectCurrentLocation({ adopt: true });" +
                            "  }" +
                            "})()", loc.getLatitude(), loc.getLongitude(), loc.hasAccuracy() ? loc.getAccuracy() : 25.0f);
            webView.evaluateJavascript(script, null);
        });
    }

    private void injectGeolocationBridge() {
        if (webView == null) return;
        String script = "(function(){\n" +
                "  if (window.__planwise_geo_patched) return;\n" +
                "  window.__planwise_geo_patched = true;\n" +
                "  if (!window.AndroidLocationBridge) return;\n" +
                "  var orig = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);\n" +
                "  navigator.geolocation.getCurrentPosition = function(success, error, options) {\n" +
                "    try {\n" +
                "      var raw = window.AndroidLocationBridge.getDeviceLocation();\n" +
                "      if (raw) {\n" +
                "        var p = JSON.parse(raw);\n" +
                "        if (p && typeof p.lat === 'number' && typeof p.lon === 'number') {\n" +
                "          success({\n" +
                "            coords: {\n" +
                "              latitude: p.lat,\n" +
                "              longitude: p.lon,\n" +
                "              accuracy: p.accuracy || 25,\n" +
                "              altitude: null,\n" +
                "              altitudeAccuracy: null,\n" +
                "              heading: null,\n" +
                "              speed: null\n" +
                "            },\n" +
                "            timestamp: p.time || Date.now()\n" +
                "          });\n" +
                "          return;\n" +
                "        }\n" +
                "      }\n" +
                "    } catch(e) { console.warn('Bridge location parse error', e); }\n" +
                "    window.AndroidLocationBridge.requestDeviceLocation();\n" +
                "    orig(success, error, options);\n" +
                "  };\n" +
                "})();";
        webView.evaluateJavascript(script, null);
    }

    public class WebAppInterface {
        @JavascriptInterface
        public String getDeviceLocation() {
            if (!hasLocationPermission()) {
                handler.post(MainActivity.this::requestLocationPermissionIfNeeded);
                return null;
            }
            Location loc = getBestLastKnownLocation();
            if (loc != null) {
                return String.format(Locale.US,
                        "{\"lat\":%.7f,\"lon\":%.7f,\"accuracy\":%.1f,\"time\":%d}",
                        loc.getLatitude(), loc.getLongitude(),
                        loc.hasAccuracy() ? loc.getAccuracy() : 25.0f,
                        loc.getTime());
            }
            handler.post(MainActivity.this::requestFreshLocation);
            return null;
        }

        @JavascriptInterface
        public void requestDeviceLocation() {
            handler.post(() -> {
                if (hasLocationPermission()) {
                    requestFreshLocation();
                } else {
                    requestLocationPermissionIfNeeded();
                }
            });
        }

        @JavascriptInterface
        public boolean hasPermission() {
            return hasLocationPermission();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != LOCATION_REQUEST) {
            return;
        }
        boolean granted = hasLocationPermission();
        if (pendingGeoCallback != null) {
            pendingGeoCallback.invoke(pendingGeoOrigin, granted, true);
            pendingGeoCallback = null;
            pendingGeoOrigin = null;
        }
        if (granted) {
            requestFreshLocation();
            // Automatically invoke detectCurrentLocation in the web page now that permission is active
            handler.postDelayed(() -> {
                if (webView != null) {
                    webView.evaluateJavascript(
                            "(function(){ if (typeof detectCurrentLocation === 'function') { detectCurrentLocation({ adopt: true }); } })()",
                            null);
                }
            }, 600);
        } else {
            Toast.makeText(this, R.string.location_denied, Toast.LENGTH_LONG).show();
        }
    }

    // ── Back button ─────────────────────────────────────────────────

    private void registerBackHandler() {
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        // Android 12 and older; newer versions use the callback registered above
        handleBack();
    }

    /**
     * The site is a single page with two views. Back from the planner goes to
     * Explore (like the site's own button); then normal history; then a
     * second press exits.
     */
    private void handleBack() {
        if (errorView.getVisibility() == View.VISIBLE || !firstPageLoaded) {
            exitWithConfirm();
            return;
        }
        String script = "(function(){var p=document.getElementById('view-planner');"
                + "if(p&&getComputedStyle(p).display!=='none'){"
                + "var b=document.getElementById('btn-back-explore');if(b){b.click();return 'handled';}}"
                + "return 'no';})()";
        webView.evaluateJavascript(script, result -> {
            if (result != null && result.contains("handled")) {
                return;
            }
            if (webView.canGoBack()) {
                webView.goBack();
            } else {
                exitWithConfirm();
            }
        });
    }

    private void exitWithConfirm() {
        long now = System.currentTimeMillis();
        if (now - lastBackPress < 2000) {
            finish();
        } else {
            lastBackPress = now;
            Toast.makeText(this, R.string.press_back_again, Toast.LENGTH_SHORT).show();
        }
    }

    // ── Lifecycle ───────────────────────────────────────────────────

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    protected void onPause() {
        stopLocationUpdates();
        webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        stopLocationUpdates();
        handler.removeCallbacksAndMessages(null);
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        super.onDestroy();
    }
}
