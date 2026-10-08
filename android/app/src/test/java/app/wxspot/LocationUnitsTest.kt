package app.wxspot

import app.wxspot.domain.LocationUnits
import org.junit.Assert.assertEquals
import org.junit.Test

class LocationUnitsTest {
    @Test
    fun exactUnitsConvertConsistently() {
        assertEquals(32.0, LocationUnits.temperature(0.0, false), 1e-9)
        assertEquals(-40.0, LocationUnits.temperature(-40.0, false), 1e-9)
        assertEquals(36.0, LocationUnits.speed(10.0, true), 1e-9)
        assertEquals(22.369362921, LocationUnits.speed(10.0, false), 1e-8)
        assertEquals(1.0, LocationUnits.rain(25.4, false), 1e-9)
    }
}
