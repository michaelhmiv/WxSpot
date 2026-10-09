package app.wxspot.ui

import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.wxspot.data.ApiException
import app.wxspot.data.ApiRepository
import app.wxspot.domain.HuntChallenge
import app.wxspot.domain.HuntLeaderboard
import app.wxspot.domain.HuntPractice
import app.wxspot.domain.HuntProfile
import app.wxspot.domain.HuntResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SoundingHuntUiState(
    val tab: String = "Home",
    val page: String = "home",
    val challenge: HuntChallenge? = null,
    val reviewChallenge: HuntChallenge? = null,
    val practice: HuntPractice? = null,
    val result: HuntResult? = null,
    val leaderboard: HuntLeaderboard? = null,
    val profile: HuntProfile? = null,
    val isPractice: Boolean = false,
    val guessLatitude: Double? = null,
    val guessLongitude: Double? = null,
    val loading: Boolean = true,
    val busy: Boolean = false,
    val error: String? = null,
)

class SoundingHuntViewModel(private val api: ApiRepository) : ViewModel() {
    private val mutable = MutableStateFlow(SoundingHuntUiState())
    val state = mutable.asStateFlow()
    private var refreshActive = false
    private var lastRefreshAt = 0L

    init {
        refresh()
    }

    fun refresh(force: Boolean = false) {
        val elapsed = SystemClock.elapsedRealtime() - lastRefreshAt
        val shouldThrottle = !force && lastRefreshAt > 0 && elapsed < 60_000
        if (refreshActive || shouldThrottle) return
        refreshActive = true
        viewModelScope.launch {
            mutable.update { it.copy(loading = true, error = null) }
            runCatching {
                api.ensureDeviceProfile()
                api.huntToday()
            }
                .onSuccess { challenge ->
                    lastRefreshAt = SystemClock.elapsedRealtime()
                    mutable.update { it.copy(challenge = challenge, loading = false) }
                    if (mutable.value.tab == "Rankings") loadLeaderboard(challenge.challengeDay)
                }
                .onFailure { error ->
                    mutable.update {
                        it.copy(
                            loading = false,
                            error = error.message ?: "Today's challenge could not be loaded.",
                        )
                    }
                }
            runCatching { api.huntProfile() }
                .onSuccess { profile -> mutable.update { it.copy(profile = profile) } }
            refreshActive = false
        }
    }

    fun navigate(tab: String) {
        mutable.update { it.copy(tab = tab, page = tab.lowercase(), error = null) }
        when (tab) {
            "Rankings" -> loadLeaderboard()
            "Profile" -> loadProfile()
        }
    }

    fun startDaily() {
        val challenge = mutable.value.challenge ?: return refresh()
        if (challenge.completed) {
            viewModelScope.launch {
                mutable.update { it.copy(busy = true, error = null) }
                runCatching { api.huntDailyResult(challenge.challengeDay) }
                    .onSuccess { result ->
                        mutable.update {
                            it.copy(
                                page = "result",
                                result = result,
                                isPractice = false,
                                busy = false,
                            )
                        }
                    }
                    .onFailure { error -> fail(error) }
            }
        } else {
            mutable.update {
                it.copy(
                    tab = "Play",
                    page = "sounding",
                    isPractice = false,
                    reviewChallenge = null,
                    result = null,
                    practice = null,
                    guessLatitude = null,
                    guessLongitude = null,
                    error = null,
                )
            }
        }
    }

    fun startPractice() {
        viewModelScope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            runCatching { api.huntPractice() }
                .onSuccess { practice ->
                    mutable.update {
                        it.copy(
                            tab = "Play",
                            page = "sounding",
                            practice = practice,
                            reviewChallenge = null,
                            result = null,
                            isPractice = true,
                            guessLatitude = null,
                            guessLongitude = null,
                            busy = false,
                        )
                    }
                }
                .onFailure { error -> fail(error) }
        }
    }

    fun chooseLocation() {
        mutable.update { it.copy(page = "guess", error = null) }
    }

    fun setGuess(latitude: Double, longitude: Double) {
        if (!latitude.isFinite() || !longitude.isFinite() ||
            latitude !in 24.0..50.0 || longitude !in -125.0..-66.0
        ) {
            mutable.update {
                it.copy(
                    guessLatitude = null,
                    guessLongitude = null,
                    error = "Choose a coordinate within the contiguous U.S.",
                )
            }
            return
        }
        mutable.update {
            it.copy(guessLatitude = latitude, guessLongitude = longitude, error = null)
        }
    }

    fun submitGuess() {
        val current = mutable.value
        val latitude = current.guessLatitude ?: return setError("Place a pin before submitting.")
        val longitude = current.guessLongitude ?: return setError("Place a pin before submitting.")
        viewModelScope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            runCatching {
                if (current.isPractice) {
                    val practice =
                        current.practice ?: return@launch setError("Practice sounding expired.")
                    api.huntPracticeGuess(practice.practiceId, latitude, longitude)
                } else {
                    val challenge =
                        current.challenge ?: return@launch setError("Daily challenge expired.")
                    api.huntDailyGuess(challenge.challengeDay, latitude, longitude)
                }
            }
                .onSuccess { result ->
                    mutable.update {
                        it.copy(
                            page = "result",
                            result = result,
                            busy = false,
                            challenge =
                                if (it.isPractice) it.challenge
                                else it.challenge?.copy(completed = true),
                        )
                    }
                    if (!current.isPractice) {
                        loadProfile()
                        loadLeaderboard(result.challengeDay ?: current.challenge?.challengeDay)
                    }
                }
                .onFailure { error ->
                    val challenge = current.challenge
                    if (
                        !current.isPractice &&
                            error is ApiException &&
                            error.status == 409 &&
                            error.message.orEmpty()
                                .contains("already submitted", ignoreCase = true) &&
                            challenge != null
                    ) {
                        runCatching { api.huntDailyResult(challenge.challengeDay) }
                            .onSuccess { result ->
                                mutable.update {
                                    it.copy(
                                        page = "result",
                                        result = result,
                                        busy = false,
                                        challenge = challenge.copy(completed = true),
                                    )
                                }
                            }
                            .onFailure { failure -> fail(failure) }
                    } else {
                        fail(error)
                    }
                }
        }
    }

    fun openLeaderboard(day: String? = null) {
        mutable.update { it.copy(tab = "Rankings", page = "rankings", error = null) }
        loadLeaderboard(day)
    }

    fun openHistoricalResult(challengeDay: String) {
        viewModelScope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            runCatching { api.huntDailyResult(challengeDay) }
                .onSuccess { result ->
                    mutable.update {
                        it.copy(
                            page = "result",
                            result = result,
                            isPractice = false,
                            reviewChallenge = null,
                            busy = false,
                        )
                    }
                }
                .onFailure { error -> fail(error) }
        }
    }

    fun reviewSounding() {
        val current = mutable.value
        if (current.isPractice) {
            mutable.update { it.copy(page = "sounding", error = null) }
            return
        }
        val day = current.result?.challengeDay ?: current.challenge?.challengeDay ?: return
        viewModelScope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            runCatching { api.huntDailyChallenge(day) }
                .onSuccess { challenge ->
                    mutable.update {
                        it.copy(page = "sounding", reviewChallenge = challenge, busy = false)
                    }
                }
                .onFailure { error -> fail(error) }
        }
    }

    fun home() {
        mutable.update { it.copy(tab = "Home", page = "home", error = null) }
    }

    fun clearGuess() {
        mutable.update { it.copy(guessLatitude = null, guessLongitude = null, error = null) }
    }

    private fun loadLeaderboard(day: String? = null) {
        val challengeDay = day ?: mutable.value.challenge?.challengeDay ?: return
        viewModelScope.launch {
            runCatching { api.huntLeaderboard(challengeDay) }
                .onSuccess { board -> mutable.update { it.copy(leaderboard = board) } }
                .onFailure { error -> mutable.update { it.copy(error = error.message) } }
        }
    }

    private fun loadProfile() {
        viewModelScope.launch {
            runCatching { api.huntProfile() }
                .onSuccess { profile -> mutable.update { it.copy(profile = profile) } }
                .onFailure { error -> mutable.update { it.copy(error = error.message) } }
        }
    }

    private fun fail(error: Throwable) {
        mutable.update {
            it.copy(
                busy = false,
                error = error.message ?: "Something went wrong. Check your connection.",
            )
        }
    }

    private fun setError(message: String) {
        mutable.update { it.copy(error = message) }
    }
}
