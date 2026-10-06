package app.wxspot.data

import android.content.Context
import app.wxspot.domain.Draft
import java.io.File
import kotlinx.serialization.json.Json

class DraftStore(context: Context, private val json: Json) {
    private val file = File(context.filesDir, "annotation-draft.json")

    fun read(): Draft? = runCatching { json.decodeFromString<Draft>(file.readText()) }.getOrNull()

    fun save(draft: Draft?) {
        if (draft == null) {
            file.delete()
        } else {
            val next = File(file.parentFile, file.name + ".tmp")
            next.writeText(json.encodeToString(draft))
            check(next.renameTo(file)) { "Unable to save draft" }
        }
    }
}
