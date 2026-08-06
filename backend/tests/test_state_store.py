import asyncio
import time
import pytest
from agent.state_store import InMemoryStateStore, RedisStateStore
from config import Config

@pytest.mark.asyncio
async def test_in_memory_state_store_basic():
    store = InMemoryStateStore()
    
    # Test set/get/exists/delete
    await store.set("test_key", "test_val")
    assert await store.exists("test_key") is True
    assert await store.get("test_key") == "test_val"
    
    await store.delete("test_key")
    assert await store.exists("test_key") is False
    assert await store.get("test_key") is None

@pytest.mark.asyncio
async def test_in_memory_state_store_lists():
    store = InMemoryStateStore()
    
    # Test rpush/llen/lrange/ltrim/rpop
    await store.rpush("test_list", "item1")
    await store.rpush("test_list", "item2")
    await store.rpush("test_list", "item3")
    
    assert await store.llen("test_list") == 3
    assert await store.lrange("test_list", 0, -1) == ["item1", "item2", "item3"]
    
    await store.ltrim("test_list", 1, 2)
    assert await store.lrange("test_list", 0, -1) == ["item2", "item3"]
    
    val = await store.rpop("test_list")
    assert val == "item3"
    assert await store.lrange("test_list", 0, -1) == ["item2"]

@pytest.mark.asyncio
async def test_in_memory_state_store_hashes():
    store = InMemoryStateStore()
    
    # Test hset/hget/hgetall/hdel
    await store.hset("test_hash", "field1", "val1")
    await store.hset("test_hash", "field2", "val2")
    
    assert await store.hget("test_hash", "field1") == "val1"
    
    all_fields = await store.hgetall("test_hash")
    assert all_fields == {"field1": "val1", "field2": "val2"}
    
    deleted = await store.hdel("test_hash", "field1")
    assert deleted == 1
    assert await store.hget("test_hash", "field1") is None
    
    all_fields_after = await store.hgetall("test_hash")
    assert all_fields_after == {"field2": "val2"}

@pytest.mark.asyncio
async def test_in_memory_state_store_expiration():
    store = InMemoryStateStore()
    
    await store.set("exp_key", "exp_val")
    await store.expire("exp_key", 1)  # Expires in 1 second
    
    assert await store.get("exp_key") == "exp_val"
    
    # Wait for expiration
    await asyncio.sleep(1.1)
    assert await store.get("exp_key") is None

@pytest.mark.asyncio
async def test_in_memory_state_store_pubsub():
    store = InMemoryStateStore()
    
    listener = await store.subscribe("test_channel")
    
    async def publish_later():
        await asyncio.sleep(0.1)
        await store.publish("test_channel", "hello")
        await store.publish("test_channel", "world")
        await store.publish("test_channel", "STOP")
        
    asyncio.create_task(publish_later())
    
    messages = []
    async for msg in listener.listen():
        data = msg["data"]
        if data == "STOP":
            break
        messages.append(data)
        
    assert messages == ["hello", "world"]

