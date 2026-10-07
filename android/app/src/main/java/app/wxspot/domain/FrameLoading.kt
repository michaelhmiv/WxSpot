package app.wxspot.domain

data class FrameRequestKey(
    val sourceId: String,
    val frameId: String,
    val selectionGeneration: Long,
    val viewportGeneration: Long,
    val mapSourceId: String,
)

data class WeatherTileKey(val x: Int, val y: Int, val z: Int, val wrap: Int, val overscaledZ: Int)

enum class WeatherTileEvent {
    REQUESTED_FROM_CACHE,
    REQUESTED_FROM_NETWORK,
    LOAD_FROM_CACHE,
    LOAD_FROM_NETWORK,
    START_PARSE,
    END_PARSE,
    ERROR,
    CANCELLED,
}

data class FrameLoadMetrics(
    val elapsedMillis: Long,
    val parsedTiles: Int,
    val pendingTiles: Int,
    val cacheLoads: Int,
    val networkLoads: Int,
    val cancelledTiles: Int,
    val failedTiles: Int,
)

object WeatherLoadingPolicy {
    const val MAX_CONCURRENT_REQUESTS = 4
    const val MAX_REQUESTS_PER_ORIGIN = 2
    const val MAX_PREFETCH_FRAMES = 4
    const val PREFETCH_AHEAD = 2
    const val PREFETCH_BEHIND = 1
    const val TILE_CACHE_BYTES = 256L * 1024 * 1024
    const val FRAME_READY_TIMEOUT_MS = 10_000L
}

/** Tracks visible-frame readiness without trusting a map-wide render callback by itself. */
class FrameReadinessTracker(private val nowMillis: () -> Long = { System.nanoTime() / 1_000_000 }) {
    private var active: FrameRequestKey? = null
    private var startedAt = 0L
    private val pending = mutableSetOf<WeatherTileKey>()
    private val parsed = mutableSetOf<WeatherTileKey>()
    private val failed = mutableSetOf<WeatherTileKey>()
    private val cacheLoads = mutableSetOf<WeatherTileKey>()
    private val networkLoads = mutableSetOf<WeatherTileKey>()
    private val cancelledTiles = mutableSetOf<WeatherTileKey>()

    fun begin(key: FrameRequestKey) {
        active = key
        startedAt = nowMillis()
        pending.clear()
        parsed.clear()
        failed.clear()
        cacheLoads.clear()
        networkLoads.clear()
        cancelledTiles.clear()
    }

    fun observe(key: FrameRequestKey, tile: WeatherTileKey, event: WeatherTileEvent): Boolean {
        if (key != active) return false
        when (event) {
            WeatherTileEvent.REQUESTED_FROM_CACHE,
            WeatherTileEvent.REQUESTED_FROM_NETWORK -> Unit
            WeatherTileEvent.LOAD_FROM_CACHE,
            WeatherTileEvent.LOAD_FROM_NETWORK,
            WeatherTileEvent.START_PARSE -> pending.add(tile)
            WeatherTileEvent.END_PARSE -> {
                pending.remove(tile)
                parsed.add(tile)
            }
            WeatherTileEvent.ERROR -> {
                pending.remove(tile)
                failed.add(tile)
            }
            WeatherTileEvent.CANCELLED -> {
                pending.remove(tile)
                cancelledTiles.add(tile)
            }
        }
        when (event) {
            WeatherTileEvent.REQUESTED_FROM_CACHE,
            WeatherTileEvent.LOAD_FROM_CACHE -> cacheLoads.add(tile)
            WeatherTileEvent.REQUESTED_FROM_NETWORK,
            WeatherTileEvent.LOAD_FROM_NETWORK -> networkLoads.add(tile)
            else -> Unit
        }
        return true
    }

    fun finishRendering(
        key: FrameRequestKey,
        renderedAfterCandidateTiles: Boolean,
    ): FrameReadiness? {
        if (key != active || !renderedAfterCandidateTiles || pending.isNotEmpty()) return null
        if (failed.isNotEmpty()) return readiness(key, "error", "One or more radar tiles failed")
        if (parsed.isEmpty()) return null
        return readiness(key, "ready")
    }

    fun imageSourceChanged(key: FrameRequestKey): Boolean {
        if (key != active) return false
        parsed.add(WeatherTileKey(x = -1, y = -1, z = -1, wrap = 0, overscaledZ = -1))
        return true
    }

    fun fail(key: FrameRequestKey, message: String): FrameReadiness? =
        if (key == active) readiness(key, "error", message) else null

    fun metrics(): FrameLoadMetrics =
        FrameLoadMetrics(
            elapsedMillis = (nowMillis() - startedAt).coerceAtLeast(0),
            parsedTiles = parsed.size,
            pendingTiles = pending.size,
            cacheLoads = cacheLoads.size,
            networkLoads = networkLoads.size,
            cancelledTiles = cancelledTiles.size,
            failedTiles = failed.size,
        )

    private fun readiness(key: FrameRequestKey, state: String, error: String? = null) =
        FrameReadiness(
            sourceId = key.sourceId,
            frameId = key.frameId,
            selectionGeneration = key.selectionGeneration,
            viewportGeneration = key.viewportGeneration,
            state = state,
            error = error,
        )

    companion object {
        fun <T> prefetchWindow(frames: List<T>, index: Int, identity: (T) -> String): List<T> {
            if (frames.isEmpty() || index !in frames.indices) return emptyList()
            val offsets =
                listOf(0) +
                    (1..WeatherLoadingPolicy.PREFETCH_AHEAD).toList() +
                    (-WeatherLoadingPolicy.PREFETCH_BEHIND..-1).toList()
            return offsets
                .map { offset -> frames[(index + offset + frames.size) % frames.size] }
                .distinctBy(identity)
                .take(WeatherLoadingPolicy.MAX_PREFETCH_FRAMES)
        }
    }
}
