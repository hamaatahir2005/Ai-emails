package com.aiemail.os.ui

import android.net.Uri
import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.aiemail.os.data.Repository
import com.google.gson.*
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.HttpException
import javax.inject.Inject

fun JsonObject.text(key: String): String = get(key)?.takeUnless { it.isJsonNull }?.asString ?: ""
fun obj(vararg pairs: Pair<String, Any?>): JsonObject = Gson().toJsonTree(pairs.toMap()).asJsonObject

@HiltViewModel
class OsViewModel @Inject constructor(val repo: Repository, @ApplicationContext private val context: Context) : ViewModel() {
    val authenticated = MutableStateFlow(repo.session.token() != null)
    val busy = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val info = MutableStateFlow<String?>(null)
    val settings = MutableStateFlow(JsonObject())
    val customers = MutableStateFlow<List<JsonObject>>(emptyList())
    val selectedCampaign = MutableStateFlow<JsonObject?>(null)
    val preview = MutableStateFlow<JsonObject?>(null)
    val history = MutableStateFlow("")
    val analytics = repo.cache.observe("analytics").map { it?.let { JsonParser.parseString(it.json).asJsonObject } ?: JsonObject() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), JsonObject())
    val campaigns = repo.cache.observe("campaigns").map { row -> row?.let { JsonParser.parseString(it.json).asJsonArray.map { it.asJsonObject } } ?: emptyList() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val cachedAt = repo.cache.observe("analytics").map { it?.updatedAt ?: 0L }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), 0L)
    init {
        viewModelScope.launch {
            repo.cache.observe("customers").collect { row ->
                if (row != null) customers.value = JsonParser.parseString(row.json).asJsonArray.map { it.asJsonObject }
            }
        }
    }
    fun runTask(block: suspend () -> Unit) {
        viewModelScope.launch {
            busy.value = true
            try { block() }
            catch (e: Exception) {
                if (e is CancellationException) throw e
                error.value = if (e is HttpException) {
                    if (e.code() == 401) { authenticated.value = false; repo.cache.clear() }
                    runCatching { JsonParser.parseString(e.response()?.errorBody()?.string()).asJsonObject.get("detail").toString() }.getOrNull() ?: "HTTP ${e.code()}"
                } else e.message ?: "Connection failed"
            } finally { busy.value = false }
        }
    }
    fun login(email: String, password: String) = runTask {
        val response = repo.api.login(mapOf("email" to email, "password" to password))
        repo.session.save(response.text("access_token"))
        authenticated.value = true
        repo.refresh()
        registerPush()
    }
    private fun registerPush() {
        if (FirebaseApp.getApps(context).isEmpty()) return
        FirebaseMessaging.getInstance().token.addOnSuccessListener { value ->
            runTask { repo.api.device(mapOf("token" to value)) }
        }
    }
    fun logout() = runTask {
        try { repo.api.logout() } finally {
            repo.session.clear(); repo.cache.clear(); authenticated.value = false
            settings.value = JsonObject(); customers.value = emptyList(); selectedCampaign.value = null
        }
    }
    suspend fun refreshNow(days: Int) { repo.refresh(days) }
    private var selectedDays = 30
    fun poll() = runTask { repo.refreshMetrics(selectedDays) }
    fun refresh(days: Int = selectedDays) = runTask { selectedDays = days; repo.refresh(days) }
    fun search(q: String, category: String, segment: String, offset: Int = 0) = runTask {
        val rows = repo.api.customers(q, category, segment, offset)
        customers.value = if (offset == 0) rows else customers.value + rows
    }
    fun saveCustomer(data: JsonObject) = runTask { repo.api.addCustomer(data); repo.refresh(); info.value = "Saved" }
    fun suppress(id: Int) = runTask { repo.api.suppress(id); repo.refresh() }
    fun deleteCustomer(id: Int) = runTask { repo.api.deleteCustomer(id); repo.refresh() }
    fun customerHistory(id: Int) = runTask { history.value = GsonBuilder().setPrettyPrinting().create().toJson(repo.api.customer(id)) }
    fun preference(id: Int, segment: String, followups: Boolean) = runTask {
        repo.api.preferences(id, obj("marketing" to true, "followups" to followups, "segment" to segment)); repo.refresh()
    }
    fun import(uri: Uri, name: String) = runTask {
        val bytes = withContext(Dispatchers.IO) {
            context.contentResolver.openInputStream(uri)?.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (output.size() <= 5 * 1024 * 1024) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    output.write(buffer, 0, read)
                }
                output.toByteArray() } ?: error("Cannot open file")
        }
        if (bytes.size > 5 * 1024 * 1024) error("Maximum file size is 5 MB")
        val part = MultipartBody.Part.createFormData("file", name, bytes.toRequestBody("application/octet-stream".toMediaType()))
        info.value = repo.api.importCustomers(part).toString()
        repo.refresh()
    }
    fun export(uri: Uri, analytics: Boolean) = runTask {
        val response = if (analytics) repo.api.exportAnalytics() else repo.api.exportCustomers()
        withContext(Dispatchers.IO) {
            response.use { body ->
                context.contentResolver.openOutputStream(uri)?.use { output -> body.byteStream().use { it.copyTo(output) } } ?: error("Cannot write file")
            }
        }
        info.value = "Export saved"
    }
    fun saveCampaign(data: JsonObject, id: Int? = null) = runTask {
        selectedCampaign.value = if (id == null) repo.api.addCampaign(data) else repo.api.editCampaign(id, data)
        repo.refresh()
        info.value = "Draft saved"
    }
    fun action(id: Int, action: String, at: String = "") = runTask {
        repo.api.action(id, action, if (action == "schedule") obj("scheduled_at" to at) else JsonObject())
        repo.refresh()
        selectedCampaign.value = repo.api.campaigns().firstOrNull { it.text("id") == id.toString() }
        info.value = "Saved"
    }
    fun preview(id: Int, customer: Int) = runTask { preview.value = repo.api.action(id, "preview", obj("customer_id" to customer)) }
    fun generate(id: Int, language: String, instruction: String, customerId: Int? = null) = runTask {
        preview.value = repo.api.generate(obj("campaign_id" to id, "language" to language, "instruction" to instruction, "customer_id" to customerId))
    }
    fun loadSettings() = runTask { settings.value = repo.api.settings() }
    fun saveSettings(data: JsonObject) = runTask { repo.api.saveSettings(data); settings.value = repo.api.settings(); info.value = "Settings saved" }
    fun messageStatus(id: Int) = runTask {
        history.value = GsonBuilder().setPrettyPrinting().create().toJson(repo.api.messages(id))
    }
    fun stop() = runTask { repo.api.stop(); repo.refresh(); info.value = "Emergency stop activated" }
    fun password(old: String, new: String) = runTask {
        repo.api.password(mapOf("old_password" to old, "new_password" to new))
        repo.session.clear(); repo.cache.clear(); authenticated.value = false
    }
}
