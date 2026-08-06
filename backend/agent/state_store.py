import time
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger("edumentor.agent.state_store")

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
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        await self.client.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.client.exists(key) > 0

    async def rpush(self, key: str, value: str) -> int:
        return await self.client.rpush(key, value)

    async def rpop(self, key: str) -> Optional[str]:
        return await self.client.rpop(key)

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        return await self.client.lrange(key, start, end)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        await self.client.ltrim(key, start, end)

    async def llen(self, key: str) -> int:
        return await self.client.llen(key)

    async def hset(self, key: str, field: str, value: str) -> int:
        return await self.client.hset(key, field, value)

    async def hget(self, key: str, field: str) -> Optional[str]:
        return await self.client.hget(key, field)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return await self.client.hgetall(key)

    async def hdel(self, key: str, field: str) -> int:
        return await self.client.hdel(key, field)

    async def expire(self, key: str, seconds: int) -> bool:
        return await self.client.expire(key, seconds)

    async def publish(self, channel: str, message: str) -> int:
        return await self.client.publish(channel, message)

    async def subscribe(self, channel: str):
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
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
        if self._is_expired(key):
            return None
        return self._strings.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self._delete_key(key)
        self._strings[key] = str(value)
        if ex is not None:
            self._expires[key] = time.time() + ex

    async def delete(self, key: str) -> None:
        self._delete_key(key)

    async def exists(self, key: str) -> bool:
        if self._is_expired(key):
            return False
        return (key in self._strings) or (key in self._lists) or (key in self._hashes)

    async def rpush(self, key: str, value: str) -> int:
        if self._is_expired(key):
            self._delete_key(key)
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].append(str(value))
        return len(self._lists[key])

    async def rpop(self, key: str) -> Optional[str]:
        if self._is_expired(key):
            return None
        if key in self._lists and self._lists[key]:
            return self._lists[key].pop()
        return None

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        if self._is_expired(key):
            return []
        if key not in self._lists:
            return []
        lst = self._lists[key]
        length = len(lst)
        s = start if start >= 0 else max(0, length + start)
        if end < 0:
            e = max(0, length + end + 1)
        else:
            e = min(length, end + 1)
        return lst[s:e]

    async def ltrim(self, key: str, start: int, end: int) -> None:
        if self._is_expired(key):
            return
        if key not in self._lists:
            return
        lst = self._lists[key]
        length = len(lst)
        s = start if start >= 0 else max(0, length + start)
        if end < 0:
            e = max(0, length + end + 1)
        else:
            e = min(length, end + 1)
        self._lists[key] = lst[s:e]

    async def llen(self, key: str) -> int:
        if self._is_expired(key):
            return 0
        return len(self._lists.get(key, []))

    async def hset(self, key: str, field: str, value: str) -> int:
        if self._is_expired(key):
            self._delete_key(key)
        if key not in self._hashes:
            self._hashes[key] = {}
        is_new = field not in self._hashes[key]
        self._hashes[key][field] = str(value)
        return 1 if is_new else 0

    async def hget(self, key: str, field: str) -> Optional[str]:
        if self._is_expired(key):
            return None
        if key in self._hashes:
            return self._hashes[key].get(field)
        return None

    async def hgetall(self, key: str) -> Dict[str, str]:
        if self._is_expired(key):
            return {}
        return self._hashes.get(key, {})

    async def hdel(self, key: str, field: str) -> int:
        if self._is_expired(key):
            return 0
        if key in self._hashes and field in self._hashes[key]:
            del self._hashes[key][field]
            return 1
        return 0

    async def expire(self, key: str, seconds: int) -> bool:
        if await self.exists(key):
            self._expires[key] = time.time() + seconds
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
