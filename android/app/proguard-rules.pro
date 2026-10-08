-keep class org.maplibre.** { *; }
-keep class com.mapbox.geojson.** { *; }
# The release instrumentation runner shares this dependency with the target app.
-keep class androidx.tracing.Trace { *; }
