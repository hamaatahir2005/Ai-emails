package com.aiemail.os

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.aiemail.os.data.Repository
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.*
import javax.inject.Inject

@AndroidEntryPoint
class PushService : FirebaseMessagingService() {
    @Inject lateinit var repo: Repository
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    override fun onNewToken(token: String) {
        if (repo.session.token() != null) scope.launch { runCatching { repo.api.device(mapOf("token" to token)) } }
    }
    override fun onMessageReceived(message: RemoteMessage) {
        if (repo.session.token() == null) return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("campaigns", getString(R.string.campaigns), NotificationManager.IMPORTANCE_DEFAULT))
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED && android.os.Build.VERSION.SDK_INT >= 33) return
        val pending = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        manager.notify((message.messageId ?: message.data.toString()).hashCode(),
            NotificationCompat.Builder(this, "campaigns").setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle(message.notification?.title ?: getString(R.string.app_name))
                .setContentText(message.notification?.body ?: message.data["kind"]).setContentIntent(pending).setAutoCancel(true).build())
    }
    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}
