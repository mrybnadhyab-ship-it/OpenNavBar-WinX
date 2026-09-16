import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


# ============================================================
# 1. Add required imports
# ============================================================

imports = [
    "import android.app.AlertDialog",
    "import android.content.pm.PackageManager",
    "import android.graphics.Typeface",
    "import android.graphics.drawable.GradientDrawable",
    "import android.widget.TextView",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

for imp in imports:
    if imp not in code:
        code = code.replace(
            "import android.accessibilityservice.AccessibilityService",
            "import android.accessibilityservice.AccessibilityService\n" + imp
        )


# ============================================================
# 2. Add WinX state + stable foreground check
# ============================================================

if "WINX_STABLE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    insert = """

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

            val currentPackage = getCurrentForegroundPackage()

            if (currentPackage == "com.InternityLabs.Launcher.WinX") {

                // We are really inside Win X
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

                // Only restore if Win X was previously active.
                if (isWinXLauncher) {

                    isWinXLauncher = false

                    forceShowAfterWinX()
                }
            }
        }

        handler.postDelayed(winXCheckRunnable!!, 250)
    }

    private fun forceShowAfterWinX() {

        val view = overlayView ?: return

        // Cancel any running animation
        view.animate().cancel()

        // Cancel automatic hide
        autoHideRunnable?.let {
            handler.removeCallbacks(it)
        }

        autoHideRunnable = null

        // Restore overlay immediately
        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        disableRevealZoneTouch()
    }

    // WINX_STABLE_PATCH_END

"""

    code = code[:match.end()] + insert + code[match.end():]


# ============================================================
# 3. Patch AccessibilityEvent
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "onAccessibilityEvent(AccessibilityEvent?) not found"
        )

    patch = """

        // WINX_STABLE_EVENT_PATCH

        checkWinXStateDelayed()

        // WINX_STABLE_EVENT_PATCH_END

"""

    code = code[:match.end()] + patch + code[match.end():]


# ============================================================
# 4. Protect normal show functions
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\s+" + re.escape(name) +
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
# 5. Add WinX apps + digital clock system
# ============================================================

if "WINX_APPS_CLOCK_PATCH" not in code:

    marker = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not marker:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    extra = """

    // WINX_APPS_CLOCK_PATCH

    private var winXClockTextView: TextView? = null

    private var winXClockStarted = false

    private val winXClockRunnable = object : Runnable {
        override fun run() {

            try {
                winXClockTextView?.text =
                    SimpleDateFormat(
                        "HH:mm",
                        Locale.getDefault()
                    ).format(Date())
            } catch (_: Exception) {
            }

            handler.postDelayed(this, 1000)
        }
    }


    private fun startWinXClock() {

        if (!winXClockStarted) {

            winXClockStarted = true

            handler.removeCallbacks(winXClockRunnable)

            handler.post(winXClockRunnable)
        }
    }


    private fun getWinXAppPackage(slot: Int): String {

        return prefs.getString(
            "winx_app_$slot",
            ""
        ) ?: ""
    }


    private fun saveWinXAppPackage(
        slot: Int,
        packageName: String
    ) {

        prefs.edit()
            .putString(
                "winx_app_$slot",
                packageName
            )
            .apply()
    }


    private fun getWinXAppShape(slot: Int): String {

        return prefs.getString(
            "winx_app_shape_$slot",
            "rounded"
        ) ?: "rounded"
    }


    private fun cycleWinXAppShape(slot: Int) {

        val current = getWinXAppShape(slot)

        val next = when (current) {

            "circle" -> "rounded"

            "rounded" -> "square"

            "square" -> "sharp"

            else -> "circle"
        }

        prefs.edit()
            .putString(
                "winx_app_shape_$slot",
                next
            )
            .apply()

        updateOverlayLive()
    }


    private fun createWinXAppButton(
        slot: Int,
        hitboxSize: Int,
        buttonColor: Int
    ): FrameLayout {

        val frame = FrameLayout(this)

        frame.isClickable = true
        frame.isFocusable = true

        val icon = ImageView(this)

        val size = dpToPx(36)

        val iconParams = FrameLayout.LayoutParams(
            size,
            size
        )

        iconParams.gravity = Gravity.CENTER

        icon.layoutParams = iconParams

        val packageName = getWinXAppPackage(slot)

        if (packageName.isNotEmpty()) {

            try {

                val appIcon =
                    packageManager.getApplicationIcon(
                        packageName
                    )

                icon.setImageDrawable(appIcon)

            } catch (_: Exception) {

                icon.setImageResource(
                    android.R.drawable.sym_def_app_icon
                )
            }

        } else {

            icon.setImageResource(
                android.R.drawable.ic_input_add
            )

            icon.alpha = 0.55f
        }


        val shape = getWinXAppShape(slot)

        val drawable = GradientDrawable()

        when (shape) {

            "circle" -> {

                drawable.shape =
                    GradientDrawable.OVAL
            }

            "square" -> {

                drawable.shape =
                    GradientDrawable.RECTANGLE

                drawable.cornerRadius =
                    dpToPx(6).toFloat()
            }

            "sharp" -> {

                drawable.shape =
                    GradientDrawable.RECTANGLE

                drawable.cornerRadius = 0f
            }

            else -> {

                drawable.shape =
                    GradientDrawable.RECTANGLE

                drawable.cornerRadius =
                    dpToPx(12).toFloat()
            }
        }

        drawable.setColor(
            Color.TRANSPARENT
        )

        drawable.setStroke(
            dpToPx(1),
            buttonColor
        )

        icon.background = drawable
        icon.clipToOutline = true

        frame.addView(icon)


        frame.setOnClickListener {

            val selectedPackage =
                getWinXAppPackage(slot)

            if (selectedPackage.isEmpty()) {

                showWinXAppPicker(slot)

            } else {

                try {

                    val intent =
                        packageManager.getLaunchIntentForPackage(
                            selectedPackage
                        )

                    if (intent != null) {

                        intent.addFlags(
                            Intent.FLAG_ACTIVITY_NEW_TASK
                        )

                        startActivity(intent)
                    }

                } catch (_: Exception) {
                }
            }
        }


        frame.setOnLongClickListener {

            val selectedPackage =
                getWinXAppPackage(slot)

            if (selectedPackage.isEmpty()) {

                showWinXAppPicker(slot)

            } else {

                cycleWinXAppShape(slot)
            }

            true
        }


        return frame
    }


    private fun showWinXAppPicker(slot: Int) {

        try {

            val apps =
                packageManager
                    .getInstalledApplications(
                        PackageManager.GET_META_DATA
                    )
                    .filter {

                        it.packageName != packageName &&
                        packageManager
                            .getLaunchIntentForPackage(
                                it.packageName
                            ) != null
                    }
                    .sortedBy {

                        packageManager
                            .getApplicationLabel(it)
                            .toString()
                            .lowercase(
                                Locale.getDefault()
                            )
                    }


            if (apps.isEmpty()) return


            val labels =
                apps.map {

                    packageManager
                        .getApplicationLabel(it)
                        .toString()

                }.toTypedArray()


            val dialog =
                AlertDialog.Builder(this)
                    .setTitle(
                        "اختر تطبيقًا"
                    )
                    .setItems(labels) { _, which ->

                        if (
                            which >= 0 &&
                            which < apps.size
                        ) {

                            saveWinXAppPackage(
                                slot,
                                apps[which].packageName
                            )

                            updateOverlayLive()
                        }
                    }
                    .setNegativeButton(
                        "إلغاء",
                        null
                    )
                    .create()


            dialog.window?.setType(
                WindowManager.LayoutParams
                    .TYPE_ACCESSIBILITY_OVERLAY
            )

            dialog.show()

        } catch (_: Exception) {
        }
    }


    private fun createWinXClockView(
        buttonColor: Int
    ): TextView {

        val textView = TextView(this)

        textView.gravity =
            Gravity.CENTER

        textView.text =
            SimpleDateFormat(
                "HH:mm",
                Locale.getDefault()
            ).format(Date())

        textView.setTextColor(
            buttonColor
        )

        textView.textSize = 14f

        textView.typeface =
            Typeface.DEFAULT_BOLD

        textView.isSingleLine = true

        textView.setPadding(
            dpToPx(4),
            0,
            dpToPx(4),
            0
        )

        winXClockTextView =
            textView

        startWinXClock()

        return textView
    }


    private fun addWinXSpecialViews(
        container: LinearLayout,
        shouldSwap: Boolean,
        hitboxSize: Int,
        separation: Int,
        buttonColor: Int,
        isVerticalBar: Boolean
    ) {

        val app1 =
            createWinXAppButton(
                1,
                hitboxSize,
                buttonColor
            )

        val app2 =
            createWinXAppButton(
                2,
                hitboxSize,
                buttonColor
            )

        val app3 =
            createWinXAppButton(
                3,
                hitboxSize,
                buttonColor
            )

        val app4 =
            createWinXAppButton(
                4,
                hitboxSize,
                buttonColor
            )

        val clock =
            createWinXClockView(
                buttonColor
            )


        val back =
            container.findViewById<FrameLayout>(
                R.id.backButton
            )

        val home =
            container.findViewById<FrameLayout>(
                R.id.homeButton
            )

        val recent =
            container.findViewById<FrameLayout>(
                R.id.recentButton
            )


        val views: List<View> =

            if (!shouldSwap) {

                listOf(
                    back,
                    app1,
                    app2,
                    home,
                    app3,
                    app4,
                    clock,
                    recent
                )

            } else {

                listOf(
                    recent,
                    clock,
                    app4,
                    app3,
                    home,
                    app2,
                    app1,
                    back
                )
            }


        views.forEachIndexed { index, view ->

            val lp =
                LinearLayout.LayoutParams(
                    if (isVerticalBar)
                        LinearLayout.LayoutParams.MATCH_PARENT
                    else
                        if (view === clock)
                            dpToPx(65)
                        else
                            hitboxSize,

                    if (isVerticalBar)
                        if (view === clock)
                            dpToPx(65)
                        else
                            hitboxSize
                    else
                        LinearLayout.LayoutParams.MATCH_PARENT,

                    0f
                )


            if (
                index <
                views.size - 1
            ) {

                if (isVerticalBar) {

                    lp.bottomMargin =
                        separation

                } else {

                    lp.marginEnd =
                        separation
                }
            }


            view.layoutParams = lp

            container.addView(view)
        }
    }

    // WINX_APPS_CLOCK_PATCH_END

"""

    code = (
        code[:marker.end()]
        + extra
        + code[marker.end():]
    )


# ============================================================
# 6. Replace normal button ordering
#    Back → Apps → Home → Apps → Clock → Recent
# ============================================================

if "WINX_SPECIAL_ORDER_PATCH" not in code:

    old_pattern = re.compile(
        r"val order = if \(shouldSwap\) "
        r"listOf\(recentButton, homeButton, backButton\) "
        r"else listOf\(backButton, homeButton, recentButton\)"
    )

    match = old_pattern.search(code)

    if not match:
        raise RuntimeError(
            "Original navigation order not found"
        )

    replacement = """
    // WINX_SPECIAL_ORDER_PATCH

    addWinXSpecialViews(
        container,
        shouldSwap,
        hitboxSize,
        separation,
        buttonColor,
        isVerticalBar
    )

    // WINX_SPECIAL_ORDER_PATCH_END

    """

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 7. Prevent original order loop from running
# ============================================================

# The special order already adds the buttons.
# Remove the original order.forEach block only if it remains.

if "WINX_SPECIAL_ORDER_PATCH" in code:

    original_loop = re.compile(
        r"\n\s*order\.forEachIndexed\s*\{.*?"
        r"\n\s*\}\n\s*\n\s*val buttonMap",
        re.DOTALL
    )

    match = original_loop.search(code)

    if match:

        code = (
            code[:match.start()]
            + "\n\n    val buttonMap"
            + code[match.end():]
        )


# ============================================================
# 8. Save
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("==============================================")
print("WIN X STABLE + APPS + DIGITAL CLOCK")
print("==============================================")
print("Win X package:", WINX_PACKAGE)
print("")
print("ORDER:")
print("Back")
print("App 1")
print("App 2")
print("Home")
print("App 3")
print("App 4")
print("Digital Clock")
print("Recent Apps")
print("")
print("Apps: 4 configurable slots")
print("Empty slot: tap to select app")
print("Long press: change icon shape")
print("Shapes: circle / rounded / square / sharp")
print("Clock: HH:mm")
print("")
print("Detection: rootInActiveWindow")
print("Check delay: 250ms")
print("Inside Win X: HIDE")
print("Outside Win X: FORCE SHOW")
print("==============================================")
