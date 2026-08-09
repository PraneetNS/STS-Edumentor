import time
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger("edumentor.agent.state_store")

def sanitize_redis_key(key: str) -> str:
    """
    Sanitize tenant input parts of a key to prevent key namespacing injection.
    Replaces any colons in sub-keys (after the first namespace colon) with hyphens.
    """
    if not key:
        return key
    parts = key.split(":")
    if len(parts) <= 1:
        return key
    # Namespace is parts[0], rest is the tenant key/session id.
    # Replace colons in tenant key with hyphens to keep the partition boundaries clean.
    sanitized_parts = [parts[0]]
    for p in parts[1:]:
        sanitized_parts.append(p.replace(":", "-"))
    return ":".join(sanitized_parts)

class StateStore:
    """
    Common interface for interacting with the shared state storage.
    """
    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError()

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        raise NotImplementedError()

    async def delete(self, key: str) -> None:
        raise NotImplementedError()

    async def exists(self, key: str) -> bool:
        raise NotImplementedError()

    async def rpush(self, key: str, value: str) -> int:
        raise NotImplementedError()

    async def rpop(self, key: str) -> Optional[str]:
        raise NotImplementedError()

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        raise NotImplementedError()

    async def ltrim(self, key: str, start: int, end: int) -> None:
        raise NotImplementedError()

    async def llen(self, key: str) -> int:
        raise NotImplementedError()

    async def hset(self, key: str, field: str, value: str) -> int:
        raise NotImplementedError()

    async def hget(self, key: str, field: str) -> Optional[str]:
        raise NotImplementedError()

    async def hgetall(self, key: str) -> Dict[str, str]:
        raise NotImplementedError()

    async def hdel(self, key: str, field: str) -> int:
        raise NotImplementedError()

    async def expire(self, key: str, seconds: int) -> bool:
        raise NotImplementedError()

    async def publish(self, channel: str, message: str) -> int:
        raise NotImplementedError()

    async def subscribe(self, channel: str):
        raise NotImplementedError()


class RedisStateStore(StateStore):
    """
    State store backed by Redis (using redis.asyncio).
    """
    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis
        self.client = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("RedisStateStore initialized with url: %s", redis_url)

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(sanitize_redis_key(key))

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        await self.client.set(sanitize_redis_key(key), value, ex=ex)

    async def delete(self, key: str) -> None:
        await self.client.delete(sanitize_redis_key(key))

    async def exists(self, key: str) -> bool:
        return await self.client.exists(sanitize_redis_key(key)) > 0

    async def rpush(self, key: str, value: str) -> int:
        return await self.client.rpush(sanitize_redis_key(key), value)

    async def rpop(self, key: str) -> Optional[str]:
        return await self.client.rpop(sanitize_redis_key(key))

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        return await self.client.lrange(sanitize_redis_key(key), start, end)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        await self.client.ltrim(sanitize_redis_key(key), start, end)

    async def llen(self, key: str) -> int:
        return await self.client.llen(sanitize_redis_key(key))

    async def hset(self, key: str, field: str, value: str) -> int:
        return await self.client.hset(sanitize_redis_key(key), field, value)

    async def hget(self, key: str, field: str) -> Optional[str]:
        return await self.client.hget(sanitize_redis_key(key), field)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return await self.client.hgetall(sanitize_redis_key(key))

    async def hdel(self, key: str, field: str) -> int:
        return await self.client.hdel(sanitize_redis_key(key), field)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self.client.expire(sanitize_redis_key(key), seconds)

    async def publish(self, channel: str, message: str) -> int:
        return await self.client.publish(sanitize_redis_key(channel), message)

    async def subscribe(self, channel: str):
        pubsub = self.client.pubsub()
        await pubsub.subscribe(sanitize_redis_key(channel))
        return RedisPubSubListener(pubsub)

    async def close(self) -> None:
        await self.client.aclose()


class RedisPubSubListener:
    def __init__(self, pubsub) -> None:
        self.pubsub = pubsub

    async def listen(self):
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                yield {"channel": message["channel"], "data": message["data"]}

    async def unsubscribe(self) -> None:
        await self.pubsub.unsubscribe()


class InMemoryStateStore(StateStore):
    """
    Process-memory mock state store for pure local development fallback.
    """
    def __init__(self) -> None:
        self._strings: Dict[str, str] = {}
        self._lists: Dict[str, List[str]] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._expires: Dict[str, float] = {}
        self._subscribers: Dict[str, set] = {}
        logger.info("InMemoryStateStore initialized.")

    def _is_expired(self, key: str) -> bool:
        if key in self._expires:
            if time.time() > self._expires[key]:
                self._delete_key(key)
                return True
        return False

    def _delete_key(self, key: str) -> None:
        self._strings.pop(key, None)
        self._lists.pop(key, None)
        self._hashes.pop(key, None)
        self._expires.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return None
        return self._strings.get(san_key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        san_key = sanitize_redis_key(key)
        self._delete_key(san_key)
        self._strings[san_key] = str(value)
        if ex is not None:
            self._expires[san_key] = time.time() + ex

    async def delete(self, key: str) -> None:
        san_key = sanitize_redis_key(key)
        self._delete_key(san_key)

    async def exists(self, key: str) -> bool:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return False
        return (san_key in self._strings) or (san_key in self._lists) or (san_key in self._hashes)

    async def rpush(self, key: str, value: str) -> int:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            self._delete_key(san_key)
        if san_key not in self._lists:
            self._lists[san_key] = []
        self._lists[san_key].append(str(value))
        return len(self._lists[san_key])

    async def rpop(self, key: str) -> Optional[str]:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return None
        if san_key in self._lists and self._lists[san_key]:
            return self._lists[san_key].pop()
        return None

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return []
        if san_key not in self._lists:
            return []
        lst = self._lists[san_key]
        length = len(lst)
        s = start if start >= 0 else max(0, length + start)
        if end < 0:
            e = max(0, length + end + 1)
        else:
            e = min(length, end + 1)
        return lst[s:e]

    async def ltrim(self, key: str, start: int, end: int) -> None:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return
        if san_key not in self._lists:
            return
        lst = self._lists[san_key]
        length = len(lst)
        s = start if start >= 0 else max(0, length + start)
        if end < 0:
            e = max(0, length + end + 1)
        else:
            e = min(length, end + 1)
        self._lists[san_key] = lst[s:e]

    async def llen(self, key: str) -> int:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return 0
        return len(self._lists.get(san_key, []))

    async def hset(self, key: str, field: str, value: str) -> int:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            self._delete_key(san_key)
        if san_key not in self._hashes:
            self._hashes[san_key] = {}
        is_new = field not in self._hashes[san_key]
        self._hashes[san_key][field] = str(value)
        return 1 if is_new else 0

    async def hget(self, key: str, field: str) -> Optional[str]:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return None
        if san_key in self._hashes:
            return self._hashes[san_key].get(field)
        return None

    async def hgetall(self, key: str) -> Dict[str, str]:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return {}
        return self._hashes.get(san_key, {})

    async def hdel(self, key: str, field: str) -> int:
        san_key = sanitize_redis_key(key)
        if self._is_expired(san_key):
            return 0
        if san_key in self._hashes and field in self._hashes[san_key]:
            del self._hashes[san_key][field]
            return 1
        return 0

    async def expire(self, key: str, seconds: int) -> bool:
        san_key = sanitize_redis_key(key)
        if await self.exists(san_key):
            self._expires[san_key] = time.time() + seconds
            return True
        return False


    async def publish(self, channel: str, message: str) -> int:
        queues = self._subscribers.get(channel, set())
        for q in queues:
            await q.put(message)
        return len(queues)

    async def subscribe(self, channel: str):
        queue = asyncio.Queue()
        if channel not in self._subscribers:
            self._subscribers[channel] = set()
        self._subscribers[channel].add(queue)
        return InMemoryPubSubListener(queue, self, channel)

    def _unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        if channel in self._subscribers:
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]


class InMemoryPubSubListener:
    def __init__(self, queue: asyncio.Queue, store: InMemoryStateStore, channel: str) -> None:
        self.queue = queue
        self.store = store
        self.channel = channel

    async def listen(self):
        try:
            while True:
                msg = await self.queue.get()
                yield {"channel": self.channel, "data": msg}
        except asyncio.CancelledError:
            pass

    async def unsubscribe(self) -> None:
        self.store._unsubscribe(self.channel, self.queue)


_state_store_instance: Optional[StateStore] = None

def get_state_store() -> StateStore:
    global _state_store_instance
    if _state_store_instance is None:
        from config import Config
        if Config.REDIS_ENABLED:
            _state_store_instance = RedisStateStore(Config.REDIS_URL)
        else:
            _state_store_instance = InMemoryStateStore()
    return _state_store_instance

def set_state_store(store: StateStore) -> None:
    global _state_store_instance
    _state_store_instance = store
