from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Literal, TypeAlias

from Desim.Core import SimModule, SimTime
from Desim.module.FIFO import FIFO

from NeutronSim.Commands import ReceiveCommand, ReceiveBaseCommand, QuantCommand
from Desim.module.Pipeline import PipeGraph, PipeStage

from Desim.memory.Memory import DepMemory, DepMemoryPort, ChunkMemory, ChunkPacket

from NeutronSim.Config import element_bytes_dict
from deps.Desim.Desim.memory.Memory import ChunkMemoryPort

PipeArg:TypeAlias = Optional[dict[str,FIFO]]



@dataclass
class ReceiveEngineConfig:
    recv_engine_width:int = 10







class ReceiveEngine(SimModule):
    def __init__(self):
        super().__init__()


        self.recv_command_queue:Optional[FIFO] = None

        self.current_command:Optional[ReceiveBaseCommand] = None

        self.register_coroutine(self.process)

        self.external_l3_memory:Optional[ChunkMemory] = None
        self.external_reduce_memory:Optional[ChunkMemory] = None




    def load_command(self,command_list:list[ReceiveBaseCommand]):
        command_size = len(command_list)
        self.recv_command_queue = FIFO(command_size,command_size,command_list)


    def process(self):
        while True:
            if self.recv_command_queue.is_empty():
                return

            # 可以继续读取指令
            self.current_command = self.recv_command_queue.read()

            # 资源是独占的, 可以直接进行解码, 并执行相关的计算
            pipe_graph = PipeGraph()

            if isinstance(self.current_command, ReceiveCommand):
                # 还是构建一个固定的流水线吧, 通过调整里面的流水级的函数实现 各种操作

                if self.current_command.src0_loc == 'l3':
                    read_dma_0_stage = PipeStage.dynamic_create(self.l3_read_dma_helper(0))
                elif self.current_command.src0_loc == 'reduce':
                    read_dma_0_stage = PipeStage.dynamic_create(self.reduce_read_dma_helper(0))
                else:
                    assert False

                if self.current_command.src1_loc == 'l3':
                    read_dma_1_stage = PipeStage.dynamic_create(self.l3_read_dma_helper(1))
                elif self.current_command.src1_loc == 'reduce':
                    read_dma_1_stage = PipeStage.dynamic_create(self.reduce_read_dma_helper(1))
                else:
                    assert False

                read_dma_a_stage = PipeStage.dynamic_create(self.l3_read_dma_helper(2))
                act_stage = PipeStage.dynamic_create(self.act_handler)
                mul_quant_stage = PipeStage.dynamic_create(self.mul_quant_handler)
                add_stage = PipeStage.dynamic_create(self.add_handler)
                fork_stage = PipeStage.dynamic_create(self.fork_handler)

                write_dma_0_stage = PipeStage.dynamic_create(self.l3_write_dma_helper(0))
                write_dma_1_stage = PipeStage.dynamic_create(self.l3_write_dma_helper(1))

                pipe_graph.add_stage(read_dma_0_stage,'read_dma_0_stage')
                pipe_graph.add_stage(read_dma_1_stage,'read_dma_1_stage')
                pipe_graph.add_stage(read_dma_a_stage,'read_dma_a_stage')
                pipe_graph.add_stage(act_stage,'act_stage')
                pipe_graph.add_stage(mul_quant_stage,'mul_quant_stage')
                pipe_graph.add_stage(add_stage,'add_stage')
                pipe_graph.add_stage(fork_stage,'fork_stage')
                pipe_graph.add_stage(write_dma_0_stage,'write_dma_0_stage')
                pipe_graph.add_stage(write_dma_1_stage,'write_dma_1_stage')

                pipe_graph.add_edge('read_dma_0_stage','act_stage','to_act',1)
                pipe_graph.add_edge('read_dma_1_stage','mul_quant_stage','to_mul_quant_0',1)
                pipe_graph.add_edge('act_stage','mul_quant_stage','to_mul_quant_1',1)
                pipe_graph.add_edge('mul_quant_stage','add_stage','to_add_0',1)
                pipe_graph.add_edge('read_dma_a_stage','add_stage','to_add_1',1)
                pipe_graph.add_edge('add_stage','fork_stage','to_fork',1)
                pipe_graph.add_edge('fork_stage','write_dma_0_stage','to_write_dma_0',1)
                pipe_graph.add_edge('fork_stage','write_dma_1_stage','to_write_dma_1',1)

                pipe_graph.build_graph()
                pipe_graph.config_sink_stage_names(['write_dma_0_stage','write_dma_1_stage'])


            elif isinstance(self.current_command, QuantCommand):
                read_dma_0_stage = PipeStage.dynamic_create(self.l3_read_dma_helper(0))
                mul_quant_stage = PipeStage.dynamic_create(self.mul_quant_handler)
                fork_stage = PipeStage.dynamic_create(self.fork_handler)

                write_dma_0_stage = PipeStage.dynamic_create(self.l3_write_dma_helper(0))

                pipe_graph.add_stage(read_dma_0_stage,'read_dma_0_stage')
                pipe_graph.add_stage(mul_quant_stage,'mul_quant_stage')
                pipe_graph.add_stage(fork_stage,'fork_stage')
                pipe_graph.add_stage(write_dma_0_stage,'write_dma_0_stage')

                pipe_graph.add_edge('read_dma_0_stage','mul_quant_stage','to_mul_quant_0',1)
                pipe_graph.add_edge('mul_quant_stage','fork_stage','to_fork',1)
                pipe_graph.add_edge('fork_stage','write_dma_0_stage','to_write_dma_0',1)

                pipe_graph.build_graph()
                pipe_graph.config_sink_stage_names(['write_dma_0_stage'])


            pipe_graph.start_pipe_graph()

            # 等待流水线执行完毕
            pipe_graph.wait_pipe_graph_finish()

            self.current_command = None
            SimModule.wait_time(SimTime(1))



    def check_read_dma_in_use(self,read_dma_id:int)->bool:
        if read_dma_id == 0:
            return True
        elif read_dma_id == 1:
            if self.current_command.opcode in ['RECEIVE_BIN','RECEIVE_TRI']:
                return True
        elif read_dma_id == 2:
            if self.current_command.opcode == 'RECEIVE_TRI':
                return True
        else:
            raise ValueError
        return False

    def check_write_dma_in_use(self,write_dma_id:int)->bool:
        if write_dma_id == 0:
            return True
        elif write_dma_id == 1:
            if isinstance(self.current_command, ReceiveCommand):
                if self.current_command.dst1_flag:
                    return True
        else:
            raise ValueError

        return False



    def reduce_read_dma_helper(self,read_dma_id:int ):
        """
        暂时只支持 receive 指令的操作
        quant 指令暂时没法读取 reduce buffer
        """

        def reduce_read_dma_handler(input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
            # 首先决定是否启用 这个 dma
            if not self.check_read_dma_in_use(read_dma_id):
                return False

            # 构建 port 进行连接
            reduce_read_port = ChunkMemoryPort()
            reduce_read_port.config_chunk_memory(self.external_reduce_memory)



            if isinstance(self.current_command, ReceiveCommand):
                src_map = {0:self.current_command.src0,1:self.current_command.src1,2:self.current_command.asrc}
            else:
                raise ValueError

            src_addr = src_map[read_dma_id]

            # 该 DMA 会被使用，根据指令确定读取次数，并发送到指定的下一个队列中
            for i in range(self.current_command.chunk_num):
                # 读取一个chunk的数据

                enable_free = self.current_command.free0 if read_dma_id == 0 else self.current_command.free1

                chunk_data = reduce_read_port.read(src_addr+i,
                                                   self.current_command.redcount,
                                                   enable_free,
                                                   self.current_command.chunk_size,
                                                   self.current_command.batch_size,
                                                   2) # reduce 固定是 fp32
                packet = ChunkPacket(
                    chunk_data,
                    self.current_command.chunk_size,
                    self.current_command.batch_size,
                    2
                )



                # 根据指令的情况，向后面的部件转发数据
                # TODO 暂时简单操作， 直接向所有的 fifo 发送， 看看会不会有问题
                for output_fifo_name,output_fifo in output_fifo_map.items():
                    output_fifo.write(packet)

                # 开启下一次的操作

            return False

        return reduce_read_dma_handler



    def l3_read_dma_helper(self,read_dma_id):


        def l3_read_dma_handler(input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:

            if not self.check_read_dma_in_use(read_dma_id):
                return False

            l3_read_port = ChunkMemoryPort()
            l3_read_port.config_chunk_memory(self.external_l3_memory)

            if isinstance(self.current_command, ReceiveCommand):
                src_map = {0:self.current_command.src0,1:self.current_command.src1,2:self.current_command.asrc}
            elif isinstance(self.current_command, QuantCommand):
                src_map = {0:self.current_command.src}
            else:
                raise ValueError

            src_addr = src_map[read_dma_id]

            for i in range(self.current_command.chunk_num):
                if isinstance(self.current_command, ReceiveCommand):
                    enable_free = {0:self.current_command.free0,1:self.current_command.free1,3:self.current_command.afree}[read_dma_id]
                    element_bytes = element_bytes_dict[{0:self.current_command.src0_dtype,1:self.current_command.src1_dtype,3:self.current_command.adtype}[read_dma_id]]

                    chunk_data = l3_read_port.read(src_addr+i,
                                                   1,
                                                   enable_free,
                                                   self.current_command.chunk_size,
                                                   self.current_command.batch_size,
                                                   element_bytes
                                                   )

                    packet = ChunkPacket(
                        chunk_data,
                        self.current_command.chunk_size,
                        self.current_command.batch_size,
                        element_bytes
                    )


                elif isinstance(self.current_command, QuantCommand):
                    enable_free = self.current_command.free
                    element_bytes = element_bytes_dict[self.current_command.src_dtype]
                    chunk_data = l3_read_port.read(src_addr+i,
                                                   1,
                                                   enable_free,
                                                   self.current_command.chunk_size,
                                                   self.current_command.batch_size,
                                                   element_bytes
                                                   )
                    packet = ChunkPacket(
                        chunk_data,
                        self.current_command.chunk_size,
                        self.current_command.batch_size,
                        element_bytes
                    )

                else:
                    raise ValueError

                for fifo_name,fifo in output_fifo_map.items():
                    fifo.write(packet)

            return False


        return l3_read_dma_handler

    def l3_write_dma_helper(self,write_dma_id):

        def l3_write_dma_handler(input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
            if not self.check_write_dma_in_use(write_dma_id):
                return False

            l3_write_port = ChunkMemoryPort()
            l3_write_port.config_chunk_memory(self.external_l3_memory)

            input_fifo = input_fifo_map[f'to_write_dma_{write_dma_id}']

            write_addr = 0

            if isinstance(self.current_command, ReceiveCommand):
                if write_dma_id == 0 :
                    write_addr = self.current_command.dst0
                elif write_dma_id == 1 :
                    write_addr = self.current_command.dst1
            elif isinstance(self.current_command, QuantCommand):
                write_addr = self.current_command.dstq
            else:
                raise ValueError


            for i in range(self.current_command.chunk_num):
                chunk_packet:ChunkPacket = input_fifo.read()


                l3_write_port.write(write_addr+i,
                                    chunk_packet.payload,
                                    True,
                                    chunk_packet.num_elements,
                                    chunk_packet.batch_size,
                                    chunk_packet.element_bytes)


            return False




    def act_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:

        input_fifo = input_fifo_map['to_act']
        for i in range(self.current_command.chunk_num):
            packet = input_fifo.read()

            if isinstance(self.current_command, ReceiveCommand):
                if self.current_command.act:
                    SimModule.wait_time(SimTime(100)) # TODO 修正为正确的时间
            else:
                raise ValueError


            for fifo_name,fifo in output_fifo_map.items():
                fifo.write(packet)

        return False

    def mul_quant_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:

        input_from_act = input_fifo_map['to_mul_quant_0']
        input_from_dma = input_fifo_map['to_mul_quant_1']

        for i in range(self.current_command.chunk_num):
            if isinstance(self.current_command, ReceiveCommand):
                if self.current_command.mul:
                    packet_from_act = input_from_act.read()
                    packet_from_dma = input_from_dma.read()

                    packet = packet_from_act
                    SimModule.wait_time(SimTime(100))  # TODO 修正为正确的时间

                else:
                    packet_from_act = input_from_act.read()
                    packet = packet_from_act

            elif isinstance(self.current_command, QuantCommand):
                packet_from_act:ChunkPacket = input_from_act.read()
                packet = ChunkPacket(
                    packet_from_act.payload,
                    packet_from_act.num_elements,
                    packet_from_act.batch_size,
                    1, # 量化之后时int8了
                )
            else:
                raise ValueError

            for fifo_name,fifo in output_fifo_map.items():
                fifo.write(packet)


        return False

    def add_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:

        input_from_mul_quant = input_fifo_map['to_add_1']
        input_from_dma = input_fifo_map['to_add_2']
        for i in range(self.current_command.chunk_num):
            if isinstance(self.current_command, ReceiveCommand):
                if self.current_command.add:
                    packet_from_mul_quant = input_from_mul_quant.read()
                    packet_from_dma = input_from_dma.read()
                    packet = packet_from_mul_quant
                else:
                    packet_from_mul_quant = input_from_mul_quant.read()
                    packet = packet_from_mul_quant
            elif isinstance(self.current_command, QuantCommand):
                # 直接转发
                packet = input_from_mul_quant.read()

            else:
                raise ValueError

            for fifo_name,fifo in output_fifo_map.items():
                fifo.write(packet)

        return False


    def fork_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:

        input_fifo = input_fifo_map['to_fork']

        output_fifo_0 = output_fifo_map['to_write_dma_0']
        output_fifo_1 = output_fifo_map['to_write_dma_1']

        for i in range(self.current_command.chunk_num):
            packet:ChunkPacket = input_fifo.read()

            if isinstance(self.current_command, ReceiveCommand):
                # 不是很懂， 这里还可以改变数据类型

                packet_0 = ChunkPacket(
                    packet.payload,
                    packet.num_elements,
                    packet.batch_size,
                    element_bytes_dict[self.current_command.dst0_type]
                )

                if self.current_command.dst1_flag:
                    packet_1 = ChunkPacket(
                        packet.payload,
                        packet.num_elements,
                        packet.batch_size,
                        element_bytes_dict[self.current_command.dst1_type]
                    )

                    output_fifo_1.write(packet_1)

                output_fifo_0.write(packet_0)

            elif isinstance(self.current_command, QuantCommand):
                output_fifo_0.write(packet)
            else:
                raise ValueError

        return False

    def config_connection(self,l3_memory:ChunkMemory,reduce_memory:ChunkMemory):
        self.external_reduce_memory = reduce_memory
        self.external_l3_memory = l3_memory










