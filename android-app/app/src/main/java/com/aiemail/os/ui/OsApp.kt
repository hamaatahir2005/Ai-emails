package com.aiemail.os.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import com.aiemail.os.R
import com.aiemail.os.BuildConfig
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag

@Composable
fun OsApp(vm: OsViewModel = hiltViewModel()) {
    val signedIn by vm.authenticated.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val info by vm.info.collectAsStateWithLifecycle()
    var theme by rememberSaveable { mutableStateOf("system") }
    val lifecycle = LocalLifecycleOwner.current
    LaunchedEffect(signedIn) {
        if (signedIn) lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                vm.poll()
                delay(30_000)
            }
        }
    }
    OsTheme(theme) {
        Surface(Modifier.fillMaxSize()) {
            if (!signedIn) LoginScreen(vm)
            else OsScaffold(onStop = vm::stop) { page ->
                when (page) {
                    0 -> DashboardScreen(vm)
                    1 -> CustomersScreen(vm)
                    2 -> CampaignsScreen(vm)
                    3 -> AnalyticsScreen(vm)
                    else -> SettingsScreen(vm, theme) { theme = it }
                }
            }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (error != null || info != null) AlertDialog(
                onDismissRequest = { vm.error.value = null; vm.info.value = null },
                text = { Text(error ?: info ?: "") },
                confirmButton = { TextButton(onClick = { vm.error.value = null; vm.info.value = null }) { Text(stringResource(R.string.close)) } })
        }
    }
}

@Composable
fun OsScaffold(onStop: () -> Unit, content: @Composable (Int) -> Unit) {
    var page by rememberSaveable { mutableIntStateOf(0) }
    var confirmStop by remember { mutableStateOf(false) }
    val titles = listOf(R.string.dashboard, R.string.customers, R.string.campaigns, R.string.analytics, R.string.settings)
    val icons = listOf(Icons.Outlined.Dashboard, Icons.Outlined.People, Icons.Outlined.Campaign, Icons.Outlined.BarChart, Icons.Outlined.Settings)
    Scaffold(
        topBar = {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text("EMAIL / OS", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                    Text(stringResource(titles[page]), style = MaterialTheme.typography.headlineMedium)
                }
                IconButton(onClick = { confirmStop = true }) { Icon(Icons.Outlined.StopCircle, stringResource(R.string.stop), tint = MaterialTheme.colorScheme.error) }
            }
        },
        bottomBar = {
            NavigationBar {
                titles.forEachIndexed { index, title ->
                    NavigationBarItem(selected = page == index, onClick = { page = index },
                        icon = { Icon(icons[index], null) }, label = { Text(stringResource(title), maxLines = 1) })
                }
            }
        }
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).background(Brush.verticalGradient(listOf(MaterialTheme.colorScheme.primary.copy(alpha = .08f), MaterialTheme.colorScheme.background)))) {
            AnimatedContent(targetState = page, label = "navigation") { current -> content(current) }
        }
    }
    if (confirmStop) AlertDialog(onDismissRequest = { confirmStop = false },
        text = { Text(stringResource(R.string.stop)) },
        confirmButton = { TextButton(onClick = { confirmStop = false; onStop() }) { Text(stringResource(R.string.confirm)) } },
        dismissButton = { TextButton(onClick = { confirmStop = false }) { Text(stringResource(R.string.cancel)) } })
}

@Composable
private fun LoginScreen(vm: OsViewModel) {
    val context = LocalContext.current
    val busy by vm.busy.collectAsStateWithLifecycle()
    LoginForm(
        googleConfigured = BuildConfig.GOOGLE_WEB_CLIENT_ID.isNotBlank(),
        busy = busy,
        onPasswordSignIn = { email, password -> vm.login(email, password) },
        onGoogleSignIn = { vm.googleLogin(context) }
    )
}

@Composable
fun LoginForm(googleConfigured: Boolean, busy: Boolean = false,
              onPasswordSignIn: (String, String) -> Unit, onGoogleSignIn: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(28.dp), verticalArrangement = Arrangement.Center) {
        Text("EMAIL / OS", style = MaterialTheme.typography.displaySmall, color = MaterialTheme.colorScheme.primary)
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(32.dp))
        Field(R.string.email, email) { email = it }
        OutlinedTextField(value = password, onValueChange = { password = it }, label = { Text(stringResource(R.string.password)) },
            visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(16.dp))
        Button(onClick = { onPasswordSignIn(email, password); password = "" }, enabled = !busy && email.isNotBlank() && password.length >= 12, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.login))
        }
        Spacer(Modifier.height(16.dp))
        OutlinedButton(
            onClick = onGoogleSignIn, enabled = googleConfigured && !busy,
            modifier = Modifier.fillMaxWidth().testTag("google_sign_in")
        ) { Text(stringResource(R.string.google_sign_in)) }
        if (!googleConfigured) Text(
            stringResource(R.string.google_not_configured),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 8.dp)
        )
    }
}

@Composable
fun Field(label: Int, value: String, lines: Int = 1, onChange: (String) -> Unit) {
    OutlinedTextField(value = value, onValueChange = onChange, label = { Text(stringResource(label)) },
        singleLine = lines == 1, minLines = lines, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp))
}
@Composable
fun Toggle(label: Int, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(stringResource(label), modifier = Modifier.weight(1f).padding(vertical = 12.dp))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
