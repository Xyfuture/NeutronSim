from dataclasses import dataclass
from typing import Optional, Literal, TypeAlias

from Desim.Core import SimModule, SimTime
from Desim.module.FIFO import FIFO

from NeutronSim.Commands import ReceiveCommand, ReceiveBaseCommand, QuantCommand
from Desim.module.Pipeline import PipeGraph, PipeStage

from Desim.memory.Memory import DepMemory, DepMemoryPort

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

        self.l3_memory:Optional[DepMemory] = None
        self.reduce_memory:Optional[DepMemory] = None


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
                    read_dma_0_stage = PipeStage(self.l3_read_dma_helper())
                elif self.current_command.src0_loc == 'reduce':
                    read_dma_0_stage = PipeStage(self.reduce_read_dma_helper())
                else:
                    assert False

                if self.current_command.src1_loc == 'l3':
                    read_dma_1_stage = PipeStage(self.l3_read_dma_helper())
                elif self.current_command.src1_loc == 'reduce':
                    read_dma_1_stage = PipeStage(self.reduce_read_dma_helper())
                else:
                    assert False

                read_dma_a_stage = PipeStage(self.l3_read_dma_helper())
                act_stage = PipeStage(self.act_handler)
                mul_quant_stage = PipeStage(self.mul_quant_handler)
                add_stage = PipeStage(self.add_handler)
                fork_stage = PipeStage(self.fork_handler)

                write_dma_0_stage = PipeStage(self.l3_write_dma_helper())
                write_dma_1_stage = PipeStage(self.l3_write_dma_helper())

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
                pass

            # 等待流水线执行完毕
            pipe_graph.wait_pipe_graph_finish()

            self.current_command = None
            SimModule.wait_time(SimTime(1))


    @property
    def repeat_times(self):
        # TODO implement this method
        return 10

    @property
    def block_elements(self):
        """
        每次的单元中有多少个 element
        """

        return  10

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
        def reduce_read_dma_handler(input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
            # 首先决定是否启用 这个 dma
            if not self.check_read_dma_in_use(read_dma_id):
                return False

            # 构建 port 进行连接
            reduce_read_port = DepMemoryPort()
            reduce_read_port.config_dep_memory(self.reduce_memory)

            if isinstance(self.current_command, ReceiveCommand):
                src_map = {0:self.current_command.src0,1:self.current_command.src1,2:self.current_command.asrc}
            elif isinstance(self.current_command,QuantCommand):
                src_map = {0:self.current_command.src}
            else:
                raise ValueError

            src = src_map[read_dma_id]

            # 该 DMA 会被使用，根据指令确定读取次数，并发送到指定的下一个队列中
            for i in range(self.repeat_times):
                pass



        return reduce_read_dma_handler



    def l3_read_dma_helper(self):
        pass

    def l3_write_dma_helper(self):
        pass

    def act_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
        pass

    def mul_quant_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
        pass

    def add_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
        pass

    def fork_handler(self,input_fifo_map:PipeArg,output_fifo_map:PipeArg)->bool:
        pass









