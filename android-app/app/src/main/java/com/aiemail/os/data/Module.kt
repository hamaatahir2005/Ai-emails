package com.aiemail.os.data

import android.content.Context
import androidx.room.Room
import com.aiemail.os.BuildConfig
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton fun client(store: SessionStore): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val request = chain.request().newBuilder()
            store.token()?.let { request.header("Authorization", "Bearer $it") }
            chain.proceed(request.build()).also { if (it.code == 401) store.clear() }
        }.callTimeout(90, TimeUnit.SECONDS).build()
    @Provides @Singleton fun api(client: OkHttpClient): Api = Retrofit.Builder()
        .baseUrl(BuildConfig.BACKEND_URL).client(client)
        .addConverterFactory(GsonConverterFactory.create()).build().create(Api::class.java)
    @Provides @Singleton fun db(@ApplicationContext context: Context): CacheDatabase =
        Room.databaseBuilder(context, CacheDatabase::class.java, "emailos-cache").build()
    @Provides fun cache(db: CacheDatabase): CacheDao = db.cache()
}
