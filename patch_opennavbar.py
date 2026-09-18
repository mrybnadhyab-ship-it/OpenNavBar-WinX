#!/usr/bin/env python3

from pathlib import Path
import re
import sys


# ============================================================
# OpenNavBar-WinX Patch
# ============================================================

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"

SOURCE = Path("OpenNavBar/app/src/main/java/com/zariep/opennavbar/NavigationOverlayService.kt")


def fail(message):
    print("ERROR:", message)
    sys.exit(1)


def find_matching_brace(text, opening_pos):
    depth = 0
    in_string = False
    escape = False
    in_char = False

    i = opening_pos

    while i < len(text):
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

        i += 1

    return -1


def find_function(text, signature):
    pos = text.find(signature)

    if pos == -1:
        return None

    brace = text.find("{", pos)

    if brace == -1:
        return None

    end = find_matching_brace(text, brace)

    if end == -1:
        return None

    return pos, brace, end


def replace_function(text, signature, new_function):
    result = find_function(text, signature)

    if not result:
        fail("Could not find function: " + signature)

    start, brace, end = result

    return text[:start] + new_function.rstrip() + text[end + 1:]


def add_import(text, import_line):
    if import_line in text:
        return text

    marker = "import "

    positions = [m.start() for m in re.finditer(r"^import ", text, re.MULTILINE)]

    if not positions:
        return text

    last = positions[-1]

    line_end = text.find("\n", last)

    if line_end == -1:
        line_end = len(text)

    return text[:line_end + 1] + import_line + "\n" + text[line_end + 1:]


if not SOURCE.exists():
    fail(f"Source file not found: {SOURCE}")


code = SOURCE.read_text(encoding="utf-8")


# ============================================================
# 1. Required imports
# ============================================================

imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

for imp in imports:
    code = add_import(code, imp)


# ============================================================
# 2. WinX variables
# ============================================================

if "WINX_PATCH_STATE" not in code:

    marker = "class NavigationOverlayService"

    pos = code.find(marker)

    if pos == -1:
        fail("NavigationOverlayService class not found")

    brace = code.find("{", pos)

    if brace == -1:
        fail("Class opening brace not found")

    variables = r'''

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

'''

    code = code[:brace + 1] + variables + code[brace + 1:]


# ============================================================
# 3. WinX helper functions
# ============================================================

if "WINX_PATCH_HELPERS" not in code:

    marker = "    // ========================================================\n    // WINX_PATCH_STATE"

    helper_pos = code.find(marker)

    if helper_pos == -1:
        fail("WINX state marker not found")

    helper_block = r'''

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
                if (!pkg.isNullOrEmpty()) {
                    return pkg
                }
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

        isWinXLauncher = packageName == WINX_PACKAGE

        if (isWinXLauncher && !wasWinX) {
            try {
                hideOverlay()
            } catch (_: Exception) {
            }
        }

        if (!isWinXLauncher && wasWinX) {
            try {
                showOverlayAnimated()
            } catch (_: Exception) {
            }
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

            val nodesByText = try {
                root.findAccessibilityNodeInfosByText("Start")
            } catch (_: Exception) {
                emptyList()
            }

            for (node in nodesByText) {
                try {
                    if (node.isClickable && node.performAction(
                            AccessibilityNodeInfo.ACTION_CLICK
                        )
                    ) {
                        return true
                    }

                    if (node.parent != null &&
                        node.parent.performAction(
                            AccessibilityNodeInfo.ACTION_CLICK
                        )
                    ) {
                        return true
                    }
                } catch (_: Exception) {
                }
            }

            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(root)

            while (queue.isNotEmpty()) {
                val node = queue.removeFirst()

                try {
                    val text = node.text?.toString()?.lowercase(Locale.getDefault()) ?: ""
                    val description =
                        node.contentDescription?.toString()?.lowercase(Locale.getDefault()) ?: ""
                    val viewId =
                        node.viewIdResourceName?.lowercase(Locale.getDefault()) ?: ""

                    val looksLikeStart =
                        text == "start" ||
                        description == "start" ||
                        viewId.contains("start")

                    if (looksLikeStart) {
                        if (node.isClickable &&
                            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                        ) {
                            return true
                        }

                        var parent = node.parent

                        while (parent != null) {
                            if (parent.isClickable &&
                                parent.performAction(
                                    AccessibilityNodeInfo.ACTION_CLICK
                                )
                            ) {
                                return true
                            }

                            parent = parent.parent
                        }
                    }

                    for (i in 0 until node.childCount) {
                        try {
                            node.getChild(i)?.let {
                                queue.add(it)
                            }
                        } catch (_: Exception) {
                        }
                    }
                } catch (_: Exception) {
                }
            }
        } catch (_: Exception) {
        }

        return false
    }

    private fun openWinXStart() {
        try {
            if (!isWinXLauncher) {
                val intent = packageManager.getLaunchIntentForPackage(WINX_PACKAGE)

                if (intent != null) {
                    intent.addFlags(
                        Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED
                    )

                    startActivity(intent)
                }

                handler.postDelayed({
                    try {
                        updateWinXState(WINX_PACKAGE)
                        clickWinXStartButton()
                    } catch (_: Exception) {
                    }
                }, 650)

            } else {
                if (!clickWinXStartButton()) {
                    handler.postDelayed({
                        try {
                            clickWinXStartButton()
                        } catch (_: Exception) {
                        }
                    }, 250)
                }
            }
        } catch (_: Exception) {
        }
    }

'''

    code = code[:helper_pos] + helper_block + code[helper_pos:]


# ============================================================
# 4. AccessibilityNodeInfo import
# ============================================================

code = add_import(
    code,
    "import android.view.accessibility.AccessibilityNodeInfo"
)


# ============================================================
# 5. onAccessibilityEvent
# ============================================================

event_signature = "override fun onAccessibilityEvent(event: AccessibilityEvent?)"

event_result = find_function(code, event_signature)

if not event_result:
    fail("onAccessibilityEvent not found")

event_start, event_brace, event_end = event_result

old_event = code[event_start:event_end + 1]

if "WINX_EVENT_PATCH" not in old_event:

    new_event = r'''override fun onAccessibilityEvent(event: AccessibilityEvent?) {
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

        try {
            handleKeyboardStateChange(event)
        } catch (_: Exception) {
        }

        try {
            val fullscreen =
                event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED

            if (isWinXLauncher &&
                fullscreen &&
                prefs.getBoolean("hide_on_fullscreen", true)
            ) {
                if (!isSystemNavBarPresent()) {
                    scheduleTemporaryHide(250)
                }
            }
        } catch (_: Exception) {
        }
    }'''

    code = code[:event_start] + new_event + code[event_end + 1:]


# ============================================================
# 6. scheduleTemporaryHide
# ============================================================

temp_signature = "private fun scheduleTemporaryHide"

temp_result = find_function(code, temp_signature)

if temp_result:

    temp_start, temp_brace, temp_end = temp_result

    temp_old = code[temp_start:temp_end + 1]

    if "WINX_TEMP_HIDE_PROTECTION" not in temp_old:

        temp_new = temp_old.replace(
            "{",
            "{\n        // WINX_TEMP_HIDE_PROTECTION\n        if (!isWinXLauncher) return",
            1
        )

        code = code[:temp_start] + temp_new + code[temp_end + 1:]


# ============================================================
# 7. scheduleAutoHide
# ============================================================

auto_signature = "private fun scheduleAutoHide"

auto_result = find_function(code, auto_signature)

if auto_result:

    auto_start, auto_brace, auto_end = auto_result

    auto_old = code[auto_start:auto_end + 1]

    if "WINX_AUTO_HIDE_PROTECTION" not in auto_old:

        auto_new = auto_old.replace(
            "{",
            "{\n        // WINX_AUTO_HIDE_PROTECTION\n        if (!isWinXLauncher) return",
            1
        )

        code = code[:auto_start] + auto_new + code[auto_end + 1:]


# ============================================================
# 8. handleKeyboardStateChange
# ============================================================

keyboard_signature = "private fun handleKeyboardStateChange"

keyboard_result = find_function(code, keyboard_signature)

if keyboard_result:

    kb_start, kb_brace, kb_end = keyboard_result

    kb_old = code[kb_start:kb_end + 1]

    if "WINX_KEYBOARD_PROTECTION" not in kb_old:

        kb_new = kb_old.replace(
            "if (isKeyboardVisible) {",
            """if (isKeyboardVisible && isWinXLauncher) {
            // WINX_KEYBOARD_PROTECTION""",
            1
        )

        code = code[:kb_start] + kb_new + code[kb_end + 1:]


# ============================================================
# 9. protect showOverlay
# ============================================================

show_signature = "private fun showOverlay"

show_result = find_function(code, show_signature)

if show_result:

    show_start, show_brace, show_end = show_result

    show_old = code[show_start:show_end + 1]

    if "WINX_SHOW_PROTECTION" not in show_old:

        show_new = show_old.replace(
            "{",
            """{
        // WINX_SHOW_PROTECTION
        if (isWinXLauncher) return""",
            1
        )

        code = code[:show_start] + show_new + code[show_end + 1:]


# ============================================================
# 10. protect showOverlayAnimated
# ============================================================

show_anim_signature = "private fun showOverlayAnimated"

show_anim_result = find_function(code, show_anim_signature)

if show_anim_result:

    sa_start, sa_brace, sa_end = show_anim_result

    sa_old = code[sa_start:sa_end + 1]

    if "WINX_SHOW_ANIMATED_PROTECTION" not in sa_old:

        sa_new = sa_old.replace(
            "{",
            """{
        // WINX_SHOW_ANIMATED_PROTECTION
        if (isWinXLauncher) return""",
            1
        )

        code = code[:sa_start] + sa_new + code[sa_end + 1:]


# ============================================================
# 11. protect updateOverlayLive
# ============================================================

update_signature = "private fun updateOverlayLive"

update_result = find_function(code, update_signature)

if update_result:

    up_start, up_brace, up_end = update_result

    up_old = code[up_start:up_end + 1]

    if "WINX_UPDATE_LIVE_PROTECTION" not in up_old:

        up_new = up_old.replace(
            "{",
            """{
        // WINX_UPDATE_LIVE_PROTECTION
        if (isWinXLauncher) return""",
            1
        )

        code = code[:up_start] + up_new + code[up_end + 1:]


# ============================================================
# 12. Long press Home -> WinX Start
# ============================================================

long_signature = "private fun handleLongPress"

long_result = find_function(code, long_signature)

if not long_result:
    fail("handleLongPress not found")

lp_start, lp_brace, lp_end = long_result

lp_old = code[lp_start:lp_end + 1]

if "WINX_LONG_PRESS_START" not in lp_old:

    lp_new = r'''private fun handleLongPress(buttonType: String) {
        // ====================================================
        // WINX_LONG_PRESS_START
        // ====================================================

        if (isButtonDisabled(buttonType)) return
        if (isButtonHidden(buttonType)) return
        if (!prefs.getBoolean("enable_long_press", true)) return

        if (buttonType == "home") {
            openWinXStart()
            return
        }

        executeAction("long_press_$buttonType", 70)
    }'''

    code = code[:lp_start] + lp_new + code[lp_end + 1:]


# ============================================================
# 13. WinX clock/date
# ============================================================

configure_signature = "private fun configureOverlayView"

configure_result = find_function(code, configure_signature)

if not configure_result:
    fail("configureOverlayView not found")

fn_start, fn_brace, fn_end = configure_result

configure_code = code[fn_start:fn_end + 1]

if "WINX_CLOCK_INSERTED" not in configure_code:

    # Find the button container loop's addView(frame)
    add_match = re.search(
        r"container\.addView\(frame\)",
        configure_code
    )

    if not add_match:
        fail("Could not find container.addView(frame)")

    fn_open = fn_brace - fn_start

    abs_add_end = fn_open + 1 + add_match.end()

    tail = configure_code[abs_add_end:]

    loop_close_rel = tail.find("}")

    if loop_close_rel == -1:
        fail("Could not find button loop closing brace")

    insert_pos = abs_add_end + loop_close_rel + 1

    clock_block = r'''

        // ====================================================
        // WINX_CLOCK_INSERTED
        // ====================================================

        try {
            winXClockView?.let {
                try {
                    container.removeView(it)
                } catch (_: Exception) {
                }
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
                rotation = 0f
            }

            winXClockHandler?.removeCallbacksAndMessages(null)

            winXClockHandler = Handler(Looper.getMainLooper())

            winXClockRunnable = object : Runnable {
                override fun run() {
                    try {
                        val now = Date()

                        val timeFormat = SimpleDateFormat(
                            "HH:mm",
                            Locale.getDefault()
                        )

                        val dateFormat = SimpleDateFormat(
                            "dd/MM",
                            Locale.getDefault()
                        )

                        winXClockView?.text =
                            timeFormat.format(now) +
                            "\n" +
                            dateFormat.format(now)

                    } catch (_: Exception) {
                    }

                    try {
                        winXClockHandler?.postDelayed(this, 1000)
                    } catch (_: Exception) {
                    }
                }
            }

            val clockParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )

            clockParams.gravity = Gravity.CENTER_VERTICAL
            clockParams.l
