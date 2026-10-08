"""
JARVIS Performance Cache Manager
=============================
Advanced caching system with Redis, memory caching, and intelligent cache strategies.
"""

import asyncio
import json
import logging
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid
import weakref

from infrastructure.config import settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Cache level enumeration"""
    L1_MEMORY = "l1_memory"  # Fastest, smallest
    L2_REDIS = "l2_redis"   # Fast, larger
    L3_DISK = "l3_disk"      # Slower, persistent


class CachePolicy(Enum):
    """Cache eviction policy"""
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL = "ttl"


@dataclass
class CacheEntry:
    """Cache entry structure"""
    key: str
    value: Any
    level: CacheLevel
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    size_bytes: int = 0
    tags: List[str] = field(default_factory=list)


@dataclass
class CacheStats:
    """Cache statistics"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_size: int = 0
    entry_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class MemoryCache:
    """In-memory cache with LRU eviction"""
    
    def __init__(self, max_size: int = 1000, max_memory_mb: int = 100):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: Dict[str, CacheEntry] = {}
        self.access_order: List[str] = []
        self.stats = CacheStats()
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache"""
        async with self._lock:
            entry = self.cache.get(key)
            if entry is None:
                self.stats.misses += 1
                return None
            
            # Check expiration
            if entry.expires_at and datetime.now() > entry.expires_at:
                del self.cache[key]
                self.access_order.remove(key)
                self.stats.misses += 1
                return None
            
            # Update access
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            
            # Move to end of access order (LRU)
            self.access_order.remove(key)
            self.access_order.append(key)
            
            self.stats.hits += 1
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None, tags: Optional[List[str]] = None) -> bool:
        """Set value in memory cache"""
        async with self._lock:
            # Calculate size
            try:
                size_bytes = len(pickle.dumps(value))
            except:
                size_bytes = len(str(value).encode())
            
            # Check memory limit
            if size_bytes > self.max_memory_bytes:
                return False
            
            # Evict if necessary
            while (len(self.cache) >= self.max_size or 
                   self._get_total_size() + size_bytes > self.max_memory_bytes):
                if not self._evict_lru():
                    break
            
            # Create entry
            expires_at = None
            if ttl:
                expires_at = datetime.now() + timedelta(seconds=ttl)
            
            entry = CacheEntry(
                key=key,
                value=value,
                level=CacheLevel.L1_MEMORY,
                expires_at=expires_at,
                size_bytes=size_bytes,
                tags=tags or []
            )
            
            # Store
            self.cache[key] = entry
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            
            self._update_stats()
            return True
    
    def _evict_lru(self) -> bool:
        """Evict least recently used entry"""
        if not self.access_order:
            return False
        
        lru_key = self.access_order.pop(0)
        del self.cache[lru_key]
        self.stats.evictions += 1
        return True
    
    def _get_total_size(self) -> int:
        """Get total cache size in bytes"""
        return sum(entry.size_bytes for entry in self.cache.values())
    
    def _update_stats(self):
        """Update cache statistics"""
        self.stats.total_size = self._get_total_size()
        self.stats.entry_count = len(self.cache)
    
    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        self.access_order.clear()
        self.stats = CacheStats()
    
    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        self._update_stats()
        return self.stats


class RedisCache:
    """Redis-based distributed cache"""
    
    def __init__(self, redis_url: str = None, key_prefix: str = "jarvis:"):
        # Get Redis URL from settings if not provided
        # settings.redis.url uses the typed Settings object
        if redis_url is None:
            try:
                redis_url = settings.redis.url
            except AttributeError:
                # Fallback to environment variable
                import os
                redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.redis_client = None
        self.stats = CacheStats()
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize Redis connection.
        
        Uses RESP2 protocol (protocol=2) for compatibility with Redis < 6.0.
        Redis 3.x on Windows requires this setting.
        """
        try:
            import redis.asyncio as redis
            # Force RESP2 protocol for compatibility with Redis 3.x
            self.redis_client = redis.from_url(self.redis_url, protocol=2)
            await self.redis_client.ping()
            logger.info("Redis cache initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self.redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        if not self.redis_client:
            self.stats.misses += 1
            return None
        
        try:
            full_key = f"{self.key_prefix}{key}"
            data = await self.redis_client.get(full_key)
            
            if data is None:
                self.stats.misses += 1
                return None
            
            # Deserialize
            value = pickle.loads(data)
            self.stats.hits += 1
            return value
            
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            self.stats.misses += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None, tags: Optional[List[str]] = None) -> bool:
        """Set value in Redis cache"""
        if not self.redis_client:
            return False
        
        try:
            full_key = f"{self.key_prefix}{key}"
            data = pickle.dumps(value)
            
            # Set with TTL
            if ttl:
                await self.redis_client.setex(full_key, ttl, data)
            else:
                await self.redis_client.set(full_key, data)
            
            # Store tags in separate set
            if tags:
                tag_key = f"{self.key_prefix}tags:{key}"
                await self.redis_client.delete(tag_key)
                for tag in tags:
                    await self.redis_client.sadd(tag_key, tag)
                    await self.redis_client.sadd(f"{self.key_prefix}tag:{tag}", key)
            
            return True
            
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        if not self.redis_client:
            return False
        
        try:
            full_key = f"{self.key_prefix}{key}"
            result = await self.redis_client.delete(full_key)
            
            # Clean up tags
            tag_key = f"{self.key_prefix}tags:{key}"
            tags = await self.redis_client.smembers(tag_key)
            for tag in tags:
                await self.redis_client.srem(f"{self.key_prefix}tag:{tag}", key)
            await self.redis_client.delete(tag_key)
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    async def clear_by_tag(self, tag: str) -> int:
        """Clear all entries with specific tag"""
        if not self.redis_client:
            return 0
        
        try:
            tag_key = f"{self.key_prefix}tag:{tag}"
            keys = await self.redis_client.smembers(tag_key)
            
            if not keys:
                return 0
            
            # Delete all keys with this tag
            full_keys = [f"{self.key_prefix}{key}" for key in keys]
            deleted = await self.redis_client.delete(*full_keys)
            
            # Clean up tag sets
            for key in keys:
                await self.redis_client.delete(f"{self.key_prefix}tags:{key}")
            await self.redis_client.delete(tag_key)
            
            return deleted
            
        except Exception as e:
            logger.error(f"Redis clear by tag error: {e}")
            return 0
    
    def get_stats(self) -> CacheStats:
        """Get Redis cache statistics"""
        return self.stats


class CacheManager:
    """Advanced cache manager with multi-level caching"""
    
    def __init__(self):
        self.l1_cache = MemoryCache(max_size=1000, max_memory_mb=50)
        self.l2_cache = RedisCache()
        self.cache_stats = {
            "l1": self.l1_cache.get_stats(),
            "l2": self.l2_cache.get_stats()
        }
        self._initialized = False
    
    async def initialize(self):
        """Initialize cache manager"""
        await self.l2_cache.initialize()
        self._initialized = True
        logger.info("Cache manager initialized")
    
    def _generate_key(self, key: str, namespace: Optional[str] = None) -> str:
        """Generate cache key with namespace"""
        if namespace:
            return f"{namespace}:{key}"
        return key
    
    def _hash_key(self, key: str, max_length: int = 250) -> str:
        """Hash key if too long"""
        if len(key) <= max_length:
            return key
        
        return hashlib.md5(key.encode()).hexdigest()
    
    async def get(self, key: str, namespace: Optional[str] = None) -> Optional[Any]:
        """Get value from cache (L1 -> L2)"""
        if not self._initialized:
            return None
        
        full_key = self._generate_key(key, namespace)
        full_key = self._hash_key(full_key)
        
        # Try L1 (memory) first
        value = await self.l1_cache.get(full_key)
        if value is not None:
            return value
        
        # Try L2 (Redis)
        value = await self.l2_cache.get(full_key)
        if value is not None:
            # Promote to L1
            await self.l1_cache.set(full_key, value)
            return value
        
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        namespace: Optional[str] = None,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        cache_levels: Optional[List[CacheLevel]] = None
    ) -> bool:
        """Set value in cache"""
        if not self._initialized:
            return False
        
        full_key = self._generate_key(key, namespace)
        full_key = self._hash_key(full_key)
        
        levels = cache_levels or [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS]
        success = True
        
        for level in levels:
            if level == CacheLevel.L1_MEMORY:
                l1_ttl = min(ttl, 300) if ttl else 300  # Max 5 minutes in L1
                result = await self.l1_cache.set(full_key, value, l1_ttl, tags)
                success = success and result
            elif level == CacheLevel.L2_REDIS:
                result = await self.l2_cache.set(full_key, value, ttl, tags)
                success = success and result
        
        return success
    
    async def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """Delete key from all cache levels"""
        if not self._initialized:
            return False
        
        full_key = self._generate_key(key, namespace)
        full_key = self._hash_key(full_key)
        
        # Delete from L1
        if full_key in self.l1_cache.cache:
            del self.l1_cache.cache[full_key]
            if full_key in self.l1_cache.access_order:
                self.l1_cache.access_order.remove(full_key)
        
        # Delete from L2
        return await self.l2_cache.delete(full_key)
    
    async def clear_by_tag(self, tag: str) -> int:
        """Clear all entries with specific tag"""
        if not self._initialized:
            return 0
        
        count = 0
        
        # Clear from L1
        keys_to_remove = []
        for key, entry in self.l1_cache.cache.items():
            if tag in entry.tags:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.l1_cache.cache[key]
            if key in self.l1_cache.access_order:
                self.l1_cache.access_order.remove(key)
            count += 1
        
        # Clear from L2
        count += await self.l2_cache.clear_by_tag(tag)
        
        return count
    
    async def clear_all(self):
        """Clear all cache entries"""
        self.l1_cache.clear()
        
        # Clear Redis (if available)
        if self.l2_cache.redis_client:
            try:
                pattern = f"{self.l2_cache.key_prefix}*"
                keys = await self.l2_cache.redis_client.keys(pattern)
                if keys:
                    await self.l2_cache.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Failed to clear Redis: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        l1_stats = self.l1_cache.get_stats()
        l2_stats = self.l2_cache.get_stats()
        
        total_hits = l1_stats.hits + l2_stats.hits
        total_misses = l1_stats.misses + l2_stats.misses
        total_requests = total_hits + total_misses
        
        return {
            "l1_memory": {
                "hits": l1_stats.hits,
                "misses": l1_stats.misses,
                "hit_rate": l1_stats.hit_rate,
                "entries": l1_stats.entry_count,
                "size_mb": l1_stats.total_size / (1024 * 1024),
                "evictions": l1_stats.evictions
            },
            "l2_redis": {
                "hits": l2_stats.hits,
                "misses": l2_stats.misses,
                "hit_rate": l2_stats.hit_rate,
                "connected": self.l2_cache.redis_client is not None
            },
            "overall": {
                "total_hits": total_hits,
                "total_misses": total_misses,
                "hit_rate": total_hits / total_requests if total_requests > 0 else 0.0,
                "total_requests": total_requests
            }
        }


# Cache decorator for functions
def cached(
    ttl: int = 300,
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    cache_levels: Optional[List[CacheLevel]] = None
):
    """Decorator to cache function results"""
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key_data = {
                "func": func.__name__,
                "args": args,
                "kwargs": kwargs
            }
            cache_key = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
            
            # Try to get from cache
            cache_manager = get_cache_manager()
            cached_result = await cache_manager.get(cache_key, namespace)
            
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache_manager.set(
                cache_key,
                result,
                namespace=namespace,
                ttl=ttl,
                tags=tags,
                cache_levels=cache_levels
            )
            
            return result
        
        return wrapper
    return decorator


# Global instance
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """Get global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
