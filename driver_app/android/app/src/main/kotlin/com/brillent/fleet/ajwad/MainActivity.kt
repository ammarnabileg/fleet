package com.brillent.fleet.ajwad

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

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
        // in-app updates (lib/core/updater.dart): the app is installed from an APK, not from a store. Android shows its
        // own confirmation; a sideloaded app can never install silently.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "fleet/update").setMethodCallHandler { call, result ->
            when (call.method) {
                "canInstall" -> result.success(
                    Build.VERSION.SDK_INT < Build.VERSION_CODES.O || packageManager.canRequestPackageInstalls(),
                )
                "openInstallSettings" -> {
                    try {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            startActivity(
                                Intent(
                                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                    Uri.parse("package:$packageName"),
                                ),
                            )
                        } else {
                            startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS))
                        }
                        result.success(true)
                    } catch (e: ActivityNotFoundException) {
                        result.success(false)
                    }
                }
                "install" -> {
                    val path = call.arguments as? String
                    val file = path?.let { File(it) }
                    // only a file in the app's own cache folder of updates (what the FileProvider shares)
                    val folder = File(cacheDir, "updates").canonicalPath
                    if (file == null || !file.exists() || file.canonicalFile.parent != folder) {
                        result.success(false)
                        return@setMethodCallHandler
                    }
                    try {
                        val uri = FileProvider.getUriForFile(this, "$packageName.updates", file)
                        val intent = Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(uri, "application/vnd.android.package-archive")
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        startActivity(intent)
                        result.success(true)
                    } catch (e: Exception) {
                        result.success(false)
                    }
                }
                "unmetered" -> {
                    val cm = getSystemService(ConnectivityManager::class.java)
                    val caps = cm?.getNetworkCapabilities(cm.activeNetwork)
                    result.success(caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true)
                }
                else -> result.notImplemented()
            }
        }
    }
}
