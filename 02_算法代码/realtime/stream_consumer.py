# -*- coding: utf-8 -*-
"""实时流式数据接入（Phase 4.1）。

抽象基类 + 3 种实现: Kafka, MQTT, Simulator
"""
from __future__ import annotations
import json
import time
import queue
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, Iterator


class StreamConsumer(ABC):
    def __init__(self, name: str = "abstract"):
        self.name = name
        self._running = False
        self._buffer: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=10000)
        self._thread: Optional[threading.Thread] = None

    @abstractmethod
    def _connect(self) -> None: ...

    @abstractmethod
    def _consume_loop(self) -> Iterator[Dict[str, Any]]: ...

    def _run(self) -> None:
        self._connect()
        for item in self._consume_loop():
            if not self._running:
                break
            try:
                self._buffer.put(item, timeout=1)
            except queue.Full:
                pass

    def start(self) -> None:
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread: self._thread.join(timeout=2)

    def get(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try: return self._buffer.get(timeout=timeout)
        except queue.Empty: return None

    def __enter__(self): self.start(); return self
    def __exit__(self, *a): self.stop()


class SimulatorConsumer(StreamConsumer):
    def __init__(self, replay_path: Optional[str] = None, speed: float = 1.0):
        super().__init__("simulator")
        self.replay_path = replay_path
        self.speed = speed
        self._idx = 0
        self._data = []

    def _connect(self) -> None:
        if self.replay_path and Path(self.replay_path).exists():
            try: self._data = json.loads(Path(self.replay_path).read_text(encoding="utf-8"))
            except Exception: self._data = []
        if not self._data:
            self._data = [{"timestamp": time.time() + i, "type": "telemetry", "value": 1.0 + 0.01 * i} for i in range(100)]

    def _consume_loop(self) -> Iterator[Dict[str, Any]]:
        while self._running:
            if self._idx >= len(self._data): self._idx = 0
            item = self._data[self._idx]; self._idx += 1
            time.sleep(1.0 / max(self.speed, 0.01))
            yield item


class KafkaConsumerImpl(StreamConsumer):
    def __init__(self, topic: str, bootstrap_servers: str = "localhost:9092"):
        super().__init__("kafka")
        self.topic = topic; self.bootstrap_servers = bootstrap_servers; self._consumer = None

    def _connect(self) -> None:
        try:
            from kafka import KafkaConsumer
            self._consumer = KafkaConsumer(
                self.topic, bootstrap_servers=self.bootstrap_servers,
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                auto_offset_reset="latest", consumer_timeout_ms=1000)
        except ImportError: self._consumer = None

    def _consume_loop(self) -> Iterator[Dict[str, Any]]:
        if self._consumer is None:
            sim = SimulatorConsumer(); sim._connect()
            yield from sim._consume_loop(); return
        for msg in self._consumer:
            if not self._running: break
            yield msg.value


class MQTTConsumer(StreamConsumer):
    def __init__(self, topic: str, host: str = "localhost", port: int = 1883):
        super().__init__("mqtt")
        self.topic = topic; self.host = host; self.port = port
        self._client = None; self._latest = None

    def _connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client()
            self._client.on_message = lambda c, u, m: self._on_message(m)
            self._client.connect(self.host, self.port, 60)
            self._client.loop_start(); self._client.subscribe(self.topic)
        except ImportError: self._client = None

    def _on_message(self, msg) -> None:
        try: self._latest = json.loads(msg.payload.decode("utf-8"))
        except Exception: self._latest = None

    def _consume_loop(self) -> Iterator[Dict[str, Any]]:
        if self._client is None:
            sim = SimulatorConsumer(); sim._connect()
            yield from sim._consume_loop(); return
        while self._running:
            if self._latest is not None:
                yield self._latest; self._latest = None
            time.sleep(0.1)


if __name__ == "__main__":
    print("Stream: Simulator, Kafka, MQTT")
    with SimulatorConsumer() as c:
        for _ in range(3):
            x = c.get(timeout=0.5)
            if x: print("  got:", x.get("type"))
