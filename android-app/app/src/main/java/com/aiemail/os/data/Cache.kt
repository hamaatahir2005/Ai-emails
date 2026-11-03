package com.aiemail.os.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "cache")
data class CacheEntry(@PrimaryKey val key: String, val json: String, val updatedAt: Long)

@Dao
interface CacheDao {
    @Query("SELECT * FROM cache WHERE key = :key") fun observe(key: String): Flow<CacheEntry?>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(entry: CacheEntry)
    @Query("DELETE FROM cache") suspend fun clear()
}
@Database(entities = [CacheEntry::class], version = 1, exportSchema = false)
abstract class CacheDatabase : RoomDatabase() { abstract fun cache(): CacheDao }
