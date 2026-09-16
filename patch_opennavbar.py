import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()


# ============================================================
# IMPORTS
# ============================================================

imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import android.widget.ScrollView",
    "import android.content.pm.PackageManager",
    "import android.graphics.drawable.Drawable",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

anchor = "import android.accessibilityservice.AccessibilityService"

for imp in imports:
    if imp not in code:
        code = code.replace(anchor, anchor + "\n" + imp)


# ============================================================
# WIN X STABLE HIDE / SHOW
# ============================================================

if "WINX_STABLE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    insert = r"""

    // WINX_STABLE_PATCH

    private var isWinXLauncher = false

    private var winXCheckRunnable: Runnable? = null

    private fun getCurrentForegroundPackage(): String {
        return try {
            rootInActiveWindow?.packageName?.toString() ?: ""
        } catch (e: Exception) {
            ""
        }
    }

    private fun checkWinXStateDelayed() {

        winXCheckRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXCheckRunnable = Runnable {

            val currentPackage =
                getCurrentForegroundPackage()

            if (currentPackage == "com.InternityLabs.Launcher.WinX") {

                if (!isWinXLauncher) {

                    isWinXLauncher = true

                    navBarCheckRunnable?.let {
                        handler.removeCallbacks(it)
                    }

                    insetsDebounce?.let {
                        handler.removeCallbacks(it)
                    }

                    autoHideRunnable?.let {
                        handler.removeCallbacks(it)
                    }

                    hideOverlay()
                }

            } else {

                if (isWinXLauncher) {

                    isWinXLauncher = false

                    forceShowAfterWinX()
                }
            }
        }

        handler.postDelayed(
            winXCheckRunnable!!,
            250
        )
    }

    private fun forceShowAfterWinX() {

        val view = overlayView ?: return

        view.animate().cancel()

        autoHideRunnable?.let {
            handler.removeCallbacks(it)
        }

        autoHideRunnable = null

        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        // Recreate the reveal zone so swipe-to-show
        // continues working after leaving Win X.
        showRevealZone()
    }

    // WINX_STABLE_PATCH_END

"""

    code = (
        code[:match.end()]
        + insert
        + code[match.end():]
    )


# ============================================================
# ACCESSIBILITY EVENT
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*"
        r"\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError("onAccessibilityEvent not found")

    patch = """

        // WINX_STABLE_EVENT_PATCH

        checkWinXStateDelayed()

        // WINX_STABLE_EVENT_PATCH_END

"""

    code = (
        code[:match.end()]
        + patch
        + code[match.end():]
    )


# ============================================================
# PROTECT SHOW FUNCTIONS
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\s+" +
        re.escape(name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        print("Warning: function not found:", name)
        return

    start = match.end()

    section = code[start:start + 600]

    if "if (isWinXLauncher) return" not in section:

        code = (
            code[:start]
            + """

        if (isWinXLauncher) return

"""
            + code[start:]
        )


protect_function("showOverlay")
protect_function("showOverlayAnimated")


# ============================================================
# CLOCK + DATE
# ============================================================

if "WINX_CLOCK_DATE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    clock_code = """

    // WINX_CLOCK_DATE_PATCH

    private var winXClockTextView: TextView? = null
    private var winXDateTextView: TextView? = null

    private var winXClockStarted = false

    private val winXClockRunnable =
        object : Runnable {

            override fun run() {

                try {

                    val now = Date()

                    winXClockTextView?.text =
                        SimpleDateFormat(
                            "hh:mm a",
                            Locale.ENGLISH
                        ).format(now)
                            .replace("AM", "ص")
                            .replace("PM", "م")

                    winXDateTextView?.text =
                        SimpleDateFormat(
                            "yyyy/MM/dd",
                            Locale.ENGLISH
                        ).format(now)

                } catch (_: Exception) {
                }

                handler.postDelayed(
                    this,
                    1000
                )
            }
        }

    private fun createWinXClock(
        buttonColor: Int
    ): FrameLayout {

        val box = FrameLayout(this)

        box.gravity = Gravity.CENTER

        val clock = TextView(this)

        clock.gravity = Gravity.CENTER
        clock.isSingleLine = true
        clock.textSize = 13f
        clock.typeface = Typeface.DEFAULT_BOLD
        clock.setTextColor(buttonColor)

        val date = TextView(this)

        date.gravity = Gravity.CENTER
        date.isSingleLine = true
        date.textSize = 9f
        date.setTextColor(buttonColor)

        val layout =
            LinearLayout(this)

        layout.orientation =
            LinearLayout.VERTICAL

        layout.gravity =
            Gravity.CENTER

        layout.addView(
            clock,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                0,
                1f
            )
        )

        layout.addView(
            date,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                0,
                0.75f
            )
        )

        box.addView(
            layout,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
                Gravity.CENTER
            )
        )

        winXClockTextView = clock
        winXDateTextView = date

        if (!winXClockStarted) {

            winXClockStarted = true

            handler.removeCallbacks(
                winXClockRunnable
            )

            handler.post(
                winXClockRunnable
            )
        }

        return box
    }

    // WINX_CLOCK_DATE_PATCH_END

"""

    code = (
        code[:match.end()]
        + clock_code
        + code[match.end():]
    )


# ============================================================
# APP SLOTS
# ============================================================

if "WINX_APP_SLOTS_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    app_code = """

    // WINX_APP_SLOTS_PATCH

    private var winXAppPickerView: View? = null

    private fun createWinXAppSlot(
        slot: Int,
        buttonColor: Int
    ): FrameLayout {

        val frame = FrameLayout(this)

        frame.gravity = Gravity.CENTER

        val icon = ImageView(this)

        icon.scaleType =
            ImageView.ScaleType.CENTER_INSIDE

        icon.setPadding(
            dpToPx(10),
            dpToPx(10),
            dpToPx(10),
            dpToPx(10)
        )

        val packageName =
            prefs.getString(
                "winx_app_$slot",
                null
            )

        if (!packageName.isNullOrEmpty()) {

            try {

                val appInfo =
                    packageManager.getApplicationInfo(
                        packageName,
                        0
                    )

                icon.setImageDrawable(
                    packageManager.getApplicationIcon(
                        appInfo
                    )
                )

            } catch (_: Exception) {

                icon.setImageResource(
                    android.R.drawable.ic_menu_add
                )
            }

        } else {

            icon.setImageResource(
                android.R.drawable.ic_menu_add
            )

            icon.setColorFilter(
                buttonColor
            )
        }

        frame.addView(
            icon,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        frame.setOnClickListener {

            val selected =
                prefs.getString(
                    "winx_app_$slot",
                    null
                )

            if (!selected.isNullOrEmpty()) {

                try {

                    val launchIntent =
                        packageManager.getLaunchIntentForPackage(
                            selected
                        )

                    if (launchIntent != null) {

                        launchIntent.addFlags(
                            Intent.FLAG_ACTIVITY_NEW_TASK
                        )

                        startActivity(launchIntent)
                    }

                } catch (_: Exception) {
                }

            } else {

                showWinXAppPicker(slot)
            }
        }

        frame.setOnLongClickListener {

            showWinXAppPicker(slot)

            true
        }

        return frame
    }


    private fun showWinXAppPicker(
        slot: Int
    ) {

        try {

            winXAppPickerView?.let {
                try {
                    windowManager.removeView(it)
                } catch (_: Exception) {
                }
            }

            val root =
                LinearLayout(this)

            root.orientation =
                LinearLayout.VERTICAL

            root.setBackgroundColor(
                Color.argb(
                    245,
                    25,
                    25,
                    25
                )
            )

            val title =
                TextView(this)

            title.text =
                "اختر تطبيقًا للخانة $slot"

            title.textSize = 17f

            title.typeface =
                Typeface.DEFAULT_BOLD

            title.setTextColor(
                Color.WHITE
            )

            title.gravity =
                Gravity.CENTER

            title.setPadding(
                dpToPx(12),
                dpToPx(12),
                dpToPx(12),
                dpToPx(12)
            )

            root.addView(
                title,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
            )

            val scroll =
                ScrollView(this)

            val list =
                LinearLayout(this)

            list.orientation =
                LinearLayout.VERTICAL

            val apps =
                packageManager.queryIntentActivities(
                    Intent(Intent.ACTION_MAIN).apply {
                        addCategory(
                            Intent.CATEGORY_LAUNCHER
                        )
                    },
                    PackageManager.MATCH_ALL
                )
                    .distinctBy {
                        it.activityInfo.packageName
                    }
                    .sortedBy {
                        it.loadLabel(packageManager)
                            .toString()
                            .lowercase()
                    }

            for (resolveInfo in apps) {

                val packageName =
                    resolveInfo.activityInfo.packageName

                if (packageName == packageName) {

                    val row =
                        LinearLayout(this)

                    row.orientation =
                        LinearLayout.HORIZONTAL

                    row.gravity =
                        Gravity.CENTER_VERTICAL

                    row.setPadding(
                        dpToPx(10),
                        dpToPx(7),
                        dpToPx(10),
                        dpToPx(7)
                    )

                    val appIcon =
                        ImageView(this)

                    appIcon.setImageDrawable(
                        resolveInfo.loadIcon(
                            packageManager
                        )
                    )

                    row.addView(
                        appIcon,
                        LinearLayout.LayoutParams(
                            dpToPx(45),
                            dpToPx(45)
                        )
                    )

                    val name =
                        TextView(this)

                    name.text =
                        resolveInfo.loadLabel(
                            packageManager
                        )

                    name.textSize = 15f

                    name.setTextColor(
                        Color.WHITE
                    )

                    name.setPadding(
                        dpToPx(12),
                        0,
                        dpToPx(12),
                        0
                    )

                    row.addView(
                        name,
                        LinearLayout.LayoutParams(
                            0,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                            1f
                        )
                    )

                    row.setOnClickListener {

                        prefs.edit()
                            .putString(
                                "winx_app_$slot",
                                packageName
                            )
                            .apply()

                        try {
                            windowManager.removeView(root)
                        } catch (_: Exception) {
                        }

                        winXAppPickerView = null

                        updateOverlayLive()
                    }

                    list.addView(
                        row,
                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT
                        )
                    )
                }
            }

            scroll.addView(list)

            root.addView(
                scroll,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0,
                    1f
                )
            )

            val close =
                TextView(this)

            close.text = "إلغاء"
            close.textSize = 15f
            close.gravity = Gravity.CENTER
            close.setTextColor(Color.WHITE)
            close.setPadding(
                0,
                dpToPx(12),
                0,
                dpToPx(12)
            )

            close.setOnClickListener {

                try {
                    windowManager.removeView(root)
                } catch (_: Exception) {
                }

                winXAppPickerView = null
            }

            root.addView(
                close,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
            )

            winXAppPickerView = root

            val params =
                WindowManager.LayoutParams(
                    dpToPx(330),
                    dpToPx(520),
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                    PixelFormat.TRANSLUCENT
                )

            params.gravity =
                Gravity.CENTER

            windowManager.addView(
                root,
                params
            )

        } catch (_: Exception) {
        }
    }

    // WINX_APP_SLOTS_PATCH_END

"""

    code = (
        code[:match.end()]
        + app_code
        + code[match.end():]
    )


# ============================================================
# REPLACE ORIGINAL ORDER
# ============================================================

if "WINX_FINAL_ORDER_PATCH" not in code:

    pattern = re.compile(
        r"val order = if \(shouldSwap\)\s*"
        r"listOf\(recentButton,\s*homeButton,\s*backButton\)\s*"
        r"else\s*"
        r"listOf\(backButton,\s*homeButton,\s*recentButton\)"
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "Original navigation order not found"
        )

    replacement = """

        // WINX_FINAL_ORDER_PATCH

        val app1 =
            createWinXAppSlot(
                1,
                buttonColor
            )

        val app2 =
            createWinXAppSlot(
                2,
                buttonColor
            )

        val app3 =
            createWinXAppSlot(
                3,
                buttonColor
            )

        val app4 =
            createWinXAppSlot(
                4,
                buttonColor
            )

        val clockView =
            createWinXClock(
                buttonColor
            )

        val clockWidth =
            dpToPx(58)

        clockView.layoutParams =
            LinearLayout.LayoutParams(
                clockWidth,
                LinearLayout.LayoutParams.MATCH_PARENT
            )

        val order =
            if (shouldSwap)
                listOf(
                    recentButton,
                    clockView,
                    app4,
                    app3,
                    homeButton,
                    app2,
                    app1,
                    backButton
                )
            else
                listOf(
                    backButton,
                    app1,
                    app2,
                    homeButton,
                    app3,
                    app4,
                    clockView,
                    recentButton
                )

        // WINX_FINAL_ORDER_PATCH_END

"""

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ==============================
