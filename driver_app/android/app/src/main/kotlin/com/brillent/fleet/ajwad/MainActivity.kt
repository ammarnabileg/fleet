package com.brillent.fleet.ajwad

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // the dialer opens on the supervisor's number; the driver presses call himself (no call permission needed)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "fleet/phone").setMethodCallHandler { call, result ->
            if (call.method != "dial") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            val phone = call.arguments as? String
            if (phone.isNullOrBlank()) {
                result.success(false)
                return@setMethodCallHandler
            }
            try {
                startActivity(Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", phone, null)))
                result.success(true)
            } catch (e: ActivityNotFoundException) {
                result.success(false)
            }
        }
    }
}
