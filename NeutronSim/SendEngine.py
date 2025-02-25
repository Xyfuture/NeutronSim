from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from Desim.module.Pipeline import PipeStage

from NeutronSim.Atom import AtomManager,AtomResourceRequest
from NeutronSim.Commands import SendCommand
from NeutronSim.Config import MemoryConfig, LinkConfig, element_bytes_dict
from Desim.Core import Event, SimModule, SimTime
from Desim.memory.Memory import DepMemory, DepMemoryPort, ChunkMemoryPort
from Desim.module.FIFO import FIFO,DelayFIFO
from Desim.module.Pipeline import PipeGraph

from NeutronSim.IOD import IODie


@dataclass
class SendEngineConfig:
    num_sub_engine:int = 4


class SubSendEngine(SimModule):
    def __init__(self,sub_send_engine_id:int):
        super().__init__()

        self.register_coroutine(self.process)

        self.external_send_command_queue:Optional[FIFO] = None
        self.external_send_engine:Optional[SendEngine] = None

        self.external_atom_manager:Optional[AtomManager] = None

        self.l3_memory_read_port:ChunkMemoryPort = ChunkMemoryPort()

        self.link_config:LinkConfig = LinkConfig()

        self.sub_send_engine_id = sub_send_engine_id
        
        self.current_command:Optional[SendCommand] = None 

        self.acquire_finish_event:Event = Event()

    def config_connection(self,atom_manager:AtomManager,io_die:IODie,send_engine:SendEngine):
        """
        用于构建各种连接关系
        """

        self.external_atom_manager=atom_manager
        self.l3_memory_read_port.config_chunk_memory(io_die.l3_memory)
        self.external_send_engine = send_engine
        self.external_send_command_queue = self.external_send_engine.send_command_queue


    def l3_read_dma_handler(self,input_fifo_map:Optional[dict[str,FIFO]],output_fifo_map:Optional[dict[str,FIFO]])->bool:
        # 根据指令的情况进行 分段读取数据
        read_addr = self.current_command.src
        for i in range(self.current_command.chunk_num):
            # 从 memory 中读取数据
            data = self.l3_memory_read_port.read(read_addr+i,1,self.current_command.free,
                                                 self.current_command.chunk_size,self.current_command.batch_size,
                                                 element_bytes_dict[self.current_command.dtype])

            # 写入到 DelayFIFO 中, 模拟UCI-E 的延迟行为
            # 名字就叫uci-e吧
            # 向多个fifo中写入, 需要支持

            # 计算一下传输的延迟, 邻接的下一个fifo是 DelayFIFO, 需要在这里仿真出来uci-e的传输开销
            for atom_id in self.current_command.group_id:
                output_fifo_map[f'l3-uci-e-{atom_id}'].delay_write(data,SimTime(self.link_config.link_latency))



        return False


    def link_handler(self,input_fifo_map:Optional[dict[str,FIFO]],output_fifo_map:Optional[dict[str,FIFO]])->bool:
        assert len(input_fifo_map) == 1 and len(output_fifo_map) == 1
        input_fifo = list(input_fifo_map.values())[0]
        output_fifo = list(output_fifo_map.values())[0]

        latency = (self.current_command.chunk_size * self.current_command.batch_size * element_bytes_dict[self.current_command.dtype])// self.link_config.bandwidth
        for i in range(self.current_command.chunk_num):
            data = input_fifo.read()
            SimModule.wait_time(SimTime(latency))
            output_fifo.write(data)

        return False



    # 返回一个函数, 用于作为 l2 的 write dma
    def l2_write_dma_helper(self,atom_id:int):
        def l2_write_dma_handler(input_fifo_map:Optional[dict[str,FIFO]],output_fifo_map:Optional[dict[str,FIFO]]):
            l2_write_port = ChunkMemoryPort()
            l2_write_port.config_chunk_memory(atom_die.l2_memory)

            write_addr = self.current_command.dst
            for i in range(self.current_command.chunk_num):
                data = input_fifo_map[f'uci-e-{atom_id}-l2-{atom_id}'].read()

                # 写入到 l2 memory 中
                l2_write_port.write(write_addr+i,data,True,
                                    self.current_command.chunk_size,
                                    self.current_command.batch_size,
                                    element_bytes_dict[self.current_command.dtype])

            return False

        atom_die = self.external_atom_manager.get_atom_instance(atom_id).atom_die

        return l2_write_dma_handler

    def process(self):
        while True:
            # 读取新的指令, 如果指令队列空了,就说明没有新的指令了,退出执行
            if self.external_send_command_queue.is_empty():
                return

            # 读取新的指令
            command:SendCommand = self.external_send_command_queue.read()
            self.current_command = command
            # 对指令进行解析,并申请资源 
            acquire_req = AtomResourceRequest(
                resource_type='link',
                access_type='acquire',
                resources_id=command.group_id,
                requester_id=self.sub_send_engine_id,
                acquire_finish_event= self.acquire_finish_event
            )

            self.external_atom_manager.handle_acquire_request(acquire_req)
            SimModule.wait(self.acquire_finish_event)

            # 构建流水线处理指令
            pipe_graph = PipeGraph()
            read_pipe_stage = PipeStage.dynamic_create(self.l3_read_dma_handler)

            pipe_graph.add_stage(read_pipe_stage,'l3_read_dma')

            for atom_id in self.current_command.group_id:
                link_pipe_stage = PipeStage.dynamic_create(self.link_handler)
                pipe_graph.add_stage(link_pipe_stage,f'link-{atom_id}')

                l2_write_pipe_stage = PipeStage.dynamic_create(self.l2_write_dma_helper(atom_id))
                pipe_graph.add_stage(l2_write_pipe_stage,f'l2_write_dma-{atom_id}')

                pipe_graph.add_sink_stage_by_name(f'l2_write_dma-{atom_id}')

            # 连接各个流水级
            for atom_id in self.current_command.group_id:
                delay_fifo = DelayFIFO(10,0)
                pipe_graph.add_edge_with_fifo('l3_read_dma',f'link-{atom_id}',f'l3-uci-e-{atom_id}',delay_fifo)

                pipe_graph.add_edge(f'link-{atom_id}',f'l2_write_dma-{atom_id}',f'uci-e-{atom_id}-l2-{atom_id}',10,0)


            pipe_graph.build_graph()

            # 启动流水线，并等待流水线结束, 执行完成
            pipe_graph.start_pipe_graph()
            pipe_graph.wait_pipe_graph_finish()  # 等待结束

            # 释放释放资源 
            release_req = AtomResourceRequest(
                resource_type='link',
                access_type='release',
                resources_id=command.group_id,
                requester_id=self.sub_send_engine_id,
            )
            self.external_atom_manager.handle_release_request(release_req)
            # 处理结束 等一个周期在处理下一次的请求吧
            self.current_command = None
            SimModule.wait_time(SimTime(1))
        



class SendEngine(SimModule):
    """
    对外展示为一个大的SendEngine，里面由SubSendEngine负责实际的数据传输
    包含Command队列， 控制指令的流动

    """

    def __init__(self):
        super().__init__()

        self.send_command_queue:Optional[FIFO] = None

        self.send_engine_config:SendEngineConfig = SendEngineConfig()

        self.external_atom_manager:Optional[AtomManager] = None

        # 构建所有的 send engine
        self.sub_send_engine_list:list[SubSendEngine] = []
        for i in range(self.send_engine_config.num_sub_engine):
            self.sub_send_engine_list.append(
                SubSendEngine(i)
            )

    def config_connection(self,atom_manager:AtomManager,io_die:IODie):
        """
        配置内外部各种的连接关系
        :return:
        """

        self.external_atom_manager = atom_manager

        for sub_send_engine in self.sub_send_engine_list:
            sub_send_engine.config_connection(atom_manager,io_die,self)

        pass


    def load_command(self,command_list:list[SendCommand]):
        command_size = len(command_list)
        self.send_command_queue = FIFO(command_size,command_size,command_list)





