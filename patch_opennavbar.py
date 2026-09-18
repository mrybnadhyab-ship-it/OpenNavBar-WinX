#!/usr/bin/env python3
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

# Keep the existing successful WinX patch. Only debounce WinX state changes
# so a transient AccessibilityEvent cannot make the navbar flicker/disappear.

if 'private var isWinXLauncher = false' not in s:
    m = re.search(r'(class\s+NavigationOverlayService[^\{]*\{)', s)
    if not m:
        raise SystemExit("Could not locate NavigationOverlayService class.")
    insert = m.group(1) + '''
    private var isWinXLauncher = false
    private var winXStateRunnable: Runnable? = null
    private companion object {
        const val WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"
    }
'''
    s = s[:m.start()] + insert + s[m.end():]

# Replace the existing WinX foreground-package block robustly.
if 'val targetState = foregroundPackage == WINX_PACKAGE' not in s:
    fg_pos = s.find("val foregroundPackage = event.packageName?.toString()")
    if fg_pos == -1:
        raise SystemExit("Could not locate foregroundPackage in NavigationOverlayService.")

    after_fg = s.find("\n", fg_pos)
    if_pos = s.find("if (nowWinX", after_fg)
    if if_pos == -1:
        if_pos = s.find("if (!nowWinX", after_fg)
    if if_pos == -1:
        if_pos = s.find("if (nowWinX !=", after_fg)
    if if_pos == -1:
        raise SystemExit("Could not locate the existing WinX detection block.")

    brace = s.find("{", if_pos)
    if brace == -1:
        raise SystemExit("Could not locate WinX if opening brace.")

    depth = 0
    close = -1
    for i in range(brace, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                close = i + 1
                break
    if close == -1:
        raise SystemExit("Could not locate WinX if closing brace.")

    replacement = """val foregroundPackage = event.packageName?.toString()
            if (!foregroundPackage.isNullOrEmpty()) {
                val targetState = foregroundPackage == WINX_PACKAGE
                winXStateRunnable?.let { handler.removeCallbacks(it) }
                val pendingState = targetState
                winXStateRunnable = Runnable {
                    if (pendingState != isWinXLauncher) {
                        isWinXLauncher = pendingState
                        if (pendingState) {
                            hideOverlay()
                        } else {
                            showOverlayAnimated()
                        }
                    }
                }
                handler.postDelayed(winXStateRunnable!!, 500L)
            }"""

    line_start = s.rfind("\n", 0, fg_pos) + 1
    s = s[:line_start] + "            " + replacement.strip() + s[close:]

# The successful patch must be allowed to restore the navbar after leaving WinX.
# Remove only an accidental global guard before showOverlayAnimated().
s = re.sub(r'\n\s*if \(isWinXLauncher\) return\n', '\n', s, count=1)

# Clean up the pending callback when the service is destroyed.
if 'winXStateRunnable?.let { handler.removeCallbacks(it) }' not in s:
    marker = 'override fun onDestroy()'
    pos = s.find(marker)
    if pos != -1:
        brace = s.find('{', pos)
        if brace != -1:
            s = s[:brace + 1] + '\n        winXStateRunnable?.let { handler.removeCallbacks(it) }\n' + s[brace + 1:]

p.write_text(s, encoding="utf-8")
print("Patched WinX anti-flicker:", p)

# ============================================================
# 2. GMAIL BUTTON (16dp) - next to Home on the clock side
# Keep all existing WinX, clock/date and Swipe/Reveal code unchanged.
# ============================================================

if "WINX_GMAIL_BUTTON_PATCH" not in s:
    gmail_kotlin = r'''

        // WINX_GMAIL_BUTTON_PATCH
        val winXGmailButton = android.widget.FrameLayout(this).apply {
            isClickable = true
            isFocusable = true
            isLongClickable = false

            val gmailIcon = android.widget.ImageView(this@NavigationOverlayService).apply {
                setImageResource(R.drawable.gmail_custom)
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
                    val intent = packageManager.getLaunchIntentForPackage("com.google.android.gm")
                    if (intent != null) {
                        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                    }
                } catch (_: Exception) {
                }
            }
        }
        // WINX_GMAIL_BUTTON_PATCH_END
'''

    # Locate the existing order block. Do not replace it; only add Gmail next to Home.
    order_re = re.compile(
        r'(?ms)(val\s+order\s*:\s*List<View>\s*=\s*if\s*\(shouldSwap\)\s*\{)(.*?)(\}\s*else\s*\{)(.*?)(\}\s*)\n(\s*order\.forEachIndexed)'
    )
    m = order_re.search(s)
    if not m:
        order_re = re.compile(
            r'(?ms)(val\s+order\s*=\s*if\s*\(shouldSwap\)\s*\{)(.*?)(\}\s*else\s*\{)(.*?)(\}\s*)\n(\s*order\.forEachIndexed)'
        )
        m = order_re.search(s)
    if not m:
        raise SystemExit("Could not locate the navigation order block for Gmail insertion.")

    normal = m.group(2)
    swapped = m.group(4)

    if "winXGmailButton" not in normal and "homeButton" in normal:
        normal2 = re.sub(
            r'(\bhomeButton\s*,)',
            r'\1\n                    winXGmailButton,',
            normal,
            count=1,
        )
    else:
        normal2 = normal

    if "winXGmailButton" not in swapped and "homeButton" in swapped:
        # Swapped layout: keep Gmail immediately on the clock-side of Home.
        swapped2 = re.sub(
            r'(\n\s*)(homeButton\s*,)',
            r'\1winXGmailButton,\n\1\2',
            swapped,
            count=1,
        )
    else:
        swapped2 = swapped

    if normal2 == normal and swapped2 == swapped:
        raise SystemExit("Could not insert Gmail beside Home.")

    # Remove only the existing separation after Home so Gmail sits close to it.
    # The spacer/clock spacing and all other button spacing remain unchanged.
    s = s.replace(
        "if (item === clockView)\n                            0\n                        else\n                            separation",
        "if (item === clockView || item === homeButton)\n                            0\n                        else\n                            separation",
        2,
    )

    # Declare the Gmail button immediately before the order list.
    order_start = m.start(1)
    s = s[:order_start] + gmail_kotlin + "\n" + s[order_start:m.start(2)] + normal2 + s[m.end(2):m.start(4)] + swapped2 + s[m.end(4):]

    # Create a compact blue Gmail-style envelope vector. The displayed size is 16dp.
    source_path = p.resolve()
    res_dir = None
    for parent in source_path.parents:
        candidate = parent / "src" / "main" / "res"
        if candidate.is_dir():
            res_dir = candidate
            break
    if res_dir is None:
        raise SystemExit("Could not locate app/src/main/res for Gmail icon.")

    drawable_dir = res_dir / "drawable"
    drawable_dir.mkdir(parents=True, exist_ok=True)
    gmail_xml = '''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="16dp"
    android:height="16dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
    <path
        android:fillColor="#4285F4"
        android:pathData="M3,5h18c0.55,0 1,0.45 1,1v12c0,0.55 -0.45,1 -1,1H3c-0.55,0 -1,-0.45 -1,-1V6c0,-0.55 0.45,-1 1,-1zM4,7v0.2l8,6 8,-6V7H4zM20,17V9.7l-7.4,5.55c-0.36,0.27 -0.84,0.27 -1.2,0L4,9.7V17H20z" />
</vector>
'''
    (drawable_dir / "gmail_custom.xml").write_text(gmail_xml, encoding="utf-8")

p.write_text(s, encoding="utf-8")
print("Patched WinX anti-flicker + Gmail 16dp beside Home:", p)
