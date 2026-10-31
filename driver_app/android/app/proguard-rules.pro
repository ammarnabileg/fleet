# Rules for the release build (R8 shrinks and renames the code; Flutter's Gradle plugin adds this file).

# The Flutter embedding refers to Play Store deferred components the app does not use.
-dontwarn com.google.android.play.core.**

# The tracking notification (flutter_local_notifications) stores its settings through Gson reflection.
-keep class com.dexterous.flutterlocalnotifications.** { *; }
