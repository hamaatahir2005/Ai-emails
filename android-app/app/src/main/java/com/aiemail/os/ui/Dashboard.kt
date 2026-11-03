package com.aiemail.os.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aiemail.os.R
import java.time.LocalDate
import java.time.YearMonth
import java.text.DateFormat
import java.util.Date

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DashboardScreen(vm: OsViewModel) {
    val metrics by vm.analytics.collectAsStateWithLifecycle()
    val at by vm.cachedAt.collectAsStateWithLifecycle()
    val campaigns by vm.campaigns.collectAsStateWithLifecycle()
    val cards = listOf(
        "total_customers" to R.string.total_customers, "emails_sent_today" to R.string.emails_sent_today,
        "remaining_daily_capacity" to R.string.remaining_daily_capacity, "delivered" to R.string.delivered,
        "failed" to R.string.failed, "unsubscribed" to R.string.unsubscribed,
        "replies" to R.string.replies, "ai_generated" to R.string.ai_generated)
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Button(onClick = { vm.refresh() }) { Text(stringResource(R.string.refresh)) }
        if (at > 0) Text(stringResource(R.string.cached) + ": " + DateFormat.getDateTimeInstance().format(Date(at)), style = MaterialTheme.typography.labelSmall)
        BoxWithConstraints {
            val columns = if (maxWidth > 700.dp) 4 else 2
            val width = (maxWidth - 12.dp * (columns - 1)) / columns
            FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                cards.forEachIndexed { index, pair ->
                    ElevatedCard(Modifier.width(width)) {
                        Column(Modifier.padding(16.dp)) {
                            Text(stringResource(pair.second), style = MaterialTheme.typography.labelMedium)
                            Text(metrics.text(pair.first).ifBlank { "—" }, style = MaterialTheme.typography.headlineLarge,
                                color = if (index % 2 == 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.secondary)
                        }
                    }
                }
            }
        }
        Text(stringResource(R.string.campaigns), style = MaterialTheme.typography.titleLarge)
        if (campaigns.isEmpty()) Text(stringResource(R.string.empty))
        campaigns.take(5).forEach { campaign ->
            OutlinedCard(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(campaign.text("name"), modifier = Modifier.weight(1f))
                    Text(campaign.text("status"), color = MaterialTheme.colorScheme.secondary)
                }
            }
        }
        Text(stringResource(R.string.events_note), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun AnalyticsScreen(vm: OsViewModel) {
    val data by vm.analytics.collectAsStateWithLifecycle()
    var monthly by remember { mutableStateOf(false) }
    var event by remember { mutableStateOf("delivered") }
    var selected by remember { mutableIntStateOf(-1) }
    val series = data.getAsJsonArray("series")?.map { it.asJsonObject } ?: emptyList()
    val end = runCatching { LocalDate.parse(data.text("today")) }.getOrElse { LocalDate.now() }
    val dates = if (monthly) (0..11).map { YearMonth.from(end).minusMonths((11 - it).toLong()).toString() }
                else (0..29).map { end.minusDays((29 - it).toLong()).toString() }
    val counts = dates.map { date ->
        series.filter { it.text("kind") == event && (if (monthly) it.text("date").take(7) else it.text("date")) == date }
            .sumOf { it.text("count").toIntOrNull() ?: 0 }
    }
    val color = MaterialTheme.colorScheme.secondary
    val export = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        uri?.let { vm.export(it, true) }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(!monthly, { monthly = false; selected = -1; vm.refresh(30) }, label = { Text(stringResource(R.string.days)) })
            FilterChip(monthly, { monthly = true; selected = -1; vm.refresh(366) }, label = { Text(stringResource(R.string.months)) })
        }
        var menu by remember { mutableStateOf(false) }
        Box {
            OutlinedButton(onClick = { menu = true }) { Text(event) }
            DropdownMenu(menu, { menu = false }) {
                listOf("accepted", "sent", "delivered", "hard_bounced", "complained", "unsubscribed", "replied").forEach { kind ->
                    DropdownMenuItem(text = { Text(kind) }, onClick = { event = kind; menu = false; selected = -1 })
                }
            }
        }
        ElevatedCard {
            Column(Modifier.padding(20.dp)) {
                Text(counts.sum().toString(), style = MaterialTheme.typography.displayMedium, color = MaterialTheme.colorScheme.primary)
                Canvas(Modifier.fillMaxWidth().height(220.dp).pointerInput(dates, counts) {
                    detectTapGestures { point -> selected = ((point.x / size.width) * counts.size).toInt().coerceIn(counts.indices) }
                }) {
                    val barWidth = size.width / counts.size
                    val max = (counts.maxOrNull() ?: 0).coerceAtLeast(1)
                    counts.forEachIndexed { index, count ->
                        val height = (count.toFloat() / max) * size.height
                        drawRoundRect(color = if (index == selected) Color(0xFFB6AAFF) else color,
                            topLeft = androidx.compose.ui.geometry.Offset(index * barWidth + 2, size.height - height),
                            size = androidx.compose.ui.geometry.Size((barWidth - 4).coerceAtLeast(1f), height),
                            cornerRadius = androidx.compose.ui.geometry.CornerRadius(4f))
                    }
                }
                if (selected in counts.indices) Text(dates[selected] + ": " + counts[selected])
            }
        }
        Text(stringResource(R.string.events_note))
        Button(onClick = { export.launch("campaign-events.csv") }) { Text(stringResource(R.string.export_file)) }
    }
}
