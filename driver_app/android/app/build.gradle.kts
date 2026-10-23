import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.brillianttech.fleet.driver"
    // permission_handler_android 14 is compiled against Android 37 and requires the app to be too
    // (compileSdk only; targetSdk, the runtime behaviour, stays Flutter's)
    compileSdk = maxOf(flutter.compileSdkVersion, 37)
    ndkVersion = flutter.ndkVersion

    compileOptions {
        // flutter_local_notifications (the tracking notification) needs the newer Java APIs on older Android
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.brillianttech.fleet.driver"
        minSdk = 24
        // the server the activation links point to: -PactivationHost=fleet.example.com (must match API_URL)
        manifestPlaceholders["activationHost"] = (project.findProperty("activationHost") as String?) ?: "fleet.example.com"
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // release signing from android/key.properties (kept out of git; CI writes it from secrets)
    val keyProps = Properties().apply {
        val f = rootProject.file("key.properties")
        if (f.exists()) f.inputStream().use { load(it) }
    }
    signingConfigs {
        if (keyProps.getProperty("storeFile") != null) {
            create("release") {
                storeFile = file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    // A release is signed with the release key, or the build fails: a silently debug-signed APK cannot update the
    // installed app and fails the App Link verification. Only CI, with no key in its secrets, may pass
    // -PciDebugSigning=true to sign a test build with the runner's throw-away debug key (said loudly in the log).
    val ciDebugSigning = (project.findProperty("ciDebugSigning") as String?) == "true"
    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
                ?: if (ciDebugSigning) {
                    logger.warn("WARNING: CI-only build signed with the DEBUG key (-PciDebugSigning=true); not for drivers")
                    signingConfigs.getByName("debug")
                } else {
                    null
                }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// fails before anything is built, with the reason, instead of producing an unsigned or debug-signed release
gradle.taskGraph.whenReady {
    val releasing = allTasks.any {
        it.project == project && it.name.endsWith("Release") &&
            (it.name.startsWith("assemble") || it.name.startsWith("bundle"))
    }
    if (releasing && android.signingConfigs.findByName("release") == null &&
        (project.findProperty("ciDebugSigning") as String?) != "true"
    ) {
        throw GradleException(
            "Release signing key missing: create android/key.properties (storeFile, storePassword, keyAlias, " +
                "keyPassword). CI test builds without a key pass -PciDebugSigning=true.",
        )
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
