from dataclasses import dataclass


@dataclass
class LinkConfig:
    bandwidth: int = 16 # Byte/ns
    link_latency:int = 100 # ns


@dataclass
class MemoryConfig:
    block_size:int = 128 # byte

