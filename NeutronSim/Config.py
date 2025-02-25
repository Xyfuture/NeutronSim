from dataclasses import dataclass


@dataclass
class LinkConfig:
    bandwidth: int = 16 # Byte/ns
    link_latency:int = 100 # ns


@dataclass
class MemoryConfig:
    block_size:int = 128 # byte




element_bytes_dict = {
    'fp16': 2,
    'bf16': 2,
    'fp32': 4,
    'int8': 1,
}
