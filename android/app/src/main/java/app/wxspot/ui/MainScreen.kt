package app.wxspot.ui

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import app.wxspot.domain.Tool
import app.wxspot.domain.WeatherPost
import coil3.compose.AsyncImage
import java.io.ByteArrayOutputStream
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

private val contentTypes =
    listOf(
        "analysis" to "Analysis",
        "observation" to "Observation",
        "question" to "Question",
        "photo_report" to "Photo / Report",
    )
private val topics =
    listOf(
        "rotation",
        "hail",
        "damaging_wind",
        "boundary",
        "flooding",
        "heavy_rain",
        "tropical",
        "winter",
        "model_trend",
        "temperature",
        "aviation",
        "other",
    )

fun utc(value: String?): String =
    runCatching {
            DateTimeFormatter.ofPattern("HH:mm 'UTC'")
                .withZone(ZoneOffset.UTC)
                .format(OffsetDateTime.parse(value).toInstant())
        }
        .getOrDefault("Time unavailable")

private fun label(value: String) = value.replace('_', ' ').replaceFirstChar { it.uppercase() }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: MapViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var native by remember { mutableStateOf<NativeMap?>(null) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            vm.expireAlerts()
            var ticks = 0
            while (true) {
                delay(10_000)
                vm.expireAlerts()
                ticks++
                if (ticks == 6) {
                    ticks = 0
                    if (vm.state.value.draft == null) vm.refresh()
                }
            }
        }
    }
    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            vm.clearMessage()
        }
    }
    BackHandler(state.selected != null || state.draft != null) {
        if (state.draft != null) vm.sheet("leave_draft") else vm.closePost()
    }
    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbar, Modifier.navigationBarsPadding()) },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            WeatherMap(state, vm, Modifier.fillMaxSize().testTag("weather_map")) { native = it }
            Column(
                Modifier.align(Alignment.TopCenter)
                    .fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.safeDrawing)
                    .padding(horizontal = 10.dp)
            ) {
                Surface(
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.95f),
                    shape = RoundedCornerShape(20.dp),
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            Icons.Default.Map,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                        Text(
                            "WxSpot",
                            Modifier.padding(start = 8.dp).weight(1f),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                        )
                        if (state.draft == null) {
                            TextButton(onClick = { vm.feed() }) { Text("Feed") }
                            IconButton(onClick = { vm.sheet("layers") }) {
                                Icon(Icons.Default.Layers, "Weather layers")
                            }
                            IconButton(onClick = { vm.sheet("filters") }) {
                                Icon(Icons.Default.FilterList, "Map discovery filters")
                            }
                            IconButton(onClick = vm::account) {
                                Icon(Icons.Default.Person, "Account")
                            }
                        } else {
                            TextButton(onClick = { vm.sheet("leave_draft") }) { Text("Exit") }
                        }
                    }
                }
                if (state.draft != null) {
                    Surface(Modifier.padding(top = 8.dp), shape = RoundedCornerShape(14.dp)) {
                        Column(Modifier.padding(10.dp)) {
                            Text(
                                "Marking ${utc(state.draft!!.context.layers.first().validTime)}",
                                style = MaterialTheme.typography.labelLarge,
                            )
                            Text(
                                when (state.tool) {
                                    Tool.SELECT ->
                                        "Touch a mark to select; drag it to move or drag a white handle to resize."
                                    Tool.PIN -> "Tap to place a pin."
                                    Tool.ELLIPSE ->
                                        "Drag across the feature to draw a circle or ellipse."
                                    Tool.ARROW ->
                                        "Drag in the direction you want the arrow to point."
                                    Tool.LINE,
                                    Tool.POLYGON -> "Tap each point, then choose Finish shape."
                                    Tool.FREEHAND -> "Drag to draw over the weather feature."
                                    Tool.TEXT -> "Tap where you want the label."
                                },
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                } else if (
                    state.posts.isEmpty() && state.socialState == "ready" && state.selected == null
                ) {
                    Surface(
                        Modifier.padding(top = 8.dp),
                        color = Color(0xDD0B1220),
                        shape = RoundedCornerShape(14.dp),
                    ) {
                        Text(
                            "Hold the map to mark what you see. Community posts appear here.",
                            Modifier.padding(12.dp),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
            Column(
                Modifier.align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.safeDrawing)
                    .padding(horizontal = 10.dp)
            ) {
                if (
                    state.sourceState !in listOf("ready", "loading") ||
                        state.rasterState in
                            listOf("source_unavailable", "network_unavailable", "no_data")
                ) {
                    Surface(color = Color(0xFF332C18), shape = RoundedCornerShape(10.dp)) {
                        Row(
                            Modifier.padding(horizontal = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                Icons.Default.WarningAmber,
                                null,
                                tint = Color(0xFFFDE68A),
                                modifier = Modifier.size(18.dp),
                            )
                            Text(
                                when {
                                    state.rasterState == "no_data" ->
                                        "The marked scan has expired. Your saved draft is still here."
                                    state.rasterState == "source_unavailable" ->
                                        "Radar imagery is unavailable for this scan."
                                    state.rasterState == "network_unavailable" ->
                                        "Network unavailable. Radar time is shown below."
                                    state.sourceState == "source_delayed" ->
                                        "NOAA radar source is delayed."
                                    state.sourceState == "unsupported_product" ->
                                        "This radar site does not support this product."
                                    state.sourceState == "no_data" ->
                                        "No radar scans are available."
                                    else ->
                                        "Radar source unavailable. Preserved annotations can still open."
                                },
                                Modifier.weight(1f).padding(8.dp),
                                style = MaterialTheme.typography.bodySmall,
                            )
                            IconButton(onClick = vm::refresh) {
                                Icon(Icons.Default.Refresh, "Retry weather sources")
                            }
                        }
                    }
                }
                if (state.socialState == "network_unavailable") {
                    Text(
                        "Community posts unavailable · tap Refresh to retry",
                        Modifier.background(Color(0xEE0B1220))
                            .clickable { vm.loadPosts() }
                            .padding(8.dp),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (state.selected != null && state.draft == null) PostPanel(state, vm)
                if (state.draft != null) EditorPanel(state, vm) { native?.finishShape() }
                Timeline(state, vm)
                Text(
                    "© OpenStreetMap contributors • Weather: NOAA / NWS",
                    Modifier.fillMaxWidth().background(Color(0xEE0B1220)).padding(4.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFFBBCBDD),
                )
            }
        }
    }

    val sheet = state.sheet
    if (sheet in listOf("leave_draft", "resume")) {
        AlertDialog(
            onDismissRequest = { vm.sheet(null) },
            title = {
                Text(if (sheet == "resume") "Continue your annotation?" else "Keep this draft?")
            },
            text = {
                Text("Your weather context, marks, and description are saved on this device.")
            },
            confirmButton = {
                TextButton(onClick = { vm.resumeDraft() }) { Text("Continue editing") }
            },
            dismissButton = { TextButton(onClick = vm::discardDraft) { Text("Discard draft") } },
        )
    } else if (sheet == "text") {
        var text by remember(sheet) { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { vm.sheet(null) },
            title = { Text("Add a label") },
            text = {
                OutlinedTextField(
                    text,
                    { if (it.length <= 120) text = it },
                    label = { Text("Weather feature") },
                )
            },
            confirmButton = {
                TextButton(enabled = text.isNotBlank(), onClick = { vm.addText(text) }) {
                    Text("Add label")
                }
            },
            dismissButton = { TextButton(onClick = { vm.sheet(null) }) { Text("Cancel") } },
        )
    } else if (sheet != null) {
        ModalBottomSheet(
            onDismissRequest = { vm.sheet(null) },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        ) {
            Box(Modifier.fillMaxWidth().heightIn(max = 650.dp).padding(bottom = 24.dp)) {
                when (sheet) {
                    "mark" -> MarkPanel(state, vm)
                    "layers" -> LayerPanel(state, vm)
                    "filters" -> FilterPanel(state, vm)
                    "composer" -> Composer(state, vm)
                    "feed" -> FeedPanel(state, vm)
                    "cluster" ->
                        LazyColumn {
                            item {
                                Text(
                                    "People marking this area",
                                    Modifier.padding(20.dp),
                                    style = MaterialTheme.typography.titleLarge,
                                )
                            }
                            items(state.cluster, key = { it.id }) { post ->
                                FeedItem(post) { vm.open(post) }
                            }
                        }
                    "account" -> ProfilePanel(state, vm)
                    "notifications" ->
                        LazyColumn {
                            item {
                                Text(
                                    "Community notifications",
                                    Modifier.padding(20.dp),
                                    style = MaterialTheme.typography.titleLarge,
                                )
                                Text(
                                    "Replies and posts from people you follow.",
                                    Modifier.padding(horizontal = 20.dp),
                                )
                            }
                            if (state.notifications.isEmpty())
                                item { Text("No notifications yet.", Modifier.padding(20.dp)) }
                            items(state.notifications) { n ->
                                Column(
                                    Modifier.fillMaxWidth()
                                        .clickable { vm.openNotification(n) }
                                        .padding(20.dp)
                                ) {
                                    Text(
                                        if (n["kind"]?.jsonPrimitive?.content == "reply")
                                            "Someone replied to your discussion"
                                        else "A person you follow posted an annotation"
                                    )
                                    Text(
                                        utc(n["created_at"]?.jsonPrimitive?.content),
                                        style = MaterialTheme.typography.bodySmall,
                                    )
                                }
                                HorizontalDivider()
                            }
                        }
                }
            }
        }
    }
    state.officialSelection?.let { alert ->
        ModalBottomSheet(onDismissRequest = { vm.official(null) }) {
            Column(
                Modifier.padding(20.dp).heightIn(max = 540.dp).verticalScroll(rememberScrollState())
            ) {
                Text(
                    "OFFICIAL · NATIONAL WEATHER SERVICE",
                    color = Color(0xFFFDE68A),
                    style = MaterialTheme.typography.labelLarge,
                )
                Text(
                    alert["event"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    Modifier.padding(top = 12.dp),
                    style = MaterialTheme.typography.headlineSmall,
                )
                Text(
                    alert["headline"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    Modifier.padding(vertical = 12.dp),
                )
                Text(
                    "Issued ${utc(alert["issued"]?.jsonPrimitive?.contentOrNull)} · Expires ${utc(alert["expires"]?.jsonPrimitive?.contentOrNull)}"
                )
                Text(
                    alert["issuing_office"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    alert["description"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    Modifier.padding(top = 16.dp),
                )
                Text(
                    alert["instruction"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    Modifier.padding(vertical = 16.dp),
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@Composable
private fun Timeline(state: UiState, vm: MapViewModel) {
    val frame = state.currentFrame
    var showLegend by remember { mutableStateOf(false) }
    val legend =
        frame?.legendUrl?.ifBlank { null }
            ?: state.replay?.markedLayer?.metadata?.get("legend_url")?.jsonPrimitive?.contentOrNull
    val index = state.timeline.indexOfFirst { it.id == frame?.id }.coerceAtLeast(0)
    Surface(Modifier.padding(top = 6.dp), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        "${state.site} · ${if (state.product == "velocity") "Base radial velocity" else "Base reflectivity"}",
                        style = MaterialTheme.typography.labelLarge,
                    )
                    Text(
                        if (frame == null) "Loading available scans…"
                        else {
                            val age =
                                runCatching {
                                        java.time.Duration.between(frame.instant(), Instant.now())
                                            .toMinutes()
                                    }
                                    .getOrDefault(0)
                            "${utc(frame.validTime)} · ${age.coerceAtLeast(0)} min old" +
                                if (state.rasterState == "loading") " · Loading imagery" else ""
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (state.draft == null) {
                    IconButton(onClick = vm::play, enabled = state.timeline.size > 1) {
                        Icon(
                            if (state.playing) Icons.Default.Pause else Icons.Default.PlayArrow,
                            if (state.playing) "Pause radar animation" else "Animate radar scans",
                        )
                    }
                    TextButton(onClick = vm::live, enabled = state.frames.isNotEmpty()) {
                        Text("Latest")
                    }
                }
            }
            if (!legend.isNullOrBlank()) {
                TextButton(onClick = { showLegend = !showLegend }) {
                    Text(if (showLegend) "Hide NOAA legend" else "NOAA legend")
                }
                if (showLegend) {
                    AsyncImage(
                        model = legend,
                        contentDescription = "Official NOAA radar color scale",
                        modifier = Modifier.fillMaxWidth().height(32.dp),
                    )
                    Text(
                        if (state.product == "reflectivity") "Reflectivity in dBZ"
                        else
                            "Radial velocity: toward / away from the radar. NOAA provider scale; RF = range folded.",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            state.replay?.let { replay ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Marked ${utc(replay.markedLayer.validTime)} · Viewing ${utc(replay.viewingTime)}" +
                            " (${if (replay.deltaMinutes >= 0) "+" else ""}${replay.deltaMinutes} min)",
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                TextButton(
                    onClick = vm::marked,
                    enabled = !replay.isMarked,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Return to marked frame")
                }
            }
            if (state.draft == null && state.timeline.size > 1) {
                Slider(
                    modifier = Modifier.testTag("weather_timeline"),
                    value = index.toFloat(),
                    onValueChange = {
                        vm.stopPlayback()
                        vm.scrub(it.roundToInt())
                    },
                    valueRange = 0f..state.timeline.lastIndex.toFloat(),
                    steps = (state.timeline.size - 2).coerceAtLeast(0),
                )
            }
        }
    }
}

@Composable
private fun EditorPanel(state: UiState, vm: MapViewModel, finish: () -> Unit) {
    Surface(Modifier.padding(top = 6.dp), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Tool.entries.forEach { tool ->
                    FilterChip(
                        selected = state.tool == tool,
                        onClick = { vm.tool(tool) },
                        label = { Text(tool.label) },
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                listOf("#67E8F9", "#FDE68A", "#F9A8D4", "#FFFFFF").forEach { color ->
                    TextButton(onClick = { vm.color(color) }, modifier = Modifier.size(48.dp)) {
                        Box(
                            Modifier.size(if (state.color == color) 24.dp else 16.dp)
                                .background(
                                    Color(android.graphics.Color.parseColor(color)),
                                    CircleShape,
                                )
                        )
                    }
                }
                Spacer(Modifier.weight(1f))
                TextButton(
                    onClick = {
                        vm.stroke(
                            if (state.stroke == 3.0) 5.0 else if (state.stroke == 5.0) 1.5 else 3.0
                        )
                    }
                ) {
                    Text("Stroke ${state.stroke.toInt()}")
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(enabled = state.editor.undo.isNotEmpty(), onClick = vm::undo) {
                    Text("Undo")
                }
                TextButton(enabled = state.editor.redo.isNotEmpty(), onClick = vm::redo) {
                    Text("Redo")
                }
                TextButton(enabled = state.editor.selectedId != null, onClick = vm::deleteElement) {
                    Text("Delete")
                }
                if (state.tool in listOf(Tool.LINE, Tool.POLYGON))
                    TextButton(onClick = finish) { Text("Finish shape") }
            }
            Button(
                onClick = { vm.sheet("composer") },
                enabled = state.editor.elements.isNotEmpty(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Describe & publish · ${state.editor.elements.size} marks")
            }
        }
    }
}

@Composable
private fun PostPanel(state: UiState, vm: MapViewModel) {
    val post = state.selected ?: return
    var reportTarget by remember(post.id) { mutableStateOf<Pair<String, String>?>(null) }
    var reason by remember { mutableStateOf("") }
    var replyTo by remember(post.id) { mutableStateOf<String?>(null) }
    var comment by remember(post.id) { mutableStateOf("") }
    var confirmDelete by remember { mutableStateOf(false) }
    Surface(Modifier.padding(top = 6.dp), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(post.author.displayName, fontWeight = FontWeight.SemiBold)
                    Text(
                        post.author.verifiedRole?.let { "Verified ${label(it).lowercase()}" }
                            ?: if (post.author.selfRole == "enthusiast") "Weather enthusiast"
                            else "Self-described ${label(post.author.selfRole).lowercase()}",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Text(
                    label(post.contentType),
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.labelMedium,
                )
                IconButton(onClick = vm::closePost) {
                    Icon(Icons.Default.Close, "Close annotation")
                }
            }
            Column(
                Modifier.heightIn(max = if (state.expandedPost) 310.dp else 88.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                post.title?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
                Text(
                    post.description,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = if (state.expandedPost) Int.MAX_VALUE else 3,
                )
                if (state.expandedPost) {
                    post.whyItMatters?.let {
                        Text(
                            "Why this matters",
                            Modifier.padding(top = 12.dp),
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(it)
                    }
                    post.watchNext?.let {
                        Text(
                            "What to watch next",
                            Modifier.padding(top = 12.dp),
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(it)
                    }
                    post.photos.forEach { path ->
                        AsyncImage(
                            model = vm.api.url(path),
                            contentDescription = "Photo shared by the author",
                            modifier =
                                Modifier.fillMaxWidth()
                                    .heightIn(max = 200.dp)
                                    .padding(vertical = 8.dp),
                        )
                    }
                    Text(
                        "Posted ${utc(post.createdAt)} · Community interpretation",
                        Modifier.padding(top = 10.dp),
                        style = MaterialTheme.typography.labelSmall,
                    )
                    Row {
                        TextButton(onClick = { reportTarget = "post" to post.id }) {
                            Text("Report")
                        }
                        if (state.session?.userId != post.author.id)
                            TextButton(onClick = vm::blockAuthor) { Text("Block author") }
                        else TextButton(onClick = { confirmDelete = true }) { Text("Delete post") }
                    }
                    HorizontalDivider()
                    Text(
                        "Discussion",
                        Modifier.padding(top = 12.dp),
                        style = MaterialTheme.typography.titleSmall,
                    )
                    state.comments.asReversed().forEach { entry ->
                        Column(
                            Modifier.padding(
                                start = if (entry.parentId == null) 0.dp else 18.dp,
                                top = 12.dp,
                            )
                        ) {
                            Text(
                                entry.author.displayName + " · " + utc(entry.createdAt),
                                style = MaterialTheme.typography.labelMedium,
                            )
                            Text(entry.body, style = MaterialTheme.typography.bodySmall)
                            Row {
                                if (entry.parentId == null)
                                    TextButton(onClick = { replyTo = entry.id }) { Text("Reply") }
                                TextButton(onClick = { reportTarget = "comment" to entry.id }) {
                                    Text("Report")
                                }
                                if (entry.author.id == state.session?.userId)
                                    TextButton(onClick = { vm.removeComment(entry.id) }) {
                                        Text("Delete")
                                    }
                            }
                        }
                    }
                    if (state.commentsLoading)
                        CircularProgressIndicator(Modifier.padding(12.dp).size(24.dp))
                    if (state.commentsCursor != null)
                        TextButton(onClick = { vm.loadComments(more = true) }) {
                            Text("Earlier comments")
                        }
                    if (replyTo != null)
                        TextButton(onClick = { replyTo = null }) {
                            Text("Replying to comment · Cancel")
                        }
                    OutlinedTextField(
                        comment,
                        { if (it.length <= 2000) comment = it },
                        label = {
                            Text(if (replyTo == null) "Add to the discussion" else "Your reply")
                        },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    TextButton(
                        enabled = comment.isNotBlank(),
                        onClick = {
                            vm.comment(comment, replyTo)
                            comment = ""
                            replyTo = null
                        },
                    ) {
                        Text("Post comment")
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = vm::like) {
                    Icon(
                        if (post.liked) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                        "Like annotation",
                        modifier = Modifier.size(18.dp),
                    )
                    Text(" ${post.likeCount}")
                }
                TextButton(onClick = { vm.expandedPost(!state.expandedPost) }) {
                    Text(
                        "${post.commentCount} replies · ${if (state.expandedPost) "Less" else "More"}"
                    )
                }
                Spacer(Modifier.weight(1f))
                if (state.session?.userId != post.author.id)
                    TextButton(onClick = vm::follow) {
                        Text(if (post.followingAuthor) "Following" else "Follow")
                    }
            }
        }
    }
    if (reportTarget != null)
        AlertDialog(
            onDismissRequest = { reportTarget = null },
            title = { Text("Report community content") },
            text = {
                OutlinedTextField(
                    reason,
                    { reason = it.take(1000) },
                    label = { Text("What should a moderator review?") },
                )
            },
            confirmButton = {
                TextButton(
                    enabled = reason.trim().length >= 3,
                    onClick = {
                        reportTarget?.let { vm.report(it.first, it.second, reason.trim()) }
                        reportTarget = null
                        reason = ""
                    },
                ) {
                    Text("Send report")
                }
            },
            dismissButton = { TextButton(onClick = { reportTarget = null }) { Text("Cancel") } },
        )
    if (confirmDelete)
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Remove this annotation?") },
            text = { Text("It will no longer appear on the map.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        vm.deletePost()
                        confirmDelete = false
                    }
                ) {
                    Text("Remove")
                }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
}

@Composable
private fun ProfilePanel(state: UiState, vm: MapViewModel) {
    var name by
        remember(state.session?.userId, state.session?.displayName) {
            mutableStateOf(state.session?.displayName.orEmpty())
        }
    Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState())) {
        Text("Your profile", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Saved on this device. No sign-in needed.",
            Modifier.padding(vertical = 12.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
        OutlinedTextField(
            name,
            { name = it.take(60) },
            label = { Text("Display name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { vm.updateDisplayName(name) },
            enabled = !state.busy && name.isNotBlank(),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        ) {
            if (state.busy) CircularProgressIndicator(Modifier.size(18.dp))
            else Text("Save profile")
        }
        OutlinedButton(onClick = vm::notifications, modifier = Modifier.fillMaxWidth()) {
            Text("Community notifications")
        }
        HorizontalDivider(Modifier.padding(vertical = 16.dp))
        Text("Blocked people", style = MaterialTheme.typography.titleMedium)
        if (state.blockedPeople.isEmpty()) {
            Text("You haven't blocked anyone.", style = MaterialTheme.typography.bodySmall)
        } else {
            state.blockedPeople.forEach { person ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(person.getValue("display_name").jsonPrimitive.content, Modifier.weight(1f))
                    TextButton(
                        onClick = { vm.unblock(person.getValue("id").jsonPrimitive.content) }
                    ) {
                        Text("Unblock")
                    }
                }
            }
        }
        TextButton(onClick = { vm.sheet(null) }) { Text("Return to map") }
    }
}

@Composable
private fun MarkPanel(state: UiState, vm: MapViewModel) {
    Column(Modifier.padding(horizontal = 20.dp)) {
        Text("Mark this", style = MaterialTheme.typography.headlineSmall)
        Text(
            "${state.pending?.context?.layers?.first()?.radarSite} · ${utc(state.pending?.context?.layers?.first()?.validTime)}",
            Modifier.padding(vertical = 10.dp),
        )
        contentTypes.forEach { (type, name) ->
            OutlinedButton(onClick = { vm.startDraft(type) }, modifier = Modifier.fillMaxWidth()) {
                Text(name)
            }
        }
    }
}

@Composable
private fun LayerPanel(state: UiState, vm: MapViewModel) {
    var site by remember { mutableStateOf(state.site) }
    var product by remember { mutableStateOf(state.product) }
    Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState())) {
        Text("Weather layers", style = MaterialTheme.typography.headlineSmall)
        Text(
            "NOAA radar",
            Modifier.padding(top = 14.dp),
            style = MaterialTheme.typography.titleMedium,
        )
        OutlinedTextField(
            site,
            { site = it.uppercase().take(4) },
            label = { Text("Radar site, e.g. KCLX") },
            singleLine = true,
        )
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("KCLX", "KCAE", "KGSP", "KGYX", "KBOX", "KTLX").forEach {
                FilterChip(site == it, { site = it }, label = { Text(it) })
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                product == "reflectivity",
                { product = "reflectivity" },
                label = { Text("Reflectivity") },
            )
            FilterChip(
                product == "velocity",
                { product = "velocity" },
                label = { Text("Velocity") },
            )
        }
        Text(
            if (product == "reflectivity")
                "Reflectivity shows radar energy returned by precipitation and other targets."
            else "Radial velocity shows motion toward or away from this radar.",
            style = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = { vm.layer(site, product) },
            enabled = site.matches(Regex("[KPT][A-Z0-9]{3}")),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        ) {
            Text("Show this radar")
        }
        Text("Layer opacity", Modifier.padding(top = 14.dp))
        Slider(state.opacity.toFloat(), { vm.opacity(it.toDouble()) }, valueRange = 0.2f..1f)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Live official NWS alerts", color = Color(0xFFFDE68A))
                Text(
                    "Current alerts · independent of the radar timeline",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(state.showAlerts, vm::showAlerts)
        }
        if (
            state.alertsState == "source_unavailable" || state.alertsState == "network_unavailable"
        ) {
            Text(
                "NWS alerts are unavailable. Previously received unexpired polygons may remain visible.",
                color = Color(0xFFFDE68A),
            )
        }
        TextButton(
            onClick = {
                vm.sheet(null)
                vm.longPress(state.camera.center, state.camera, state.bounds)
            }
        ) {
            Text("Mark the map center")
        }
    }
}

@Composable
private fun FilterPanel(state: UiState, vm: MapViewModel) {
    Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState())) {
        Text("Community on the map", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Up to ten annotations in this area, from the last 24 hours.",
            Modifier.padding(vertical = 12.dp),
        )
        listOf(
                "recent" to "Recent",
                "top" to "Top · engagement with time decay",
                "following" to "People you follow",
                "most_followed" to "Most-followed authors",
            )
            .forEach { (sort, name) ->
                FilterChip(state.sort == sort, { vm.filter(sort = sort) }, label = { Text(name) })
            }
        Text("Content", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleSmall)
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                state.typeFilter == null,
                { vm.filter(type = null) },
                label = { Text("All") },
            )
            contentTypes.forEach { (type, name) ->
                FilterChip(
                    state.typeFilter == type,
                    { vm.filter(type = type) },
                    label = { Text(name) },
                )
            }
        }
        Text("Topic", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleSmall)
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                state.topicFilter == null,
                { vm.filter(topic = null) },
                label = { Text("All") },
            )
            topics.forEach { topic ->
                FilterChip(
                    state.topicFilter == topic,
                    { vm.filter(topic = topic) },
                    label = { Text(label(topic)) },
                )
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Verified authors only", Modifier.weight(1f))
            Switch(state.verifiedOnly, { vm.filter(verified = it) })
        }
        Text(
            "Self-described roles are distinct from verified credentials.",
            style = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = { vm.sheet(null) },
            modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
        ) {
            Text("Return to map")
        }
    }
}

@Composable
private fun Composer(state: UiState, vm: MapViewModel) {
    val draft = state.draft ?: return
    var advanced by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val picker =
        rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            uri?.let { selected ->
                scope.launch {
                    runCatching {
                            withContext(Dispatchers.IO) {
                                context.contentResolver.openInputStream(selected)?.use { input ->
                                    val output = ByteArrayOutputStream()
                                    val buffer = ByteArray(16 * 1024)
                                    while (true) {
                                        val count = input.read(buffer)
                                        if (count < 0) break
                                        require(output.size() + count <= 5 * 1024 * 1024) {
                                            "Choose a photo smaller than 5 MB."
                                        }
                                        output.write(buffer, 0, count)
                                    }
                                    output.toByteArray()
                                }
                            }
                        }
                        .onSuccess { data -> if (data != null) vm.upload(data) }
                        .onFailure { vm.message(it.message ?: "Could not open that photo.") }
                }
            }
        }
    Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState())) {
        Text("Explain what you marked", style = MaterialTheme.typography.headlineSmall)
        Text(
            "${label(draft.contentType)} · ${utc(draft.context.layers.first().validTime)}",
            Modifier.padding(vertical = 8.dp),
            color = MaterialTheme.colorScheme.primary,
        )
        OutlinedTextField(
            draft.description,
            { vm.draft(draft.copy(description = it.take(6000))) },
            label = { Text("What are you seeing?") },
            minLines = 3,
            modifier = Modifier.fillMaxWidth(),
        )
        TextButton(onClick = { advanced = !advanced }) {
            Text(
                if (advanced) "Hide optional details" else "Add title, topics & what to watch next"
            )
        }
        if (advanced) {
            OutlinedTextField(
                draft.title,
                { vm.draft(draft.copy(title = it.take(120))) },
                label = { Text("Short title (optional)") },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                draft.whyItMatters,
                { vm.draft(draft.copy(whyItMatters = it.take(2000))) },
                label = { Text("Why this matters (optional)") },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            OutlinedTextField(
                draft.watchNext,
                { vm.draft(draft.copy(watchNext = it.take(2000))) },
                label = { Text("What to watch next (optional)") },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                topics.forEach { topic ->
                    FilterChip(
                        topic in draft.topics,
                        {
                            vm.draft(
                                draft.copy(
                                    topics =
                                        if (topic in draft.topics) draft.topics - topic
                                        else (draft.topics + topic).take(8)
                                )
                            )
                        },
                        label = { Text(label(topic)) },
                    )
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(
                enabled = !state.busy && draft.photoIds.size < 4,
                onClick = {
                    picker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
            ) {
                Text("Add photo")
            }
            Text("${draft.photoIds.size} attached", style = MaterialTheme.typography.bodySmall)
        }
        Text(
            "Community interpretation · the original weather frame and your geographic marks will be preserved.",
            style = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = vm::publish,
            enabled = !state.busy && draft.description.isNotBlank(),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        ) {
            if (state.busy) CircularProgressIndicator(Modifier.size(20.dp))
            else Text("Publish annotation")
        }
        TextButton(onClick = { vm.sheet(null) }) { Text("Back to marking") }
    }
}

@Composable
private fun FeedPanel(state: UiState, vm: MapViewModel) {
    Column {
        Text(
            "Weather conversation",
            Modifier.padding(horizontal = 20.dp),
            style = MaterialTheme.typography.headlineSmall,
        )
        Row(
            Modifier.padding(horizontal = 20.dp).horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf(
                    "nearby" to "This map area",
                    "recent" to "Recent",
                    "following" to "Following",
                    "top" to "Top",
                )
                .forEach { (scope, name) ->
                    FilterChip(state.feedScope == scope, { vm.feed(scope) }, label = { Text(name) })
                }
        }
        LazyColumn {
            if (state.feedLoading)
                item { CircularProgressIndicator(Modifier.padding(20.dp).size(24.dp)) }
            if (state.feedItems.isEmpty() && !state.feedLoading)
                item {
                    Text(
                        "No annotations here yet. Hold a location on the map to start the conversation.",
                        Modifier.padding(20.dp),
                    )
                }
            items(state.feedItems, key = { it.id }) { post -> FeedItem(post) { vm.open(post) } }
            if (state.feedCursor != null)
                item {
                    TextButton(
                        enabled = !state.feedLoading,
                        onClick = { vm.feed(state.feedScope, more = true) },
                    ) {
                        Text("More annotations")
                    }
                }
        }
    }
}

@Composable
private fun FeedItem(post: WeatherPost, click: () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .clickable(onClick = click)
            .padding(horizontal = 20.dp, vertical = 14.dp)
    ) {
        Row {
            Text(
                post.author.displayName,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Text(
                label(post.contentType),
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelMedium,
            )
        }
        post.title?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
        Text(post.description, maxLines = 3, style = MaterialTheme.typography.bodyMedium)
        Text(
            "${post.context.layers.first().radarSite} · ${utc(post.context.layers.first().validTime)} · ${post.likeCount} likes · Open on map",
            Modifier.padding(top = 6.dp),
            style = MaterialTheme.typography.labelSmall,
        )
    }
    HorizontalDivider()
}
