from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import json


@dataclass
class _OpenEvent:
    name: str
    ts_us: float


class PerfettoTracer:
    """
    PerfettoTracer emits the Chrome Trace Event JSON format, which Perfetto can import.

    变更点:
    - 对外 API 的时间参数一律以 "cycles" 为单位 (start_ts, end_ts, dur 均视为 cycles).
    - 通过 ns_per_cycle 指定 "1 个周期 = ? ns", 内部再换算为微秒 (us) 写入 JSON.
    - 默认显示单位改为 ns (displayTimeUnit="ns"), 更符合硬件仿真直觉.

    典型用法:
      tracer = PerfettoTracer(process_name="MySim", ns_per_cycle=0.5)  # 1 cycle = 0.5 ns
      alu = tracer.register_unit("ALU")
      tracer.complete_event(alu, "issue", start_cycles, end_ts=end_cycles)
      tracer.start_event(alu, "execute", start_cycles)
      tracer.end_event(alu, end_cycles)
      tracer.save("trace.json")  # ui.perfetto.dev 打开

    说明:
    - 传入的 cycles 会按: cycles * ns_per_cycle / 1000.0 -> 微秒(us) 存入 JSON.
    """

    def __init__(
        self,
        process_name: str = "Simulator",
        ns_per_cycle: float = 1.0,
        pid: int = 1,
    ) -> None:
        """
        Args:
            process_name: 进程名 (所有轨道共享同一 pid).
            ns_per_cycle: 1 个周期等于多少纳秒 (可为浮点数, 如 0.5 表示 1 cycle = 0.5 ns).
            pid: 进程 ID.
        """
        self.process_name = process_name
        self.ns_per_cycle = float(ns_per_cycle)
        # 内部换算: cycle -> us
        # us = cycles * ns_per_cycle / 1000
        self._cycle_to_us = self.ns_per_cycle / 1000.0
        self.pid = int(pid)

        self._next_tid = 1000
        self._unit_to_tid: Dict[str, int] = {}
        self._open_events: Dict[int, List[_OpenEvent]] = {}
        self._events: List[Dict[str, Any]] = []

        # 进程元数据
        self._events.append({
            "ph": "M",
            "pid": self.pid,
            "tid": 0,
            "name": "process_name",
            "args": {"name": self.process_name},
        })

    # --------- Time helpers ---------

    def _cycles_to_us(self, cycles: float) -> float:
        """把 cycles 换算为微秒(us)."""
        return float(cycles) * self._cycle_to_us

    # --------- Track / Unit registration ---------

    def register_unit(self, unit_name: str) -> int:
        if unit_name in self._unit_to_tid:
            return self._unit_to_tid[unit_name]

        tid = self._next_tid
        self._next_tid += 1
        self._unit_to_tid[unit_name] = tid
        self._open_events[tid] = []

        # 线程 (轨道) 元数据
        self._events.append({
            "ph": "M",
            "pid": self.pid,
            "tid": tid,
            "name": "thread_name",
            "args": {"name": unit_name},
        })
        return tid

    # --------- Event recording APIs ---------

    def start_event(self, tid_or_unit: int | str, name: str, ts_cycles: float) -> None:
        """
        开始一个带作用域的事件 (B). ts_cycles 以 cycles 为单位.
        必须与 end_event() 匹配 (同一 tid 栈式配对).
        """
        tid = self._resolve_tid(tid_or_unit)
        ts_us = self._cycles_to_us(ts_cycles)
        self._events.append({
            "ph": "B",
            "pid": self.pid,
            "tid": tid,
            "ts": ts_us,
            "name": name,
        })
        self._open_events[tid].append(_OpenEvent(name=name, ts_us=ts_us))

    def end_event(self, tid_or_unit: int | str, ts_cycles: float, name: Optional[str] = None) -> None:
        """
        结束最近打开的事件(E) ts_cycles 以 cycles 为单位
        如果提供 name 参数, 会检查和栈顶事件的 name 是否一致
        """
        tid = self._resolve_tid(tid_or_unit)
        ts_us = self._cycles_to_us(ts_cycles)
        if not self._open_events[tid]:
            raise RuntimeError(f"No open events to end on tid {tid}")

        top_event = self._open_events[tid][-1]
        if name is not None and top_event.name != name:
            raise RuntimeError(
                f"End event name mismatch: expected '{top_event.name}', got '{name}'"
            )

        self._events.append({
            "ph": "E",
            "pid": self.pid,
            "tid": tid,
            "ts": ts_us,
        })
        self._open_events[tid].pop()

    def complete_event(
        self,
        tid_or_unit: int | str,
        name: str,
        start_ts: float,
        end_ts: Optional[float] = None,
        dur: Optional[float] = None,
    ) -> None:
        """
        插入一个完整事件 (X). 所有时间参数均为 cycles.
        传 (start_ts + end_ts) 或 (start_ts + dur) 二选一.
        """
        tid = self._resolve_tid(tid_or_unit)
        start_us = self._cycles_to_us(start_ts)

        if (end_ts is None) == (dur is None):
            raise ValueError("Provide exactly one of end_ts or dur")

        if dur is None:
            dur_us = self._cycles_to_us(end_ts) - start_us  # type: ignore[arg-type]
        else:
            dur_us = self._cycles_to_us(dur)

        if dur_us < 0:
            raise ValueError("Duration is negative; check start/end timestamps.")

        self._events.append({
            "ph": "X",
            "pid": self.pid,
            "tid": tid,
            "ts": start_us,
            "dur": dur_us,
            "name": name,
        })

    # --------- Export ---------

    def save(self, path: str, display_time_unit: str = "ns") -> None:
        """
        写出 Chrome Trace Event JSON.
        display_time_unit: "ns" | "us" | "ms" | "s"
        仅影响 UI 展示, 不影响数据本身 (我们内部仍用 us 存 ts/dur).
        """
        # 允许存在未闭合的 B 事件; 一般是生产端 Bug, Perfetto 仍能加载.
        doc = {
            "traceEvents": self._events,
            "displayTimeUnit": display_time_unit,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    # --------- Internals ---------

    def _resolve_tid(self, tid_or_unit: int | str) -> int:
        if isinstance(tid_or_unit, int):
            return tid_or_unit
        if tid_or_unit not in self._unit_to_tid:
            raise KeyError(f"Unit '{tid_or_unit}' has not been registered. Call register_unit() first.")
        return self._unit_to_tid[tid_or_unit]