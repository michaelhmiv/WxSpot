plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.diffplug.spotless")
}

val betaBuild = providers.gradleProperty("wxspot.beta").orElse("false").get().toBooleanStrict()
val signingPath = providers.environmentVariable("WXSPOT_KEYSTORE_PATH").orNull
val signingVariables = listOf("WXSPOT_KEYSTORE_PASSWORD", "WXSPOT_KEY_ALIAS", "WXSPOT_KEY_PASSWORD")
if (signingPath != null) {
    require(signingVariables.all { !providers.environmentVariable(it).orNull.isNullOrBlank() }) {
        "All WxSpot signing environment variables must be configured together."
    }
}

android {
    namespace = "app.wxspot"
    testBuildType = providers.gradleProperty("wxspot.testBuildType").orElse("debug").get()
    compileSdk { version = release(37) { minorApiLevel = 2 } }
    defaultConfig {
        applicationId = if (betaBuild) "app.wxspot.beta" else "app.wxspot"
        minSdk = 26
        targetSdk = 36
        versionCode = providers.gradleProperty("wxspot.versionCode").orElse("3").get().toInt()
        versionName = providers.gradleProperty("wxspot.versionName").orElse("0.2.0-beta.1").get()
        manifestPlaceholders["appLabel"] = if (betaBuild) "WxSpot Beta" else "WxSpot"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField(
            "String", "API_BASE_URL",
            "\"${providers.gradleProperty("wxspot.apiUrl").orElse("https://wxspotapi-production.up.railway.app").get()}\"",
        )
    }
    buildFeatures { compose = true; buildConfig = true }
    if (signingPath != null) {
        signingConfigs {
            create("retained") {
                storeFile = file(signingPath)
                storePassword = providers.environmentVariable("WXSPOT_KEYSTORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("WXSPOT_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("WXSPOT_KEY_PASSWORD").get()
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildTypes {
        debug {
            manifestPlaceholders["cleartextAllowed"] = "true"
            if (signingPath != null) signingConfig = signingConfigs.getByName("retained")
        }
        release {
            manifestPlaceholders["cleartextAllowed"] = "false"
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            testProguardFiles("test-proguard-rules.pro")
            if (signingPath != null) signingConfig = signingConfigs.getByName("retained")
        }
    }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    testOptions { unitTests.isReturnDefaultValues = true }
}

spotless { kotlin { target("src/**/*.kt"); targetExclude("**/.rsync-tmp/**"); ktfmt("0.59").kotlinlangStyle() } }

tasks.withType<Test>().configureEach {
    systemProperty("wxspot.contractsDir", rootProject.file("../contracts").absolutePath)
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.maplibre.gl:android-sdk-opengl:13.6.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("io.coil-kt.coil3:coil-compose:3.3.0")
    implementation("io.coil-kt.coil3:coil-network-okhttp:3.3.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation(platform("androidx.compose:compose-bom:2026.09.00"))
}
