package app.wxspot

import android.app.Application
import app.wxspot.data.ApiRepository
import app.wxspot.data.DraftStore
import app.wxspot.data.SessionVault
import kotlinx.serialization.json.Json

class WxSpotApplication : Application() {
    lateinit var api: ApiRepository
    lateinit var drafts: DraftStore

    override fun onCreate() {
        super.onCreate()
        val json = Json {
            ignoreUnknownKeys = true
            encodeDefaults = true
        }
        api = ApiRepository(BuildConfig.API_BASE_URL, SessionVault(this, json), json)
        drafts = DraftStore(this, json)
    }
}
