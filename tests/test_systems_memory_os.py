import pytest

from netlab.systems import Cache, MemoryArena, network_pipeline, page_replacement, schedule_processes


def test_cache_direct_mapping_collision_and_block_offset():
    cache = Cache(lines=2, block_size=4)
    assert not cache.access(0)["hit"]
    assert cache.access(3)["hit"]
    assert not cache.access(8)["hit"]
    assert not cache.access(0)["hit"]


def test_fifo_lru_difference_and_dirty_writeback():
    lru, fifo = Cache(lines=2, ways=2, block_size=1, policy="LRU"), Cache(lines=2, ways=2, block_size=1, policy="FIFO")
    for cache in (lru, fifo):
        cache.access(0, write=True)
        cache.access(1)
        cache.access(0)
    assert lru.access(2)["evicted"]["block"] == 1
    assert fifo.access(2)["evicted"]["block"] == 0
    assert fifo.writebacks == 1


def test_cache_run_expected_latency_and_invalid_organization():
    data = Cache(lines=2, block_size=4, ways=2, hit_cycles=2, miss_cycles=20).run([0, 1, 4, 5])
    assert data["hits"] == 2 and data["misses"] == 2
    assert data["cycles"] == 44 and data["uncached_cycles"] == 80
    with pytest.raises(ValueError):
        Cache(lines=3, ways=2)
    with pytest.raises(ValueError):
        Cache().access(-1)


def test_heap_reuses_freed_gap_and_stack_collision():
    arena = MemoryArena(16)
    first, second = arena.malloc(4), arena.malloc(4)
    assert (first, second) == (0, 4)
    arena.free(first)
    assert arena.malloc(2) == 0
    arena.push(10)
    arena.push(20)
    assert arena.pop() == 20 and arena.pop() == 10
    with pytest.raises(ValueError):
        arena.pop()
    with pytest.raises(ValueError):
        arena.malloc(20)


def test_page_replacement_fifo_lru_and_opt_expected_faults():
    refs = [1, 2, 3, 1, 4, 2, 5, 1]
    fifo = page_replacement(refs, 3, "FIFO")
    lru = page_replacement(refs, 3, "LRU")
    opt = page_replacement(refs, 3, "OPT")
    assert fifo["faults"] == 6
    assert lru["faults"] == 7
    assert opt["faults"] == 5
    with pytest.raises(ValueError):
        page_replacement([-1])


def test_round_robin_arrivals_before_requeue():
    data = schedule_processes([{"pid": "P1", "arrival": 0, "burst": 5}, {"pid": "P2", "arrival": 1, "burst": 3}], "RR", 2)
    assert [row["pid"] for row in data["timeline"]] == ["P1", "P2", "P1", "P2", "P1"]
    assert [(p["pid"], p["finish"], p["waiting"]) for p in data["processes"]] == [("P1", 8, 3), ("P2", 7, 3)]
    assert data["cpu_utilization"] == 1


def test_io_blocks_wakes_and_idle():
    data = schedule_processes([{"pid": "P1", "arrival": 1, "cpu_bursts": [2, 1], "io_bursts": [3]}], "FCFS")
    assert data["total_time"] == 7
    assert data["timeline"] == [{"pid": "IDLE", "start": 0, "end": 1},
                                {"pid": "P1", "start": 1, "end": 3, "cpu_burst": 0},
                                {"pid": "IDLE", "start": 3, "end": 6},
                                {"pid": "P1", "start": 6, "end": 7, "cpu_burst": 1}]
    assert "blocked" in [e["status"] for e in data["events"]]
    assert data["processes"][0]["waiting"] == 0


def test_sjf_priority_and_invalid_process_input():
    jobs = [{"pid": "long", "burst": 5, "priority": 0}, {"pid": "short", "burst": 2, "priority": 3}]
    assert schedule_processes(jobs, "SJF")["timeline"][0]["pid"] == "short"
    assert schedule_processes(jobs, "PRIORITY")["timeline"][0]["pid"] == "long"
    with pytest.raises(ValueError):
        schedule_processes([{"pid": "P", "burst": -1}])
    with pytest.raises(ValueError):
        schedule_processes([{"pid": "P"}, {"pid": "P"}])


def test_pipeline_send_backpressure_and_bandwidth_scaling():
    data = bytes(range(256)) * 32
    slow = network_pipeline(data, packet_size=256, buffer_bytes=256, bandwidth_mbps=1)
    fast = network_pipeline(data, packet_size=256, buffer_bytes=8192, bandwidth_mbps=100)
    assert slow["delivered_bytes"] == fast["delivered_bytes"] == len(data)
    assert slow["buffer_wait_ms"] > 0
    assert slow["duration_ms"] > fast["duration_ms"]
    assert slow["throughput_mbps"] <= 1
    assert slow["peak_buffer_bytes"] <= 256
    assert slow["events"] == sorted(slow["events"], key=lambda e: (e["time"], int(e["id"].split("-")[-1])))


def test_pipeline_receive_overload_drops_and_batching_changes_cpu_cost():
    data = b"x" * 4096
    overloaded = network_pipeline(data, packet_size=64, buffer_bytes=64, bandwidth_mbps=10000, cpu_mhz=.1, direction="receive")
    assert overloaded["dropped_packets"] > 0 and overloaded["delivered_bytes"] < len(data)
    interrupt = network_pipeline(data, packet_size=64, processing="interrupt")
    polling = network_pipeline(data, packet_size=64, processing="polling")
    assert polling["cpu_cycles"] < interrupt["cpu_cycles"]


@pytest.mark.parametrize("kwargs", [{"packet_size": 0}, {"buffer_bytes": 1}, {"bandwidth_mbps": 0},
                                    {"cpu_mhz": float("nan")}, {"processing": "fake"}])
def test_pipeline_validation(kwargs):
    with pytest.raises(ValueError):
        network_pipeline("hello", **kwargs)
