package app.wxspot.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun SatelliteLayerPanel(state: UiState, vm: MapViewModel) {
    var sector by remember { mutableStateOf(state.satelliteSector) }
    var product by remember { mutableStateOf(state.product) }
    Column(
        Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Satellite layers", style = MaterialTheme.typography.headlineSmall)
        Text("CONUS sector · operational spacecraft identity comes from NOAA.")
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("east" to "GOES East", "west" to "GOES West").forEach { (id, title) ->
                FilterChip(
                    sector == id,
                    { sector = id },
                    label = { Text(title) },
                    modifier = Modifier.heightIn(min = 48.dp),
                )
            }
        }
        listOf(
                "geocolor" to "GeoColor",
                "visible" to "Visible · C02",
                "infrared" to "Clean longwave infrared · C13",
                "water_vapor_upper" to "Upper water vapor · C08",
                "water_vapor_mid" to "Middle water vapor · C09",
                "water_vapor_lower" to "Lower water vapor · C10",
            )
            .forEach { (id, title) ->
                FilterChip(
                    product == id,
                    { product = id },
                    label = { Text(title) },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                )
            }
        Text(
            "Visible C02 is dark at night. GeoColor changes from true color to an infrared composite and includes static city lights. Infrared and water vapor show brightness temperature, not surface temperature.",
            style = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = { vm.satelliteLayer(sector, product) },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
        ) {
            Text("Show satellite imagery")
        }
        Text("Layer opacity")
        Slider(state.opacity.toFloat(), { vm.opacity(it.toDouble()) }, valueRange = 0.2f..1f)
    }
}
