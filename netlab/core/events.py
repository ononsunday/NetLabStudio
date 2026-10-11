"""Serializable discrete-event scheduling shared by network and system models."""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import asdict, dataclass, field


@dataclass(order=True)
class Event:
    time: float
    order: int
    kind: str = field(compare=False)
    source: str = field(default="", compare=False)
    target: str = field(default="", compare=False)
    packet_id: str | None = field(default=None, compare=False)
    explanation: str = field(default="", compare=False)
    data: dict = field(default_factory=dict, compare=False)
    status: str = field(default="queued", compare=False)

    @property
    def id(self) -> str:
        return f"event-{self.order:08d}"

    def to_dict(self) -> dict:
        result = asdict(self)
        result["id"] = self.id
        return result


class EventEngine:
    def __init__(self, seed: int = 1):
        self.seed = seed
        self.rng = random.Random(seed)
        self.time = 0.0
        self.counter = 0
        self.queue: list[Event] = []
        self.history: list[dict] = []

    def schedule(self, delay: float, kind: str, source: str = "", target: str = "",
                 packet_id: str | None = None, explanation: str = "", data: dict | None = None) -> Event:
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("事件不能安排到过去。")
        self.counter += 1
        event = Event(self.time + delay, self.counter, kind, source, target,
                      packet_id, explanation, data or {})
        heapq.heappush(self.queue, event)
        return event

    def pop(self) -> Event | None:
        if not self.queue:
            return None
        event = heapq.heappop(self.queue)
        self.time = event.time
        event.status = "processed"
        return event

    def record(self, event: Event) -> dict:
        row = event.to_dict()
        self.history.append(row)
        return row

    def snapshot(self) -> dict:
        return {"seed": self.seed, "time": self.time, "counter": self.counter,
                "queue": [asdict(event) for event in self.queue], "history": self.history.copy(),
                "rng_state": self.rng.getstate()}

    @classmethod
    def restore(cls, data: dict) -> "EventEngine":
        engine = cls(data["seed"])
        engine.time, engine.counter = data["time"], data["counter"]
        engine.queue = [Event(**row) for row in data["queue"]]
        heapq.heapify(engine.queue)
        engine.history = data["history"].copy()
        def tuples(value):
            return tuple(tuples(item) for item in value) if isinstance(value, (list, tuple)) else value
        engine.rng.setstate(tuples(data["rng_state"]))
        return engine

