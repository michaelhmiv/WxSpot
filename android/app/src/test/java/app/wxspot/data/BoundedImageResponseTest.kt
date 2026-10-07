package app.wxspot.data

import java.io.IOException
import okio.Buffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class BoundedImageResponseTest {
    @Test
    fun acceptsACompleteBodyShorterThanTheLimit() {
        val body = "small-image".encodeToByteArray()

        assertArrayEquals(body, readBoundedImageBytes(Buffer().write(body), 128))
    }

    @Test
    fun acceptsACompleteBodyExactlyAtTheLimit() {
        val body = byteArrayOf(1, 2, 3, 4)

        assertArrayEquals(body, readBoundedImageBytes(Buffer().write(body), body.size.toLong()))
    }

    @Test
    fun rejectsTheFirstByteBeyondTheLimit() {
        val source = Buffer().write(byteArrayOf(1, 2, 3, 4, 5))

        assertThrows(IOException::class.java) { readBoundedImageBytes(source, 4) }
        assertEquals(5L, source.size)
    }
}
