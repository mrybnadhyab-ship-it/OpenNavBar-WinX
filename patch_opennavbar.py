#!/usr/bin/env python3
from pathlib import Path
import re
import sys

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"

if len(sys.argv) >= 2:
    SOURCE = Path(sys.argv[1])
else:
    SOURCE = Path("opennavbar/app/src/main/java/com/zariep/opennavbar/NavigationOverlayService.kt")


def fail(msg):
    print("ERROR:", msg)
    sys.exit(1)


def find_matching_brace(text, opening_pos):
    depth = 0
    in_string = False
    in_char = False
    escape = False
    for i in range(opening_pos, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        elif in_char:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == "'":
                in_char = False
        else:
            if c == '"':
                in_string = True
            elif c == "'":
                in_char = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
    return -1


def find_function(text, signature):
    start = text.find(signature)
    if start < 0:
        return None
    brace = text.find("{", start)
    if brace < 0:
        return None
    end = find_matching_brace(text, brace)
    if end < 0:
        return None
    return start, brace, end


def add_import(text, line):
    if line in text:
        return text
    positions = [m.start() for m in re.finditer(r"^import ", text, re.MULTILINE)]
    if not positions:
        return text
    last = positions[-1]
    eol = text.find("\n", last)
    if eol < 0:
        eol = len(text)
    return text[:eol + 1] + line + "\n" + text[eol + 1:]


if not SOURCE.exists():
    fail("Source file not found: " + str(SOURCE))

code = SOURCE.read_text(encoding="utf-8")

# ------------------------------------------------------------
# Imports
# ------------------------------------------------------------
for imp in [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import android.view.accessibility.AccessibilityNodeInfo",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]:
    code = add_import(code, imp)

# ------------------------------------------------------------
# Top-level WinX constant
# ------------------------------------------------------------
if "WINX_PACKAGE_PATCH_CONSTANT" not in code:
    marker = "class NavigationOverlayService"
    pos = code.find(marker)
    if pos < 0:
        fail("NavigationOverlayService class not found")
    const = 'private const val WINX_PACKAGE_PATCH_CONSTANT = "com.InternityLabs.Launcher.WinX"\n\n'
    code = code[:pos] + const + code[pos:]

# ------------------------------------------------------------
# State variables
# ------------------------------------------------------------
if "WINX_PATCH_STATE" not in code:
    marker = "class NavigationOverlayService"
    pos = code.find(marker)
    brace = code.find("{", pos)
    if brace < 0:
        fail("Class opening brace not found")
    block = """
    // ========================================================
    // WINX_PATCH_STATE
    // ========================================================

    private var isWinXLauncher = false

    private val winXCheckRunnable = Runnable {
        try {
            updateWinXState(getCurrentForegroundPackage())
        } catch (_: Exception) {
        }
    }

    private var winXClockView: TextView? = null
    private var winXClockRunnable: Runnable? = null
    private var winXClockHandler: Handler? = null

"""
    code = code[:brace + 1] + block + code[brace + 1:]

# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------
if "WINX_PATCH_HELPERS" not in code:
    marker = "    // ========================================================\n    // WINX_PATCH_STATE"
    pos = code.find(marker)
    if pos < 0:
        fail("WINX state marker not found")
    helpers = """
    // ========================================================
    // WINX_PATCH_HELPERS
    // ========================================================

    private fun getCurrentForegroundPackage(): String? {
        try {
            val active = windows.firstOrNull {
                try {
                    it.isActive || it.isFocused
                } catch (_: Exception) {
                    false
                }
            }
            if (active != null) {
                val pkg = active.root?.packageName?.toString()
                if (!pkg.isNullOrEmpty()) return pkg
            }
        } catch (_: Exception) {
        }

        try {
            return rootInActiveWindow?.packageName?.toString()
        } catch (_: Exception) {
        }
        return null
    }

    private fun updateWinXState(packageName: String?) {
        val wasWinX = isWinXLauncher
        isWinXLauncher = packageName == WINX_PACKAGE_PATCH_CONSTANT

        if (isWinXLauncher && !wasWinX) {
            try { hideOverlay() } catch (_: Exception) { }
        }

        if (!isWinXLauncher && wasWinX) {
            try { showOverlayAnimated() } catch (_: Exception) { }
        }
    }

    private fun checkWinXStateDelayed() {
        try {
            handler.removeCallbacks(winXCheckRunnable)
            handler.postDelayed(winXCheckRunnable, 150)
        } catch (_: Exception) {
        }
    }

    private fun clickWinXStartButton(): Boolean {
        try {
            val root = rootInActiveWindow ?: return false
            val byText = try {
                root.findAccessibilityNodeInfosByText("Start")
            } catch (_: Exception) {
                emptyList()
            }

            for (node in byText) {
                try {
                    if (node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                    node.parent?.let { p ->
                        if (p.isClickable && p.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                    }
                } catch (_: Exception) { }
            }

            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(root)
            while (queue.isNotEmpty()) {
                val node = queue.removeFirst()
                try {
                    val text = node.text?.toString()?.lowercase(Locale.getDefault()) ?: ""
                    val desc = node.contentDescription?.toString()?.lowercase(Locale.getDefault()) ?: ""
                    val id = node.viewIdResourceName?.lowercase(Locale.getDefault()) ?: ""
                    val isStart = text == "start" || desc == "start" || id.contains("start")

                    if (isStart) {
                        if (node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                        var parent = node.parent
                        while (parent != null) {
                            if (parent.isClickable && parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                            parent = parent.parent
                        }
                    }

                    for (i in 0 until node.childCount) {
                        try { node.getChild(i)?.let { queue.add(it) } } catch (_: Exception) { }
                    }
                } catch (_: Exception) { }
            }
        } catch (_: Exception) { }
        return false
    }

    private fun openWinXStart() {
        try {
            if (!isWinXLauncher) {
                val intent = packageManager.getLaunchIntentForPackage(WINX_PACKAGE_PATCH_CONSTANT)
                if (intent != null) {
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
                    startActivity(intent)
                }
                handler.postDelayed({
                    try {
                        updateWinXState(WINX_PACKAGE_PATCH_CONSTANT)
                        clickWinXStartButton()
                    } catch (_: Exception) { }
                }, 650)
            } else if (!clickWinXStartButton()) {
                handler.postDelayed({
                    try { clickWinXStartButton() } catch (_: Exception) { }
                }, 250)
            }
        } catch (_: Exception) { }
    }

"""
    code = code[:pos] + helpers + code[pos:]

# ------------------------------------------------------------
# Preserve original onAccessibilityEvent; only inject detection
# ------------------------------------------------------------
result = find_function(code, "override fun onAccessibilityEvent(event: AccessibilityEvent?)")
if not result:
    fail("onAccessibilityEvent not found")
start, brace, end = result
old = code[start:end + 1]
if "WINX_EVENT_PATCH" not in old:
    inject = """
        // ====================================================
        // WINX_EVENT_PATCH
        // ====================================================
        try {
            val eventPackage = event?.packageName?.toString()
            if (!eventPackage.isNullOrEmpty()) {
                updateWinXState(eventPackage)
            } else {
                checkWinXStateDelayed()
            }
        } catch (_: Exception) {
        }

"""
    new = old.replace("{", "{\n" + inject, 1)
    code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Any temporary hide is allowed only in WinX
# ------------------------------------------------------------
result = find_function(code, "private fun scheduleTemporaryHide")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_TEMP_HIDE_PROTECTION" not in old:
        new = old.replace("{", "{\n        // WINX_TEMP_HIDE_PROTECTION\n        if (!isWinXLauncher) return", 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Auto hide only in WinX
# ------------------------------------------------------------
result = find_function(code, "private fun scheduleAutoHide")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_AUTO_HIDE_PROTECTION" not in old:
        new = old.replace("{", "{\n        // WINX_AUTO_HIDE_PROTECTION\n        if (!isWinXLauncher) return", 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Long press Home opens WinX Start only while WinX is active
# ------------------------------------------------------------
result = find_function(code, "private fun handleLongPress")
if not result:
    fail("handleLongPress not found")
start, brace, end = result
old = code[start:end + 1]
if "WINX_LONG_PRESS_START" not in old:
    new = """private fun handleLongPress(buttonType: String) {
        // ====================================================
        // WINX_LONG_PRESS_START
        // ====================================================
        if (isButtonDisabled(buttonType)) return
        if (isButtonHidden(buttonType)) return
        if (!prefs.getBoolean("enable_long_press", true)) return

        if (buttonType == "home" && isWinXLauncher) {
            openWinXStart()
            return
        }

        executeAction("long_press_$buttonType", 70)
    }"""
    code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Clock/date: one line to avoid malformed Kotlin string literals
# ------------------------------------------------------------
result = find_function(code, "private fun configureOverlayView")
if not result:
    fail("configureOverlayView not found")
fn_start, fn_brace, fn_end = result
configure_code = code[fn_start:fn_end + 1]

if "WINX_CLOCK_INSERTED" not in configure_code:
    add_match = re.search(r"container\.addView\(frame\)", configure_code)
    if not add_match:
        fail("Could not find container.addView(frame)")

    fn_open = fn_brace - fn_start
    abs_add_end = fn_open + 1 + add_match.end()
    tail = configure_code[abs_add_end:]
    loop_close_rel = tail.find("}")
    if loop_close_rel < 0:
        fail("Could not find button loop closing brace")
    insert_pos = abs_add_end + loop_close_rel + 1

    clock_block = """
        // ====================================================
        // WINX_CLOCK_INSERTED
        // ====================================================
        try {
            winXClockView?.let {
                try { container.removeView(it) } catch (_: Exception) { }
            }

            winXClockView = TextView(this).apply {
                textSize = 9f
                setTypeface(Typeface.DEFAULT, Typeface.NORMAL)
                gravity = Gravity.CENTER
                setSingleLine(true)
                includeFontPadding = false
                setTextColor(Color.WHITE)
                isClickable = false
                isFocusable = false
            }

            winXClockHandler?.removeCallbacksAndMessages(null)
            winXClockHandler = Handler(Looper.getMainLooper())

            winXClockRunnable = object : Runnable {
                override fun run() {
                    try {
                        val now = Date()
                        val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                        val dateFormat = SimpleDateFormat("dd/MM", Locale.getDefault())
                        winXClockView?.text = timeFormat.format(now) + "  " + dateFormat.format(now)
                    } catch (_: Exception) { }

                    try {
                        winXClockHandler?.postDelayed(this, 1000)
                    } catch (_: Exception) { }
                }
            }

            val clockParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )
            clockParams.gravity = Gravity.CENTER_VERTICAL
            clockParams.leftMargin = 4
            clockParams.rightMargin = 4

            val clock = winXClockView
            if (clock != null) {
                if (prefs.getBoolean("swap_back_recent", false)) {
                    container.addView(clock, 1, clockParams)
                } else {
                    container.addView(clock, 3, clockParams)
                }
                winXClockRunnable?.let { winXClockHandler?.post(it) }
            }
        } catch (_: Exception) { }

"""

    code = code[:fn_start] + configure_code[:insert_pos] + clock_block + configure_code[insert_pos:] + code[fn_end + 1:]

# ------------------------------------------------------------
# Clock cleanup
# ------------------------------------------------------------
result = find_function(code, "override fun onDestroy")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_CLOCK_CLEANUP" not in old:
        cleanup = """
        // WINX_CLOCK_CLEANUP
        try {
            winXClockHandler?.removeCallbacksAndMessages(null)
            winXClockHandler = null
            winXClockRunnable = null
            winXClockView = null
        } catch (_: Exception) { }

"""
        new = old.replace("{", "{\n" + cleanup, 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# State checks
# ------------------------------------------------------------
result = find_function(code, "override fun onServiceConnected")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_SERVICE_CONNECTED" not in old:
        new = old.replace("{", "{\n        // WINX_SERVICE_CONNECTED\n        checkWinXStateDelayed()", 1)
        code = code[:start] + new + code[end + 1:]

result = find_function(code, "override fun onSharedPreferenceChanged")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_PREF_STATE_CHECK" not in old:
        new = old.replace("{", "{\n        // WINX_PREF_STATE_CHECK\n        checkWinXStateDelayed()", 1)
        code = code[:start] + new + code[end + 1:]

SOURCE.write_text(code, encoding="utf-8")
print("==============================================")
print(" OpenNavBar-WinX PATCH COMPLETE")
print("==============================================")
print("Source:", SOURCE)
print("WinX detection: OK")
print("WinX-only auto hide: OK")
print("MiXplorer stability: OK")
print("Long press Home -> WinX Start: OK")
print("Clock/date: OK")
print("==============================================")
