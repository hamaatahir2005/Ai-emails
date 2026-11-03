package com.aiemail.os.ui

import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aiemail.os.R
import com.google.gson.JsonObject
import java.time.Instant

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CustomersScreen(vm: OsViewModel) {
    val customers by vm.customers.collectAsStateWithLifecycle()
    val history by vm.history.collectAsStateWithLifecycle()
    var search by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("") }
    var segment by remember { mutableStateOf("") }
    var add by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<JsonObject?>(null) }
    var confirm by remember { mutableStateOf<Pair<Int, Boolean>?>(null) }
    val context = LocalContext.current
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let {
            val name = context.contentResolver.query(it, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else "contacts.csv"
            } ?: "contacts.csv"
            vm.import(it, name)
        }
    }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri -> uri?.let { vm.export(it, false) } }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Field(R.string.search, search) { search = it }
            Field(R.string.category, category) { category = it }
            Field(R.string.segment, segment) { segment = it }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { vm.search(search, category, segment) }) { Text(stringResource(R.string.search)) }
                OutlinedButton(onClick = { add = true }) { Text(stringResource(R.string.add)) }
                OutlinedButton(onClick = { importer.launch(arrayOf("text/*", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/csv")) }) { Text(stringResource(R.string.import_file)) }
                OutlinedButton(onClick = { exporter.launch("customers.csv") }) { Text(stringResource(R.string.export_file)) }
            }
        }
        if (customers.isEmpty()) item { Text(stringResource(R.string.empty)) }
        items(customers, key = { it.text("id") }) { customer ->
            ElevatedCard(onClick = { selected = customer }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("#" + customer.text("id") + " · " + customer.text("full_name"), style = MaterialTheme.typography.titleMedium)
                    Text(customer.text("email"))
                    Text(customer.text("company_name") + " · " + customer.text("subscription_status"), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        item { TextButton(onClick = { vm.search(search, category, segment, customers.size) }) { Text(stringResource(R.string.load_more)) } }
    }
    if (add) CustomerForm(onDismiss = { add = false }, onSave = { vm.saveCustomer(it); add = false })
    selected?.let { customer ->
        var followups by remember(customer) { mutableStateOf(customer.getAsJsonObject("preferences")?.get("followups")?.asBoolean ?: true) }
        var group by remember(customer) { mutableStateOf(customer.text("segment")) }
        AlertDialog(onDismissRequest = { selected = null }, title = { Text(customer.text("full_name")) },
            text = {
                Column {
                    Text(customer.text("email"))
                    Field(R.string.segment, group) { group = it }
                    Toggle(R.string.followups, followups) { followups = it }
                    TextButton(onClick = { vm.customerHistory(customer.text("id").toInt()) }) { Text(stringResource(R.string.history)) }
                    TextButton(onClick = { confirm = customer.text("id").toInt() to false }) { Text(stringResource(R.string.suppress)) }
                    TextButton(onClick = { confirm = customer.text("id").toInt() to true }) { Text(stringResource(R.string.delete_record)) }
                }
            }, confirmButton = { TextButton(onClick = { vm.preference(customer.text("id").toInt(), group, followups); selected = null }) { Text(stringResource(R.string.save)) } },
            dismissButton = { TextButton(onClick = { selected = null }) { Text(stringResource(R.string.close)) } })
    }
    confirm?.let { (id, deletion) ->
        AlertDialog(onDismissRequest = { confirm = null }, text = { Text(stringResource(if (deletion) R.string.delete_record else R.string.suppress)) },
            confirmButton = { TextButton(onClick = { if (deletion) vm.deleteCustomer(id) else vm.suppress(id); confirm = null; selected = null }) { Text(stringResource(R.string.confirm)) } },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text(stringResource(R.string.cancel)) } })
    }
    if (history.isNotEmpty()) AlertDialog(onDismissRequest = { vm.history.value = "" },
        text = { androidx.compose.foundation.text.selection.SelectionContainer { Text(history, modifier = Modifier.heightIn(max = 400.dp).then(Modifier.verticalScrollCompat())) } },
        confirmButton = { TextButton(onClick = { vm.history.value = "" }) { Text(stringResource(R.string.close)) } })
}

@Composable
fun Modifier.verticalScrollCompat(): Modifier = this.verticalScroll(androidx.compose.foundation.rememberScrollState())

@Composable
fun CustomerForm(onDismiss: () -> Unit, onSave: (JsonObject) -> Unit) {
    var fullName by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var company by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("") }
    var country by remember { mutableStateOf("") }
    var language by remember { mutableStateOf("en") }
    var source by remember { mutableStateOf("") }
    var stamp by remember { mutableStateOf(Instant.now().toString()) }
    var segment by remember { mutableStateOf("") }
    var consent by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(stringResource(R.string.add)) },
        text = {
            Column(Modifier.heightIn(max = 500.dp).verticalScrollCompat()) {
                Field(R.string.full_name, fullName) { fullName = it }
                Field(R.string.email, email) { email = it }
                Field(R.string.company, company) { company = it }
                Field(R.string.category, category) { category = it }
                Field(R.string.country, country) { country = it }
                Field(R.string.language, language) { language = it }
                Field(R.string.segment, segment) { segment = it }
                Field(R.string.consent_source, source) { source = it }
                Field(R.string.consent_timestamp, stamp) { stamp = it }
                Toggle(R.string.consent, consent) { consent = it }
            }
        },
        confirmButton = {
            TextButton(enabled = consent && source.isNotBlank() && fullName.isNotBlank() && email.isNotBlank(),
                onClick = { onSave(obj("full_name" to fullName, "email" to email, "company_name" to company,
                    "business_category" to category, "country" to country, "language" to language, "segment" to segment,
                    "consent_status" to consent, "consent_timestamp" to stamp, "consent_source" to source)) }) { Text(stringResource(R.string.save)) }
        }, dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}
