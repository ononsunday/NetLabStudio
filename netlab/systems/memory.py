"""Cache organization, page replacement, and a visible stack/heap memory arena."""
from __future__ import annotations

from collections import deque


class Cache:
    def __init__(self, lines: int = 8, block_size: int = 4, ways: int = 1, policy: str = "LRU",
                 hit_cycles: int = 1, miss_cycles: int = 100):
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (lines, block_size, ways, hit_cycles, miss_cycles)):
            raise ValueError("Cache 参数必须为整数")
        if not 1 <= lines <= 65536 or not 1 <= block_size <= 65536 or not 1 <= ways <= lines or lines % ways:
            raise ValueError("Cache 行数须可被组相联路数整除，参数应为正数")
        if hit_cycles <= 0 or miss_cycles < hit_cycles:
            raise ValueError("缺失耗时须大于或等于命中耗时，耗时须为正数")
        policy = policy.upper()
        if policy not in ("FIFO", "LRU"):
            raise ValueError("替换策略应为 FIFO 或 LRU")
        self.lines, self.block_size, self.ways, self.policy = lines, block_size, ways, policy
        self.hit_cycles, self.miss_cycles = hit_cycles, miss_cycles
        self.reset()

    def reset(self):
        self.sets = [[] for _ in range(self.lines // self.ways)]
        self.clock, self.hits, self.misses, self.cycles, self.writebacks = 0, 0, 0, 0, 0
        self.trace = []

    def access(self, address: int, write: bool = False) -> dict:
        if not isinstance(address, int) or isinstance(address, bool) or not 0 <= address < (1 << 64):
            raise ValueError("地址必须为 0 到 2^64-1 的整数")
        self.clock += 1
        block = address // self.block_size
        set_index, tag = block % len(self.sets), block // len(self.sets)
        bucket = self.sets[set_index]
        entry = next((line for line in bucket if line["tag"] == tag), None)
        hit, evicted = entry is not None, None
        if hit:
            self.hits += 1
            entry["used"] = self.clock
            self.cycles += self.hit_cycles
        else:
            self.misses += 1
            self.cycles += self.miss_cycles
            if len(bucket) == self.ways:
                key = "used" if self.policy == "LRU" else "loaded"
                victim = min(bucket, key=lambda line: line[key])
                bucket.remove(victim)
                evicted = dict(victim)
                if victim["dirty"]:
                    self.writebacks += 1
            entry = {"block": block, "tag": tag, "loaded": self.clock, "used": self.clock, "dirty": False}
            bucket.append(entry)
        if write:
            entry["dirty"] = True
        result = {"address": address, "block": block, "offset": address % self.block_size,
                  "set": set_index, "tag": tag, "hit": hit, "evicted": evicted,
                  "write": bool(write), "cycles": self.cycles,
                  "sets": [[dict(line) for line in bucket] for bucket in self.sets],
                  "explanation": f"块 {block} 映射到组 {set_index}，" + ("Cache 命中" if hit else "Cache 缺失，需要读取主存"),
                  "teaching_model": True}
        self.trace.append(result)
        return result

    def run(self, addresses: list[int]) -> dict:
        if len(addresses) > 100_000:
            raise ValueError("访问序列过长")
        results = [self.access(address) for address in addresses]
        accesses = self.hits + self.misses
        return {"trace": results, "hits": self.hits, "misses": self.misses,
                "hit_rate": self.hits / accesses if accesses else 0,
                "cycles": self.cycles, "uncached_cycles": accesses * self.miss_cycles,
                "average_cycles": self.cycles / accesses if accesses else 0,
                "writebacks": self.writebacks, "policy": self.policy,
                "organization": "direct" if self.ways == 1 else "fully_associative" if len(self.sets) == 1 else "set_associative",
                "teaching_model": True}


def page_replacement(references: list[int], frames: int = 3, policy: str = "LRU") -> dict:
    if not isinstance(frames, int) or not 1 <= frames <= 4096:
        raise ValueError("页框数须为 1 到 4096")
    if len(references) > 100_000 or any(not isinstance(page, int) or isinstance(page, bool) or page < 0 for page in references):
        raise ValueError("页号须为非负整数，访问序列最多 100000 项")
    policy = policy.upper()
    if policy not in ("LRU", "FIFO", "OPT"):
        raise ValueError("页替换支持 FIFO、LRU 和 OPT")
    residents, ages, trace, faults = [], {}, [], 0
    for index, page in enumerate(references):
        hit, evicted = page in residents, None
        if not hit:
            faults += 1
            if len(residents) == frames:
                if policy == "OPT":
                    future = references[index + 1:]
                    evicted = max(residents, key=lambda value: future.index(value) if value in future else float("inf"))
                else:
                    evicted = min(residents, key=lambda value: ages[value])
                residents[residents.index(evicted)] = page
                del ages[evicted]
            else:
                residents.append(page)
            ages[page] = index
        if policy == "LRU":
            ages[page] = index
        trace.append({"index": index, "page": page, "hit": hit, "evicted": evicted,
                      "frames": list(residents), "faults": faults,
                      "explanation": "页已在内存" if hit else "缺页，分配页框" if evicted is None else f"缺页，用页 {page} 替换页 {evicted}"})
    return {"policy": policy, "frames_count": frames, "trace": trace, "faults": faults,
            "hits": len(references) - faults, "fault_rate": faults / len(references) if references else 0,
            "teaching_model": True, "limitations": "OPT 需要未来的完整访问序列，只用于比较；未模拟磁盘实际时延。"}


class MemoryArena:
    """A byte-addressed heap growing up, and stack growing down, with collision checks."""
    def __init__(self, size: int = 256):
        if not isinstance(size, int) or not 1 <= size <= 1_048_576:
            raise ValueError("内存大小须为 1 到 1048576 字节")
        self.size = size
        self.memory = bytearray(size)
        self.stack_pointer = size
        self.allocations = {}

    def malloc(self, length: int) -> int:
        if not isinstance(length, int) or length <= 0:
            raise ValueError("分配长度须为正整数")
        cursor = 0
        for address, count in sorted(self.allocations.items()):
            if address - cursor >= length:
                break
            cursor = address + count
        if cursor + length > self.stack_pointer:
            raise ValueError("堆栈空间不足")
        self.allocations[cursor] = length
        return cursor

    def free(self, address: int) -> None:
        if address not in self.allocations:
            raise ValueError("无效的堆分配地址")
        del self.allocations[address]

    def push(self, value: int):
        if not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError("栈元素须为一个字节")
        next_pointer = self.stack_pointer - 1
        heap_end = max((address + count for address, count in self.allocations.items()), default=0)
        if next_pointer < heap_end:
            raise ValueError("堆栈冲突")
        self.stack_pointer = next_pointer
        self.memory[next_pointer] = value
        return next_pointer

    def pop(self) -> int:
        if self.stack_pointer == self.size:
            raise ValueError("栈为空")
        value = self.memory[self.stack_pointer]
        self.stack_pointer += 1
        return value

    def snapshot(self) -> dict:
        return {"size": self.size, "stack_pointer": self.stack_pointer,
                "allocations": dict(self.allocations), "memory": list(self.memory), "teaching_model": True}
