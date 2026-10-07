package app.wxspot.data

import java.io.IOException
import okio.BufferedSource

/** Reads a response body without buffering more than one byte beyond the allowed size. */
internal fun readBoundedImageBytes(source: BufferedSource, maxBytes: Long): ByteArray {
    require(maxBytes >= 0) { "Maximum response size cannot be negative" }
    source.request(maxBytes + 1)
    if (source.buffer.size > maxBytes) {
        throw IOException("Archive image exceeded the size limit")
    }
    return source.readByteArray()
}
