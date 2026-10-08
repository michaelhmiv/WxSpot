package app.wxspot

import app.wxspot.domain.SkewTransform
import kotlin.math.sqrt
import org.junit.Assert.assertEquals
import org.junit.Test

class SoundingTransformTest {
    @Test
    fun logPressureHasGeometricMidpointAndReversibleTemperatureSkew() {
        val transform = SkewTransform(400.0, 600.0)
        assertEquals(0.0, transform.y(100.0), 1e-9)
        assertEquals(600.0, transform.y(1050.0), 1e-9)
        assertEquals(300.0, transform.y(sqrt(100.0 * 1050.0)), 1e-9)
        for (pressure in listOf(100.0, 500.0, 850.0, 1050.0)) {
            for (temperature in listOf(-65.0, -10.0, 30.0)) {
                val x = transform.x(temperature, pressure)
                val y = transform.y(pressure)
                assertEquals(pressure, transform.pressure(y), 1e-9)
                assertEquals(temperature, transform.temperature(x, y), 1e-9)
            }
        }
        // A 30-degree affine skew moves an isotherm 600*tan(30) pixels right aloft.
        assertEquals(346.4101615, transform.x(0.0, 100.0) - transform.x(0.0, 1050.0), 1e-6)
    }
}
