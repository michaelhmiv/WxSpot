package app.wxspot.domain

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SoundingHuntContractTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun publicDailyContractCarriesUtcTimeAndAboveGroundChartHeightsOnly() {
        val response =
            json.decodeFromString<HuntChallenge>(
                """
                {
                  "challenge_day":"2026-10-08",
                  "challenge_number":42,
                  "starts_at":"2026-10-08T12:00:00Z",
                  "ends_at":"2026-10-09T12:00:00Z",
                  "observation_time":"2026-10-07T23:10:00Z",
                  "surface_pressure_hpa":1006.2,
                  "levels":[{
                    "pressure_hpa":1000,
                    "temperature_c":25.3,
                    "dewpoint_c":20.3,
                    "height_m_agl":6.7,
                    "u_ms":10.0,
                    "v_ms":0.0
                  }],
                  "completed":false,
                  "current_streak":3
                }
                """
                    .trimIndent()
            )

        assertEquals("2026-10-07T23:10:00Z", response.observationTime)
        assertEquals(6.7, response.levels.single().heightMAGL!!, 0.01)
        assertFalse(response.completed)
        assertEquals(3, response.currentStreak)
    }

    @Test
    fun revealContractIncludesAnswerOnlyAfterSubmission() {
        val result =
            json.decodeFromString<HuntResult>(
                """
                {
                  "challenge_day":"2026-10-08",
                  "challenge_number":42,
                  "observation_time":"2026-10-07T23:10:00Z",
                  "selected_latitude":33.0,
                  "selected_longitude":-80.0,
                  "answer":{
                    "station_id":"USM00072208",
                    "station_name":"Charleston International Airport",
                    "state":"SC",
                    "latitude":32.895,
                    "longitude":-80.0275,
                    "elevation_m":13.3,
                    "source":"NOAA / NCEI Integrated Global Radiosonde Archive",
                    "source_version":"IGRA 2.2"
                  },
                  "distance_miles":7.3,
                  "score":4952,
                  "scoring_version":"exp-distance-v1",
                  "insights":["The launch was close to your pin."],
                  "historical":false
                }
                """
                    .trimIndent()
            )

        assertEquals(42, result.challengeNumber)
        assertEquals("USM00072208", result.answer.stationId)
        assertEquals(4952, result.score)
        assertEquals("exp-distance-v1", result.scoringVersion)
    }
}
