# AndroidX Test references these CLASS-retention compiler annotations.
# They have no runtime implementation or behavior; keep this rule test-only.
-dontwarn com.google.errorprone.annotations.CanIgnoreReturnValue
-dontwarn com.google.errorprone.annotations.MustBeClosed

# The runner and JUnit discover this test and its rules by their original names.
# These classes are in the instrumentation APK, not the distributed application.
-keep class androidx.test.** { *; }
-keep class org.junit.** { *; }
-keep class app.wxspot.UpgradeAcceptanceTest { *; }

# The platform runner verifies the fully optimized target without shared test libraries.
-keep class app.wxspot.UpgradeInstrumentation { *; }
