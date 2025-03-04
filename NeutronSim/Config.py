from dataclasses import dataclass


@dataclass
class LinkConfig:
    bandwidth: int = 16 # Byte/ns
    link_latency:int = 100 # ns


@dataclass
class MemoryConfig:
    block_size:int = 128 # byte
    bandwidth:int = 16 # Byte/ns


@dataclass
class AtomConfig:
    # TODO 目前 这个貌似会有点问题
    single_batch_OPS:int = 8192
    max_batch_size:int = 16


element_bytes_dict = {
    'fp16': 2,
    'bf16': 2,
    'fp32': 4,
    'int8': 1,
}
