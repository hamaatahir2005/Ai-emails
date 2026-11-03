package com.aiemail.os.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aiemail.os.R
import com.google.gson.*
import java.time.Instant

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CampaignsScreen(vm: OsViewModel) {
    val campaigns by vm.campaigns.collectAsStateWithLifecycle()
    val selected by vm.selectedCampaign.collectAsStateWithLifecycle()
    val preview by vm.preview.collectAsStateWithLifecycle()
    val history by vm.history.collectAsStateWithLifecycle()
    var editor by remember { mutableStateOf(false) }
    var editValue by remember { mutableStateOf<JsonObject?>(null) }
    var customerId by remember { mutableStateOf("") }
    var schedule by remember { mutableStateOf(Instant.now().plusSeconds(3600).toString()) }
    var instruction by remember { mutableStateOf("") }
    var language by remember { mutableStateOf("en") }
    var confirmAction by remember { mutableStateOf<String?>(null) }
    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Button(onClick = { editValue = null; editor = true }) { Text(stringResource(R.string.new_campaign)) } }
        if (campaigns.isEmpty()) item { Text(stringResource(R.string.empty)) }
        items(campaigns, key = { it.text("id") }) { campaign ->
            ElevatedCard(onClick = { vm.selectedCampaign.value = campaign }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text(campaign.text("name"), style = MaterialTheme.typography.titleMedium)
                    Text(campaign.text("subject"))
                    Text(campaign.text("status"), color = MaterialTheme.colorScheme.secondary)
                }
            }
        }
    }
    selected?.let { campaign ->
        val id = campaign.text("id").toInt()
        val status = campaign.text("status")
        AlertDialog(onDismissRequest = { vm.selectedCampaign.value = null },
            title = { Text(campaign.text("name")) },
            text = {
                Column(Modifier.heightIn(max = 500.dp).verticalScrollCompat(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(status, color = MaterialTheme.colorScheme.primary)
                    Text(campaign.text("pause_reason"))
                    Text(campaign.text("subject"), style = MaterialTheme.typography.titleMedium)
                    Text(campaign.text("body"))
                    Text(stringResource(R.string.total_customers) + ": " + campaign.text("total_recipients"))
                    Text(stringResource(R.string.delivered) + ": " + campaign.text("delivered_count"))
                    Text(stringResource(R.string.failed) + ": " + campaign.text("failed_count"))
                    TextButton(onClick = { vm.messageStatus(id) }) { Text(stringResource(R.string.history)) }
                    Field(R.string.customer_id, customerId) { customerId = it }
                    OutlinedButton(onClick = { customerId.toIntOrNull()?.let { vm.preview(id, it) } }, enabled = customerId.toIntOrNull() != null) { Text(stringResource(R.string.preview)) }
                    if (status == "draft") {
                        Field(R.string.instruction, instruction) { instruction = it }
                        Field(R.string.language, language) { language = it }
                        OutlinedButton(onClick = { vm.generate(id, language, instruction.ifBlank { "Create a professional introduction" }, customerId.toIntOrNull()) }) { Text(stringResource(R.string.generate)) }
                        OutlinedButton(onClick = { editValue = campaign; editor = true }) { Text(stringResource(R.string.edit)) }
                        Button(onClick = { confirmAction = "submit" }) { Text(stringResource(R.string.submit)) }
                    }
                    if (status == "awaiting_approval") {
                        if (campaign.text("approved_by").isBlank()) Button(onClick = { confirmAction = "approve" }) { Text(stringResource(R.string.approve)) }
                        else {
                            Field(R.string.schedule_at, schedule) { schedule = it }
                            Button(onClick = { confirmAction = "schedule" }) { Text(stringResource(R.string.schedule)) }
                        }
                    }
                    if (status in listOf("running", "scheduled")) Button(onClick = { confirmAction = "pause" }) { Text(stringResource(R.string.pause)) }
                    if (status == "paused") Button(onClick = { confirmAction = "resume" }) { Text(stringResource(R.string.resume)) }
                    if (status !in listOf("completed", "cancelled")) OutlinedButton(onClick = { confirmAction = "cancel" }) { Text(stringResource(R.string.cancel)) }
                    OutlinedButton(onClick = { confirmAction = "test" }) { Text(stringResource(R.string.test_email)) }
                }
            }, confirmButton = { TextButton(onClick = { vm.selectedCampaign.value = null }) { Text(stringResource(R.string.close)) } })
        confirmAction?.let { action ->
            AlertDialog(onDismissRequest = { confirmAction = null }, text = { Text(stringResource(R.string.confirm_action) + "\n" + action) },
                confirmButton = { TextButton(onClick = { vm.action(id, action, schedule); confirmAction = null }) { Text(stringResource(R.string.confirm)) } },
                dismissButton = { TextButton(onClick = { confirmAction = null }) { Text(stringResource(R.string.cancel)) } })
        }
    }
    if (history.isNotEmpty()) AlertDialog(onDismissRequest = { vm.history.value = "" },
        text = { androidx.compose.foundation.text.selection.SelectionContainer { Text(history, modifier = Modifier.heightIn(max = 400.dp).verticalScrollCompat()) } },
        confirmButton = { TextButton(onClick = { vm.history.value = "" }) { Text(stringResource(R.string.close)) } })
    if (editor) CampaignForm(editValue, onDismiss = { editor = false }, onSave = { data ->
        vm.saveCampaign(data, editValue?.text("id")?.toIntOrNull()); editor = false
    })
    preview?.let { draft ->
        AlertDialog(onDismissRequest = { vm.preview.value = null },
            title = { Text(stringResource(R.string.preview)) },
            text = { Column(Modifier.heightIn(max = 500.dp).verticalScrollCompat()) {
                Text(stringResource(R.string.review_warning), color = MaterialTheme.colorScheme.error)
                Text(draft.text("subject"), style = MaterialTheme.typography.titleMedium)
                Text(draft.text("body"))
                if (draft.has("followups")) Text(draft.get("followups").toString())
                Text(draft.text("footer"))
            } },
            confirmButton = {
                if (selected?.text("status") == "draft" && draft.has("requires_human_review")) TextButton(onClick = {
                    editValue = selected?.deepCopy()?.apply {
                        addProperty("subject", draft.text("subject")); addProperty("body", draft.text("body"))
                    }; editor = true; vm.preview.value = null
                }) { Text(stringResource(R.string.apply_draft)) }
                else TextButton(onClick = { vm.preview.value = null }) { Text(stringResource(R.string.close)) }
            }, dismissButton = { TextButton(onClick = { vm.preview.value = null }) { Text(stringResource(R.string.cancel)) } })
    }
}

@Composable
fun CampaignForm(initial: JsonObject?, onDismiss: () -> Unit, onSave: (JsonObject) -> Unit) {
    var name by remember(initial) { mutableStateOf(initial?.text("name") ?: "") }
    var product by remember(initial) { mutableStateOf(initial?.text("product_name") ?: "") }
    var description by remember(initial) { mutableStateOf(initial?.text("service_description") ?: "") }
    var segment by remember(initial) { mutableStateOf(initial?.text("segment") ?: "") }
    var subject by remember(initial) { mutableStateOf(initial?.text("subject") ?: "") }
    var body by remember(initial) { mutableStateOf(initial?.text("body") ?: "") }
    var daily by remember(initial) { mutableStateOf(initial?.text("daily_limit") ?: "300") }
    var followups by remember(initial) { mutableStateOf(initial?.get("followups")?.toString() ?: "[]") }
    var invalid by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(stringResource(R.string.campaigns)) },
        text = {
            Column(Modifier.heightIn(max = 500.dp).verticalScrollCompat()) {
                Field(R.string.name, name) { name = it }
                Field(R.string.product, product) { product = it }
                Field(R.string.description, description, 3) { description = it }
                Field(R.string.segment, segment) { segment = it }
                Field(R.string.subject, subject) { subject = it }
                Field(R.string.body, body, 5) { body = it }
                Field(R.string.daily_limit, daily) { daily = it }
                Field(R.string.followup_json, followups, 3) { followups = it; invalid = false }
                if (invalid) Text("JSON: [{\"delay_days\":3,\"subject\":\"…\",\"body\":\"…\"}]", color = MaterialTheme.colorScheme.error)
                Text(stringResource(R.string.review_warning))
            }
        },
        confirmButton = { TextButton(enabled = name.isNotBlank() && product.isNotBlank() && description.isNotBlank() && subject.isNotBlank() && body.isNotBlank() && (daily.toIntOrNull() ?: 0) > 0, onClick = {
            val parsed = runCatching { JsonParser.parseString(followups).asJsonArray }.getOrNull()
            if (parsed == null) invalid = true else onSave(obj(
                "name" to name, "product_name" to product, "service_description" to description, "segment" to segment,
                "subject" to subject, "body" to body, "daily_limit" to daily.toInt()).apply { add("followups", parsed) })
        }) { Text(stringResource(R.string.save)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}
