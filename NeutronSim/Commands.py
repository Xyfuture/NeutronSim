from __future__ import  annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Literal

from Desim.module.FIFO import FIFO


dtype_to_bytes = {
    'fp16':2,
    'bf16':2,
    'int8':1
}


@dataclass
class MemoryShape:

    shape:list[int] = field(default_factory= list)

    chunk_dim:int = -1
    elements_per_chunk_dim:int = 0

    dtype:Literal['fp16','bf16','int8'] = ''


    @property
    def element_per_chunk(self):
        total_elements = math.prod(self.shape)
        elements = self.elements_per_chunk_dim * (total_elements // self.shape[self.chunk_dim])

        return elements



    @property
    def memory_size_per_chunk(self):
        return dtype_to_bytes[self.dtype] * self.element_per_chunk


    @property
    def num_chunks(self):
        return self.shape[self.chunk_dim] // self.elements_per_chunk_dim


@dataclass
class CommandBase:

    input_nodes:dict[CommandBase,FIFO]= field(default_factory=dict)
    output_nodes:dict[CommandBase,FIFO] = field(default_factory=dict) # 自动维护

    prev_nodes:dict[CommandBase,None] = field(default_factory=dict)
    next_nodes:dict[CommandBase,None] = field(default_factory=dict)


    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

@dataclass(eq=False)
class RootCommand(CommandBase):
    pass



@dataclass(eq=False)
class SendCommand (CommandBase):
    group_id:list[int] = field(default_factory=list)

    dshape:MemoryShape = field(default_factory=MemoryShape)






@dataclass(eq=False)
class ComputeCommand(CommandBase):
    group_id:list[int] = field(default_factory=list)

    src_dshape:MemoryShape = field(default_factory=MemoryShape)
    dst_dshape:MemoryShape = field(default_factory=MemoryShape)

    first_acc:bool = False
    last_acc:bool = False




@dataclass(eq=False)
class ReceiveCommand(CommandBase):



    dshape:MemoryShape = field(default_factory=MemoryShape)




class CommandGraph:

    def __init__(self):
        self.root_command:Optional[RootCommand] = None

        self.command_list:dict[CommandBase,None] = {}

    def gen_dep_map(self)->dict[CommandBase,int]:

        dep_map:dict[CommandBase,int] = {}

        for command in self.command_list.keys():
            dep_map[command] = len(command.prev_nodes)

        return dep_map


    def add_command(self,command:CommandBase):

        # 比较奇怪的用法
        self.command_list[command] = None


    def build_graph(self):
        # 自动补全 graph 的连接关系
        # 默认只配置 input nodes , 在这个函数中自动配置输出关系

        for command in self.command_list.keys():
            for cur_producer_command in command.input_nodes.keys():
                if cur_producer_command.output_nodes is None:
                    cur_producer_command.output_nodes = {}
                cur_producer_command.output_nodes[command] = command.input_nodes[cur_producer_command]

        # 自动补全input/output nodes中的 prev 和 next 关系
        for command in self.command_list.keys():
            for cur_producer_command in command.input_nodes.keys():
                # cur_producer_command.next_nodes[command] = None
                command.prev_nodes[cur_producer_command] = None

            for cur_consumer_command in command.output_nodes.keys():
                # cur_consumer_command.prev_nodes[command] = None
                command.next_nodes[cur_consumer_command] = None