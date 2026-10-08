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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

@Composable
fun ModelLayerPanel(state: UiState, vm: MapViewModel) {
    var model by remember { mutableStateOf(state.modelName) }
    var product by remember { mutableStateOf(state.product) }
    var run by remember { mutableStateOf(state.modelRunTime) }
    Column(
        Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Model forecasts", style = MaterialTheme.typography.headlineSmall)
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("hrrr" to "HRRR · 3 km", "gfs" to "GFS · 0.25°").forEach { (id, title) ->
                FilterChip(
                    model == id,
                    {
                        if (model != id) run = null
                        model = id
                    },
                    label = { Text(title) },
                    modifier = Modifier.heightIn(min = 48.dp),
                )
            }
        }
        Text("CONUS · model forecast, with native scientific resolution.")
        listOf(
                "reflectivity" to "Simulated reflectivity",
                "temperature" to "2 m temperature",
                "dew_point" to "2 m dew point",
                "wind" to "10 m wind speed / barbs",
                "gust" to "Surface wind gust",
                "precip_interval" to "Precipitation · actual interval",
                "precip_total" to "Precipitation · run total",
                "cape" to "Surface-based CAPE",
                "cin" to "Surface-based CIN",
                "pwat" to "Precipitable water",
            )
            .forEach { (id, title) ->
                FilterChip(
                    product == id,
                    { product = id },
                    label = { Text(title) },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                )
            }
        if (model == state.modelName) {
            Text("Published run (UTC)")
            state.weatherOptions["runs"]?.jsonArray?.forEach { value ->
                val id = value.jsonPrimitive.content
                FilterChip(
                    run == id,
                    { run = id },
                    label = { Text(id.replace("T", " ").take(16) + " UTC") },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                )
            }
        }
        Text(
            "The timeline uses only published hours from one run. HRRR: F18 or F48 extended cycles. GFS: hourly through F120, then every 3 hours through F168. Missing intervals keep precipitation totals unavailable.",
            style = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = { vm.modelLayer(model, product, run) },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
        ) {
            Text("Show forecast")
        }
        TextButton(
            onClick = { vm.modelLayer(model, product, null) },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
        ) {
            Text("Latest published run")
        }
        Text("Layer opacity")
        Slider(state.opacity.toFloat(), { vm.opacity(it.toDouble()) }, valueRange = 0.2f..1f)
    }
}
