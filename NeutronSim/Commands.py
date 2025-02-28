
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SendCommand:
    opcode:str = 'SEND'
    group_id:list[int] = field(default_factory=list)

    chunk_size:int = -1
    batch_size:int = -1
    chunk_num:int = -1

    dtype:Literal['fp16','bf16','fp32'] = ''

    dst:int = -1
    src:int = -1
    free:bool = False


@dataclass 
class ComputeCommand:
    opcode:str

    group_id:list[int] = field(default_factory=list)

    batch_size:int = -1

    dst:int = -1  # L2 memory上的地址
    dst_chunk_size:int = -1
    dst_chunk_num:int = -1

    dst_free:bool = False

    reddst:int = -1
    redid:int = -1

    src:int = -1
    src_chunk_size:int = -1
    src_chunk_num:int = -1
    src_dtype:Literal['fp16','bf16','fp32'] = ''
    src_free:bool = False

    first_acc:bool = False
    last_acc:bool = False




@dataclass
class ReceiveBaseCommand:
    opcode:str

    chunk_size:int = -1
    batch_size:int = -1
    chunk_num:int = -1


@dataclass
class ReceiveCommand(ReceiveBaseCommand):
    opcode:Literal['RECEIVE_MONO','RECEIVE_BIN','RECEIVE_TRI'] = 'RECEIVE'
    bdcst:list[int]  = field(default_factory=list)

    # Chunk的信息提到了Base中

    dst0:int = -1
    dst0_type:Literal['fp16','bf16','fp32'] = ''

    dst1:int = -1
    dst1_type:Literal['fp16','bf16','fp32'] = ''
    dst1_flag:bool = False

    src0:int = -1
    src0_dtype:Literal['fp16','bf16','fp32'] = ''
    free0:bool = False
    src0_loc:Literal['l3','reduce'] = ''

    src1:int = -1
    src1_dtype:Literal['fp16','bf16','fp32'] = ''
    free1:bool = False
    src1_loc:Literal['l3','reduce'] = ''

    redcount:int = 0

    act:Literal[0,1,2,3,4,5,6] = 0
    mul:bool  = False

    add:bool = False
    asrc:int = -1
    adtype:Literal['fp16','bf16','fp32'] = ''
    afree:bool = False

@dataclass
class QuantCommand(ReceiveBaseCommand):
    opcode:str = 'QUANT'

    bdcst:list[int] = field(default_factory=list)





    dstq:int = -1
    dstzs:int = -1

    src:int = -1
    src_dtype:Literal['fp16','bf16','fp32'] = ''
    free:bool = False

    ngroup:Literal[0,1,2,3] = -1




