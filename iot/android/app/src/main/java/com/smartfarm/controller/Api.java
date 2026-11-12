package com.smartfarm.controller;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Talks to the farm controller's REST API (the same one the web dashboard uses). */
final class Api {

    interface Callback {
        /** Exactly one of res / error is set. Runs on the main thread. */
        void done(JSONObject res, String error);
    }

    private final ExecutorService pool = Executors.newFixedThreadPool(3);
    private final Handler main = new Handler(Looper.getMainLooper());
    volatile String base = "";
    volatile String key = "";

    /** Accepts "192.168.1.20", "farm.ngrok-free.app", full URLs, with or without a trailing slash. */
    static String normalize(String address) {
        String a = address == null ? "" : address.trim();
        while (a.endsWith("/")) a = a.substring(0, a.length() - 1);
        if (a.isEmpty()) return "";
        if (!a.startsWith("http://") && !a.startsWith("https://")) {
            String host = a.split("[:/]")[0];
            boolean local = host.matches("[0-9.]+") || host.endsWith(".local");
            a = (local ? "http://" : "https://") + a;
            if (local && host.equals(a.substring(7))) a += ":8000";
        }
        return a;
    }

    void get(String path, Callback cb) {
        call("GET", path, null, cb);
    }

    void post(String path, JSONObject body, Callback cb) {
        call("POST", path, body == null ? new JSONObject() : body, cb);
    }

    private void call(String method, String path, JSONObject body, Callback cb) {
        final String b = base, k = key;
        pool.execute(() -> {
            JSONObject res = null;
            String err;
            try {
                if (b.isEmpty()) throw new IOException("No farm address set");
                HttpURLConnection c = (HttpURLConnection) new URL(b + path).openConnection();
                c.setRequestMethod(method);
                c.setConnectTimeout(8000);
                c.setReadTimeout(20000);
                c.setRequestProperty("Accept", "application/json");
                c.setRequestProperty("User-Agent", "SmartFarmApp/1.0");
                c.setRequestProperty("X-Farm-Key", k);
                c.setRequestProperty("ngrok-skip-browser-warning", "1");
                if (body != null) {
                    byte[] out = body.toString().getBytes(StandardCharsets.UTF_8);
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json");
                    try (OutputStream os = c.getOutputStream()) {
                        os.write(out);
                    }
                }
                int code = c.getResponseCode();
                String text = read(code >= 400 ? c.getErrorStream() : c.getInputStream());
                c.disconnect();
                JSONObject json = null;
                try {
                    json = new JSONObject(text);
                } catch (Exception ignored) {
                }
                if (code == 401) {
                    err = "Wrong access key. Check it on the farm screen: Device → App key.";
                } else if (code >= 400) {
                    String msg = json != null ? json.optString("message", "") : "";
                    err = msg.isEmpty() ? "The farm replied with error " + code : msg;
                } else if (json == null) {
                    err = "Unexpected reply. Is the address right?";
                } else {
                    res = json;
                    err = null;
                }
            } catch (UnknownHostException e) {
                err = "Can't find the farm. Check the address and your internet.";
            } catch (SocketTimeoutException e) {
                err = "The farm is not answering (timed out).";
            } catch (IOException e) {
                String m = e.getMessage();
                err = "Can't reach the farm" + (m == null ? "." : ": " + m);
            }
            final JSONObject r = res;
            final String e2 = err;
            main.post(() -> cb.done(r, e2));
        });
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream is = in) {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int n;
            while ((n = is.read(chunk)) > 0) buf.write(chunk, 0, n);
            return new String(buf.toByteArray(), StandardCharsets.UTF_8);
        }
    }
}
