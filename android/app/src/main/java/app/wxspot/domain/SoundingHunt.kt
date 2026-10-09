package app.wxspot.domain

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HuntLevel(
    @SerialName("pressure_hpa") val pressureHpa: Double,
    @SerialName("temperature_c") val temperatureC: Double? = null,
    @SerialName("dewpoint_c") val dewpointC: Double? = null,
    @SerialName("height_m_agl") val heightMAGL: Double? = null,
    @SerialName("u_ms") val uMs: Double? = null,
    @SerialName("v_ms") val vMs: Double? = null,
)

@Serializable
data class HuntChallenge(
    @SerialName("challenge_day") val challengeDay: String,
    @SerialName("challenge_number") val challengeNumber: Int,
    @SerialName("starts_at") val startsAt: String,
    @SerialName("ends_at") val endsAt: String,
    @SerialName("observation_time") val observationTime: String,
    @SerialName("observation_time_basis") val observationTimeBasis: String = "launch",
    @SerialName("surface_pressure_hpa") val surfacePressureHpa: Double? = null,
    val levels: List<HuntLevel>,
    val completed: Boolean,
    @SerialName("current_streak") val currentStreak: Int,
)

@Serializable
data class HuntPractice(
    @SerialName("practice_id") val practiceId: String,
    @SerialName("observation_time") val observationTime: String,
    @SerialName("observation_time_basis") val observationTimeBasis: String = "launch",
    @SerialName("surface_pressure_hpa") val surfacePressureHpa: Double? = null,
    val levels: List<HuntLevel>,
)

@Serializable
data class HuntAnswer(
    @SerialName("station_id") val stationId: String,
    @SerialName("station_name") val stationName: String,
    val state: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("elevation_m") val elevationM: Double,
    val source: String,
    @SerialName("source_version") val sourceVersion: String,
    @SerialName("source_revision") val sourceRevision: String? = null,
    @SerialName("nominal_time") val nominalTime: String? = null,
)

@Serializable
data class HuntResult(
    @SerialName("challenge_day") val challengeDay: String? = null,
    @SerialName("challenge_number") val challengeNumber: Int? = null,
    @SerialName("observation_time") val observationTime: String,
    @SerialName("selected_latitude") val selectedLatitude: Double? = null,
    @SerialName("selected_longitude") val selectedLongitude: Double? = null,
    val answer: HuntAnswer,
    @SerialName("distance_miles") val distanceMiles: Double? = null,
    val score: Int? = null,
    @SerialName("scoring_version") val scoringVersion: String? = null,
    val insights: List<String>,
    val historical: Boolean = false,
)

@Serializable
data class HuntLeaderboardRow(
    val rank: Int,
    @SerialName("display_name") val displayName: String,
    val score: Int,
    @SerialName("distance_miles") val distanceMiles: Double,
    @SerialName("submitted_at") val submittedAt: String,
    @SerialName("is_you") val isYou: Boolean,
)

@Serializable
data class HuntLeaderboard(
    @SerialName("challenge_day") val challengeDay: String,
    @SerialName("challenge_number") val challengeNumber: Int,
    val rows: List<HuntLeaderboardRow>,
    @SerialName("player_rank") val playerRank: Int? = null,
    @SerialName("total_players") val totalPlayers: Int,
    val page: Int,
)

@Serializable
data class HuntHistoryItem(
    @SerialName("challenge_day") val challengeDay: String,
    @SerialName("challenge_number") val challengeNumber: Int,
    val score: Int,
    @SerialName("distance_miles") val distanceMiles: Double,
    @SerialName("submitted_at") val submittedAt: String,
)

@Serializable
data class HuntProfile(
    @SerialName("display_name") val displayName: String,
    @SerialName("daily_challenges_played") val dailyChallengesPlayed: Int,
    @SerialName("average_score") val averageScore: Double? = null,
    @SerialName("best_score") val bestScore: Int? = null,
    @SerialName("average_error_miles") val averageErrorMiles: Double? = null,
    @SerialName("current_streak") val currentStreak: Int,
    @SerialName("longest_streak") val longestStreak: Int,
    val history: List<HuntHistoryItem> = emptyList(),
)

data class HuntSounding(
    val observationTime: String,
    val observationTimeBasis: String,
    val surfacePressureHpa: Double?,
    val levels: List<HuntLevel>,
)

fun HuntChallenge.asSounding() =
    HuntSounding(observationTime, observationTimeBasis, surfacePressureHpa, levels)

fun HuntPractice.asSounding() =
    HuntSounding(observationTime, observationTimeBasis, surfacePressureHpa, levels)
