package app.wxspot.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.wxspot.data.ApiException
import app.wxspot.data.ApiRepository
import app.wxspot.data.DraftStore
import app.wxspot.data.Session
import app.wxspot.domain.AlertLifetime
import app.wxspot.domain.AnnotationElement
import app.wxspot.domain.Camera
import app.wxspot.domain.Comment
import app.wxspot.domain.Draft
import app.wxspot.domain.EditorState
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.PostCreate
import app.wxspot.domain.RadarFrame
import app.wxspot.domain.ReplaySession
import app.wxspot.domain.Tool
import app.wxspot.domain.WeatherContext
import app.wxspot.domain.WeatherPost
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

data class PendingMark(val point: List<Double>, val context: WeatherContext)

data class UiState(
    val site: String = "KCLX",
    val product: String = "reflectivity",
    val frames: List<RadarFrame> = emptyList(),
    val viewingId: String? = null,
    val sourceState: String = "loading",
    val rasterState: String = "loading",
    val camera: Camera = Camera(),
    val bounds: List<Double> = listOf(-82.0, 31.5, -78.0, 34.5),
    val cameraRevision: Int = 0,
    val opacity: Double = 0.8,
    val posts: List<WeatherPost> = emptyList(),
    val socialState: String = "loading",
    val sort: String = "recent",
    val typeFilter: String? = null,
    val topicFilter: String? = null,
    val verifiedOnly: Boolean = false,
    val alerts: String = """{"type":"FeatureCollection","features":[]}""",
    val alertsState: String = "loading",
    val showAlerts: Boolean = true,
    val officialSelection: JsonObject? = null,
    val selected: WeatherPost? = null,
    val replay: ReplaySession? = null,
    val comments: List<Comment> = emptyList(),
    val commentsCursor: String? = null,
    val commentsLoading: Boolean = false,
    val draft: Draft? = null,
    val editor: EditorState = EditorState(),
    val tool: Tool = Tool.ARROW,
    val color: String = "#67E8F9",
    val stroke: Double = 3.0,
    val textLabel: String = "",
    val textPoint: List<Double>? = null,
    val pending: PendingMark? = null,
    val session: Session? = null,
    val sheet: String? = null,
    val cluster: List<WeatherPost> = emptyList(),
    val message: String? = null,
    val busy: Boolean = false,
    val playing: Boolean = false,
    val followLive: Boolean = true,
    val expandedPost: Boolean = false,
    val notifications: List<JsonObject> = emptyList(),
    val feedItems: List<WeatherPost> = emptyList(),
    val feedCursor: String? = null,
    val feedScope: String = "nearby",
    val feedLoading: Boolean = false,
) {
    val timeline: List<RadarFrame>
        get() =
            draft?.let { draft ->
                val layer = draft.context.layers.first()
                val captured =
                    RadarFrame(
                        layer.frameId,
                        layer.validTime,
                        layer.radarSite.orEmpty(),
                        layer.product,
                    )
                (frames + captured).distinctBy { it.id }.sortedBy { it.instant() }
            } ?: replay?.timeline ?: frames

    val currentFrame: RadarFrame?
        get() =
            timeline.firstOrNull {
                it.id ==
                    (draft?.context?.layers?.first()?.frameId ?: replay?.viewingId ?: viewingId)
            }

    val annotationElements: List<AnnotationElement>
        get() = if (draft != null) editor.elements else selected?.elements.orEmpty()
}

class MapViewModel(val api: ApiRepository, private val drafts: DraftStore) : ViewModel() {
    private val restored = drafts.read()
    private val mutable =
        MutableStateFlow(
            UiState(
                session = api.vault.current,
                draft = restored,
                editor = EditorState(restored?.elements.orEmpty()),
                camera = restored?.context?.camera ?: Camera(),
                sheet = if (restored != null) "resume" else null,
            )
        )
    val state = mutable.asStateFlow()
    private var viewportJob: Job? = null
    private var playbackJob: Job? = null
    private var afterLogin: (() -> Unit)? = null
    private var frameJob: Job? = null

    init {
        refresh()
    }

    fun message(value: String) {
        mutable.update { it.copy(message = value) }
    }

    fun clearMessage() {
        mutable.update { it.copy(message = null) }
    }

    fun sheet(value: String?) {
        mutable.update { it.copy(sheet = value) }
    }

    fun expandedPost(value: Boolean) {
        mutable.update { it.copy(expandedPost = value) }
    }

    private fun task(action: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                action()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                if (error is ApiException && error.status == 401) {
                    api.vault.save(null)
                    mutable.update { it.copy(session = null, sheet = "auth") }
                }
                message(error.message ?: "Network unavailable. Try again.")
            }
        }
    }

    private fun authenticated(action: () -> Unit) {
        if (mutable.value.session == null) {
            afterLogin = action
            sheet("auth")
        } else action()
    }

    fun refresh() {
        expireAlerts()
        loadFrames()
        loadPosts()
        task {
            try {
                val data = api.alerts()
                mutable.update {
                    it.copy(
                        alerts =
                            AlertLifetime.activeCollection(
                                data.getValue("collection").toString(),
                                Instant.now(),
                            ),
                        alertsState = data.getValue("state").jsonPrimitive.content,
                    )
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                mutable.update { it.copy(alertsState = "network_unavailable") }
            }
        }
    }

    fun expireAlerts() {
        val now = Instant.now()
        mutable.update {
            it.copy(
                alerts = AlertLifetime.activeCollection(it.alerts, now),
                officialSelection =
                    it.officialSelection?.takeIf { p -> AlertLifetime.isActive(p, now) },
            )
        }
    }

    private fun loadFrames() {
        val site = mutable.value.site
        val product = mutable.value.product
        frameJob?.cancel()
        frameJob =
            viewModelScope.launch {
                try {
                    val response = api.frames(site, product)
                    mutable.update { s ->
                        if (s.site != site || s.product != product) s
                        else {
                            val replay =
                                s.replay?.let { r ->
                                    val validId =
                                        if (
                                            r.isMarked ||
                                                response.frames.any { it.id == r.viewingId }
                                        ) {
                                            r.viewingId
                                        } else r.markedLayer.frameId
                                    r.copy(frames = response.frames, viewingId = validId)
                                }
                            val chosen =
                                if (s.draft != null) {
                                    s.draft.context.layers.first().frameId
                                } else if (
                                    s.followLive || response.frames.none { it.id == s.viewingId }
                                ) {
                                    response.frames.lastOrNull()?.id
                                } else s.viewingId
                            s.copy(
                                frames = response.frames,
                                sourceState = response.state,
                                viewingId = chosen,
                                replay = replay,
                                rasterState =
                                    if (chosen != s.viewingId) "loading" else s.rasterState,
                            )
                        }
                    }
                    if (response.message != null) message(response.message)
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    mutable.update { it.copy(sourceState = "network_unavailable") }
                }
            }
    }

    fun layer(site: String, product: String) {
        if (mutable.value.draft != null) return
        stopPlayback()
        mutable.update {
            it.copy(
                site = site,
                product = product,
                replay = null,
                selected = null,
                frames = emptyList(),
                viewingId = null,
                sourceState = "loading",
                rasterState = "loading",
                followLive = true,
                sheet = null,
            )
        }
        loadFrames()
    }

    fun opacity(value: Double) {
        mutable.update { it.copy(opacity = value) }
    }

    fun showAlerts(value: Boolean) {
        mutable.update { it.copy(showAlerts = value) }
    }

    fun official(value: JsonObject?) {
        mutable.update { it.copy(officialSelection = value) }
    }

    fun viewport(camera: Camera, bounds: List<Double>) {
        mutable.update { it.copy(camera = camera, bounds = bounds) }
        if (mutable.value.draft != null) return
        viewportJob?.cancel()
        viewportJob =
            viewModelScope.launch {
                delay(350)
                loadPosts()
            }
    }

    fun filter(
        sort: String? = null,
        type: String? = mutable.value.typeFilter,
        topic: String? = mutable.value.topicFilter,
        verified: Boolean = mutable.value.verifiedOnly,
    ) {
        if (sort == "following" && mutable.value.session == null) {
            authenticated { filter("following", type, topic, verified) }
            return
        }
        mutable.update {
            it.copy(
                sort = sort ?: it.sort,
                typeFilter = type,
                topicFilter = topic,
                verifiedOnly = verified,
            )
        }
        loadPosts()
    }

    fun loadPosts() {
        val s = mutable.value
        val query =
            "bbox=${s.bounds.joinToString(",")}&sort=${s.sort}" +
                (s.typeFilter?.let { "&content_type=$it" } ?: "") +
                (s.topicFilter?.let { "&topic=$it" } ?: "") +
                "&verified_only=${s.verifiedOnly}&limit=10"
        task {
            try {
                val response = api.posts(query)
                mutable.update { current ->
                    if (
                        current.bounds != s.bounds ||
                            current.sort != s.sort ||
                            current.typeFilter != s.typeFilter ||
                            current.topicFilter != s.topicFilter ||
                            current.verifiedOnly != s.verifiedOnly
                    )
                        current
                    else current.copy(posts = response.items, socialState = "ready")
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                mutable.update { it.copy(socialState = "network_unavailable") }
                if (error is ApiException && error.status == 401) throw error
            }
        }
    }

    fun open(post: WeatherPost) {
        stopPlayback()
        val layer = post.context.layers.first()
        mutable.update {
            it.copy(
                selected = post,
                replay = ReplaySession(post, emptyList()),
                camera = post.context.camera,
                cameraRevision = it.cameraRevision + 1,
                site = layer.radarSite ?: it.site,
                product = layer.product,
                opacity = layer.opacity,
                viewingId = layer.frameId,
                sheet = null,
                comments = emptyList(),
                expandedPost = false,
                followLive = false,
                rasterState = "loading",
                officialSelection = null,
            )
        }
        loadFrames()
        loadComments()
    }

    fun open(id: String) {
        task { open(api.post(id)) }
    }

    fun closePost() {
        mutable.update {
            it.copy(selected = null, replay = null, expandedPost = false, followLive = true)
        }
        live()
    }

    fun cluster(posts: List<WeatherPost>) {
        if (posts.size == 1) open(posts.first())
        else mutable.update { it.copy(cluster = posts, sheet = "cluster") }
    }

    fun scrub(index: Int) {
        if (mutable.value.draft != null) return
        val frame = mutable.value.timeline.getOrNull(index) ?: return
        mutable.update {
            it.copy(
                viewingId = frame.id,
                replay = it.replay?.advance(frame.id),
                followLive = false,
                rasterState = "loading",
            )
        }
    }

    fun marked() {
        stopPlayback()
        mutable.update { s ->
            val r = s.replay ?: return@update s
            s.copy(
                replay = r.returnToMarked(),
                viewingId = r.markedLayer.frameId,
                camera = r.post.context.camera,
                cameraRevision = s.cameraRevision + 1,
                rasterState = "loading",
                followLive = false,
            )
        }
    }

    fun live() {
        stopPlayback()
        val timeline = mutable.value.timeline
        scrub(timeline.lastIndex)
        mutable.update { it.copy(followLive = it.replay == null) }
    }

    fun play() {
        if (mutable.value.playing) {
            stopPlayback()
            return
        }
        mutable.update { it.copy(playing = true, followLive = false) }
        playbackJob =
            viewModelScope.launch {
                while (true) {
                    val s = mutable.value
                    if (s.timeline.size < 2) break
                    val current = s.timeline.indexOfFirst { it.id == s.currentFrame?.id }
                    scrub((current + 1) % s.timeline.size)
                    delay(1600)
                }
                mutable.update { it.copy(playing = false) }
            }
    }

    fun stopPlayback() {
        playbackJob?.cancel()
        mutable.update { it.copy(playing = false) }
    }

    fun raster(time: String, status: String) {
        mutable.update { s ->
            if (
                runCatching { Instant.parse(s.currentFrame?.validTime) == Instant.parse(time) }
                    .getOrDefault(false)
            ) {
                s.copy(rasterState = status)
            } else s
        }
    }

    fun longPress(point: List<Double>, camera: Camera, bounds: List<Double>) {
        val s = mutable.value
        if (s.draft != null) return
        val frame = s.currentFrame ?: return message("Choose an available radar scan first.")
        if (s.replay?.isMarked == true && s.frames.none { it.id == frame.id }) {
            message(
                "This is a preserved scan. Advance to an available scan to create a new annotation."
            )
            return
        }
        stopPlayback()
        val context =
            WeatherContext(
                capturedAt = Instant.now().toString(),
                camera = camera,
                bounds = bounds,
                layers = listOf(frame.layer(s.opacity)),
            )
        mutable.update { it.copy(pending = PendingMark(point, context), followLive = false) }
        authenticated { sheet("mark") }
    }

    fun startDraft(type: String) {
        val pending = mutable.value.pending ?: return
        val pin =
            AnnotationElement(
                tool = "pin",
                geometry = GeoGeometry.of("Point", listOf(pending.point)),
            )
        val draft = Draft(pending.context, listOf(pin), contentType = type)
        mutable.update {
            it.copy(
                draft = draft,
                editor = EditorState().add(pin),
                tool = Tool.ARROW,
                selected = null,
                replay = null,
                sheet = null,
                pending = null,
                followLive = false,
                viewingId = pending.context.layers.first().frameId,
                camera = pending.context.camera,
                cameraRevision = it.cameraRevision + 1,
            )
        }
        drafts.save(draft)
    }

    fun resumeDraft() {
        val s = mutable.value
        val draft = s.draft ?: return
        val layer = draft.context.layers.first()
        mutable.update {
            it.copy(
                camera = draft.context.camera,
                cameraRevision = it.cameraRevision + 1,
                site = layer.radarSite ?: it.site,
                product = layer.product,
                viewingId = layer.frameId,
                followLive = false,
                sheet = null,
            )
        }
        loadFrames()
    }

    fun discardDraft() {
        drafts.save(null)
        mutable.update {
            it.copy(draft = null, editor = EditorState(), sheet = null, pending = null)
        }
        live()
    }

    fun tool(value: Tool) {
        mutable.update { it.copy(tool = value) }
    }

    fun color(value: String) {
        mutable.update { it.copy(color = value) }
        styleSelected()
    }

    fun stroke(value: Double) {
        mutable.update { it.copy(stroke = value) }
        styleSelected()
    }

    private fun styleSelected() {
        val s = mutable.value
        if (s.draft == null || s.tool != Tool.SELECT || s.editor.selectedId == null) return
        commit(
            s.editor.elements.map {
                if (it.id == s.editor.selectedId) it.copy(color = s.color, stroke = s.stroke)
                else it
            }
        )
    }

    fun select(id: String?) {
        mutable.update { it.copy(editor = it.editor.copy(selectedId = id)) }
    }

    fun commit(elements: List<AnnotationElement>) {
        mutable.update { it.copy(editor = it.editor.commit(elements)) }
        saveEditor()
    }

    fun add(element: AnnotationElement) {
        mutable.update { it.copy(editor = it.editor.add(element)) }
        saveEditor()
    }

    fun undo() {
        mutable.update { it.copy(editor = it.editor.undo()) }
        saveEditor()
    }

    fun redo() {
        mutable.update { it.copy(editor = it.editor.redo()) }
        saveEditor()
    }

    fun deleteElement() {
        mutable.update { it.copy(editor = it.editor.deleteSelected()) }
        saveEditor()
    }

    private fun saveEditor() {
        mutable.update { it.copy(draft = it.draft?.copy(elements = it.editor.elements)) }
        drafts.save(mutable.value.draft)
    }

    fun draft(value: Draft) {
        mutable.update { it.copy(draft = value) }
        drafts.save(value)
    }

    fun textPoint(point: List<Double>) {
        mutable.update { it.copy(textPoint = point, sheet = "text") }
    }

    fun addText(label: String) {
        mutable.value.textPoint?.let { point ->
            add(
                AnnotationElement(
                    tool = "text",
                    geometry = GeoGeometry.of("Point", listOf(point)),
                    color = mutable.value.color,
                    stroke = mutable.value.stroke,
                    label = label.trim(),
                )
            )
        }
        mutable.update { it.copy(textPoint = null, sheet = null) }
    }

    fun publish() {
        authenticated {
            task {
                val s = mutable.value
                val draft = s.draft ?: return@task
                if (draft.description.isBlank())
                    return@task message("Explain what you marked before publishing.")
                mutable.update { it.copy(busy = true) }
                try {
                    val published =
                        api.publish(
                            PostCreate(
                                contentType = draft.contentType,
                                description = draft.description.trim(),
                                title = draft.title.ifBlank { null },
                                whyItMatters = draft.whyItMatters.ifBlank { null },
                                watchNext = draft.watchNext.ifBlank { null },
                                topics = draft.topics,
                                context = draft.context,
                                elements = s.editor.elements,
                                photoIds = draft.photoIds,
                            )
                        )
                    drafts.save(null)
                    mutable.update { it.copy(draft = null, editor = EditorState(), sheet = null) }
                    open(published)
                    loadPosts()
                    message("Your annotation is on the map.")
                } finally {
                    mutable.update { it.copy(busy = false) }
                }
            }
        }
    }

    fun signIn(email: String, password: String, name: String?) {
        task {
            mutable.update { it.copy(busy = true) }
            try {
                api.signIn(email, password, name)
                mutable.update { it.copy(session = api.vault.current, sheet = null) }
                afterLogin?.invoke()
                afterLogin = null
                loadPosts()
            } finally {
                mutable.update { it.copy(busy = false) }
            }
        }
    }

    fun signOut() {
        task {
            api.signOut()
            mutable.update {
                it.copy(
                    session = null,
                    sheet = null,
                    sort = "recent",
                    selected = null,
                    replay = null,
                )
            }
            loadPosts()
        }
    }

    fun like() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request("/posts/${selected.id}/like", if (selected.liked) "DELETE" else "PUT")
            refreshSelected()
        }
    }

    fun follow() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request(
                "/profiles/${selected.author.id}/follow",
                if (selected.followingAuthor) "DELETE" else "PUT",
            )
            refreshSelected()
        }
    }

    private suspend fun refreshSelected() {
        val id = mutable.value.selected?.id ?: return
        val post = api.post(id)
        mutable.update { s ->
            if (s.selected?.id != id) s
            else
                s.copy(
                    selected = post,
                    replay = s.replay?.copy(post = post),
                    posts = s.posts.map { if (it.id == id) post else it },
                )
        }
    }

    fun loadComments(more: Boolean = false) {
        val s = mutable.value
        val id = s.selected?.id ?: return
        mutable.update { it.copy(commentsLoading = true) }
        task {
            try {
                val response = api.comments(id, if (more) s.commentsCursor else null)
                mutable.update { current ->
                    if (current.selected?.id != id) current
                    else
                        current.copy(
                            comments =
                                (if (more) current.comments + response.items else response.items)
                                    .distinctBy { it.id },
                            commentsCursor = response.nextCursor,
                        )
                }
            } finally {
                mutable.update { it.copy(commentsLoading = false) }
            }
        }
    }

    fun comment(body: String, parent: String?) = authenticated {
        task {
            val id = mutable.value.selected?.id ?: return@task
            api.request(
                "/posts/$id/comments",
                "POST",
                api.body(
                    buildJsonObject {
                        put("body", body.trim())
                        if (parent != null) put("parent_id", parent)
                    }
                ),
            )
            loadComments()
            refreshSelected()
        }
    }

    fun removeComment(id: String) = authenticated {
        task {
            api.request("/comments/$id", "DELETE")
            loadComments()
            refreshSelected()
        }
    }

    fun report(type: String, id: String, reason: String) = authenticated {
        task {
            api.request(
                "/reports",
                "POST",
                api.body(
                    buildJsonObject {
                        put("target_type", type)
                        put("target_id", id)
                        put("reason", reason)
                    }
                ),
            )
            message("Report sent for review.")
        }
    }

    fun blockAuthor() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request("/profiles/${selected.author.id}/block", "PUT")
            closePost()
            loadPosts()
            message("This account is blocked.")
        }
    }

    fun deletePost() = authenticated {
        task {
            val id = mutable.value.selected?.id ?: return@task
            api.request("/posts/$id", "DELETE")
            closePost()
            loadPosts()
        }
    }

    fun upload(data: ByteArray) = authenticated {
        task {
            mutable.update { it.copy(busy = true) }
            try {
                val id = api.upload(data)
                mutable.value.draft?.let { draft(it.copy(photoIds = it.photoIds + id)) }
            } finally {
                mutable.update { it.copy(busy = false) }
            }
        }
    }

    fun notifications() = authenticated {
        task {
            val data = api.json.parseToJsonElement(api.request("/notifications"))
            mutable.update {
                it.copy(
                    notifications =
                        (data as kotlinx.serialization.json.JsonArray).map { n -> n.jsonObject },
                    sheet = "notifications",
                )
            }
        }
    }

    fun feed(scope: String = "nearby", more: Boolean = false) {
        if (scope == "following" && mutable.value.session == null) {
            authenticated { feed(scope) }
            return
        }
        val s = mutable.value
        mutable.update { it.copy(sheet = "feed", feedScope = scope, feedLoading = true) }
        val sort = if (scope == "nearby") "recent" else scope
        val query =
            "sort=$sort&limit=20" +
                (if (scope == "nearby") "&bbox=${s.bounds.joinToString(",")}" else "") +
                (if (more && s.feedCursor != null) "&cursor=${s.feedCursor}" else "")
        task {
            try {
                val result = api.posts(query)
                mutable.update { current ->
                    if (current.feedScope != scope) current
                    else
                        current.copy(
                            feedItems =
                                (if (more) current.feedItems + result.items else result.items)
                                    .distinctBy { it.id },
                            feedCursor = result.nextCursor,
                        )
                }
            } finally {
                mutable.update { it.copy(feedLoading = false) }
            }
        }
    }

    fun openNotification(value: JsonObject) {
        task {
            api.request("/notifications/${value.getValue("id").jsonPrimitive.content}/read", "PUT")
            open(value.getValue("post_id").jsonPrimitive.content)
        }
    }
}
