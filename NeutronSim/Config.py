from dataclasses import dataclass


@dataclass
class LinkConfig:
    bandwidth: int = 16 # Byte/ns
    link_latency:int = 100 # ns


@dataclass
class MemoryConfig:
    block_size:int = 128 # byte



@dataclass
class BasicChunkConfig:
    """
    仅配置 num elements 和 batch size
    这两个值应该贯穿整个执行的过程
    数据格式不约束，由具体的指令来指定
    """

    num_elements:int = 128
    batch_size:int = 16



element_bytes_dict = {
    'fp16': 2,
    'bf16': 2,
    'fp32': 4,
    'int8': 1,
}
