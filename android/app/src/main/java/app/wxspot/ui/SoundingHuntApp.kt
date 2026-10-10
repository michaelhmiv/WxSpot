package app.wxspot.ui

import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.Explore
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Leaderboard
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.SportsEsports
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.wxspot.WxSpotApplication
import app.wxspot.domain.HuntChallenge
import app.wxspot.domain.HuntHistoryItem
import app.wxspot.domain.asSounding
import app.wxspot.ui.components.QuestEyebrow
import app.wxspot.ui.components.ScoreMedallion
import app.wxspot.ui.components.WeatherWorldBanner
import app.wxspot.ui.theme.WxGame
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt
import kotlinx.coroutines.delay

private val Ink: Color
    @Composable get() = WxGame.colors.background
private val Panel: Color
    @Composable get() = WxGame.colors.card
private val Mint: Color
    @Composable get() = WxGame.colors.grass
private val Sky: Color
    @Composable get() = WxGame.colors.sky
private val Warm: Color
    @Composable get() = WxGame.colors.sun
private val Muted: Color
    @Composable get() = WxGame.colors.muted

@Composable
fun SoundingHuntApp(
    appearance: String = "light",
    onAppearanceChange: (String) -> Unit = {},
    vm: SoundingHuntViewModel = huntViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val immersive = state.page in setOf("sounding", "guess", "result")
    var confirmSubmit by remember { mutableStateOf(false) }
    BackHandler(enabled = immersive) {
        when (state.page) {
            "guess" -> vm.reviewSounding()
            "result" -> vm.home()
            else -> vm.home()
        }
    }
    DisposableEffect(lifecycle, vm) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) vm.refresh(force = true)
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(state.page, state.challenge == null) {
        if (state.page in setOf("home", "play", "rankings", "profile")) {
            val retryDelay = if (state.challenge == null) 15_000L else 300_000L
            while (true) {
                delay(retryDelay)
                vm.refresh(force = state.challenge == null)
            }
        }
    }
    Scaffold(
        containerColor = Ink,
        bottomBar = {
            if (!immersive) {
                NavigationBar(containerColor = WxGame.colors.nav, tonalElevation = 4.dp) {
                    listOf(
                            Triple("Home", Icons.Outlined.Home, "home"),
                            Triple("Play", Icons.Outlined.SportsEsports, "play"),
                            Triple("Rankings", Icons.Outlined.Leaderboard, "rankings"),
                            Triple("Profile", Icons.Outlined.AccountCircle, "profile"),
                        )
                        .forEach { (label, icon, _) ->
                            NavigationBarItem(
                                selected = state.tab == label,
                                onClick = { vm.navigate(label) },
                                icon = { Icon(icon, contentDescription = label) },
                                label = {
                                    Text(
                                        label,
                                        fontWeight =
                                            if (state.tab == label) FontWeight.Bold
                                            else FontWeight.Medium,
                                    )
                                },
                                colors =
                                    androidx.compose.material3.NavigationBarItemDefaults.colors(
                                        selectedIconColor =
                                            MaterialTheme.colorScheme.onPrimaryContainer,
                                        selectedTextColor = MaterialTheme.colorScheme.primary,
                                        indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                                        unselectedIconColor = Muted,
                                        unselectedTextColor = Muted,
                                    ),
                            )
                        }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(if (immersive) PaddingValues(0.dp) else padding)) {
            when (state.page) {
                "home" -> HomePage(state, vm)
                "play" -> PlayPage(state, vm)
                "rankings" -> RankingsPage(state, vm)
                "profile" -> ProfilePage(state, vm, appearance, onAppearanceChange)
                "sounding" -> SoundingPage(state, vm)
                "guess" -> GuessPage(state, vm) { confirmSubmit = true }
                "result" -> ResultPage(state, vm)
                else -> HomePage(state, vm)
            }
            if (state.error != null) {
                Surface(
                    color = WxGame.colors.error,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
                ) {
                    Text(
                        state.error.orEmpty(),
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        color = WxGame.colors.errorInk,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
            if (state.busy) {
                Surface(
                    color = WxGame.colors.background.copy(alpha = 0.96f),
                    modifier = Modifier.fillMaxSize(),
                ) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = Sky)
                            Spacer(Modifier.height(12.dp))
                            Text("Finding your sounding…")
                        }
                    }
                }
            }
        }
    }
    if (confirmSubmit) {
        AlertDialog(
            onDismissRequest = { confirmSubmit = false },
            title = { Text("Lock in your guess?") },
            text = {
                Text("Your guess is final after submission. There is one ranked attempt per day.")
            },
            confirmButton = {
                Button(
                    onClick = {
                        confirmSubmit = false
                        vm.submitGuess()
                    }
                ) {
                    Text("Confirm guess")
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmSubmit = false }) { Text("Keep editing") }
            },
            containerColor = Panel,
        )
    }
}

@Composable
private fun huntViewModel(): SoundingHuntViewModel {
    val app = LocalContext.current.applicationContext as WxSpotApplication
    return viewModel(
        factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : androidx.lifecycle.ViewModel> create(modelClass: Class<T>): T =
                    SoundingHuntViewModel(app.api) as T
            }
    )
}

@Composable
private fun PageColumn(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        content = content,
    )
}

@Composable
private fun BrandHeader(subtitle: String? = null) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(48.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(MaterialTheme.colorScheme.primary),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Outlined.Explore,
                "WXspot weather exploration",
                tint = MaterialTheme.colorScheme.onPrimary,
            )
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(
                "WXspot",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                subtitle ?: "SOUNDING HUNT · WEATHER GEOGRAPHY",
                style = MaterialTheme.typography.labelSmall,
                color = Muted,
            )
        }
    }
}

@Composable
private fun HomePage(state: SoundingHuntUiState, vm: SoundingHuntViewModel) {
    PageColumn {
        Spacer(Modifier.height(18.dp))
        BrandHeader()
        WeatherWorldBanner()
        Spacer(Modifier.height(4.dp))
        Text(
            "Today’s expedition",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        if (state.challenge == null) {
            ElevatedCard(colors = cardColors()) {
                Column(
                    Modifier.fillMaxWidth().padding(22.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (state.loading) {
                        CircularProgressIndicator(
                            color = Sky,
                            modifier = Modifier.size(28.dp),
                            strokeWidth = 3.dp,
                        )
                        Text("Loading today’s challenge…")
                    } else {
                        Text("Today’s challenge is temporarily unavailable.")
                        TextButton(onClick = { vm.refresh(force = true) }) { Text("Try again") }
                    }
                    Text("We’ll retry automatically when the connection is ready.", color = Muted)
                }
            }
        } else {
            state.challenge?.let { challenge ->
                DailyHero(challenge, state.profile?.currentStreak ?: challenge.currentStreak, vm)
            }
        }
        state.profile?.history?.firstOrNull()?.let { item ->
            ElevatedCard(colors = cardColors()) {
                Column(
                    Modifier.fillMaxWidth().padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        "LAST EXPEDITION",
                        style = MaterialTheme.typography.labelMedium,
                        color = Muted,
                    )
                    Text(
                        "#${item.challengeNumber}  ·  ${item.score} points",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "${dateLabel(item.challengeDay)}  ·  " +
                            "${formatDistance(item.distanceMiles)} away",
                        color = Muted,
                    )
                }
            }
        }
        OutlinedButton(onClick = vm::startPractice, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Outlined.Refresh, null)
            Spacer(Modifier.width(8.dp))
            Text("Play an unlimited practice sounding")
        }
    }
}

@Composable
private fun DailyHero(challenge: HuntChallenge, streak: Int, vm: SoundingHuntViewModel) {
    ElevatedCard(colors = cardColors(), shape = RoundedCornerShape(26.dp)) {
        Column(
            Modifier.fillMaxWidth().padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = CircleShape) {
                    Text(
                        "DAILY CHALLENGE  #${challenge.challengeNumber}",
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                        color = Sky,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                if (challenge.completed) Icon(Icons.Outlined.CheckCircle, "Completed", tint = Mint)
            }
            Text(
                "Read the sky.\nFind the place.",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "A real weather balloon left its clues in the atmosphere. Find where it launched.",
                color = Muted,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatPill(
                    "STREAK",
                    "${streak} day${if (streak == 1) "" else "s"}",
                    Icons.Outlined.EmojiEvents,
                )
                StatPill(
                    "STATUS",
                    if (challenge.completed) "Complete" else "Ready",
                    Icons.Outlined.CheckCircle,
                )
            }
            Button(onClick = vm::startDaily, modifier = Modifier.fillMaxWidth().height(54.dp)) {
                Text(
                    if (challenge.completed) "View today’s result" else "Play today’s hunt",
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                "Resets at 8:00 AM Eastern · no timer",
                style = MaterialTheme.typography.labelMedium,
                color = Muted,
            )
        }
    }
}

@Composable
private fun StatPill(
    label: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
) {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        shape = RoundedCornerShape(16.dp),
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, null, tint = Warm, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Column {
                Text(label, style = MaterialTheme.typography.labelSmall, color = Muted)
                Text(
                    value,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlayPage(state: SoundingHuntUiState, vm: SoundingHuntViewModel) {
    PageColumn {
        Spacer(Modifier.height(18.dp))
        BrandHeader("SOUNDING HUNT · CHOOSE A MISSION")
        QuestEyebrow("TWO WAYS TO EXPLORE")
        Text(
            "Pick your expedition",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
        )
        state.challenge?.let { challenge ->
            ElevatedCard(
                onClick = vm::startDaily,
                colors =
                    androidx.compose.material3.CardDefaults.elevatedCardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    ),
                shape = RoundedCornerShape(26.dp),
            ) {
                Column(
                    Modifier.fillMaxWidth().padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        "DAILY EXPEDITION · RANKED",
                        style = MaterialTheme.typography.labelMedium,
                        color = Sky,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "Challenge #${challenge.challengeNumber}",
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        if (challenge.completed) "Your result is ready to review."
                        else "One official guess · leaderboard and streak eligible",
                        color = Muted,
                    )
                    Text(
                        if (challenge.completed) "View result" else "Start daily challenge  →",
                        color = Mint,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
        ElevatedCard(
            onClick = vm::startPractice,
            colors =
                androidx.compose.material3.CardDefaults.elevatedCardColors(
                    containerColor = MaterialTheme.colorScheme.secondaryContainer
                ),
            shape = RoundedCornerShape(26.dp),
        ) {
            Column(
                Modifier.fillMaxWidth().padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "FIELD TRAINING · UNLIMITED",
                    style = MaterialTheme.typography.labelMedium,
                    color = Warm,
                    fontWeight = FontWeight.Bold,
                )
                Text("Play at your own pace", style = MaterialTheme.typography.titleLarge)
                Text(
                    "Historical soundings, normal scoring, no effect on your streak or ranking.",
                    color = Muted,
                )
                Text("Start practice  →", color = Mint, fontWeight = FontWeight.Bold)
            }
        }
        state.profile
            ?.history
            ?.takeIf { it.isNotEmpty() }
            ?.let { history ->
                Text(
                    "Completed challenges",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                history.take(12).forEach { item ->
                    HistoryRow(item) { vm.openHistoricalResult(item.challengeDay) }
                }
            }
    }
}

@Composable
private fun SoundingPage(state: SoundingHuntUiState, vm: SoundingHuntViewModel) {
    val challenge = state.reviewChallenge ?: state.challenge
    val sounding = state.practice?.asSounding() ?: challenge?.asSounding()
    val context = LocalContext.current.applicationContext as WxSpotApplication
    val radarId = if (state.isPractice) state.practice?.practiceId else challenge?.challengeDay
    val radarKind = if (state.isPractice) "practice" else "daily"
    var radar by remember(radarId) { mutableStateOf<app.wxspot.domain.HuntRadarEvidence?>(null) }
    var chartReset by remember { mutableIntStateOf(0) }
    var fraction by rememberSaveable { mutableStateOf(0.60f) }
    val density = androidx.compose.ui.platform.LocalDensity.current
    LaunchedEffect(radarKind, radarId) {
        radar = null
        if (radarId != null) {
            radar = runCatching { context.api.huntRadar(radarKind, radarId) }
                .getOrElse {
                    app.wxspot.domain.HuntRadarEvidence(
                        state = "unavailable",
                        source = "Iowa Environmental Mesonet",
                        attribution = "Iowa Environmental Mesonet / NOAA NEXRAD",
                        product = "reflectivity",
                        observationTime = sounding?.observationTime.orEmpty(),
                        anchorTime = sounding?.observationTime.orEmpty(),
                        message = "Historical radar unavailable. The sounding remains playable.",
                    )
                }
        }
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp, vertical = 8.dp)) {
        ImmersiveHeader("Sounding Hunt", onBack = vm::home)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                if (state.isPractice) "PRACTICE"
                else "DAILY  #" + (challenge?.challengeNumber ?: "—"),
                style = MaterialTheme.typography.labelMedium,
                color = Sky,
                fontWeight = FontWeight.Bold,
            )
            val basis = if (sounding?.observationTimeBasis == "nominal") "Nominal" else "Launch"
            Text(
                basis + " " + (sounding?.observationTime?.let(::utcLabel) ?: "—") + " UTC",
                style = MaterialTheme.typography.labelSmall,
                color = Muted,
            )
        }
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
            val available = maxHeight
            val totalPixels = with(density) { available.toPx() }
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxWidth().height(available * fraction)) {
                    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "Atmospheric evidence",
                                style = MaterialTheme.typography.titleMedium,
                            )
                            IconButton(
                                onClick = { chartReset++ },
                                modifier = Modifier.size(40.dp),
                            ) {
                                Icon(Icons.Outlined.Refresh, "Reset chart view", tint = Sky)
                            }
                        }
                        if (sounding != null) SoundingHuntChart(sounding, chartReset)
                        else Text("Sounding data is unavailable.")
                    }
                }
                Box(
                    Modifier.fillMaxWidth()
                        .height(24.dp)
                        .background(WxGame.colors.nav, RoundedCornerShape(8.dp))
                        .pointerInput(totalPixels) {
                            detectVerticalDragGestures { change, dragAmount ->
                                change.consume()
                                fraction =
                                    (fraction + dragAmount / totalPixels).coerceIn(0.18f, 0.82f)
                            }
                        }
                        .semantics {
                            contentDescription =
                                "Drag to resize sounding above and historical radar below"
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Box(
                        Modifier.width(52.dp).height(5.dp)
                            .background(WxGame.colors.muted, RoundedCornerShape(4.dp))
                    )
                }
                HuntRadarPanel(
                    api = context.api,
                    evidence = radar,
                    modifier = Modifier.fillMaxWidth().weight(1f),
                )
            }
        }
        Button(onClick = vm::chooseLocation, modifier = Modifier.fillMaxWidth().height(52.dp)) {
            Text("Choose location", fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun GuessPage(state: SoundingHuntUiState, vm: SoundingHuntViewModel, onSubmit: () -> Unit) {
    var latitude by
        rememberSaveable(state.page) {
            mutableStateOf(state.guessLatitude?.let { "%.5f".format(Locale.US, it) } ?: "")
        }
    var longitude by
        rememberSaveable(state.page) {
            mutableStateOf(state.guessLongitude?.let { "%.5f".format(Locale.US, it) } ?: "")
        }
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 10.dp)) {
        ImmersiveHeader("Place your pin", onBack = vm::reviewSounding)
        Text(
            "Where did it launch?",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Text("Explore the lower 48 and plant your expedition flag. No timer.", color = Muted)
        SoundingHuntMap(
            api = (LocalContext.current.applicationContext as WxSpotApplication).api,
            guess =
                if (state.guessLatitude != null && state.guessLongitude != null) {
                    state.guessLatitude to state.guessLongitude
                } else {
                    null
                },
            allowGuess = true,
            modifier = Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(20.dp)),
            onGuess = { lat, lon ->
                latitude = "%.5f".format(Locale.US, lat)
                longitude = "%.5f".format(Locale.US, lon)
                vm.setGuess(lat, lon)
            },
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = latitude,
                onValueChange = {
                    latitude = it.take(12)
                    updateCoordinates(latitude, longitude, vm)
                },
                modifier = Modifier.weight(1f),
                label = { Text("Latitude") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
            )
            OutlinedTextField(
                value = longitude,
                onValueChange = {
                    longitude = it.take(12)
                    updateCoordinates(latitude, longitude, vm)
                },
                modifier = Modifier.weight(1f),
                label = { Text("Longitude") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
            )
        }
        Button(
            onClick = onSubmit,
            enabled = state.guessLatitude != null && state.guessLongitude != null && !state.busy,
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            Text("Confirm final guess", fontWeight = FontWeight.Bold)
        }
    }
}

private fun updateCoordinates(latitude: String, longitude: String, vm: SoundingHuntViewModel) {
    val lat = latitude.toDoubleOrNull()
    val lon = longitude.toDoubleOrNull()
    if (lat != null && lon != null) vm.setGuess(lat, lon) else vm.clearGuess()
}

@Composable
private fun ResultPage(state: SoundingHuntUiState, vm: SoundingHuntViewModel) {
    val result = state.result
    val api = (LocalContext.current.applicationContext as WxSpotApplication).api
    val context = LocalContext.current
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 10.dp)) {
        ImmersiveHeader("Challenge result", onBack = vm::home)
        if (result == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Result unavailable.")
            }
            return@Column
        }
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(
                color = MaterialTheme.colorScheme.primaryContainer,
                shape = RoundedCornerShape(26.dp),
            ) {
                Column(
                    Modifier.fillMaxWidth().padding(18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        "SOUNDING REVEALED",
                        style = MaterialTheme.typography.labelMedium,
                        color = Mint,
                        fontWeight = FontWeight.Bold,
                    )
                    if (result.score != null) {
                        ScoreMedallion(result.score)
                    } else {
                        Text(
                            if (result.historical) "Archived expedition" else "Practice complete",
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    Text(
                        when {
                            state.isPractice -> "UNRANKED PRACTICE"
                            result.score != null -> "POINTS OUT OF 5,000"
                            result.historical -> "HISTORICAL CHALLENGE"
                            else -> "UNRANKED PRACTICE"
                        },
                        color = Muted,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
            SoundingHuntMap(
                api = api,
                guess =
                    if (result.selectedLatitude != null && result.selectedLongitude != null) {
                        result.selectedLatitude to result.selectedLongitude
                    } else {
                        null
                    },
                answer = result.answer.latitude to result.answer.longitude,
                allowGuess = false,
                modifier = Modifier.fillMaxWidth().height(270.dp).clip(RoundedCornerShape(20.dp)),
            )
            Text(
                result.answer.stationName,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "${result.answer.state}  ·  " +
                    "${"%.3f".format(Locale.US, result.answer.latitude)}, " +
                    "${"%.3f".format(Locale.US, result.answer.longitude)}",
                color = Muted,
            )
            if (result.distanceMiles != null) {
                Text(
                    "${result.distanceMiles.roundToInt()} miles off",
                    style = MaterialTheme.typography.titleMedium,
                    color = Warm,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text("Observed ${utcLabel(result.observationTime)} UTC", color = Muted)
            Text(
                "What the profile showed",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            result.insights.forEach { insight -> InsightRow(insight) }
            val launchTime =
                result.answer.nominalTime?.let(::utcLabel) ?: utcLabel(result.observationTime)
            Text(
                "Source: ${result.answer.source}, ${result.answer.sourceVersion}. " +
                    "Launch $launchTime UTC.",
                style = MaterialTheme.typography.bodySmall,
                color = Muted,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { result.challengeDay?.let(vm::openLeaderboard) },
                modifier = Modifier.weight(1f),
                enabled = !state.isPractice && result.challengeDay != null,
            ) {
                Text("Leaderboard")
            }
            Button(
                onClick = {
                    val scoreLine = result.score?.let { "$it / 5,000" } ?: "Practice complete"
                    val distanceLine =
                        result.distanceMiles?.let { " · ${formatDistance(it)} away" }.orEmpty()
                    val challengeLabel =
                        result.challengeNumber?.let { "Hunt #$it" } ?: "Sounding Hunt practice"
                    val shareText =
                        "WXspot Sounding Hunt · $challengeLabel · $scoreLine$distanceLine · " +
                            "${utcLabel(result.observationTime)} UTC"
                    val send =
                        Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, shareText)
                    context.startActivity(Intent.createChooser(send, "Share result"))
                },
                modifier = Modifier.weight(1f),
            ) {
                Icon(Icons.AutoMirrored.Outlined.Send, null)
                Spacer(Modifier.width(7.dp))
                Text("Share")
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = vm::reviewSounding, modifier = Modifier.weight(1f)) {
                Text("Review sounding")
            }
            Button(
                onClick = if (state.isPractice) vm::startPractice else vm::home,
                modifier = Modifier.weight(1f),
            ) {
                Text(if (state.isPractice) "Practice again" else "Home")
            }
        }
    }
}

@Composable
private fun RankingsPage(state: SoundingHuntUiState, vm: SoundingHuntViewModel) {
    PageColumn {
        Spacer(Modifier.height(18.dp))
        BrandHeader("DAILY LEADERBOARD")
        Text(
            "Rankings",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
        )
        Text("Every point counts. Explore the atmosphere together.", color = Muted)
        val board = state.leaderboard
        if (board == null) {
            Text("Leaderboard will appear when today’s challenge is available.", color = Muted)
        } else {
            ElevatedCard(colors = cardColors()) {
                Column(
                    Modifier.fillMaxWidth().padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        "CHALLENGE #${board.challengeNumber}",
                        style = MaterialTheme.typography.labelMedium,
                        color = Sky,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        "${board.totalPlayers} players",
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        board.playerRank?.let { "Your place  #$it" }
                            ?: "Submit today to join the board",
                        color = Muted,
                    )
                }
            }
            val podium = if (board.page == 1) board.rows.take(3) else emptyList()
            if (podium.isNotEmpty()) {
                Text(
                    "TOP EXPLORERS",
                    style = MaterialTheme.typography.labelLarge,
                    color = Sky,
                    fontWeight = FontWeight.Bold,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    podium.forEachIndexed { index, row ->
                        Surface(
                            color =
                                when (index) {
                                    0 -> MaterialTheme.colorScheme.tertiaryContainer
                                    1 -> MaterialTheme.colorScheme.primaryContainer
                                    else -> MaterialTheme.colorScheme.secondaryContainer
                                },
                            shape = RoundedCornerShape(20.dp),
                            modifier = Modifier.weight(1f),
                        ) {
                            Column(
                                Modifier.padding(horizontal = 9.dp, vertical = 16.dp),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                Icon(Icons.Outlined.EmojiEvents, "Rank ${row.rank}", tint = Warm)
                                Text("#${row.rank}", fontWeight = FontWeight.Black)
                                Text(
                                    row.displayName + if (row.isYou) " · you" else "",
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    style = MaterialTheme.typography.labelMedium,
                                )
                                Text(row.score.toString(), fontWeight = FontWeight.Black)
                            }
                        }
                    }
                }
            }
            board.rows.drop(podium.size).forEach { row ->
                Surface(
                    color = if (row.isYou) WxGame.colors.selected else Panel,
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            if (row.rank <= 3) "★ #${row.rank}" else "#${row.rank}",
                            modifier = Modifier.width(46.dp),
                            color = Sky,
                            fontWeight = FontWeight.Bold,
                        )
                        Column(Modifier.weight(1f)) {
                            Text(
                                row.displayName + if (row.isYou) "  ·  you" else "",
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                "${formatDistance(row.distanceMiles)} away",
                                color = Muted,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        Text(row.score.toString(), fontWeight = FontWeight.Bold, color = Warm)
                    }
                }
            }
            if (board.rows.isEmpty()) Text("No guesses yet. Be first on the board.", color = Muted)
        }
        state.challenge?.let {
            if (!it.completed) {
                Button(onClick = vm::startDaily, modifier = Modifier.fillMaxWidth()) {
                    Text("Play today’s challenge")
                }
            }
        }
    }
}

@Composable
private fun ProfilePage(
    state: SoundingHuntUiState,
    vm: SoundingHuntViewModel,
    appearance: String,
    onAppearanceChange: (String) -> Unit,
) {
    val profile = state.profile
    PageColumn {
        Spacer(Modifier.height(18.dp))
        BrandHeader("SOUNDING HUNT · YOUR JOURNEY")
        Text(
            "Profile",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "Appearance",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("light" to "Sunlit", "dark" to "Night", "system" to "Device").forEach {
                (mode, label) ->
                FilterChip(
                    selected = appearance == mode,
                    onClick = { onAppearanceChange(mode) },
                    label = { Text(label) },
                )
            }
        }
        ElevatedCard(colors = cardColors()) {
            Column(
                Modifier.fillMaxWidth().padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(
                    profile?.displayName ?: "Guest player",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text("Guest profile · progress saved to this device account", color = Muted)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard(
                "Played",
                profile?.dailyChallengesPlayed?.toString() ?: "—",
                Modifier.weight(1f),
            )
            MetricCard(
                "Average",
                profile?.averageScore?.roundToInt()?.toString() ?: "—",
                Modifier.weight(1f),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("Best", profile?.bestScore?.toString() ?: "—", Modifier.weight(1f))
            MetricCard(
                "Avg. error",
                profile?.averageErrorMiles?.let(::formatDistance) ?: "—",
                Modifier.weight(1f),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MetricCard("Streak", "${profile?.currentStreak ?: 0} days", Modifier.weight(1f))
            MetricCard("Longest", "${profile?.longestStreak ?: 0} days", Modifier.weight(1f))
        }
        Text(
            "Challenge history",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
        if (profile?.history.isNullOrEmpty()) {
            Text("Your completed daily hunts will show here.", color = Muted)
        }
        profile?.history.orEmpty().forEach { item ->
            HistoryRow(item) { vm.openHistoricalResult(item.challengeDay) }
        }
        OutlinedButton(onClick = vm::home, modifier = Modifier.fillMaxWidth()) {
            Text("Back to today")
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        shape = RoundedCornerShape(16.dp),
        modifier = modifier,
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(
                label.uppercase(Locale.US),
                style = MaterialTheme.typography.labelSmall,
                color = Muted,
            )
            Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun HistoryRow(item: HuntHistoryItem, onClick: () -> Unit) {
    Surface(onClick = onClick, color = Panel, shape = RoundedCornerShape(14.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.LocationOn, null, tint = Sky)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Hunt #${item.challengeNumber} · ${dateLabel(item.challengeDay)}",
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "${formatDistance(item.distanceMiles)} away",
                    color = Muted,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Text(item.score.toString(), color = Warm, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun InsightRow(text: String) {
    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.padding(top = 6.dp).size(7.dp).clip(CircleShape).background(Mint))
        Text(text, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun ImmersiveHeader(title: String, onBack: () -> Unit) {
    Row(Modifier.fillMaxWidth().height(44.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack, modifier = Modifier.size(44.dp)) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back")
        }
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun cardColors() =
    androidx.compose.material3.CardDefaults.elevatedCardColors(containerColor = Panel)

private fun utcLabel(value: String): String =
    runCatching {
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm", Locale.US)
                .withZone(ZoneOffset.UTC)
                .format(Instant.parse(value))
        }
        .getOrDefault(value.replace('T', ' ').take(16))

private fun dateLabel(value: String) = value

private fun formatDistance(miles: Double): String =
    if (miles < 1.0) "<1 mi" else "${miles.roundToInt()} mi"
