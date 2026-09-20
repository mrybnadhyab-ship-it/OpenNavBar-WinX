import sys
import re
from pathlib import Path

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


def find_matching_brace(text, open_pos):
    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    i = open_pos

    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
                i += 1
        elif in_string:
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
            if c == "/" and n == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and n == "*":
                in_block_comment = True
                i += 1
            elif c == '"':
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


def find_function(text, name):
    m = re.search(
        rf"private\s+fun\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
        text,
    )
    if not m:
        return None

    open_pos = text.find("{", m.start(), m.end())
    if open_pos < 0:
        return None

    close_pos = find_matching_brace(text, open_pos)
    if close_pos < 0:
        return None

    return m, open_pos, close_pos


# ============================================================
# 1. IMPORTS
# ============================================================

required_imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

anchor = "import android.accessibilityservice.AccessibilityService"
if anchor not in code:
    raise RuntimeError("AccessibilityService import not found")

for imp in required_imports:
    if imp not in code:
        code = code.replace(anchor, anchor + "\n" + imp, 1)


# ============================================================
# 2. WIN X STABLE PATCH
# ============================================================

if "WINX_STABLE_PATCH" not in code:
    match = re.search(r"(class\s+NavigationOverlayService[^{]*\{)", code)
    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    winx_patch = r'''

    // WINX_STABLE_PATCH
    // WINX_OVERLAY_HEALTH_PATCH

    private var winXOverlayHealthRunnable: Runnable? = null
    private var winXOverlayHealthRecoveryRunning = false

    private fun scheduleWinXOverlayHealthCheck(delayMs: Long = 350L) {
        if (isWinXLauncher) return

        winXOverlayHealthRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXOverlayHealthRunnable = Runnable {
            if (isWinXLauncher || winXOverlayHealthRecoveryRunning) return@Runnable

            val view = overlayView
            val windowAttached = try {
                view != null && view.windowToken != null
            } catch (_: Exception) {
                false
            }

            // Match Navigation Bar v3.3.0's important recovery rule:
            // a missing window token means the overlay was detached.
            // Do NOT use visibility here, because normal auto-hide is valid.
            if (!windowAttached) {
                winXOverlayHealthRecoveryRunning = true

                try {
                    hideOverlay()
                } catch (_: Exception) {
                }

                handler.postDelayed({
                    try {
                        if (!isWinXLauncher) {
                            showOverlay()
                        }
                    } catch (_: Exception) {
                    }
                    winXOverlayHealthRecoveryRunning = false
                }, 180L)
            }
        }

        handler.postDelayed(winXOverlayHealthRunnable!!, delayMs)
    }

    // WINX_OVERLAY_HEALTH_PATCH_END


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
            } else if (currentPackage.isNotEmpty()) {
                // A real package is visible, so leaving Win-X is confirmed.
                // Empty packageName is treated as a temporary Accessibility
                // disconnect and MUST NOT make OpenNavBar stop or lose state.
                if (isWinXLauncher) {
                    isWinXLauncher = false
                    forceShowAfterWinX()
                }
            }

            // Keep checking independently of AccessibilityEvent delivery.
            // This lets OpenNavBar survive a temporary Win-X/accessibility
            // disconnect and hide again automatically when Win-X returns.
            handler.postDelayed({
                checkWinXStateDelayed()
            }, 750L)
        }

        handler.postDelayed(winXCheckRunnable!!, 250)
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

        disableRevealZoneTouch()
    }

    // WINX_STABLE_PATCH_END
'''

    code = code[:match.end()] + winx_patch + code[match.end():]


# ============================================================
# 3. ACCESSIBILITY EVENT
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:
    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*"
        r"\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code,
    )
    if not match:
        raise RuntimeError("onAccessibilityEvent(AccessibilityEvent?) not found")

    event_patch = r'''
        // WINX_STABLE_EVENT_PATCH
        checkWinXStateDelayed()
        scheduleWinXOverlayHealthCheck()
        // WINX_STABLE_EVENT_PATCH_END

'''

    code = code[:match.end()] + event_patch + code[match.end():]


# ============================================================
# 4. PROTECT ONLY showOverlay()
#    Do NOT touch showOverlayAnimated() or showRevealZone().
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:
    match = re.search(
        r"(private\s+fun\s+showOverlay\s*\([^)]*\)\s*\{)",
        code,
    )
    if not match:
        raise RuntimeError("showOverlay() not found")

    protection = r'''
        // WINX_SHOW_OVERLAY_PROTECTION
        if (isWinXLauncher) return

'''
    code = code[:match.end()] + protection + code[match.end():]


# ============================================================
# 4.5. KEEP OVERLAY VISIBLE IN FULLSCREEN
#      Only disable the existing fullscreen auto-hide condition.
#      Do not change Win-X, clock/date, Gmail, or Swipe/Reveal.
# ============================================================

if "WINX_FULLSCREEN_STABLE_PATCH" not in code:
    fullscreen_expr = 'prefs.getBoolean("hide_on_fullscreen", true)'
    fullscreen_replacement = 'false /* WINX_FULLSCREEN_STABLE_PATCH */'

    if fullscreen_expr in code:
        code = code.replace(fullscreen_expr, fullscreen_replacement, 1)
    else:
        raise RuntimeError("hide_on_fullscreen preference not found")


# ============================================================
# 5. CLOCK + DATE
# ============================================================

if "WINX_CLOCK_DATE_PATCH" not in code:
    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code,
    )
    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    clock_patch = r'''

    // WINX_CLOCK_DATE_PATCH

    private var winXClockTextView: TextView? = null

private var winXDateTextView: TextView? = null
    private var winXClockStarted = false

    private val winXClockRunnable = object : Runnable {
        override fun run() {
            try {
                val now = Date()

                val timeText = SimpleDateFormat(
                    "hh:mm a",
                    Locale.ENGLISH
                ).format(now)
                    .replace("AM", "ص")
                    .replace("PM", "م")

                val dateText = SimpleDateFormat(
                    "yyyy/MM/dd",
                    Locale.ENGLISH
                ).format(now)

                winXClockTextView?.text = timeText
                winXDateTextView?.text = dateText
            } catch (_: Exception) {
            }

            handler.postDelayed(this, 1000)
        }
    }

    private fun createWinXClock(
        textColor: Int,
        rotation: Float
    ): LinearLayout {

        val clockLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 0)
            this.rotation = rotation
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val clock = TextView(this).apply {
            gravity = Gravity.CENTER
            isSingleLine = true
            includeFontPadding = false
            textSize = 9f
            typeface = Typeface.DEFAULT
            setTextColor(textColor)
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val date = TextView(this).apply {
            gravity = Gravity.CENTER
            isSingleLine = true
            includeFontPadding = false
            textSize = 9f
            typeface = Typeface.DEFAULT
            setTextColor(textColor)
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        clockLayout.addView(
            clock,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        val dateParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = dpToPx(1)
        }

        clockLayout.addView(date, dateParams)

        winXClockTextView = clock
        winXDateTextView = date

        if (!winXClockStarted) {
            winXClockStarted = true
            handler.removeCallbacks(winXClockRunnable)
            handler.post(winXClockRunnable)
        }

        return clockLayout
    }

    // WINX_CLOCK_DATE_PATCH_END
'''

    code = code[:match.end()] + clock_patch + code[match.end():]


# ============================================================
# 6. INSERT CLOCK WITHOUT REPLACING THE ORIGINAL BUTTON LAYOUT
#    This keeps all original SwipeInterceptLayout code untouched.
# ============================================================

if "WINX_CLOCK_LAYOUT_PATCH" not in code:
    fn = find_function(code, "configureOverlayView")
    if not fn:
        raise RuntimeError("configureOverlayView() not found")

    _, fn_open, fn_close = fn
    body = code[fn_open + 1:fn_close]

    add_match = re.search(r"container\.addView\s*\(\s*frame\s*\)", body)
    if not add_match:
        raise RuntimeError("Original navigation button addView(frame) not found")

    abs_add_end = fn_open + 1 + add_match.end()
    tail = code[abs_add_end:fn_close]
    loop_close_rel = tail.find("}")
    if loop_close_rel < 0:
        raise RuntimeError("Navigation button loop end not found")

    insert_pos = abs_add_end + loop_close_rel + 1

    clock_layout_patch = r'''

        // WINX_CLOCK_LAYOUT_PATCH

        val winXClockRotation = when (position) {
            "left" -> 90f
            "right" -> -90f
            else -> 0f
        }

        val winXClockView = createWinXClock(
            buttonColor,
            winXClockRotation
        ).apply {
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXSpacer = View(this).apply {
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXClockParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize,
                0f
            )
        } else {
            LinearLayout.LayoutParams(
                dpToPx(50),
                LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            )
        }

        val winXSpacerParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
            )
        } else {
            LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.MATCH_PARENT,
                1f
            )
        }

        if (shouldSwap) {
            // Recent | Clock | SPACE | Home | Back
            container.addView(winXClockView, 1, winXClockParams)
            container.addView(winXSpacer, 2, winXSpacerParams)
        } else {
            // Back | Home | SPACE | Clock | Recent
            container.addView(winXSpacer, 2, winXSpacerParams)
            container.addView(winXClockView, 3, winXClockParams)
        }

        // WINX_GMAIL_BUTTON_PATCH
        val winXGmailButton = android.widget.FrameLayout(this).apply {
            isClickable = true
            isFocusable = true
            isLongClickable = false

            val gmailIcon = android.widget.ImageView(this@NavigationOverlayService).apply {
                try {
                    val gmailIconBase64 = "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAApmUlEQVR42u19ebglZXnn7/2q6qx37W56A4GWfUThCSAgEtyCRuMSFfVRMC5ZJ6OPmedxYhy1JXk0DlkcM0smi5M4ycxkICqo6KgMiyCytQ1EtmZpoKGBpve7nHOq6nvf+aO2r6q+Oqfu0tDgLZ5L33vurXOq6t1+7+99v/cDVo6VY+VYOVaOlWPlWDlWjpVj5Vg5Vo6VY+X4eTno5+IeL7pc4Yr3aADoTGx4I515ycf1mk0nysFdTXEbgdNZvQN7Hn1E7r3yv/efuvcmAMAFm13ccKkGICsK8EI9Nm9WuPRSBgAPOFWd95ufUked+T6sOdHRjpe7eRIGnrkvpCfu+Jrc/Nd/2AceBwBcdJGDK67QKwrwwjoURAREAmBN+6yLP4ajzvg0H3WGy1CgsM8QTu9dhCIr91pKgaEev+0gHr3lP/Xu/vp/BvA0RAhECoBeUYDDXfAXXU6Ju2+f9Ma3YdO5/xHH/eIm7TSAYKAh2gEpZMI3PLwwhBytvIbjhD7w0A0P4LEffaq37YYrI29wuYMr3iMAeEUBDrfDcNXt9uoz8cpLvoRN572eJ4+CBL0QHDogRVbBpw+DowciLKJcTV7LdQ7shDxy03eDn/z9H4bhzK3GZ/GLAR+8CBTgIgeIBN8EjlNnf+QP5JizPyAbTm1JGDLCAUGp3H0WhU8QkAAg0xsIRFjIaTEp13Ge3Mqy47a/DLf8z7/wgW3Fz15RgOfX3TvtE1/32zj5jZ+VY85dx1BA2NcQcUA0RPAAieQFHws/tW0RgEiL21QOB4SdW/fJfd/7Qv/B6/8CQPBCDwv0grxmI61rr3352+n0d3xKjj7zHO4eAfF7YRznK909SXzjVJCZxAJHUR8EEA0opclrOc7cs5Dtt9zI9/9g8+CZe64z8MELLiy8sBTgggtc3HBDCADjjcaJfMYHPy3HXfBres0J4LCvKfSVKXib8JUk0h9i9blzOfegSFjEabJyGw49+yDkiZ/+g3vHV78w4/sPvBDTxheIAmxWQJTPTwJT/mnv+n0c/5qPYf2pXU0OI+gDRGqUuwcEVJKyzeo5fkmyUFE8iYXhNogIRE/9yyy23/bV+bsv/yMAe6K08fOUXPOKAiyPu3dbp1z4LnXs+Zvl2HNO0V47Tut4RJyX3L/DBS/x+ZLHCbYrY47CAiktXttxwz7k4R89hCdu/8T8g9d/F4C8EPABHbbXdcEFTuLu3VUnnO2dcuHn5aTXv0nG10GCQa20Ttmee2Wc53qCFwGkiB1YhByt3JarDu4Etv/4Ft529Sd6e5+89XAPC4ehAmTuvgOspzPf/3m96fzfko2nQQKfoQNAQZmXbgo/dfWltC7+n5S0IXX3NOyhiMSKY8EOGYZgcTw4rquw64GQdmz5+/COr31xAGyPwsJ71OGWNh5OCmCmdc32y97+UTnu1ZfS0a9co4lEQp9pVFonABFXCA9D3T0tVPDx5+cySBJQ9BrDbZKjiLBjyzN4/Cf/buaeq/8RAGOzKFxKOFzCAh0W12Ckdc3VR7+OzrjkMjrm3DO4swrs9zQNo2/TtM6Wz9usvuzulfWyxBB+DYUigZJcWICQCuG2XdXbA9lx+83htmv/xH/qriujjObwqDY+vwpgxMaxBk6Ws//N7+kjf+HXZd3JikNfkx4okDOaxasF8MppXeXNc0U6L7HVW0Gm7bMAiBZxmkxuw6H9j4N23P43wZb//We+P3NYpI3PkwJsVpDPJ9W6idbZv/ExddRpn+YNL+8wERD0Oaq+0cIEX5nPLwHg2TwJRd9XvU/+WuPzWBiuByIotXtbnx+95Uvzd//znwKYMxwRv9gVQGGzAJdGgbpz9Fm/Iqf+yhdl0/kvZ6cJBP3h1bplSOtUpdVXGKEUBG8yiaMEX1IeBkhpcj1HhT6wY8tD8uh1m+ceueWfAPDzkTY+dwpguDp3Yt0rvdPf+0d0zDkX6uljIWFfg0M1lL6ttPgqwXPpRmkpcZ5kAYKX9B8TlyQEJEXVRlZe08Hss+DHb71Vtl7+sV5vz+1FxvNFoAAXOZDLGUTSAl6iznj/V/DS839VbzwNHIZMeoC42aIirTOQdjGtswkOnJ4/Oq3j0cg+9RxS4SAkb/Gm8hSEn39fhrCwOB6U4yh69oEeb//xlfM/u+rTAB59rvABPUfuXnVO/qVLcMqbP80vOfNEFgjCAY+u1tWP86bVDxc8VyhOXviEPBU8DIhmVk9x9bBAI0s+LIj5c3TNDK+plNaQZ+59Wrbf+OX5bT/8CoDBoQ4LdEje84LNDm64NASA9oZT3yGnvOX36dhzztHj6yCWtC4jY7Kf1SLd/WKs3uruAasnsMf5ssUrsSLJEiYxrkuEFCuv5VB/P/jJO++Vh6//fO/JO6+IvMGhqTYurwIYLqsBnOie/7tfkGPOeTevOQ7i+wz2AVJqKMATxE5Bagi+BpEDidM6u0KIRMAwjTIkCxe8oTSwuProT8n4lEK4MF4nYSFqaPJaLvZth+y86+/8O//xMt/37z8U+GCZFCCX1h3ROu1dH8Gm8/4AR585yUyMoAcoGkLfEgA+RGldPRaPEgFKDXdvviVxhaunykzEKvgEIGbgNK42EsmuB+Zkx5b/Ovezb/45siZVWo6wsFQFMOlbam969bvw0vP+VE54/THc7EL8/kgWT1XdQ02rzx6+QBI8MUTwYBvOwAiAl1gyZWmdcU1l4UcKkJWUixaf/1slVZ/PEECT13RIB8CTdz2ud/70i70HfvhXyxUWaNHnGdW6zsbTTseJr/usHPuqd/LkkeDQD0n7ztLSOtOK2KI4NmuiekROCdmLRT7J54uRLlLO6qNYn3ft0fnmY9WFj5AKgJhT8zymEBaQo8lpuNTbD9lx6/X63u9/sndwxx1GWFgUrbwIBcgaIVvA0eqsD/2eHPeLH5d1JykOA4YeUCR4sqZKZXQtyN9vXihiCJiMgJEKXWC/bzLiNFM+JZNMCaXKUxRdvim4Ah8gIhjixqxZRxHk2uobeeWOgCIcj8nxHOx51Ken7/lauOV/fG4eeLoom0OhAGbRptU+4TW/qU584+f0pnNWMzlA6BtNmFm6Q5EbAyhuxyp+vLBBmkUwIsukJFIMMoWO0kMtl4Pzr5cwgiS2zSVMlgduAmXE8pJHsb6W/yCSivIxmUpYVDaTOJLY41DsgRggaFENRwGQPdt28iM3/fX8tmsiWnmB1Uaq9TebhVL6dv3pb5Z/9YbL5JhzX8YTGyH+nAbnu3KIxUA0EttsuRZvRdZxPM8/QLL+XR4npFLNvAZRnkgqnZ/k7VJm8ZLYXpJNAXuVQk7BS5AY54vFQeUBY/bQ2Qg5kn6UyjIQESImt+Uofw76iS3/oh+7/jO9nfd+ayH4YLgCGClHG9ioXvU7X5Jjz7okPOIUSDjQCPsRfStIa+H5B2FaOEU3lYtzYjh1yT0DSp4QCyoy6lxcpYJ8E+FZaVrL65mSSnU6CZullr2AokwxqyJUClRzpFERw0jBC1lAahQWtHIbLh3YCd659ZuDB7777/3ZvfcZqXmlIlANq++2Xv62P6aTLnyvbHj5Wi2A+D0mIkVEpXQmiakqZ/CSPWQxYirZ0zzKPWjKWVHx4UdWpTIOwXzfkgQkpxSSXj/ihywFQCj5aymlbxSFrQKYo1wIGtJBlHhIIQMQU+6zpFLxkIbHWJlYOQ0iR5Hs3ubz0z/7yuzd37wMwO7yGw9XgPQP25tefRGOe/Uf4vjXnqzdDiToaQKrzDchv4AisSAbEi9YeFn4eWQ87MbLOCATnkqfcUX+blZljPPTKqNIQXGLEcb0NlIRWjLBmd5NCjRzKvQkkzAVnYspggCichdDRqIicYlaEWlxGo5iDf30nU/qXfd+vHf/NVfF6UhJCao8wETn/N/9G9l03nv0xEsgYU+TDhUUUWJRkXVIHugIyvl3AuSsBE1eINZYXeFDi/QvFQRCsXVWZwpSwBs21A8L/hALRxELT6jkcTJxS6EimMdJReJLQPY0GZTCLZXjG0y7YgE5rNymI4N9kB0/vTa459sf6vf37RjpASaBqfA1//b68BVvP03CUCMYEChWPUPAiQJQqe5t5s3Z68kKbCoZTIUVGS6UCk4DqePPMJIUyCGRxEFLCcgVAZqkXH5m5RCpxgBSJoJgzenFTGbzmKSgZAlYJZN2kgzYZllD3l9SkXnMk2ECx9Wq0XX1Izf+ZPaW//Z6AD3zCp2SRhxz9r/GWRd/UIsTqKDnEoEodescgTLRccyNYr2KqdmI1WOQxF9xWkdJsySyLxVTv9HrHH9J9ppEBSFl/EwiUMLx6wyF7LOz904+X6fvmVw3AVDQ5c9LrjN3Tck9m+8bCclRkl1D4b4oKU7FVUcSAXF0LiT++1g5VazEybNA8owlXnOQeNc0q4v+hsBQoChlZo5fExsLShBWwmHgdlcd40H2+LsfusWUt1vS2U3n/5aWJlPQc0GAaM4Ai8HBE0cPre+HQBAaACp+4FKRH1tW4VT/rnC+VOTTUkzhCm5eERxFCEMegeTz7t9xFFxF+esSoBfq+BlLPu2Iv/UcgqOQ4zOKAIgg8EOGZkk9T9PN0EHW1p4rWABxGSAIGUIOui0PwpJljEWnTgTSvqvJE9098qMAvjxUAY668K10sNdS+7c/KuK6UfFOGCI6tYDErfZ7Pk59SRcXv+oEnLRxAiRU8kRUxpbWmG7+lqQ+p0liQtLycjAWQdNz0fEc7J/z47ghZba3ICARQbflodNw00w0Adz753pgTsJIMUkQTHQa8DynyPmUru1gbwA/CKNVbSBMjjWimlmSQZsKZugmi+ChnfvwD9fcgx/d8xTGOk1IepHKkL0DYUbQ62Ns4zpac+Frvfu2fBVDFaC1fkK31x+Pzjhh132Pwe8PoFwncsXMkNh19fsDvPOM9fjzD56BjdPtCM8oilm7pFhlxi563lpQJX5ojqIFcWAsYl9xpNTQs7PzaCjFbL6PAGCWUn+EII9TRBgsgnNPXo+3nHUsPvlX1+J/3fAg2u1m9DcUDbkgUggHPhQYG04/Hi955xuh9z5RupmSAnAgSgB0TzoWx6xfgz33PIIDjz8JzQzHdUHCGAwCnHZ0F1++5HRMth3sPtiDo1QkfOMLSZ6aauTz14VOiyyZ0QhKaCn8ulivUQoJUARkMwWIvtdao+k5+NKvX4CHdu7BbQ/uRrfVgAigNQN+iKlj1mPDa1+J8ZedAOl0EOz0MVIBML8fCoAOQtDkONaedzrGj1qL3Xffi/k9e+F4LhAO8NFXn4KpjosD8wM0PTcCIqTSlIwSDp/sgn8+leFwPaLMilL3TyUIlGRgDCJgru9jvO3hoxeejK3brgG0QtgfoNFtYuPrzsT6158H3e0gmO/BCaXYelkBAnuzklqw1ghBaB17JI5atxr77roHe+7bBhXM4fh1Xcz3fYAFYRhCxY0+RASloiFdSqlKoUdDvFaUwFYJFCP0MHP6c/LFzNHrzJjvD3DCkavR4ADB7AxWn7QJR7/tDWi+9Fj4Ax/oDaLnXPGsXYv/4iyxjXt1ggBoeJg+9wyMHX0kdv/kx2iKD9Ih/EDQgJNenKkIzJwLCYnQE8H/vCuBWCqa5r+mwIvC11oj0BoEBdfvoTPexLpffhNWvfIXELou/PleBOAVWesp1QowNu1K8YQY/mo/gLdxA9a95a34Vq+PyZkA65rAIJAoZXLyipAIO/EINjyQlmx/zhShSvhVX6bgNTNCreFqjUHA2NJcg+M/8Ttw1q2H3+uDfN9svRx6lBWg02WjOa3kwjnwAc/BVQe72PpggA+v6+E1q3wQHAxY4BqKkCjBMAH/vHmDKndfVIKi1WutwcyR1WuNBgfYHrr4Rn8at6lxuNMK4dx8JPgFPEfXksOMgLiRN+g4wE7t4QtPKNx4IMAH1/dxwpiPfuiAY0VwHCeHB4pZQtEjvNi9QdHqqyw/EX5i9RxbPGuGxwH2hsC1/gR+EExgD1y0IZAwrG31wxWg5sEAvIgXxf+baeHueQ/vXt3D29cGGPMEA3bgisBVCspxUsEmIaHoBUwP8GJUhDrCtwles0YQMhwOIaxxh9/ANwfTuI/baJKgk/Q1LfJZuUu6qfjfris4IA7+ctcYbp4Z4NfWD3D2VIggZAyUAy/2AMmXqQxV3uDFEBZs7r4q1tuEH2gN0RoNDvFkoPAtfxo/CrsI4aBLjOVYLuQux42yAC4Engvc1W/i84+5+OUDA1y01seGNmMgDKVcuI5UgsRh2OCF6A2GxfqRIE8zQtbwdABfC/6v38W3/Ek8Ix5aJGhl3YxLPtxlu+GYcu0qgQ+Ff9rTwS0zHi5eO8DrVodwXMaAHXiOA6cAEosKYVr/C00RhuX0dVM7xFb/M7+Bq/1xbOEuFAgdkrjeunyHu9wPgBHVW8Y9wZPaxX940sXNBwZ4/3ofLxsP4WtAs8B1HDhOFhq01qkSjPIIh6sSLCS1M12+1hqhZnBs9ftCwvf8CXw/mMAMHHRiBpCXYJyoeAf3kDwIAFqABgFwgGtnW7h7u4v3rvHx5jU+ppuEQchgceEqgcSKkBBHVZZ+uCpBHas3BZ63+gjhOxxCNON6v4Vv+1N4jBvwSNBdFncvANsLW+4hfTAJt+QKZsXBf3m6g+v3u/jQ+j7OmQ4AxGFBorBQpJGLANEMC4dLSFhsapeQOdAarg6xI1T41mAaN4ZjEALaJEsGeWb3kbBYU3zXIrRlf6QsUevRmCe4P2jgc487eNvMAO9YG+DoTgA/kDgsqBKdXFSKouCfL2+wEJBXdPc6tnxPB5hh4LpBB9/1p7A7BnlYBqsXo/tYOFucM9oD7H7KpaNOxMhy9iJBYpsETA7+z94ObjwY4sPre/ilVSEcYgSxJ3AMIZuhwQwRzyeBNMrqiwWcPIXLUDqEo0P8NGzi64MpbNNNOAS0iZdN8Ok1skAka8QbqQAkHBzKzo140RXGXWC3uLjsiTHcuN/HB9b3cep4iJAZ2olIJMcSDhLvYFr+c5UpLNTdR99HaZ2OlaChA+wJCd/xJ/GDYAJ9Ucvj7hNrh0Qrycy1D2kLfh0M8BxZkWaCB0CUwo9mmtg65+K9a/p457oAk8TwmcFO5hFsKaMpjENZZRyG7pPvbWldQuGGmuFxCNaMa/02rvYnsJ2baJFEHnGZ4nzWsY1M+BLHYDsEOLQgsA42AARdRxCIi68+08HNBwJ8ZGMf50yFYGH4LPAcBcdRIKpmEqvCwlI8wlKYPK01QmZAh2hwiG2Bi38erMZdYQdYppzevB6S4oqnbNmjVLS2PQ8KQNa5DSzRusG2Au4fePjMIy4unI64g2O6AQahA80OPDcv5DpM4nOR09usXmtGgwPsD4Fr/XFcHUxin7hoR/55eayezSVkUR8WE8WLc/PrEAR2bXOfK8Gnay2ojC7Ni2yqqC36yr0t3HbQxfvW9fHWI3w0lEI/dOC4Dty4ymiGBVttIfkyG1PqPmBbvB8mdE5AHgtIB5AwxG1hC98IprFNt9AgQQdLB3nZgpus8VSI0tboZGW2SP7aldTkAYT18oIAyVK3Qg+39YKSl8YcwS7t4CtPdLH1wAAXr5/HiWMhQnYQKjdXbi4Wmmyl5+RBjFKChXTmJDX6iMJlCGs0wgBPBArfDKdxO4/DJwedJYI8s1E0iudSWP6QrV0wh3GIUKYzLNZm1nIW0JlwZcmTyChd35ZfVEGVgs8LgKABNCgiEK6baeLOWQ9vXd3Du9f5WNUK4Bt9B+I42dIww+KH9SSOEv7ofJ6hdZgSOg0doKcZP/Q7uDqcxk5qo0W85MKNSH4tooi5Mtm0GskBfTHWcJbPHRYCJqaDbEnLQhMRSgVtWxo9XPB51lokW9XXVYQ5OPi7XV3cOuPhwxv6OHvKB8RFn114InBYpZRyVZGpmC1UuX5bQ2auRl/ozvG0j58FTXwnmMKdMgZFlLr7JVk9Zw+nCPBM5C+juID4PahWFsCLvWRlxPl42cwIdz8MaZtjoEKJKIwxF3iw38DnHnFw4fQAl2zs46i2xiBwoZO+gyFp4zAPUDetiwo3UXeOqwPsDoFrgin8UE9hlly0l8jkFZF9IuB0Caq5WEjyy85tgk88AIkqLxtbThAY7cUsOVdfz+qLP2eDWXI3Ev++QQImhav2trF11sP71vZx4REBOi5j4DM8lyExNkgwQrE7uY4HKNK3ZmpHOgTCEDcFbXw7nMajUujOWQZ3nx9koaxhYKjg49XGSqIhlSKHohhkgIx0jl4Nl58tm5IcWBm2P0AqoKTA5ABPhy7+5Ikurtsf4DeO7OEVEwH8kBEywzN6DsywUEcBEuHnBB+DPE/7eDxw8I3gCNwhY9Bw0Flid07e6rNRcym6N5F/wXhKwk/mG6U/GjisXhpICxQ8agmv/LqULH6Y4EtMIgCXAM8l3D7TxMMPOvjVIwZ45/oAqxsB+sxwYpCYeIMEGNoUoKo7J9TRvx4HmAsY3wkncK2ewDNoogWBs8TULlXqHLqPhc/lmUbDrD5y9YTi0Ij03lDHA7DGsNFBGcCDsYyXFhTns9fUggRfyCLTRZ9dRzAnDv72qTZu3u/hQxv7eNUqDQXBgFXOGzCzlTiqEj5xVLi5x2/gqnAKd2MMDhKQR4vOl/JkjhjjkChTCOSniGXIvhjnk+HUVJosw/GS/qpIXOYB9j/L6uhTytVAUeXJGbIwwdsAXl2Lz0GLxB1S5g0UBF0HeKDn4bMPO3jD3gE+sHGA48Y0+kEUFtwkFMSrck3KOF+rF3Dce/90SPhOMI2b9CR65KIVT/5k0JLivORGzRSzp6LFS762nxtYlc4XySacJcBRDEwmZB2iWuYBWCs7fVtfUHaAJwWARwtKE834Bikog0GQNRVDhPDt3S1snfHwoY0DvGFNgBY0BtqBoxQco55QtH7NAkdCaK1xU9DGleFqPIY22sRox1a/tKKNpDOCEvo2i9PV7t5mTEoMxUkmpkkWVkio8vwhGCBv4SKo7dbLAM/8eXFWX0wDxIQMpXlU2UyecQ/YFSp8cXsLP9zj4CNHDvCKiQABE0KoaBCDcbKOx+B4OsTDoYur9BHYyhMAEbpLyOmriRxlzDvMx/9UTyxxPqJ6o+dpDqMWsxIoqpQGFsPGCBCoorTOnKaBuiwekB+LthyCj93gEMEXj5AFLgDPBW472MQ9My7et76Pd6zrY8rT6LNZPgZaEmI/E64Jp3CtTGE/GmhRFOWXiu5LRE4ydbxk6SY4lhLAy8KnVKaEqfDTuQLm86rBA7BQNsJswYJH7bSursWXY39dnBGPd2KgrQSBOPjbnV1ct7eBjxw5i1dN9KGFIBwNlboFE/ierMFD6MBDVriRpVi94ZLT+7C8bqJ2kQLXn46UIyvJkymZQjLapsirJPLg2jyA1LVSspZNF5PWFRsFqly9VIIMExwl+W92jkK0nnF738Wlj0zgtZMNvO+IGXhNwg94PX5CqxGQikEeLd7dG3G+RN+KSd9SCeQVn2WG5u1pXb7SaitfU9opRCzxRLUFEEGj0b1YBE9Da+pmSlcgDePmhaIyjECXpc+hin0iIqE0KULw39vXxdaZBqbXNtFfPYmWEjS1zjadWEqsN/P53Hhci8se6sWieUt5LCDZ0CpRFV6BclXEJHvjeiAQ2UwawoiHXRZ8XYsXKte4ZQnu3iiKDf38hK/sOoy97GDPkyHGDuzD1IYu2l0v7qJF7WKY5Fg6kxchY6+DzOqL8b34PJUk081UIonC3yaj86lQ+k0yKyoPoxTUZwKH1eiLg5QXI3jbm1snpptj34FFWX2lB4vf1hEBFGFuVtB75CAmVzcxubYD11PgcHhFNA/wsnw+c/cZDpCKglPe82UbYiRTThPrlXS3ElPAZtpH1fijAEIXXAsoDl7OC34JwmcDGFFZQ6WWuy+6knqfLQVErZRAWLD36R5m9wdYtb6DsVXNyG2ylBpQy3E+zpwo782KQ6JtvL2kI2IpNztbTI+Sc/V5b1B879L09fQ67bbkVpm7TQDLYvVJfCRbqlcTOBa0vj45VVRezoUx5SoEA8Yzj85i7mCA1Rva8FoOWMsQgJfk58Vcn0by9hCkewHks4BsEH46b7z03mR9bxJYK6moyGjKCtBoKmFzMwOTt6+X1tkAXm7C9pChoUPjvJB9cnztNDXdRqKw9VzsWjnbEnxmTx+9GR9Ta1uYWNMCKURhITf+k3Ij3EYNfcpX68gKBtmgd0nM7EZQMnIR6yhds8cyDU9cd11Ae6IlMQpaLItXRvZiVwgs1OqxCHefF3ze6pU1zJEAcIAgYDy7Yw6z+32sWt9Gu+tG3ECKOSiH+m3IPlfqTelZVUbuqUBVKa3NkL3kKHQpbE8jafOIOT45Cm+Euj2BoT/I3txZPJGTAyRYEItXx93Xi/PGBgsFd5/1LYq9PBvhQ8Ah9GcC7JwLMbWmicl1bTgOxWGBS0A53rzDeq2mRZcUBNFUfjKFKChUAk3quLgzSVnwKBWEaigAH9yro4HFyhhYvLCHT5zF+UULvgLk1RM8wdwQNi8QVUuhlWGF4kQXs++ZPuYPhphc20J3qhHtgsTVDZdptS5Zm2elbymdDm7P5y2VQLH0/Bep5FzzaHXZuhwCHDfLMWVx1TpeKsDDwtI6MxfOBC8FwZeBa9qTVNx2TgDObX0XEzKOoN8L0X9sFmP7G5ha14bXUnmQaFp8Klhzj0IU0rpy+VaKPRZGWkfId0ZJsmNqYa1Ajj1MVwfVzAIW2tFbrM9XsXijiZylCN6M81Jy91aQWggAKu2cEuS5OAUBQ1igVHSNs/t99GYDTBzRwviqJpQiaB0Vi5UYOyEXSrq5HQMq6NscFWzuGmJB90nziNV7GrWFaA/tBfUEUn2rL3TqjBK8Dd0vDuDJEIBnWoHkLb7QU5BYvc7t26eMlIohlOx6FiuLInAo2LtzHr2DPqbWttHqOtFmH0zptnclFk/yNZSc1Qvl6xli+b6YBQzzHKaMmOpVA4t15BTJkyW+WXY6ey7cvS2fH8VTmNadXLO5XxPDdNuEYhsV2TqdKdoUvTcTojc3i/FVDUyubsF1I2wguZhNhoAl57lECrjeKASZCiwFZSh6jTJZhZQidoRhW4hsWRpmif00okxbK58vagctIa0z0b02NF9Zq2lCebeeKnXR1eeEPLpAljz4aI9swcFn++jNhJhe20Jn3I3dM6Us30gWj6WE7G3o3lZGLp3Dxg5mwmAWcOBPLZgKtlm9VIA8qcXbL5W+JQPZj8jnU4ImH+fFtPgY4JnVs7qCN+OdSLRndjBg7Noxh86kh6nVbTSaDrTmgtBtCjE6rcvc/hDBZ8Age84CCDOU12gvTgFMl7LItG5pgqec1YvonDJUAUxtAXgmxapkYX0Lmacx4XU+xUr2FZrd66M/E2J8dQPjU614zWJBSSvy+exXNgyg7BXZRHc5DolF1B+tEKWFKYC5EVceZNcu2Cymr7AK5NnTOlRmLFTcZxpZs6RKc2OphUGyH7kEuGznKZegtWDf0xF3ML22hUbLja4hcfVVyL5qMajFa0TuHsYK4fyq4GQ0CJECa72/ngJEOxgBipZI5Cw1n6eCxVekdUWLKeb5xm9UugempJtI1iuHV4WAivOScWsKGMwHeGZHiPHJBsamm3BcBQnFwkJWlW+VvX8gWY7HQFWPgcmKCtxeDR7AAClVLVmHNK0rkjlF+tby4FDeOTQhc1JsL8Y+m8kwpRFL2SJB8xDBSy3vRk5kCAf2DDA/E2JiTROdMQ8klMvNq9G9WNF90uifqw9YegKjhbsCIRkdAgTp/oSVbdc0NK3DAnoK7QDPns+PJqfIuAaJK27KWE4thb2F7ddGhQYYsm4BV79JNtsRnogQ+Bp7nppHb9zDxKoWHE9BNBtehgoZghkrKF2HmXUilYUvUuZypP6UMGS7V6uy1dMwZPwcsngMKSH71K3HKV3WZMFZLl6ZuVIpzmfxlGqEiYoMiPO5Z9JbMrffR38uxPh0E51xF6QIwqPQPWezfoSGZihFvECCeiuDIiqrPn17aFk8QXFbea6gb6UQBEyqlWoJMB/rimsaOCFoFin4ooekmEnct6uH+RkHE9MtNNuupa8A+Y7iKvBoUYjSGsJaxSApM4GHJp830zrJub9ibizIihnJR5r5vI3MqWelpnepRveyAMGX+hZI7K/Hv1MABvMau/vzGJtsoDvVgIrLzWDKpWKl6qDlevN9hyYpZl/A7trdshxi3j6JY2bcU9ZqHUmBvrUVbERZc+nRAM+0+PrKLBWbXOewA6Fa8EYFMGISI2Lr4N4e+nM+utMttDpeJAuWijQYlW1hpTCSLC6pOSy68mHWabseDvBMd48Ci1dw9ZRfyULIVqPbWLyFkTlmnKfi5uBDuWCxLkhJHtzoDiYUavhpi1hMKft9hv/UPNpjHsYmm3Ab0dCrwoLggqcst4uRubBEFrA8PCsgGHPDl9SVYwqonM+XqFCppm91DvgtdM0hGZNM7GmdVLj7obhBRsR/2Js38ulSnN5Ksl5R0JsJ4Pc0ulMe2mMNgOL1CihbfWFlXtb+VRojW0cBYEs7llqtS9xXtmZQYMcYpcVlRpk2KcdSen4d3t4CgYQqJ2vRQgVPUttD2jutqbBwU9ICk9aMA7v76M9rdCcbaDQcY+ZfoRHUtPoSVRynswypoQDJFJDFtF0nl2K2Y+kSfTsqjKRNjsbK3Fy1Lumnr0T3ZEX2Q0unC43zZZ55uKsvCF+SMuWoZ0GEwXwAvx+iPeahM96AUpmXyZePpRD/zUGRDAn1qtohoMj41I/z5UUMdfN50wbY4u5tRE752oqDqyxIeUicr1aICqvnIcWzip8XkkEl2aiIYO5AgMG8RneqgWbLzZfuS4ScZLOlQCBmkHI7oxWAYacfa+fzJlqtZvFsgjcXRFD837BSc3VaZ6+XY6EAb4jVyyKsfiEZlNkgQnE3DxEQBhoHnu2h1XExNtGA40Rzj7L3UinxhdQ7xGNyHTWoXQ0cti6vjEZpKJFDWeW0FLupIHiTt0/GntAIa8mXaZM1DVT7nioFD4vV29D9IgVvzVLISBEl8XPKSM+jV3pzIQZ9je6Yh1bXje6eI9ZTDJApIilzKJb5Nm7lRdVYHZxdWLE+T1aenq1x3kzrbPn8sJhto29VxXyi+mC2ksWrldYtfgmbmf2QmeVAWyd86FBwcP8A/Z5Gd8KD5ylIsbiUrhgma3bjVqcAVHGvprvXFk9QvrniZIoiizcsnx9ae8ghMFq64ItunQRStbBuqNXTglcySVx3sD8HuxFQvDxt0A8R+BrtMRftjhc3pUg2qV3Szt0aPYFKOcWrLFfD2IK4R0/9ImNgpRTInPpovBjnOc+DLyLOLyitswxnzi+opVrpqRnnES8XIyygBlNQhAgk+ujPh+iON9BoushNC2eGCJrF9yhNTBw8fu++7C3FMr+3uLaOhnbl5Fk8ia0+LtVWDDAexuLlp5MIRFTZW1WAKmshiw0Wz3T3XG31hQvKB3CunkJasviMAxxx3zVxSwwSD+4dYPbAADrkWJIsymmw/8CP9xVPcUoaEfo7mkeddDE2Hg/pz8eRI0b22dOiYsFIxU84+rv41gwEKnGfWrRwIl3yTCmzkRY9ks8qVOayOqgxlAG5Uln+PKO0XHw9XjCZbqpjvi9L6W+RKn3+tdy1MKo/23wtCXySGUYSEBn56xx6P9b7zt4z9DX8fggSiDu5SvHDd9Dsd758sb/3qW0oMzP5Y/LMN39y/K0fu8w58Vxo9jPXlg4vZggzzAZJkmgHsGJax2aRVowKYCJZFkApu3stkX2SrSVI4r61C8XWOUQWPp3je8p/FuWYWqmgbzOQZ+6CU+zjL67llVTwTvw6GyvOjWofwbg2LmUwUlFrITLYV2Yo5aC15/55//t/9scHt3z3i8WSYFkBLrrcwRXv0eMvPe0tY2/67c84Lz19nZ47MBGvlQVE4LiepxSNZ+mmAAQOQ30AOhSCQhFIEwB0x/dBAJ4/MA0RKFJN5XqNELRLgkFbCg9fYjOhUjyuAkplCpgoTwdnJQ5JlaK08EUEolxftccP6PmDU8TaMzVEyEzRRuADmKuRDJDHAFyvj2Z7RuYProEIpViIlED3RelgH9wmheSssnZZUT6ckXJYQfaTP6sFgHKamg7u2KVv//oXDtx3wzXYLAqX0nJuPr5yrBwrx8qxcqwcK8fKsXKsHCvHyrFyrBwrx8qxcrxQjv8PBw4vD7+nsBsAAAAASUVORK5CYII="
                    val gmailIconBytes = android.util.Base64.decode(
                        gmailIconBase64,
                        android.util.Base64.DEFAULT
                    )
                    setImageBitmap(
                        android.graphics.BitmapFactory.decodeByteArray(
                            gmailIconBytes,
                            0,
                            gmailIconBytes.size
                        )
                    )
                } catch (_: Exception) {
                    try {
                        setImageDrawable(
                            packageManager.getApplicationIcon("com.google.android.gm")
                        )
                    } catch (_: Exception) {
                        setImageResource(android.R.drawable.ic_dialog_email)
                    }
                }

                scaleType = android.widget.ImageView.ScaleType.CENTER_INSIDE
                isClickable = false
                isFocusable = false
                isLongClickable = false
            }

            addView(
                gmailIcon,
                android.widget.FrameLayout.LayoutParams(
                    dpToPx(16),
                    dpToPx(16),
                    android.view.Gravity.CENTER
                )
            )

            setOnClickListener {
                try {
                    val launchIntent = android.content.Intent(
                        android.content.Intent.ACTION_MAIN
                    ).apply {
                        addCategory(android.content.Intent.CATEGORY_LAUNCHER)
                        setPackage("com.google.android.gm")
                        addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    }

                    val resolved = packageManager.queryIntentActivities(
                        launchIntent,
                        0
                    )

                    if (resolved.isNotEmpty()) {
                        val info = resolved[0].activityInfo
                        launchIntent.setClassName(info.packageName, info.name)
                        startActivity(launchIntent)
                    } else {
                        val fallback =
                            packageManager.getLaunchIntentForPackage("com.google.android.gm")
                        if (fallback != null) {
                            fallback.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                            startActivity(fallback)
                        }
                    }
                } catch (_: Exception) {
                    try {
                        val fallback =
                            packageManager.getLaunchIntentForPackage("com.google.android.gm")
                        if (fallback != null) {
                            fallback.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                            startActivity(fallback)
                        }
                    } catch (_: Exception) {
                    }
                }
            }
        }

      // WINX_MICROSOFT_BUTTON_PATCH
        // EXACT USER-SUPPLIED IMAGE:
        // Adobe_20230903_191353.png
        //
        // The Python patch copies the exact PNG into:
        // app/src/main/res/drawable-nodpi/microsoft_adobe.png
        //
        // No Base64.
        // No BitmapFactory.
        // No pixel scanning.
        // Gmail remains completely untouched.

        val winXMicrosoftButton =
            android.widget.FrameLayout(this).apply {

                isClickable = true
                isFocusable = true
                isLongClickable = false

                val microsoftIcon =
                    android.widget.ImageView(
                        this@NavigationOverlayService
                    ).apply {

                        setImageResource(
                            R.drawable.microsoft_adobe
                        )

                        scaleType =
                            android.widget.ImageView.ScaleType.CENTER_INSIDE

                        isClickable = false
                        isFocusable = false
                        isLongClickable = false
                    }

             // EXACT visible Microsoft icon size:
addView(
    microsoftIcon,
    android.widget.FrameLayout.LayoutParams(
        dpToPx(20),
        dpToPx(20),
        android.view.Gravity.CENTER
    )
)

                setOnClickListener {
                    try {
                        val intent =
                            android.content.Intent(
                                android.content.Intent.ACTION_VIEW,
                                android.net.Uri.parse(
                                    "https://apps.microsoft.com/"
                                )
                            ).apply {
                                addFlags(
                                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                                )
                            }

                        startActivity(intent)

                    } catch (_: Exception) {
                    }
                }
            }

        // WINX_MICROSOFT_BUTTON_PATCH_END
        // WINX_GMAIL_POSITION_PATCH
        // shouldSwap: Recent | Clock | Gmail | SPACE | Microsoft | Home | Back
        // normal:    Back | Home | Microsoft | SPACE | Gmail | Clock | Recent
        if (shouldSwap) {
            // Recent | Gmail | SPACE | Microsoft | Clock | Home | Back
            // winXSpacer was already inserted above; never add it a second time.
            container.addView(
                winXGmailButton,
                2,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0f
                )
            )
            container.addView(
                winXMicrosoftButton,
                4,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0f
                )
            )
        } else {
            // Back | Home | Microsoft | Gmail | SPACE | Clock | Recent
            // winXSpacer was already inserted above; never add it a second time.
            container.addView(
                winXMicrosoftButton,
                2,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0f
                )
            )
            container.addView(
                winXGmailButton,
                3,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0f
                )
            )
        }
        // WINX_GMAIL_POSITION_PATCH_END

        // WINX_CLOCK_LAYOUT_PATCH_END
'''

    code = code[:insert_pos] + clock_layout_patch + code[insert_pos:]


# ============================================================
# 7. CONTAINER GRAVITY
# ============================================================

if "WINX_CLOCK_GRAVITY_PATCH" not in code:
    old = "container.gravity = Gravity.CENTER"
    new = r'''container.gravity =
        if (isVerticalBar)
            Gravity.CENTER_HORIZONTAL
        else
            Gravity.CENTER_VERTICAL

        // WINX_CLOCK_GRAVITY_PATCH'''

    if old in code:
        code = code.replace(old, new, 1)
    else:
        print("Warning: container.gravity line not found; leaving original gravity")


# ============================================================
# 8. CLOCK CLEANUP
# ============================================================

if "WINX_CLOCK_CLEANUP_PATCH" not in code:
    match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )
    if match:
        cleanup = r'''
        // WINX_OVERLAY_HEALTH_CLEANUP
        winXOverlayHealthRunnable?.let {
            handler.removeCallbacks(it)
        }
        winXOverlayHealthRunnable = null
        winXOverlayHealthRecoveryRunning = false
        // WINX_OVERLAY_HEALTH_CLEANUP

        // WINX_CLOCK_CLEANUP_PATCH
        handler.removeCallbacks(winXClockRunnable)
        winXClockStarted = false
        winXClockTextView = null
        winXDateTextView = null

'''
        code = code[:match.end()] + cleanup + code[match.end():]


# ============================================================
# 8.5. LOCK / UNLOCK RECOVERY ONLY
#      Restore the overlay after the screen is unlocked.
#      Do not change Win-X, fullscreen, Gmail, clock/date, or Swipe/Reveal.
# ============================================================

if "WINX_LOCK_UNLOCK_RECOVERY_PATCH" not in code:
    class_match = re.search(
        r"(class\s+NavigationOverlayService[^\{]*\{)",
        code,
    )
    if not class_match:
        raise RuntimeError("NavigationOverlayService class not found")

    recovery_fields = r'''

    // WINX_LOCK_UNLOCK_RECOVERY_PATCH
    private var winXScreenReceiverRegistered = false

    private val winXScreenReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(
            context: android.content.Context?,
            intent: android.content.Intent?
        ) {
            when (intent?.action) {
                android.content.Intent.ACTION_SCREEN_OFF -> {
                    winXOverlayHealthRunnable?.let {
                        handler.removeCallbacks(it)
                    }
                }
                android.content.Intent.ACTION_SCREEN_ON,
                android.content.Intent.ACTION_USER_PRESENT -> {
                    handler.postDelayed({
                        if (!isWinXLauncher) {
                            forceShowAfterWinX()
                            checkWinXStateDelayed()
                        }
                    }, 700L)
                }
            }
        }
    }
    // WINX_LOCK_UNLOCK_RECOVERY_PATCH_END
'''

    code = code[:class_match.end()] + recovery_fields + code[class_match.end():]

    service_match = re.search(
        r"(override\s+fun\s+onServiceConnected\s*\(\s*\)\s*\{)",
        code,
    )
    if not service_match:
        raise RuntimeError("onServiceConnected() not found")

    register_code = r'''
        // WINX_LOCK_UNLOCK_REGISTER
        if (!winXScreenReceiverRegistered) {
            val screenFilter = android.content.IntentFilter().apply {
                addAction(android.content.Intent.ACTION_SCREEN_OFF)
                addAction(android.content.Intent.ACTION_SCREEN_ON)
                addAction(android.content.Intent.ACTION_USER_PRESENT)
            }

            try {
                if (android.os.Build.VERSION.SDK_INT >= 33) {
                    registerReceiver(
                        winXScreenReceiver,
                        screenFilter,
                        android.content.Context.RECEIVER_NOT_EXPORTED
                    )
                } else {
                    registerReceiver(winXScreenReceiver, screenFilter)
                }
                winXScreenReceiverRegistered = true
            } catch (_: Exception) {
            }
        }
        // WINX_LOCK_UNLOCK_REGISTER

        // WINX_OVERLAY_HEALTH_CONNECTED
        scheduleWinXOverlayHealthCheck(500L)
        // WINX_OVERLAY_HEALTH_CONNECTED

'''
    code = code[:service_match.end()] + register_code + code[service_match.end():]

    destroy_match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )
    if not destroy_match:
        raise RuntimeError("onDestroy() not found")

    unregister_code = r'''
        // WINX_LOCK_UNLOCK_UNREGISTER
        if (winXScreenReceiverRegistered) {
            try {
                unregisterReceiver(winXScreenReceiver)
            } catch (_: Exception) {
            }
            winXScreenReceiverRegistered = false
        }
        // WINX_LOCK_UNLOCK_UNREGISTER_END

'''
    code = code[:destroy_match.end()] + unregister_code + code[destroy_match.end():]

# ============================================================
# 8.9. COPY THE EXACT ADOBE IMAGE
#      Gmail is NOT touched.
# ============================================================

icon_path = (
    Path(__file__).resolve().parent
    / "Adobe_20230903_191353.png"
)

if not icon_path.is_file():
    raise FileNotFoundError(
        "Required exact Microsoft icon not found: "
        + str(icon_path)
    )

import shutil

project_root = (
    Path(__file__).resolve().parent
    / "opennavbar"
)

drawable_dir = (
    project_root
    / "app"
    / "src"
    / "main"
    / "res"
    / "drawable-nodpi"
)

drawable_dir.mkdir(
    parents=True,
    exist_ok=True
)

microsoft_drawable = (
    drawable_dir
    / "microsoft_adobe.png"
)

shutil.copyfile(
    icon_path,
    microsoft_drawable
)

# ============================================================
# 9. SAVE
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("================================================")
print(" OPENNAVBAR WIN X + CLOCK PATCH")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide only on Win X launcher")
print("Clock: 9sp time / 9sp date / group rotation / 1dp gap / non-touch")
print("Gmail: custom supplied icon / 16dp")
print("Gmail: 16dp icon / beside Home on clock side")
print("Xiaomi Community: removed")
print("Microsoft: EXACT Adobe_20230903_191353.png / 20dp visible logo / overlay health recovery / Windows-style 40dp button slots")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
