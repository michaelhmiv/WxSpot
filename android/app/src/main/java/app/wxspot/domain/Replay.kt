package app.wxspot.domain

/** An immutable authored context and independent viewing frame; marks never mutate on scrub. */
data class ReplaySession(
    val post: WeatherPost,
    val frames: List<RadarFrame>,
    val viewingId: String = post.context.layers.first().frameId,
) {
    val markedLayer: WeatherLayer
        get() = post.context.layers.first()

    val isMarked: Boolean
        get() = viewingId == markedLayer.frameId

    val viewingTime: String
        get() =
            if (isMarked) markedLayer.validTime else frames.first { it.id == viewingId }.validTime

    val deltaMinutes: Long
        get() =
            java.time.Duration.between(
                    java.time.Instant.parse(markedLayer.validTime),
                    java.time.Instant.parse(viewingTime),
                )
                .toMinutes()

    fun advance(frameId: String): ReplaySession {
        require(frameId == markedLayer.frameId || frames.any { it.id == frameId })
        return copy(viewingId = frameId)
    }

    fun returnToMarked(): ReplaySession = copy(viewingId = markedLayer.frameId)

    val timeline: List<RadarFrame>
        get() {
            val marked =
                RadarFrame(
                    markedLayer.frameId,
                    markedLayer.validTime,
                    markedLayer.radarSite.orEmpty(),
                    markedLayer.product,
                    "Marked frame",
                    provider = markedLayer.provider,
                    sourceType = markedLayer.sourceType,
                    elevation = markedLayer.elevation,
                    metadata = markedLayer.metadata,
                )
            return (frames + marked).distinctBy { it.id }.sortedBy { it.instant() }
        }
}
