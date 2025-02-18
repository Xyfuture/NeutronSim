
from dataclasses import dataclass, field
from email.policy import default


@dataclass
class SendCommand:
    opcode:str
    group_id:list[int] = field(default_factory=list)
    length:int = -1
    dst:int = -1
    src:int = -1
    free:bool = False


@dataclass 
class ComputeCommand:
    pass


@dataclass
class ReceiveCommand:
    pass 

