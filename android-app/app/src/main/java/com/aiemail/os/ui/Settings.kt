package com.aiemail.os.ui

import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aiemail.os.R

@Composable
fun SettingsScreen(vm: OsViewModel, theme: String, onTheme: (String) -> Unit) {
    val loaded by vm.settings.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { vm.loadSettings() }
    var oldPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().padding(16.dp).verticalScrollCompat(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(R.string.appearance), style = MaterialTheme.typography.titleLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("system" to R.string.system_theme, "dark" to R.string.dark_theme, "light" to R.string.light_theme).forEach { (value, label) ->
                FilterChip(selected = theme == value, onClick = { onTheme(value) }, label = { Text(stringResource(label)) })
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("en" to "English", "ar" to "العربية", "ckb" to "کوردی").forEach { (code, label) ->
                OutlinedButton(onClick = { AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(code)) }) { Text(label) }
            }
        }
        if (loaded.has("id")) key(loaded.toString()) {
            var daily by remember { mutableStateOf(loaded.text("daily_limit")) }
            var quota by remember { mutableStateOf(loaded.text("provider_daily_limit")) }
            var rate by remember { mutableStateOf(loaded.text("provider_per_minute")) }
            var zone by remember { mutableStateOf(loaded.text("timezone")) }
            var start by remember { mutableStateOf(loaded.text("start_hour")) }
            var end by remember { mutableStateOf(loaded.text("end_hour")) }
            var senderEmail by remember { mutableStateOf(loaded.text("sender_email")) }
            var senderName by remember { mutableStateOf(loaded.text("sender_name")) }
            var address by remember { mutableStateOf(loaded.text("postal_address")) }
            var dns by remember { mutableStateOf(loaded.get("dns_confirmed")?.asBoolean ?: false) }
            var stopped by remember { mutableStateOf(loaded.get("emergency_stop")?.asBoolean ?: true) }
            var notifications by remember { mutableStateOf(loaded.get("notifications_enabled")?.asBoolean ?: true) }
            var language by remember { mutableStateOf(loaded.text("language")) }
            var gemini by remember { mutableStateOf("") }
            var brevo by remember { mutableStateOf("") }
            Text(stringResource(R.string.settings), style = MaterialTheme.typography.titleLarge)
            Field(R.string.daily_limit, daily) { daily = it }
            Field(R.string.provider_limit, quota) { quota = it }
            Field(R.string.provider_rate, rate) { rate = it }
            Field(R.string.timezone, zone) { zone = it }
            Field(R.string.start_hour, start) { start = it }
            Field(R.string.end_hour, end) { end = it }
            Field(R.string.sender_email, senderEmail) { senderEmail = it }
            Field(R.string.sender_name, senderName) { senderName = it }
            Field(R.string.postal_address, address, 3) { address = it }
            Field(R.string.language, language) { language = it }
            Toggle(R.string.dns, dns) { dns = it }
            Toggle(R.string.emergency, stopped) { stopped = it }
            Toggle(R.string.notifications, notifications) { notifications = it }
            OutlinedTextField(value = gemini, onValueChange = { gemini = it }, modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.gemini_key)) }, visualTransformation = PasswordVisualTransformation())
            OutlinedTextField(value = brevo, onValueChange = { brevo = it }, modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.brevo_key)) }, visualTransformation = PasswordVisualTransformation())
            Text("Gemini: " + loaded.text("gemini_configured") + " · Brevo: " + loaded.text("brevo_configured"))
            Button(onClick = {
                vm.saveSettings(obj("daily_limit" to (daily.toIntOrNull() ?: 0), "provider_daily_limit" to (quota.toIntOrNull() ?: 0),
                    "provider_per_minute" to (rate.toIntOrNull() ?: 0), "timezone" to zone, "start_hour" to (start.toIntOrNull() ?: -1),
                    "end_hour" to (end.toIntOrNull() ?: -1), "sender_email" to senderEmail, "sender_name" to senderName,
                    "postal_address" to address, "dns_confirmed" to dns, "emergency_stop" to stopped,
                    "language" to language, "notifications_enabled" to notifications).apply {
                    if (gemini.isNotBlank()) addProperty("gemini_key", gemini)
                    if (brevo.isNotBlank()) addProperty("brevo_key", brevo)
                })
                gemini = ""; brevo = ""
            }) { Text(stringResource(R.string.save)) }
        }
        HorizontalDivider()
        OutlinedTextField(oldPassword, { oldPassword = it }, label = { Text(stringResource(R.string.old_password)) }, visualTransformation = PasswordVisualTransformation())
        OutlinedTextField(newPassword, { newPassword = it }, label = { Text(stringResource(R.string.new_password)) }, visualTransformation = PasswordVisualTransformation())
        Button(enabled = oldPassword.isNotBlank() && newPassword.length >= 12, onClick = { vm.password(oldPassword, newPassword); oldPassword = ""; newPassword = "" }) { Text(stringResource(R.string.change_password)) }
        OutlinedButton(onClick = { vm.logout() }) { Text(stringResource(R.string.logout)) }
        Spacer(Modifier.height(24.dp))
    }
}
