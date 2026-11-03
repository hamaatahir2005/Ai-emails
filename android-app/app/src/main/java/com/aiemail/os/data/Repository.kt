package com.aiemail.os.data

import com.google.gson.Gson
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class Repository @Inject constructor(val api: Api, val cache: CacheDao, val session: SessionStore) {
    suspend fun refreshMetrics(days: Int = 30) {
        cache.put(CacheEntry("analytics", api.analytics(days).toString(), System.currentTimeMillis()))
        cache.put(CacheEntry("campaigns", Gson().toJson(api.campaigns()), System.currentTimeMillis()))
    }
    suspend fun refresh(days: Int = 30) {
        refreshMetrics(days)
        cache.put(CacheEntry("customers", Gson().toJson(api.customers()), System.currentTimeMillis()))
    }
}
