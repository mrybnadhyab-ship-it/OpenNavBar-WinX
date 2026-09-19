import re
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print("Usage: python3 patch_lock_screen_fix.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = Path(sys.argv[1])
code = path.read_text(encoding="utf-8")

MARKER = "WINX_LOCK_SCREEN_RECOVERY_V2"

if "import android.content.BroadcastReceiver" not in code:
    anchor = "import android.content.Context"
    if anchor not in code:
        raise RuntimeError("android.content.Context import not found")
    code = code.replace(anchor, anchor + "\nimport android.content.BroadcastReceiver", 1)

old_start = code.find("// WINX_LOCK_UNLOCK_RECOVERY_PATCH")
if old_start >= 0:
    old_end_marker = "// WINX_LOCK_UNLOCK_RECOVERY_PATCH_END"
    old_end = code.find(old_end_marker, old_start)
    if old_end >= 0:
        old_end += len(old_end_marker)
        code = code[:old_start] + code[old_end:]

if MARKER not in code:
    class_match = re.search(r"(class\s+NavigationOverlayService[^{]*\{)", code)
    if not class_match:
        raise RuntimeError("NavigationOverlayService class not found")

    recovery = """
    // WINX_LOCK_SCREEN_RECOVERY_V2

    private var winXScreenReceiverRegistered = false

    private val winXScreenReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_OFF -> {
                    try { hideOverlay() } catch (_: Exception) {}
                }

                Intent.ACTION_SCREEN_ON,
                Intent.ACTION_USER_PRESENT -> {
                    handler.postDelayed({
                        try {
                            checkWinXStateDelayed()

                            handler.postDelayed({
                                if (!isWinXLauncher) {
                                    try {
                                        if (overlayView == null) {
                                            showOverlay()
                                        } else {
                                            forceShowAfterWinX()
                                        }
                                    } catch (_: Exception) {}

                                    handler.postDelayed({
                                        if (!isWinXLauncher) {
                                            try {
                                                if (overlayView == null) {
                                                    showOverlay()
                                                } else {
                                                    forceShowAfterWinX()
                                                }
                                            } catch (_: Exception) {}
                                        }
                                    }, 500)
                                }
                            }, 500)
                        } catch (_: Exception) {}
                    }, 900)
                }
            }
        }
    }

    private fun registerWinXScreenReceiver() {
        if (winXScreenReceiverRegistered) return
        try {
            val filter = IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_USER_PRESENT)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                registerReceiver(
                    winXScreenReceiver,
                    filter,
                    Context.RECEIVER_NOT_EXPORTED
                )
            } else {
                registerReceiver(winXScreenReceiver, filter)
            }

            winXScreenReceiverRegistered = true
        } catch (_: Exception) {}
    }

    private fun unregisterWinXScreenReceiver() {
        if (!winXScreenReceiverRegistered) return
        try { unregisterReceiver(winXScreenReceiver) } catch (_: Exception) {}
        winXScreenReceiverRegistered = false
    }

    // WINX_LOCK_SCREEN_RECOVERY_V2_END
"""
    code = code[:class_match.end()] + recovery + code[class_match.end():]

start = code.find("private fun forceShowAfterWinX()")
if start < 0:
    raise RuntimeError("forceShowAfterWinX() not found")

brace = code.find("{", start)
depth = 0
close = -1
for i in range(brace, len(code)):
    if code[i] == "{":
        depth += 1
    elif code[i] == "}":
        depth -= 1
        if depth == 0:
            close = i
            break

if close < 0:
    raise RuntimeError("forceShowAfterWinX() closing brace not found")

new_force = """
private fun forceShowAfterWinX() {
        if (isWinXLauncher) return

        if (overlayView == null) {
            try { showOverlay() } catch (_: Exception) {}
            return
        }

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
    }"""
code = code[:start] + new_force + code[close + 1:]

service_match = re.search(r"override\s+fun\s+onServiceConnected\s*\(\s*\)\s*\{", code)
if not service_match:
    raise RuntimeError("onServiceConnected() not found")

body_start = service_match.end()
body_end = code.find("\n}", body_start)
if body_end < 0:
    raise RuntimeError("onServiceConnected() closing brace not found")

if "registerWinXScreenReceiver()" not in code[body_start:body_end]:
    code = code[:body_start] + "\n        registerWinXScreenReceiver()" + code[body_start:]

destroy_match = re.search(r"override\s+fun\s+onDestroy\s*\(\s*\)\s*\{", code)
if not destroy_match:
    raise RuntimeError("onDestroy() not found")

body_start = destroy_match.end()
body_end = code.find("\n}", body_start)
if body_end < 0:
    raise RuntimeError("onDestroy() closing brace not found")

if "unregisterWinXScreenReceiver()" not in code[body_start:body_end]:
    code = code[:body_start] + "\n        unregisterWinXScreenReceiver()" + code[body_start:]

path.write_text(code, encoding="utf-8")
print("Lock-screen recovery patch applied successfully.")
