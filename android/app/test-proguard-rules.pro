# AndroidX Test references these CLASS-retention compiler annotations.
# They have no runtime implementation or behavior; keep this rule test-only.
-dontwarn com.google.errorprone.annotations.CanIgnoreReturnValue
-dontwarn com.google.errorprone.annotations.MustBeClosed
