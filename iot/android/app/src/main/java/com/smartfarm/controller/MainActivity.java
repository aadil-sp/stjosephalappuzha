package com.smartfarm.controller;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/**
 * Smart Farm remote control: live sensors, pump 1 (water) and pump 2 (fertilizer),
 * rain tank alert, today's advice, Farm AI and crop settings. Everything is drawn in
 * code with the platform widgets, so the app has no library dependencies.
 */
public class MainActivity extends Activity {

    // ---------------------------------------------------------------- colours
    static final int BG = 0xFFF2F5F0, CARD = 0xFFFFFFFF, TEXT = 0xFF1B2A1F, MUTED = 0xFF6B7A70,
            LINE = 0xFFE3E8E1, GREEN = 0xFF2E7D32, GREEN_SOFT = 0xFFE8F5E9, WATER = 0xFF1E88E5,
            WATER_SOFT = 0xFFE3F2FD, FERT = 0xFF8E24AA, FERT_SOFT = 0xFFF3E5F5, TANK = 0xFF00897B,
            SUN = 0xFFF57C00, ALERT = 0xFFD32F2F, ALERT_SOFT = 0xFFFFEBEE;

    static final int TAB_HOME = 0, TAB_TODAY = 1, TAB_CROP = 2, TAB_SETTINGS = 3;
    static final String[] TAB_NAMES = {"Home", "Today", "Crop", "Settings"};
    static final String[] TAB_ICONS = {"⌂", "☀", "☘", "⚙"};

    final Api api = new Api();
    final Handler handler = new Handler(Looper.getMainLooper());
    SharedPreferences prefs;

    JSONObject tele, advice, aiStatus, crops;
    String lastError;
    boolean teleBusy, resumed, finding;
    int failures;
    long adviceAt, aiAt, cropsAt, findAt;
    int tab = TAB_HOME;
    double fertMinutes = 1.0;
    boolean settingsFilled;

    FrameLayout content;
    final View[] pages = new View[4];
    final TextView[] tabButtons = new TextView[4];
    TextView headerStatus;

    // home
    LinearLayout tankBanner;
    TextView tankBannerText, soilValue, soilSub, tempValue, tempSub, humValue, humSub, tankValue, tankSub;
    TextView p1State, p1Info, p1Mode, p2State, p2Info, p2Minutes, deviceLine;
    Button p1Toggle, p1Auto, p1Manual, p2Start, p2Stop;
    // today
    TextView wxLine, waterTitle, waterText, fertTitle, fertText, tipsText;
    TextView aiHeadline, aiBody, aiState, askAnswer;
    Button aiRefresh, askButton;
    EditText askInput;
    // crop
    TextView cropCurrent;
    LinearLayout cropList;
    final List<Button> stageButtons = new ArrayList<>();
    EditText dryInput, stopInput, tankAlertInput;
    // settings
    EditText addressInput, keyInput;
    TextView connectResult;
    Button findButton;

    final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            poll();
            handler.postDelayed(this, 3000);
        }
    };

    // ================================================================ lifecycle
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("farm", MODE_PRIVATE);
        api.base = prefs.getString("address", "");
        api.key = prefs.getString("key", "");

        Window w = getWindow();
        w.setStatusBarColor(GREEN);
        w.setNavigationBarColor(CARD);

        LinearLayout root = vbox();
        root.setBackgroundColor(BG);
        root.addView(buildHeader());
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(buildTabBar());
        setContentView(root);

        pages[TAB_HOME] = scroll(buildHome());
        pages[TAB_TODAY] = scroll(buildToday());
        pages[TAB_CROP] = scroll(buildCrop());
        pages[TAB_SETTINGS] = scroll(buildSettings());
        for (View p : pages) {
            p.setVisibility(View.GONE);
            content.addView(p, new FrameLayout.LayoutParams(-1, -1));
        }
        showTab(api.base.isEmpty() ? TAB_SETTINGS : TAB_HOME);
        render();
        if (api.base.isEmpty()) findFarm(false);
    }

    @Override
    protected void onResume() {
        super.onResume();
        resumed = true;
        handler.removeCallbacks(ticker);
        handler.post(ticker);
    }

    @Override
    protected void onPause() {
        super.onPause();
        resumed = false;
        handler.removeCallbacks(ticker);
    }

    // ================================================================ data
    void poll() {
        if (api.base.isEmpty()) return;
        long now = System.currentTimeMillis();
        if (!teleBusy) {
            teleBusy = true;
            api.get("/api/telemetry", (res, err) -> {
                teleBusy = false;
                if (res != null) {
                    tele = res;
                    lastError = null;
                    failures = 0;
                } else {
                    lastError = err;
                    // The Pi's Wi-Fi address can change after a router restart: look for it again
                    if (++failures >= 3 && Api.isLocal(api.base)
                            && System.currentTimeMillis() - findAt > 60_000) findFarm(true);
                }
                render();
            });
        }
        if (now - adviceAt > (tab == TAB_TODAY ? 60_000 : 300_000)) {
            adviceAt = now;
            api.get("/api/advice", (res, err) -> {
                if (res != null) advice = res;
                renderToday();
            });
        }
        boolean aiBusy = aiTask("brief").optString("status").equals("busy")
                || aiTask("ask").optString("status").equals("busy");
        if (now - aiAt > (aiBusy ? 2_500 : tab == TAB_TODAY ? 30_000 : 300_000)) {
            aiAt = now;
            refreshAi();
        }
        if (crops == null && now - cropsAt > 30_000) {
            cropsAt = now;
            api.get("/api/crops", (res, err) -> {
                if (res != null) {
                    crops = res;
                    buildCropList();
                    renderCrop();
                }
            });
        }
    }

    void refreshAi() {
        api.get("/api/ai/status", (res, err) -> {
            if (res != null) aiStatus = res;
            renderToday();
        });
    }

    /** POST, then re-read telemetry so the screen shows the new state straight away. */
    void send(String path, JSONObject body, String done) {
        api.post(path, body, (res, err) -> {
            if (err != null) {
                toast(err);
                return;
            }
            if (done != null) toast(done);
            teleBusy = false;
            poll();
        });
    }

    JSONObject aiTask(String name) {
        JSONObject tasks = aiStatus == null ? null : aiStatus.optJSONObject("tasks");
        JSONObject t = tasks == null ? null : tasks.optJSONObject(name);
        return t == null ? new JSONObject() : t;
    }

    // ================================================================ header + tabs
    View buildHeader() {
        LinearLayout h = vbox();
        h.setBackgroundColor(GREEN);
        h.setPadding(dp(18), dp(14), dp(18), dp(14));
        h.addView(text("Smart Farm", 22, Color.WHITE, true));
        headerStatus = text("Not connected", 13, 0xCCFFFFFF, false);
        headerStatus.setMaxLines(2);
        headerStatus.setEllipsize(android.text.TextUtils.TruncateAt.END);
        h.addView(headerStatus);
        return h;
    }

    View buildTabBar() {
        LinearLayout bar = hbox();
        bar.setBackgroundColor(CARD);
        bar.setElevation(dp(8));
        for (int i = 0; i < 4; i++) {
            final int idx = i;
            TextView t = text(TAB_ICONS[i] + "\n" + TAB_NAMES[i], 12, MUTED, false);
            t.setGravity(Gravity.CENTER);
            t.setPadding(0, dp(8), 0, dp(8));
            t.setOnClickListener(v -> showTab(idx));
            tabButtons[i] = t;
            bar.addView(t, new LinearLayout.LayoutParams(0, -2, 1));
        }
        return bar;
    }

    void showTab(int i) {
        tab = i;
        for (int k = 0; k < 4; k++) {
            pages[k].setVisibility(k == i ? View.VISIBLE : View.GONE);
            tabButtons[k].setTextColor(k == i ? GREEN : MUTED);
            tabButtons[k].setTypeface(null, k == i ? Typeface.BOLD : Typeface.NORMAL);
        }
        hideKeyboard();
        if (i == TAB_TODAY) {
            adviceAt = 0;
            aiAt = 0;
            poll();
        }
    }

    // ================================================================ home
    View buildHome() {
        LinearLayout page = pageBox();

        tankBanner = vbox();
        tankBanner.setBackground(round(ALERT_SOFT, 16, ALERT));
        tankBanner.setPadding(dp(16), dp(14), dp(16), dp(14));
        tankBanner.addView(text("Rain tank is full", 17, ALERT, true));
        tankBannerText = text("", 14, TEXT, false);
        tankBanner.addView(tankBannerText);
        Button released = button("Water released · Reset alert", ALERT, true);
        released.setOnClickListener(v -> confirm("Reset the tank alert?",
                "Do this after you have released water from the rain tank.",
                () -> send("/api/tank/reset", null, "Tank alert reset")));
        tankBanner.addView(released, topMargin(10));
        page.addView(tankBanner, gap());

        LinearLayout row1 = hbox(), row2 = hbox();
        TextView[] soil = tile(row1, "Soil moisture", GREEN);
        TextView[] temp = tile(row1, "Temperature", SUN);
        TextView[] hum = tile(row2, "Humidity", WATER);
        TextView[] tank = tile(row2, "Rain tank", TANK);
        soilValue = soil[0]; soilSub = soil[1];
        tempValue = temp[0]; tempSub = temp[1];
        humValue = hum[0]; humSub = hum[1];
        tankValue = tank[0]; tankSub = tank[1];
        page.addView(row1, gap());
        page.addView(row2, gap());

        // Pump 1 - water
        LinearLayout p1 = card();
        LinearLayout p1Top = hbox();
        p1Top.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout p1Titles = vbox();
        p1Titles.addView(text("Pump 1 · Water", 17, TEXT, true));
        p1Mode = text("", 13, MUTED, false);
        p1Titles.addView(p1Mode);
        p1Top.addView(p1Titles, new LinearLayout.LayoutParams(0, -2, 1));
        p1State = pill("OFF", MUTED);
        p1Top.addView(p1State);
        p1.addView(p1Top);
        LinearLayout modes = hbox();
        p1Auto = button("AUTO", WATER, false);
        p1Manual = button("MANUAL", WATER, false);
        p1Auto.setOnClickListener(v -> setMode("AUTO"));
        p1Manual.setOnClickListener(v -> setMode("MANUAL"));
        modes.addView(p1Auto, weight(0, 4));
        modes.addView(p1Manual, weight(4, 0));
        p1.addView(modes, topMargin(12));
        p1Toggle = button("Turn ON", WATER, true);
        p1Toggle.setOnClickListener(v -> send("/api/pump/toggle", null, null));
        p1.addView(p1Toggle, topMargin(8));
        p1Info = text("", 13, MUTED, false);
        p1.addView(p1Info, topMargin(8));
        page.addView(p1, gap());

        // Pump 2 - fertilizer
        LinearLayout p2 = card();
        LinearLayout p2Top = hbox();
        p2Top.setGravity(Gravity.CENTER_VERTICAL);
        p2Top.addView(text("Pump 2 · Fertilizer", 17, TEXT, true), new LinearLayout.LayoutParams(0, -2, 1));
        p2State = pill("OFF", MUTED);
        p2Top.addView(p2State);
        p2.addView(p2Top);
        LinearLayout stepper = hbox();
        stepper.setGravity(Gravity.CENTER_VERTICAL);
        Button minus = button("−", FERT, false);
        Button plus = button("+", FERT, false);
        p2Minutes = text("", 18, TEXT, true);
        p2Minutes.setGravity(Gravity.CENTER);
        minus.setOnClickListener(v -> stepFert(-0.5));
        plus.setOnClickListener(v -> stepFert(0.5));
        stepper.addView(minus, new LinearLayout.LayoutParams(dp(56), dp(48)));
        stepper.addView(p2Minutes, new LinearLayout.LayoutParams(0, -2, 1));
        stepper.addView(plus, new LinearLayout.LayoutParams(dp(56), dp(48)));
        p2.addView(stepper, topMargin(12));
        LinearLayout p2Buttons = hbox();
        p2Start = button("Start", FERT, true);
        p2Stop = button("Stop", FERT, false);
        p2Start.setOnClickListener(v -> {
            JSONObject b = json("on", true);
            put(b, "minutes", fertMinutes);
            send("/api/fert/set", b, null);
        });
        p2Stop.setOnClickListener(v -> send("/api/fert/set", json("on", false), null));
        p2Buttons.addView(p2Start, weight(0, 4));
        p2Buttons.addView(p2Stop, weight(4, 0));
        p2.addView(p2Buttons, topMargin(8));
        p2Info = text("", 13, MUTED, false);
        p2.addView(p2Info, topMargin(8));
        page.addView(p2, gap());

        deviceLine = text("", 13, MUTED, false);
        deviceLine.setGravity(Gravity.CENTER);
        page.addView(deviceLine, gap());
        return page;
    }

    void setMode(String mode) {
        if (tele != null && mode.equals(tele.optString("pump_mode"))) return;
        send("/api/pump/mode", null, "Pump 1: " + mode);
    }

    void stepFert(double d) {
        double max = tele == null ? 5 : tele.optDouble("fert_manual_max_min", 5);
        fertMinutes = Math.max(0.5, Math.min(max, fertMinutes + d));
        renderHome();
    }

    // ================================================================ today
    View buildToday() {
        LinearLayout page = pageBox();

        LinearLayout plan = card();
        plan.addView(text("Today's plan", 17, TEXT, true));
        wxLine = text("Loading…", 14, MUTED, false);
        plan.addView(wxLine, topMargin(4));
        LinearLayout water = soft(WATER_SOFT);
        waterTitle = text("", 16, WATER, true);
        waterText = text("", 14, TEXT, false);
        water.addView(text("Water (pump 1)", 12, MUTED, false));
        water.addView(waterTitle);
        water.addView(waterText);
        plan.addView(water, topMargin(10));
        LinearLayout fert = soft(FERT_SOFT);
        fertTitle = text("", 16, FERT, true);
        fertText = text("", 14, TEXT, false);
        fert.addView(text("Fertilizer (pump 2)", 12, MUTED, false));
        fert.addView(fertTitle);
        fert.addView(fertText);
        plan.addView(fert, topMargin(8));
        tipsText = text("", 14, TEXT, false);
        plan.addView(tipsText, topMargin(8));
        page.addView(plan, gap());

        LinearLayout ai = card();
        LinearLayout aiTop = hbox();
        aiTop.setGravity(Gravity.CENTER_VERTICAL);
        aiTop.addView(text("✦ Farm AI", 17, GREEN, true), new LinearLayout.LayoutParams(0, -2, 1));
        aiRefresh = button("Refresh", GREEN, false);
        aiRefresh.setOnClickListener(v -> api.post("/api/ai/brief", null, (res, err) -> {
            if (err != null) toast(err);
            if (res != null) aiStatus = res;
            aiAt = System.currentTimeMillis();
            renderToday();
        }));
        aiTop.addView(aiRefresh, new LinearLayout.LayoutParams(-2, dp(42)));
        ai.addView(aiTop);
        aiState = text("", 13, MUTED, false);
        ai.addView(aiState, topMargin(4));
        aiHeadline = text("", 18, TEXT, true);
        ai.addView(aiHeadline, topMargin(6));
        aiBody = text("", 14, TEXT, false);
        aiBody.setLineSpacing(0, 1.15f);
        ai.addView(aiBody, topMargin(4));
        page.addView(ai, gap());

        LinearLayout ask = card();
        ask.addView(text("Ask Farm AI", 17, TEXT, true));
        askInput = input("e.g. Leaves are turning yellow, what should I do?", InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        askInput.setMinLines(2);
        ask.addView(askInput, topMargin(8));
        askButton = button("Ask", GREEN, true);
        askButton.setOnClickListener(v -> {
            String q = askInput.getText().toString().trim();
            if (q.isEmpty()) return;
            hideKeyboard();
            api.post("/api/ai/ask", json("text", q), (res, err) -> {
                if (err != null) toast(err);
                if (res != null) aiStatus = res;
                aiAt = System.currentTimeMillis();
                renderToday();
            });
        });
        ask.addView(askButton, topMargin(8));
        askAnswer = text("", 14, TEXT, false);
        askAnswer.setLineSpacing(0, 1.15f);
        ask.addView(askAnswer, topMargin(8));
        page.addView(ask, gap());
        return page;
    }

    // ================================================================ crop
    View buildCrop() {
        LinearLayout page = pageBox();

        LinearLayout c = card();
        c.addView(text("Crop", 17, TEXT, true));
        cropCurrent = text("", 14, MUTED, false);
        c.addView(cropCurrent, topMargin(2));
        cropList = vbox();
        c.addView(cropList, topMargin(8));
        page.addView(c, gap());

        LinearLayout st = card();
        st.addView(text("Growth stage", 17, TEXT, true));
        String[][] stages = {{"early", "Young plants"}, {"mid", "Flowering / fruiting"}, {"late", "Near harvest"}};
        for (String[] s : stages) {
            Button b = button(s[1], GREEN, false);
            b.setTag(s[0]);
            b.setOnClickListener(v -> send("/api/settings/farm", json("crop_stage", s[0]), "Stage: " + s[1]));
            stageButtons.add(b);
            st.addView(b, topMargin(8));
        }
        page.addView(st, gap());

        LinearLayout cut = card();
        cut.addView(text("Watering limits", 17, TEXT, true));
        cut.addView(text("Pump 1 (AUTO) starts when soil is below the first value and stops at the second.",
                13, MUTED, false), topMargin(2));
        dryInput = input("Start below %", InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        stopInput = input("Stop at %", InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        cut.addView(labelled("Start below (%)", dryInput), topMargin(8));
        cut.addView(labelled("Stop at (%)", stopInput), topMargin(8));
        Button save = button("Save limits", GREEN, true);
        save.setOnClickListener(v -> {
            double dry = num(dryInput), stop = num(stopInput);
            if (Double.isNaN(dry) || Double.isNaN(stop) || dry < 5 || stop > 100 || dry >= stop) {
                toast("Start value must be lower than the stop value (5–100 %)");
                return;
            }
            JSONObject b = json("dry_cutoff", dry);
            put(b, "stop_cutoff", stop);
            hideKeyboard();
            send("/api/settings/cutoffs", b, "Limits saved");
        });
        cut.addView(save, topMargin(10));
        page.addView(cut, gap());

        LinearLayout tk = card();
        tk.addView(text("Rain tank alert", 17, TEXT, true));
        tankAlertInput = input("Alert at %", InputType.TYPE_CLASS_NUMBER);
        tk.addView(labelled("Alert when tank reaches (%)", tankAlertInput), topMargin(8));
        Button saveTank = button("Save", GREEN, true);
        saveTank.setOnClickListener(v -> {
            double pct = num(tankAlertInput);
            if (Double.isNaN(pct) || pct < 50 || pct > 100) {
                toast("Enter a value from 50 to 100");
                return;
            }
            hideKeyboard();
            send("/api/settings/farm", json("tank_alert_pct", pct), "Tank alert saved");
        });
        tk.addView(saveTank, topMargin(10));
        page.addView(tk, gap());
        return page;
    }

    void buildCropList() {
        cropList.removeAllViews();
        if (crops == null) return;
        for (Iterator<String> it = crops.keys(); it.hasNext(); ) {
            String key = it.next();
            JSONObject c = crops.optJSONObject(key);
            if (c == null) continue;
            Button b = button(c.optString("icon") + "  " + c.optString("name"), GREEN, false);
            b.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            b.setTag(key);
            b.setOnClickListener(v -> confirm("Switch to " + c.optString("name") + "?",
                    String.format(Locale.US, "Pump 1 will start below %.0f %% and stop at %.0f %%.",
                            c.optDouble("dry_cutoff"), c.optDouble("stop_cutoff")),
                    () -> {
                        settingsFilled = false;
                        send("/api/crops/select", json("crop_key", key), c.optString("name") + " selected");
                    }));
            cropList.addView(b, topMargin(6));
        }
    }

    // ================================================================ settings
    View buildSettings() {
        LinearLayout page = pageBox();
        LinearLayout c = card();
        c.addView(text("Connect to the farm", 17, TEXT, true));
        c.addView(text("Connect the phone to the same Wi-Fi as the farm controller, then tap Find farm.",
                13, MUTED, false), topMargin(2));
        findButton = button("Find farm on this Wi-Fi", GREEN, true);
        findButton.setOnClickListener(v -> findFarm(false));
        c.addView(findButton, topMargin(10));
        addressInput = input("farm address", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        addressInput.setText(prefs.getString("address", ""));
        keyInput = input("XXXX-XXXX-XXXX", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        keyInput.setText(prefs.getString("key", ""));
        c.addView(labelled("Farm address", addressInput), topMargin(12));
        c.addView(labelled("Access key (only needed outside the farm Wi-Fi)", keyInput), topMargin(8));
        Button connect = button("Save and connect", GREEN, false);
        connect.setOnClickListener(v -> connect());
        c.addView(connect, topMargin(12));
        connectResult = text("", 14, MUTED, false);
        c.addView(connectResult, topMargin(8));
        page.addView(c, gap());

        LinearLayout help = card();
        help.addView(text("Where to find these", 17, TEXT, true));
        help.addView(text(
                "• Find farm fills in the address by itself. If it can't find it, type the address "
                        + "shown on the farm screen under Device → Web app (for example 192.168.1.20).\n\n"
                        + "• On the farm Wi-Fi no access key is needed. To use the app from somewhere "
                        + "else, the controller needs an internet address; then enter the App key "
                        + "shown on the farm screen under Device.\n\n"
                        + "• If the farm's address changes, the app finds it again by itself.",
                14, TEXT, false), topMargin(6));
        page.addView(help, gap());

        TextView ver = text("Smart Farm app 1.1", 12, MUTED, false);
        ver.setGravity(Gravity.CENTER);
        page.addView(ver, gap());
        return page;
    }

    /** Scans the Wi-Fi for the controller; quiet = background re-find after the address stopped answering. */
    void findFarm(boolean quiet) {
        if (finding) return;
        finding = true;
        findAt = System.currentTimeMillis();
        if (!quiet) {
            hideKeyboard();
            findButton.setEnabled(false);
            findButton.setText("Searching this Wi-Fi…");
            connectResult.setTextColor(MUTED);
            connectResult.setText("Looking for the farm controller (up to 30 s)…");
        }
        api.findFarm(prefs.getString("address", ""), addr -> {
            finding = false;
            findButton.setEnabled(true);
            findButton.setText("Find farm on this Wi-Fi");
            if (addr == null) {
                if (!quiet) {
                    connectResult.setTextColor(ALERT);
                    connectResult.setText(Api.localPrefixes().isEmpty()
                            ? "This phone is not on a Wi-Fi network. Turn on Wi-Fi and join the farm's network."
                            : "No farm found on this Wi-Fi. Check the controller is on and on the same "
                            + "network, or type its address below.");
                }
                return;
            }
            if (quiet && addr.equals(api.base)) return;
            addressInput.setText(addr);
            connect();
        });
    }

    void connect() {
        String addr = Api.normalize(addressInput.getText().toString());
        String key = keyInput.getText().toString().trim().toUpperCase(Locale.US);
        if (addr.isEmpty()) {
            connectResult.setTextColor(ALERT);
            connectResult.setText("Enter the farm address.");
            return;
        }
        hideKeyboard();
        addressInput.setText(addr);
        api.base = addr;
        api.key = key;
        connectResult.setTextColor(MUTED);
        connectResult.setText("Connecting…");
        api.get("/api/telemetry", (res, err) -> {
            if (res == null) {
                connectResult.setTextColor(ALERT);
                connectResult.setText(err);
                return;
            }
            prefs.edit().putString("address", addr).putString("key", key).apply();
            tele = res;
            lastError = null;
            crops = null;
            cropsAt = adviceAt = aiAt = 0;
            settingsFilled = false;
            connectResult.setTextColor(GREEN);
            connectResult.setText("Connected to " + addr.replaceFirst("^https?://", "") + " ✓");
            failures = 0;
            render();
            if (tab == TAB_SETTINGS) handler.postDelayed(() -> showTab(TAB_HOME), 700);
        });
    }

    // ================================================================ render
    void render() {
        if (api.base.isEmpty()) {
            headerStatus.setText("Set the farm address in Settings");
        } else if (lastError != null) {
            headerStatus.setText("● Offline · " + lastError);
        } else if (tele != null) {
            headerStatus.setText("● Online · updated " + tele.optString("timestamp"));
        } else {
            headerStatus.setText("Connecting…");
        }
        renderHome();
        renderCrop();
    }

    void renderHome() {
        p2Minutes.setText(fmtMin(fertMinutes));
        if (tele == null) {
            tankBanner.setVisibility(View.GONE);
            return;
        }
        boolean stale = lastError != null;

        JSONObject tank = tele.optJSONObject("tank");
        boolean alert = tank != null && tank.optBoolean("alert");
        tankBanner.setVisibility(alert ? View.VISIBLE : View.GONE);
        if (alert) {
            tankBannerText.setText(String.format(Locale.US,
                    "The tank is at %s. Open the outlet and release some water, then reset the alert.",
                    pct(tank.opt("level"))));
        }

        Object soil = tele.opt("soil_moisture");
        soilValue.setText(pct(soil));
        soilSub.setText(isNum(soil) ? tele.optString("soil_condition") : "No reading");
        tempValue.setText(isNum(tele.opt("temperature_c"))
                ? String.format(Locale.US, "%.1f °C", tele.optDouble("temperature_c")) : "--");
        tempSub.setText(sourceLabel(tele.optString("temperature_source")));
        humValue.setText(pct(tele.opt("humidity")));
        humSub.setText(sourceLabel(tele.optString("humidity_source")));
        if (tank != null) {
            tankValue.setText(pct(tank.opt("level")));
            tankSub.setText(isNum(tank.opt("litres"))
                    ? String.format(Locale.US, "%.0f of %.0f L", tank.optDouble("litres"), tank.optDouble("capacity_l"))
                    : "No reading");
        }

        boolean on = tele.optBoolean("pump_on");
        String mode = tele.optString("pump_mode", "AUTO");
        setPill(p1State, on ? "ON" : "OFF", on ? WATER : MUTED);
        p1Mode.setText(mode.equals("AUTO") ? "AUTO · runs by soil moisture" : "MANUAL · you control it");
        styleToggle(p1Auto, WATER, mode.equals("AUTO"));
        styleToggle(p1Manual, WATER, mode.equals("MANUAL"));
        p1Toggle.setText(on ? "Turn OFF" : mode.equals("AUTO") ? "Turn ON (switches to manual)" : "Turn ON");
        p1Info.setText(String.format(Locale.US, "%s · starts below %.0f %%, stops at %.0f %%",
                tele.optString("crop_name"), tele.optDouble("dry_cutoff"), tele.optDouble("stop_cutoff")));

        boolean fon = tele.optBoolean("fert_pump_on");
        setPill(p2State, fon ? "ON" : "OFF", fon ? FERT : MUTED);
        double max = tele.optDouble("fert_manual_max_min", 5);
        if (fertMinutes > max) fertMinutes = max;
        p2Minutes.setText(fmtMin(fertMinutes));
        Object offIn = tele.opt("fert_off_in");
        p2Info.setText(fon && isNum(offIn)
                ? String.format(Locale.US, "Stops by itself in %s", fmtSecs(((Number) offIn).intValue()))
                : String.format(Locale.US, "Runs for the time above, then stops (max %s).", fmtMin(max)));
        p2Start.setEnabled(!fon);
        p2Start.setAlpha(fon ? 0.5f : 1f);

        boolean ard = tele.optBoolean("arduino_mega_online");
        deviceLine.setText((ard ? "Controller connected" : "Controller board not connected")
                + (stale ? " · last data shown" : ""));
        deviceLine.setTextColor(ard ? MUTED : ALERT);
    }

    void renderToday() {
        if (advice != null) {
            JSONObject wx = advice.optJSONObject("weather");
            String day = advice.optString("day");
            if (wx != null && advice.optBoolean("weather_ok")) {
                wxLine.setText(String.format(Locale.US, "%s · %s · %.0f–%.0f °C · rain %.1f mm (%d %%)\n%s, %s",
                        day, wx.optString("label"), wx.optDouble("min"), wx.optDouble("max"),
                        wx.optDouble("rain_mm"), wx.optInt("rain_chance"),
                        advice.optString("crop_name"), advice.optString("stage_name")));
            } else {
                wxLine.setText(day + " · weather not available yet");
            }
            JSONObject wa = advice.optJSONObject("water");
            JSONObject fe = advice.optJSONObject("fert");
            if (wa != null) {
                waterTitle.setText(wa.optString("title"));
                waterText.setText(wa.optString("text"));
            }
            if (fe != null) {
                fertTitle.setText(fe.optString("title"));
                fertText.setText(fe.optString("text"));
            }
            JSONArray tips = advice.optJSONArray("tips");
            tipsText.setText(bullets(tips));
            tipsText.setVisibility(tips != null && tips.length() > 0 ? View.VISIBLE : View.GONE);
        }

        if (aiStatus == null) {
            aiState.setText("Loading…");
            return;
        }
        boolean configured = aiStatus.optBoolean("configured");
        JSONObject brief = aiTask("brief");
        String bs = brief.optString("status");
        aiRefresh.setEnabled(configured && !bs.equals("busy"));
        if (!configured) {
            aiState.setText("Farm AI is not set up on the controller yet (Gemini key missing).");
            aiHeadline.setText("");
            aiBody.setText("");
        } else {
            aiState.setText(bs.equals("busy") ? "Thinking…"
                    : bs.equals("error") ? "Last try failed: " + brief.optString("error")
                    : brief.isNull("time") ? "" : "Updated " + brief.optString("time"));
            JSONObject r = brief.optJSONObject("result");
            if (r != null) {
                aiHeadline.setText(r.optString("headline"));
                StringBuilder sb = new StringBuilder(r.optString("summary"));
                sb.append("\n\n💧 ").append(r.optString("water"));
                sb.append("\n🧪 ").append(r.optString("fertilizer"));
                JSONArray acts = r.optJSONArray("actions");
                if (acts != null && acts.length() > 0) {
                    sb.append("\n\nTo do");
                    for (int i = 0; i < acts.length(); i++) {
                        JSONObject a = acts.optJSONObject(i);
                        if (a == null) continue;
                        sb.append("\n• ").append(a.optString("title")).append(" (").append(a.optString("when"))
                                .append(") – ").append(a.optString("detail"));
                    }
                }
                JSONArray rem = r.optJSONArray("reminders");
                if (rem != null && rem.length() > 0) {
                    sb.append("\n\nReminders");
                    for (int i = 0; i < rem.length(); i++) {
                        JSONObject a = rem.optJSONObject(i);
                        if (a != null) sb.append("\n• ").append(a.optString("day")).append(": ").append(a.optString("text"));
                    }
                }
                JSONArray warn = r.optJSONArray("warnings");
                if (warn != null && warn.length() > 0) sb.append("\n\n⚠ ").append(join(warn, "\n⚠ "));
                aiBody.setText(sb.toString());
            }
        }

        JSONObject ask = aiTask("ask");
        String as = ask.optString("status");
        askButton.setEnabled(configured && !as.equals("busy"));
        askButton.setText(as.equals("busy") ? "Thinking…" : "Ask");
        JSONObject ar = ask.optJSONObject("result");
        if (as.equals("error")) {
            askAnswer.setText("Couldn't answer: " + ask.optString("error"));
        } else if (ar != null) {
            String q = ask.optString("input");
            askAnswer.setText((q.isEmpty() || q.equals("null") ? "" : "Q: " + q + "\n\n") + ar.optString("answer"));
        }
    }

    void renderCrop() {
        if (tele == null) return;
        String sel = tele.optString("selected_crop");
        cropCurrent.setText("Now: " + tele.optString("crop_icon") + " " + tele.optString("crop_name"));
        for (int i = 0; i < cropList.getChildCount(); i++) {
            View v = cropList.getChildAt(i);
            styleToggle((Button) v, GREEN, sel.equals(v.getTag()));
        }
        JSONObject farm = tele.optJSONObject("farm");
        String stage = farm == null ? "" : farm.optString("crop_stage");
        for (Button b : stageButtons) styleToggle(b, GREEN, stage.equals(b.getTag()));
        if (!settingsFilled) {
            settingsFilled = true;
            dryInput.setText(String.format(Locale.US, "%.0f", tele.optDouble("dry_cutoff")));
            stopInput.setText(String.format(Locale.US, "%.0f", tele.optDouble("stop_cutoff")));
            JSONObject tank = tele.optJSONObject("tank");
            if (tank != null) tankAlertInput.setText(String.format(Locale.US, "%.0f", tank.optDouble("alert_pct")));
        }
    }

    // ================================================================ view helpers
    int dp(float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()));
    }

    LinearLayout vbox() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    LinearLayout hbox() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        return l;
    }

    LinearLayout pageBox() {
        LinearLayout l = vbox();
        l.setPadding(dp(14), dp(4), dp(14), dp(18));
        return l;
    }

    View scroll(View inner) {
        ScrollView s = new ScrollView(this);
        s.setFillViewport(true);
        s.addView(inner);
        return s;
    }

    TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    GradientDrawable round(int fill, float radius, int stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(radius));
        if (stroke != 0) g.setStroke(dp(1), stroke);
        return g;
    }

    LinearLayout card() {
        LinearLayout c = vbox();
        c.setBackground(round(CARD, 16, LINE));
        c.setPadding(dp(16), dp(14), dp(16), dp(16));
        return c;
    }

    LinearLayout soft(int fill) {
        LinearLayout c = vbox();
        c.setBackground(round(fill, 12, 0));
        c.setPadding(dp(12), dp(10), dp(12), dp(10));
        return c;
    }

    /** A sensor tile in a row of two; returns {value, subtitle}. */
    TextView[] tile(LinearLayout row, String title, int color) {
        LinearLayout c = card();
        c.addView(text(title, 13, MUTED, false));
        TextView v = text("--", 26, color, true);
        TextView s = text("", 12, MUTED, false);
        c.addView(v);
        c.addView(s);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -1, 1);
        if (row.getChildCount() == 0) lp.rightMargin = dp(5); else lp.leftMargin = dp(5);
        row.addView(c, lp);
        return new TextView[]{v, s};
    }

    Button button(String label, int color, boolean filled) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        b.setStateListAnimator(null);
        b.setMinHeight(dp(48));
        b.setPadding(dp(14), 0, dp(14), 0);
        styleToggle(b, color, filled);
        return b;
    }

    void styleToggle(Button b, int color, boolean filled) {
        b.setBackground(round(filled ? color : CARD, 12, color));
        b.setTextColor(filled ? Color.WHITE : color);
        b.setTypeface(Typeface.DEFAULT_BOLD);
    }

    TextView pill(String s, int color) {
        TextView t = text(s, 14, Color.WHITE, true);
        t.setPadding(dp(14), dp(5), dp(14), dp(5));
        setPill(t, s, color);
        return t;
    }

    void setPill(TextView t, String s, int color) {
        t.setText(s);
        t.setBackground(round(color, 20, 0));
    }

    EditText input(String hint, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setInputType(type);
        e.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        e.setTextColor(TEXT);
        e.setHintTextColor(0xFF9AA59D);
        e.setBackground(round(0xFFF7F9F6, 10, LINE));
        e.setPadding(dp(12), dp(10), dp(12), dp(10));
        return e;
    }

    View labelled(String label, View field) {
        LinearLayout l = vbox();
        l.addView(text(label, 13, MUTED, false));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = dp(4);
        l.addView(field, lp);
        return l;
    }

    LinearLayout.LayoutParams gap() {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = dp(10);
        return lp;
    }

    LinearLayout.LayoutParams topMargin(int m) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = dp(m);
        return lp;
    }

    LinearLayout.LayoutParams weight(int left, int right) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        lp.leftMargin = dp(left);
        lp.rightMargin = dp(right);
        return lp;
    }

    void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show();
    }

    void confirm(String title, String msg, Runnable yes) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(msg)
                .setPositiveButton("Yes", (d, w) -> yes.run())
                .setNegativeButton("Cancel", null).show();
    }

    void hideKeyboard() {
        View f = getCurrentFocus();
        if (f == null) return;
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        imm.hideSoftInputFromWindow(f.getWindowToken(), 0);
        f.clearFocus();
    }

    // ================================================================ value helpers
    static boolean isNum(Object o) {
        return o instanceof Number;
    }

    static String pct(Object o) {
        return isNum(o) ? String.format(Locale.US, "%.0f %%", ((Number) o).doubleValue()) : "--";
    }

    static String sourceLabel(String src) {
        return "weather".equals(src) ? "from weather station" : "simulator".equals(src) ? "simulator" : "sensor";
    }

    static String fmtMin(double m) {
        int s = (int) Math.round(m * 60);
        return s % 60 == 0 ? (s / 60) + " min" : String.format(Locale.US, "%d min %02d s", s / 60, s % 60);
    }

    static String fmtSecs(int s) {
        return String.format(Locale.US, "%d:%02d", s / 60, s % 60);
    }

    static double num(EditText e) {
        try {
            return Double.parseDouble(e.getText().toString().trim());
        } catch (NumberFormatException ex) {
            return Double.NaN;
        }
    }

    static String bullets(JSONArray a) {
        return a == null || a.length() == 0 ? "" : "• " + join(a, "\n• ");
    }

    static String join(JSONArray a, String sep) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < a.length(); i++) {
            if (i > 0) sb.append(sep);
            sb.append(a.optString(i));
        }
        return sb.toString();
    }

    static JSONObject json(String k, Object v) {
        return put(new JSONObject(), k, v);
    }

    static JSONObject put(JSONObject o, String k, Object v) {
        try {
            o.put(k, v);
        } catch (Exception ignored) {
        }
        return o;
    }
}
