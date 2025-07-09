from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Shape:
    batch_size:int = -1
    shape:list[int] = field(default= list)

    chunk_num:int = -1
    chunk_dim:int = -1

    dtype:Literal['fp16','bf16','fp32'] = ''

    @property
    def chunk_size(self):
        return  0



@dataclass
class CommandBase:
    opcode:str

    prev_list:list[CommandBase]
    next_list:list[CommandBase]





@dataclass
class SendCommand(CommandBase):

    # 地址协调的问题
    src:int = -1
    dst:int = -1
    free:bool = False

    dshape:Shape = field(default_factory=Shape)
    

@dataclass
class ReceiveCommand(CommandBase):
    pass




@dataclass
class ComputeCommand(CommandBase):
    pass