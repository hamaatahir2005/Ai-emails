package com.aiemail.os.data

import com.google.gson.JsonObject
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.http.*

interface Api {
    @POST("auth/login") suspend fun login(@Body data: Map<String, String>): JsonObject
    @POST("auth/google/challenge") suspend fun googleChallenge(): JsonObject
    @POST("auth/google") suspend fun googleLogin(@Body data: Map<String, String>): JsonObject
    @POST("auth/logout") suspend fun logout()
    @POST("auth/password") suspend fun password(@Body data: Map<String, String>)
    @GET("auth/me") suspend fun me(): JsonObject
    @GET("analytics") suspend fun analytics(@Query("days") days: Int = 30): JsonObject
    @GET("customers") suspend fun customers(@Query("q") q: String = "", @Query("category") category: String = "", @Query("segment") segment: String = "", @Query("offset") offset: Int = 0): List<JsonObject>
    @POST("customers") suspend fun addCustomer(@Body data: JsonObject): JsonObject
    @DELETE("customers/{id}") suspend fun deleteCustomer(@Path("id") id: Int)
    @POST("customers/{id}/suppress") suspend fun suppress(@Path("id") id: Int)
    @PUT("customers/{id}/preferences") suspend fun preferences(@Path("id") id: Int, @Body data: JsonObject): JsonObject
    @GET("customers/{id}") suspend fun customer(@Path("id") id: Int): JsonObject
    @GET("customers/export") suspend fun exportCustomers(): ResponseBody
    @Multipart @POST("customers/import") suspend fun importCustomers(@Part file: MultipartBody.Part): JsonObject
    @GET("campaigns") suspend fun campaigns(): List<JsonObject>
    @POST("campaigns") suspend fun addCampaign(@Body data: JsonObject): JsonObject
    @PUT("campaigns/{id}") suspend fun editCampaign(@Path("id") id: Int, @Body data: JsonObject): JsonObject
    @POST("campaigns/{id}/{action}") suspend fun action(@Path("id") id: Int, @Path("action") action: String, @Body data: JsonObject = JsonObject()): JsonObject
    @POST("ai/generate") suspend fun generate(@Body data: JsonObject): JsonObject
    @GET("settings") suspend fun settings(): JsonObject
    @PUT("settings") suspend fun saveSettings(@Body data: JsonObject): JsonObject
    @POST("settings/emergency-stop") suspend fun stop()
    @POST("devices") suspend fun device(@Body data: Map<String, String>)
    @GET("analytics/export") suspend fun exportAnalytics(): ResponseBody
    @GET("messages") suspend fun messages(@Query("campaign_id") id: Int): List<JsonObject>
}
