package com.zariep.opennavbar

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.Context
import android.content.SharedPreferences
import android.content.res.Configuration
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import androidx.core.app.NotificationCompat
import androidx.preference.PreferenceManager
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import android.view.accessibility.AccessibilityWindowInfo
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.PowerManager
import android.view.MotionEvent
import android.view.ContextThemeWrapper
import com.google.android.material.color.DynamicColors
import android.media.AudioManager

class NavigationOverlayService : AccessibilityService(),
	SharedPreferences.OnSharedPreferenceChangeListener {

	private lateinit var powerManager: PowerManager
	private lateinit var windowManager: WindowManager
	private lateinit var prefs: SharedPreferences
	private lateinit var vibrator: Vibrator
	private var lastKeyboardState = false

	private var overlayView: View? = null
	private var revealZoneView: View? = null

	private var touchStartY = 0f
	private var touchStartX = 0f
	private val slideThreshold get() = dpToPx(prefs.getInt("slide_threshold", 30))

	private var currentOrientation = Configuration.ORIENTATION_PORTRAIT

	private val handler = Handler(Looper.getMainLooper())
	private var autoHideRunnable: Runnable? = null
	private var isHidden = false
	private var isRotating = false
	private val rotationSettleRunnable = Runnable { isRotating = false }
	private var isFullscreenHidden = false
	private var pendingNavBarsVisible: Boolean? = null

	private var insetsDebounce: Runnable? = null

	companion object {
		private const val NOTIFICATION_ID = 1001
		private const val CHANNEL_ID = "nav_overlay_channel"
	}

	// Hide navbar on AOD
	private lateinit var keyguardManager: android.app.KeyguardManager
		private var isLockHidden = false

		private val screenStateReceiver = object : android.content.BroadcastReceiver() {
			override fun onReceive(context: Context?, intent: Intent?) {
				when (intent?.action) {
					Intent.ACTION_SCREEN_OFF -> applyLockVisibility(false)
					Intent.ACTION_SCREEN_ON -> applyLockVisibility(!keyguardManager.isKeyguardLocked)
					Intent.ACTION_USER_PRESENT -> applyLockVisibility(true)
				}
			}
		}

		private fun applyLockVisibility(visible: Boolean) {
			isLockHidden = !visible
			if (visible) {
				currentOrientation = resources.configuration.orientation
				if (overlayView == null) showOverlay() else updateOverlayLive()
				if (revealZoneView == null) showRevealZone()
			} else {
				removeOverlay()
				removeRevealZone()
			}
		}
		//

	override fun onServiceConnected() {
		super.onServiceConnected()
		windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
		prefs = PreferenceManager.getDefaultSharedPreferences(this)
		vibrator = getSystemService(Vibrator::class.java)
		powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager

		keyguardManager = getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
		registerReceiver(screenStateReceiver, android.content.IntentFilter().apply {
			addAction(Intent.ACTION_SCREEN_OFF)
			addAction(Intent.ACTION_SCREEN_ON)
			addAction(Intent.ACTION_USER_PRESENT)
		})

		if (!prefs.contains("nav_width")) {
			val displayMetrics = resources.displayMetrics
			prefs.edit().putInt("nav_width", displayMetrics.widthPixels).apply()
		}

		currentOrientation = resources.configuration.orientation
		prefs.registerOnSharedPreferenceChangeListener(this)

		createNotificationChannel()
		startForeground(NOTIFICATION_ID, createNotification())

		showOverlay()
		showRevealZone()
	}

	private fun performHapticFeedback(duration: Long = 50) {
		if (!prefs.getBoolean("enable_haptic", true)) return

		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
			val effect = VibrationEffect.createOneShot(duration, VibrationEffect.DEFAULT_AMPLITUDE)
			vibrator.vibrate(effect)
		} else {
			@Suppress("DEPRECATION")
			vibrator.vibrate(duration)
		}
	}

	override fun onDestroy() {
		try {
			prefs.unregisterOnSharedPreferenceChangeListener(this)
		} catch (_: Exception) {}

		try {
			unregisterReceiver(screenStateReceiver)
		} catch (_: Exception) {}

		handler.removeCallbacksAndMessages(null)
		removeOverlay()
		removeRevealZone()
		super.onDestroy()
	}

	override fun onInterrupt() {}

	private var navBarCheckRunnable: Runnable? = null

	override fun onAccessibilityEvent(event: AccessibilityEvent?) {
		if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
			event?.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
			handleKeyboardStateChange(checkIsKeyboardVisible())

			if (prefs.getBoolean("hide_on_fullscreen", true)) {
				navBarCheckRunnable?.let { handler.removeCallbacks(it) }
				navBarCheckRunnable = Runnable {
					if (isRotating) return@Runnable
					val navBarPresent = isSystemNavBarPresent()
					if (!navBarPresent && !isHidden) {
						isFullscreenHidden = true
						scheduleTemporaryHide(prefs.getInt("auto_hide_delay", 3000).toLong())
					} else if (navBarPresent && isFullscreenHidden) {
						isFullscreenHidden = false
						if (!prefs.getBoolean("auto_hide_enabled", false) && !checkIsKeyboardVisible()) {
							showOverlayAnimated()
						}
					}
				}
				handler.postDelayed(navBarCheckRunnable!!, 200)
			}
		}
	}

	private fun isSystemNavBarPresent(): Boolean {
		return try {
			windows.any { it.type == AccessibilityWindowInfo.TYPE_SYSTEM }
		} catch (e: Exception) {
			true
		}
	}

	private fun handleKeyboardStateChange(isKeyboardVisible: Boolean) {
		if (isKeyboardVisible == lastKeyboardState) return
		lastKeyboardState = isKeyboardVisible

		val autoHideInSettings = prefs.getBoolean("auto_hide_enabled", false)
		val hideOnKeyboard = prefs.getBoolean("hide_on_keyboard", true)

		if (isKeyboardVisible) {
			if (hideOnKeyboard) scheduleTemporaryHide(prefs.getInt("auto_hide_delay", 3000).toLong())
		} else {
			if (!autoHideInSettings) {
				showOverlayAnimated()
				autoHideRunnable?.let { handler.removeCallbacks(it) }
			} else {
				if (!isHidden) {
					scheduleAutoHide()
				}
			}
		}
	}

	private fun scheduleTemporaryHide(delayMs: Long) {
		autoHideRunnable?.let { handler.removeCallbacks(it) }
		autoHideRunnable = Runnable { hideOverlay() }
		handler.postDelayed(autoHideRunnable!!, delayMs)
	}

	private fun checkIsKeyboardVisible(): Boolean {
		return try {
			windows.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
		} catch (e: Exception) {
			false
		}
	}

	override fun onConfigurationChanged(newConfig: Configuration) {
		super.onConfigurationChanged(newConfig)
		if (newConfig.orientation != currentOrientation) {
			currentOrientation = newConfig.orientation

			isRotating = true
			handler.removeCallbacks(rotationSettleRunnable)
			handler.postDelayed(rotationSettleRunnable, 500)

			updateOverlayLive()
			showRevealZone()

			// On rotate actions
			when (newConfig.orientation) {
				Configuration.ORIENTATION_LANDSCAPE -> executeAction("rotate_landscape", 40)
				Configuration.ORIENTATION_PORTRAIT -> executeAction("rotate_portrait", 40)
				else -> {}
			}
		}
	}

	private fun showOverlay() {
		if (overlayView != null) return

		val themedContext = ContextThemeWrapper(this, R.style.Theme_CustomNav).let {
			DynamicColors.wrapContextIfAvailable(it)
		}

		overlayView = LayoutInflater.from(this).inflate(R.layout.navigation_overlay, null, false)

		// Hide on fullscreen
		ViewCompat.setOnApplyWindowInsetsListener(overlayView!!) { _, insets ->
			val navBarsVisible = insets.isVisible(WindowInsetsCompat.Type.navigationBars())

			insetsDebounce?.let { handler.removeCallbacks(it) }
			insetsDebounce = Runnable {
				if (isRotating) return@Runnable
				val stillNotVisible = ViewCompat.getRootWindowInsets(overlayView!!)
					?.isVisible(WindowInsetsCompat.Type.navigationBars()) == false
				if (prefs.getBoolean("hide_on_fullscreen", true)) {
					if (stillNotVisible && !isHidden) {
						isFullscreenHidden = true
						scheduleTemporaryHide(prefs.getInt("auto_hide_delay", 3000).toLong())
					} else if (!stillNotVisible && isFullscreenHidden) {
						isFullscreenHidden = false
						if (!prefs.getBoolean("auto_hide_enabled", false) && !checkIsKeyboardVisible()) {
							showOverlayAnimated()
						}
					}
				}
			}
			handler.postDelayed(insetsDebounce!!, 200)
			insets
		}

		var flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
					WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
					WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
					WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL

		// Attempt to fix Android12- not overlaying system navbar
		val params = WindowManager.LayoutParams(
			0, 0,
			WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
			flags,
			PixelFormat.TRANSLUCENT
		)

		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
			params.fitInsetsTypes = 0
			params.fitInsetsSides = 0
		}

		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
			params.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
		}

		windowManager.addView(overlayView, params)
		updateOverlayLive()
	}

	private fun getScreenRotation(): Int {
		return try {
			if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
				@Suppress("DEPRECATION")
				overlayView?.display?.rotation
					?: windowManager.defaultDisplay?.rotation
					?: android.view.Surface.ROTATION_0
			} else {
				@Suppress("DEPRECATION")
				windowManager.defaultDisplay.rotation
			}
		} catch (e: Exception) {
			android.view.Surface.ROTATION_0
		}
	}

	private fun isLandscapeInverted(): Boolean {
		return getScreenRotation() == android.view.Surface.ROTATION_270
	}

	private fun getColorPreference(colorKey: String, useMonetKey: String, defaultStatic: String): Int {
		val useMonet = prefs.getBoolean(useMonetKey, false)

		if (useMonet && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
			val monetTag = prefs.getString("${colorKey}_monet_tag", MonetColors.MONET_SURFACE)
			val monetColor = MonetColors.getColorFromTag(this, monetTag)
			if (monetColor != null) return monetColor
		}

		return prefs.getInt(colorKey, Color.parseColor(defaultStatic))
	}

	private fun getCurrentBackgroundColor(): Int {
		val isPowerSave = powerManager.isPowerSaveMode
		return if (isPowerSave) {
			getColorPreference("background_color_powersave", "use_monet_background_color_powersave", "#FFFF0100")
		} else {
			getColorPreference("background_color", "use_monet_background_color", "#CC000000")
		}
	}

	private fun getCurrentButtonColor(): Int {
		val isPowerSave = powerManager.isPowerSaveMode

		return if (isPowerSave) {
			getColorPreference("button_color_powersave", "use_monet_button_color_powersave", "#FFFFFFFF")
		} else {
			getColorPreference("button_color","use_monet_button_color","#FFFFFF")
		}
	}

	private fun resolvePosition(): String {
		val isLandscape = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
		return if (isLandscape) {
			val pref = prefs.getString("nav_position_landscape", "natural") ?: "natural"
			when (pref) {
				"natural" -> if (isLandscapeInverted()) "left" else "right"
				"rotated" -> if (isLandscapeInverted()) "right" else "left"
				else -> pref // "bottom", "left", "right" used as-is
			}
		} else {
			prefs.getString("nav_position_portrait", "bottom") ?: "bottom"
		}
	}

	private fun updateOverlayLive() {
// 		if (isLockHidden) return
		val view = overlayView ?: return
		val position = resolvePosition() // "bottom" | "left" | "right"

		// LinearLayout orientation of the inside the bar
		val isVerticalBar = position == "left" || position == "right"
		configureOverlayView(view)

		val params = view.layoutParams as WindowManager.LayoutParams
		val screenWidth = resources.displayMetrics.widthPixels
		val screenHeight = resources.displayMetrics.heightPixels
		val prefWidth = prefs.getInt("nav_width", screenWidth)
		val prefHeight = dpToPx(prefs.getInt("nav_height", 60))
		val offsetX = prefs.getInt("nav_offset_x", 0)
		val offsetY = prefs.getInt("nav_offset_y", 0)

		when (position) {
			"bottom" -> {
				params.width = prefWidth
				params.height = prefHeight
				params.gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
			}
			"left" -> {
				params.width = prefHeight
				params.height = if (prefWidth >= screenWidth) WindowManager.LayoutParams.MATCH_PARENT
				else prefWidth
					params.gravity = Gravity.START or Gravity.CENTER_VERTICAL
			}
			"right" -> {
				params.width = prefHeight
				params.height = if (prefWidth >= screenWidth) WindowManager.LayoutParams.MATCH_PARENT
				else prefWidth
					params.gravity = Gravity.END or Gravity.CENTER_VERTICAL
			}
		}

		// Apply offsets: WindowManager uses x/y directly when gravity is set
		params.x = offsetX
		params.y = offsetY

		windowManager.updateViewLayout(view, params)
		isHidden = false
		view.visibility = View.VISIBLE
		view.alpha = 1f
		view.translationX = 0f
		view.translationY = 0f

		if (prefs.getBoolean("auto_hide_enabled", false)) {
			scheduleAutoHide()
		}
	}

	private fun removeOverlay() {
		autoHideRunnable?.let { handler.removeCallbacks(it) }
		overlayView?.let {
			windowManager.removeView(it)
			overlayView = null
		}
	}

	private fun showRevealZone() {
		removeRevealZone()

		val position = resolvePosition() // "bottom" | "left" | "right"
		val isVerticalBar = position == "left" || position == "right"
		val thicknessPref = prefs.getInt("reveal_zone_thickness", 5)
		val zoneThickness = dpToPx(thicknessPref)

		val rotation = try {
			overlayView?.display?.rotation ?: android.view.Surface.ROTATION_0
		} catch (e: Exception) {
			android.view.Surface.ROTATION_0
		}
		val isInverted = rotation == android.view.Surface.ROTATION_270

		val zone = FrameLayout(this).apply {
			setBackgroundColor(Color.TRANSPARENT)
			setOnTouchListener { _, event ->
				val requireSlide = prefs.getBoolean("require_slide_gesture", true)
				when (event.action) {
					MotionEvent.ACTION_DOWN -> {
						touchStartX = event.rawX
						touchStartY = event.rawY
						true
					}
					MotionEvent.ACTION_UP -> {
						val requireSlide = prefs.getBoolean("require_slide_gesture", true)
						val position = resolvePosition()

						val deltaX = event.rawX - touchStartX
						val deltaY = touchStartY - event.rawY

						val slideDistance = when (position) {
							"left" -> deltaX
							"right" -> -deltaX
							else -> deltaY
						}

						if (!requireSlide || slideDistance >= slideThreshold) {
							showOverlayAnimated()
							if (checkIsKeyboardVisible() && prefs.getBoolean("auto_hide_enabled", false)) {
								autoHideRunnable?.let { handler.removeCallbacks(it) }
								autoHideRunnable = Runnable { hideOverlay() }
								handler.postDelayed(autoHideRunnable!!, prefs.getInt("auto_hide_delay", 3000).toLong())
							}
						}
						true
					}
					else -> true
				}
			}
		}

		revealZoneView = zone

		val params = WindowManager.LayoutParams(
			if (isVerticalBar) zoneThickness else WindowManager.LayoutParams.MATCH_PARENT,
				if (isVerticalBar) WindowManager.LayoutParams.MATCH_PARENT else zoneThickness,
					WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
					WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
					PixelFormat.TRANSLUCENT
		)

		params.gravity = when (position) {
			"left" -> Gravity.START
			"right" -> Gravity.END
			else -> Gravity.BOTTOM
		}

		if (!isHidden) {
			params.flags = params.flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
		}

		windowManager.addView(revealZoneView, params)
	}

	private fun removeRevealZone() {
		revealZoneView?.let {
			try {
				windowManager.removeView(it)
			} catch (e: Exception) { /* Ignore if already removed to prevent crashes */ }
			revealZoneView = null
		}
	}

	private fun scheduleAutoHide() {
		if (!prefs.getBoolean("auto_hide_enabled", false)) {
			return
		}
		val delay = prefs.getInt("auto_hide_delay", 3000)
		autoHideRunnable?.let { handler.removeCallbacks(it) }
		autoHideRunnable = Runnable { hideOverlay() }
		handler.postDelayed(autoHideRunnable!!, delay.toLong())
	}

	private fun hideOverlay() {
		if (overlayView == null || isHidden) return
			val position = resolvePosition()

			val tx = when (position) {
				"left" -> -overlayView!!.width.toFloat()
				"right" -> overlayView!!.width.toFloat()
				else -> 0f
			}
			val ty = when (position) {
				"bottom" -> overlayView!!.height.toFloat()
				else -> 0f
			}

			overlayView?.animate()
			?.translationX(tx)
			?.translationY(ty)
			?.alpha(0f)
			?.setDuration(250)
			?.withEndAction {
				overlayView?.visibility = View.GONE
				isHidden = true
				enableRevealZoneTouch()
			}
			?.start()
	}

	private fun showOverlayAnimated() {
// 		if (isLockHidden) return
		if (overlayView == null || !isHidden) return
		val isLandscape = currentOrientation == Configuration.ORIENTATION_LANDSCAPE

		overlayView?.apply {
			visibility = View.VISIBLE
			animate()
				.translationY(0f)
				.translationX(0f)
				.alpha(1f)
				.setDuration(200)
				.start()
		}

		isHidden = false
		disableRevealZoneTouch()

		if (prefs.getBoolean("auto_hide_enabled", false) && !checkIsKeyboardVisible()) {
			scheduleAutoHide()
		}
	}

	private fun enableRevealZoneTouch() {
		revealZoneView?.let { zone ->
			val params = zone.layoutParams as WindowManager.LayoutParams
			params.flags = params.flags and WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE.inv()
			windowManager.updateViewLayout(zone, params)
		}
	}

	private fun disableRevealZoneTouch() {
		revealZoneView?.let { zone ->
			val params = zone.layoutParams as WindowManager.LayoutParams
			params.flags = params.flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
			windowManager.updateViewLayout(zone, params)
		}
	}

	private fun updateOverlayBackground() {
		val view = overlayView ?: return
		val container = view.findViewById<LinearLayout>(R.id.navContainer)
		container.setBackgroundColor(getCurrentBackgroundColor())
	}

	private fun updateOverlayButtonColor() {
	val view = overlayView ?: return

	val backIcon = view.findViewById<ImageView>(R.id.backIcon)
	val homeIcon = view.findViewById<ImageView>(R.id.homeIcon)
	val recentIcon = view.findViewById<ImageView>(R.id.recentIcon)

	val buttonColor = getCurrentButtonColor()

		listOf(backIcon, homeIcon, recentIcon).forEach {
			if (prefs.getBoolean("mask_custom_images", true)) {
				it.setColorFilter(buttonColor)
			} else {
				it.clearColorFilter()
			}
		}
	}

	private fun getOverrideAction(buttonType: String): String {
		return prefs.getString("override_$buttonType", "default") ?: "default"
	}

	private fun isButtonDisabled(buttonType: String): Boolean {
		return getOverrideAction(buttonType) == "none_and_disable"
	}

	private fun isButtonHidden(buttonType: String): Boolean {
		return getOverrideAction(buttonType) == "none_and_hide"
	}

	private fun resolveSinglePressAction(buttonType: String): String? {

		val override = getOverrideAction(buttonType)

		return when (override) {
			"default" -> buttonType
			"none" -> null
			"none_and_disable" -> null
			else -> override
		}
	}

	private fun executeActionDirect(actionString: String, hapticDuration: Long, buttonType: String) {
		if (actionString == "none") return

		if (prefs.getBoolean("enable_haptic", true)) {
			performHapticFeedback(hapticDuration)
		}

		if (actionString == "hide_navbar") {
			hideOverlay()
			return
		}
		if (actionString == "show_navbar") {
			showOverlayAnimated()
			return
		}

		if (actionString == "custom_activity") {
			executeCustomActivity("override_$buttonType")
			return
		}

		if (actionString == "gesture_swipe_up" || actionString == "gesture_swipe_down") {
			performSwipeGesture("override_$buttonType", if (actionString == "gesture_swipe_up") "up" else "down")
			return
		}

		val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
		when (actionString) {
			"volume_panel" -> {
				am.adjustVolume(AudioManager.ADJUST_SAME, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
			"volume_up" -> {
				am.adjustVolume(AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
			"volume_down" -> {
				am.adjustVolume(AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
		}

		val actionId = getGlobalActionId(actionString)
		if (actionId != null) {
			performGlobalAction(actionId)
			scheduleAutoHide()
		}
	}

	private fun handleBarSwipe(direction: String) {
		if (!prefs.getBoolean("enable_bar_swipe", false)) return
		// "left" -> "bar_swipe_left" | "right" -> "bar_swipe_right"
		executeAction("bar_swipe_$direction", 55)
	}

	private fun configureOverlayView(view: View) {
		val container = view.findViewById<SwipeInterceptLayout>(R.id.navContainer)
		val backButton = view.findViewById<FrameLayout>(R.id.backButton)
		val homeButton = view.findViewById<FrameLayout>(R.id.homeButton)
		val recentButton = view.findViewById<FrameLayout>(R.id.recentButton)

		val backIcon = view.findViewById<ImageView>(R.id.backIcon)
		val homeIcon = view.findViewById<ImageView>(R.id.homeIcon)
		val recentIcon = view.findViewById<ImageView>(R.id.recentIcon)

		val bgColor = getCurrentBackgroundColor()
		val buttonColor = getCurrentButtonColor()
// 		val isLandscape = currentOrientation == Configuration.ORIENTATION_LANDSCAPE
		val position = resolvePosition()
		val isVerticalBar = position == "left" || position == "right"
		val shouldSwap = prefs.getBoolean("swap_back_recent", false) xor (prefs.getBoolean("swap_landscape", false) && isVerticalBar)
		val separation = dpToPx(prefs.getInt("icon_separation", 10))
		val hitboxSize = dpToPx(prefs.getInt("button_hitbox_size", 100))

		container.isClickable = true
		container.isFocusable = true
		container.setBackgroundColor(bgColor)
			container.orientation = if (position == "left" || position == "right") LinearLayout.VERTICAL
				else LinearLayout.HORIZONTAL
		container.gravity = Gravity.CENTER

		val iconPadding = dpToPx(prefs.getInt("button_padding", 10))
		listOf(backIcon, homeIcon, recentIcon).forEach {
			it.setPadding(iconPadding, iconPadding, iconPadding, iconPadding)
			if (prefs.getBoolean("mask_custom_images", true)) it.setColorFilter(buttonColor) else it.clearColorFilter()
		}

		loadCustomImages(backIcon, homeIcon, recentIcon)

		container.removeAllViews()
		val order = if (shouldSwap) listOf(recentButton, homeButton, backButton) else listOf(backButton, homeButton, recentButton)

		order.forEachIndexed { index, frame ->
			val lp = LinearLayout.LayoutParams(
				if (isVerticalBar) LinearLayout.LayoutParams.MATCH_PARENT else hitboxSize,
				if (isVerticalBar) hitboxSize else LinearLayout.LayoutParams.MATCH_PARENT,
				0f
			)

			if (index < order.size - 1) {
				if (isVerticalBar) lp.bottomMargin = separation else lp.marginEnd = separation
			}

			frame.layoutParams = lp
			container.addView(frame)
		}

		val buttonMap = mapOf("back" to backButton, "home" to homeButton, "recent" to recentButton)

		buttonMap.forEach { (type, frame) ->

			val override = getOverrideAction(type)
			val icon = when (type) {
				"back" -> backIcon
				"home" -> homeIcon
				else -> recentIcon
			}

			when (override) {
				"none_and_hide" -> {
					frame.visibility = View.GONE
					frame.isClickable = false
					frame.isLongClickable = false
					frame.setOnTouchListener(null)
					return@forEach
				}

				"none_and_disable" -> {
					frame.visibility = View.VISIBLE
					frame.isClickable = false
					frame.isLongClickable = false
					frame.setOnTouchListener(null)
					icon.visibility = View.INVISIBLE
					frame.alpha = 0f
					return@forEach
				}

				else -> {
					frame.visibility = View.VISIBLE
					frame.isClickable = true
					frame.isLongClickable = true
					icon.visibility = View.VISIBLE
					frame.alpha = 1f
				}
			}

			var startX = 0f
			var startY = 0f
			var slideTriggered = false

			frame.setOnTouchListener { _, event ->

				if (isButtonDisabled(type) || isButtonHidden(type))
					return@setOnTouchListener true

				when (event.action) {

					MotionEvent.ACTION_DOWN -> {
						startX = event.rawX
						startY = event.rawY
						slideTriggered = false
						false
					}

					MotionEvent.ACTION_MOVE -> {
						if (!slideTriggered && prefs.getBoolean("enable_slide_actions", true)) {
							val deltaX = startX - event.rawX
							val deltaY = startY - event.rawY
							val threshold = dpToPx(prefs.getInt("slide_action_threshold", 50))

							val isTriggered =
								if (isVerticalBar) deltaX > threshold
								else deltaY > threshold

							if (isTriggered) {
								handleSlideAction(type)
								slideTriggered = true
							}
						}
						false
					}

					else -> false
				}
			}

			// Single Press Actions
			frame.setOnClickListener {
				if (isButtonDisabled(type)) return@setOnClickListener
				updateOverlayBackground()
				updateOverlayButtonColor()

				val action = resolveSinglePressAction(type) ?: return@setOnClickListener
				executeActionDirect(action, 50, type)
			}

			// Long Press Actions
			frame.setOnLongClickListener {
				handleLongPress(type)
				true
			}
		}

		// Full-bar horizontal swipe detection via SwipeInterceptLayout
		// onInterceptTouchEvent steals the gesture before children can fire click/longclick
		if (prefs.getBoolean("enable_bar_swipe", false)) {

			var barSwipeStartX = 0f

			container.swipeThreshold = dpToPx(prefs.getInt("bar_swipe_threshold", 40)).toFloat()

			container.onSwipeUpCallback = { event ->
				val requireVisible = prefs.getBoolean("bar_swipe_require_visible", true)
				if (!requireVisible || !isHidden) {
					val dx = event.rawX - container.swipeStartX
					if (dx < 0) handleBarSwipe("left") else handleBarSwipe("right")
				}
			}

			container.setOnTouchListener { _, event ->
				when (event.action) {
					MotionEvent.ACTION_DOWN -> {
						container.swipeStartX = event.rawX
						container.intercepting = false
						false
					}
					MotionEvent.ACTION_UP -> {
						if (container.intercepting) {
							val requireVisible = prefs.getBoolean("bar_swipe_require_visible", true)
							if (!requireVisible || !isHidden) {
								val dx = event.rawX - container.swipeStartX
								if (dx < 0) handleBarSwipe("left") else handleBarSwipe("right")
							}
						}
						false
					}
					else -> false
				}
			}
		} else {
			container.setOnTouchListener(null)
			container.swipeThreshold = Float.MAX_VALUE
		}
	}

	private fun getGlobalActionId(action: String?): Int? {
		if (action == null || action == "none") return null

		return when (action) {
			"back" -> GLOBAL_ACTION_BACK
			"home" -> GLOBAL_ACTION_HOME
			"recents" -> GLOBAL_ACTION_RECENTS
			"recent" -> GLOBAL_ACTION_RECENTS 
			"notifications" -> GLOBAL_ACTION_NOTIFICATIONS
			"quick_settings" -> GLOBAL_ACTION_QUICK_SETTINGS
			"power_menu" -> GLOBAL_ACTION_POWER_DIALOG
			"split_screen" -> GLOBAL_ACTION_TOGGLE_SPLIT_SCREEN
			// Android 9+
			"lock_screen" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_LOCK_SCREEN else null
			"screenshot" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) GLOBAL_ACTION_TAKE_SCREENSHOT else null
			// Android 12+
			"all_apps" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) 14 else null
			// Android 15+
			"media_play_pause" -> if (Build.VERSION.SDK_INT >= 35) 22 else null
			"system_menu" -> if (Build.VERSION.SDK_INT >= 35) 21 else null
			// Other
			"volume_panel" -> -1 // Sentinel: not a real global action
			else -> null
		}
	}

	private fun executeCustomActivity(prefKey: String) {
		val componentString = prefs.getString("${prefKey}_custom_target", null) ?: return

		try {
			val intent = if (componentString.contains("/")) {
				val parts = componentString.split("/")
				Intent().setClassName(parts[0], parts[1])
			} else {
				// manual string/package name
				packageManager.getLaunchIntentForPackage(componentString) ?: Intent(componentString)
			}

			intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

			if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
				val options = android.app.ActivityOptions.makeBasic()
				options.setPendingIntentBackgroundActivityStartMode(
					android.app.ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED
				)
				startActivity(intent, options.toBundle())
			} else {
				startActivity(intent)
			}
		} catch (e: Exception) {
//			Toast.makeText(this, "Could not launch: $componentString", Toast.LENGTH_SHORT).show()
			return;
		}
	}

	private fun executeAction(prefKey: String, hapticDuration: Long) {
		val actionString = prefs.getString(prefKey, "none") ?: "none"

		if (actionString == "none") return

		if (prefs.getBoolean("enable_haptic", true)) {
			performHapticFeedback(hapticDuration)
		}

		when (actionString) {
			"hide_navbar" -> { hideOverlay(); return }
			"show_navbar" -> { showOverlayAnimated(); return }
			"custom_activity" -> { executeCustomActivity(prefKey); return }
			"gesture_swipe_up" -> { performSwipeGesture(prefKey, "up"); return }
			"gesture_swipe_down" -> { performSwipeGesture(prefKey, "down"); return }
			"volume_panel" -> {
				val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
				am.adjustVolume(AudioManager.ADJUST_SAME, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
			"volume_up" -> {
				val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
				am.adjustVolume(AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
			"volume_down" -> {
				val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
				am.adjustVolume(AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI)
				scheduleAutoHide()
				return
			}
		}

		val actionId = getGlobalActionId(actionString)
		if (actionId != null) {
			performGlobalAction(actionId)
			scheduleAutoHide()
		}
	}

	private fun handleLongPress(buttonType: String) {
		if (isButtonDisabled(buttonType)) return
		if (isButtonHidden(buttonType)) return
		if (!prefs.getBoolean("enable_long_press", true)) return
		executeAction("long_press_$buttonType", 70)
	}

	private fun handleSlideAction(buttonType: String) {
		if (!prefs.getBoolean("enable_slide_actions", true)) return
		executeAction("slide_$buttonType", 60)
	}

	private fun loadCustomImages(back: ImageView, home: ImageView, recent: ImageView) {
		fun load(icon: ImageView, key: String, defaultRes: Int) {
			val path = prefs.getString(key, null)
			val bitmap = path?.let { BitmapFactory.decodeFile(it) }
			if (bitmap != null) icon.setImageBitmap(bitmap) else icon.setImageResource(defaultRes)
		}
		load(back, "back_image_path", R.drawable.ic_back)
		load(home, "home_image_path", R.drawable.ic_home)
		load(recent, "recent_image_path", R.drawable.ic_recent)
	}

	override fun onSharedPreferenceChanged(sharedPreferences: SharedPreferences?, key: String?) {
		handler.post {
			when (key) {
				"auto_hide_enabled", "require_slide_gesture", "hide_on_keyboard", "reveal_zone_thickness" -> {
					showRevealZone()
					updateOverlayLive()
				}
				else -> updateOverlayLive()
			}
		}
	}

	private fun createNotificationChannel() {
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
			val chan = NotificationChannel(CHANNEL_ID, "Nav Overlay", NotificationManager.IMPORTANCE_LOW)
			getSystemService(NotificationManager::class.java).createNotificationChannel(chan)
		}
	}

	private fun createNotification(): Notification {
		return NotificationCompat.Builder(this, CHANNEL_ID)
			.setContentTitle(getString(R.string.navigation_active))
			.setSmallIcon(R.drawable.ic_navigation)
			.build()
	}

	private fun dpToPx(dp: Int): Int = (dp * resources.displayMetrics.density).toInt()


	private fun performSwipeGesture(prefKey: String, direction: String) {
		val forceDp = prefs.getInt("${prefKey}_swipe_force", 40)
		val distancePx = dpToPx(forceDp).toFloat()
		val metrics = resources.displayMetrics
		val centerX = metrics.widthPixels / 2f
		val centerY = metrics.heightPixels / 2f

		val startY = if (direction == "up") centerY + distancePx / 2 else centerY - distancePx / 2
		val endY = if (direction == "up") centerY - distancePx / 2 else centerY + distancePx / 2

		val path = android.graphics.Path().apply {
			moveTo(centerX, startY)
			lineTo(centerX, endY)
		}

		val gesture = android.accessibilityservice.GestureDescription.Builder()
		.addStroke(android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 300))
		.build()

		dispatchGesture(gesture, null, null)
	}
}
