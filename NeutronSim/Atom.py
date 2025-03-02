from __future__ import annotations
from collections import deque
from dataclasses import dataclass,field
from typing import Literal, Optional, Union
from Desim.Core import SimModule
from Desim.Core import Event

from NeutronSim.Commands import ComputeCommand
from NeutronSim.Config import MemoryConfig, element_bytes_dict
from Desim.Core import SimTime
from Desim.memory.Memory import DepMemory, ChunkMemoryPort, ChunkPacket

from Desim.memory.Memory import ChunkMemory

from Desim.module.FIFO import FIFO,DelayFIFO


class AtomInstance(SimModule):
    def __init__(self,atom_id:int = -1):
        super().__init__()

        self.atom_id:int = atom_id

        self.atom_die:Optional[AtomDie] = AtomDie(atom_id)

        self.link_request_queue:deque[AtomResourceRequest] = deque()

        # compute的资源暂时没有启用
        self.compute_request_queue:deque[AtomResourceRequest] = deque()

        self.current_link_request:Optional[AtomResourceRequest] = None

        # 暂时没有启用
        self.current_compute_request:Optional[AtomResourceRequest] = None




    def link_in_use(self)->bool:
        return self.current_link_request is not None

    def compute_in_use(self)->bool:
        return self.current_compute_request is not None

    def load_command(self,command_list:list[ComputeCommand]):
        self.atom_die.load_command(command_list)

    def config_connection(self, reduce_memory:ChunkMemory):
        self.atom_die.config_connection(reduce_memory)


@dataclass
class AtomResourceRequest:
    resource_type:Optional[Literal['link','compute']] = None  # link 仅表示单向的输入带宽,输出 link 自动控制 
    access_type:Optional[Literal['acquire','release']] = None 
    resources_id:list[int] = field(default_factory=list)
    requester_id:int = -1
    acquire_finish_event:Optional[Event] = None

    # TODO 比较函数


class AtomManager(SimModule):
    def __init__(self):
        super().__init__()

        # pending 仅表示当前周期新来的 request , 不是处于等待状态的 request
        self.pending_acquire_request_queue:deque[AtomResourceRequest] = deque()
        self.pending_release_request_queue:deque[AtomResourceRequest] = deque()

        self.waiting_acquire_request_queue:deque[AtomResourceRequest] = deque()


        self.atom_instance_dict:dict[int,AtomInstance]=dict()
        for i in range(8):
            self.atom_instance_dict[i] = AtomInstance()

        self.update_event = Event()

        self.register_coroutine(self.process)

    def process(self):
        while True:
            SimModule.wait(self.update_event)
            # 当有新的 acquire 或者 release request到来的时候, 就更新资源分配

            # 首先处理当前 release 请求
            for release_req in self.pending_release_request_queue:
                for resource_id in release_req.resources_id:
                    if release_req.resource_type == 'link':
                        self.atom_instance_dict[resource_id].current_link_request = None 
                    elif release_req.resource_type == 'compute':
                        self.atom_instance_dict[resource_id].current_compute_request = None

            # 注册 acquire 请求 
            for acquire_req in self.pending_acquire_request_queue:
                self.waiting_acquire_request_queue.append(acquire_req)
                for resource_id in acquire_req.resources_id:
                    if acquire_req.resource_type == 'link':
                        self.atom_instance_dict[resource_id].link_request_queue.append(acquire_req) 
                    elif acquire_req.resource_type == 'compute':
                        self.atom_instance_dict[resource_id].compute_request_queue.append(acquire_req)
                
            # 从 waiting 的 queue 中取出符合标准的
            issue_queue = deque()
            for waiting_req in self.waiting_acquire_request_queue:
                can_issue = True
                for resource_id in waiting_req.resources_id:
                    atom_instance = self.atom_instance_dict[resource_id]
                    if waiting_req.resource_type == 'link':
                        if atom_instance.link_in_use() or \
                                (not atom_instance.link_request_queue[0] == waiting_req):
                            can_issue = False
                            break
                    elif waiting_req.resource_type == 'compute':
                        if  atom_instance.compute_in_use() or \
                                (not atom_instance.compute_request_queue[0] == waiting_req):
                            can_issue = False
                            break
                
                if can_issue:
                    issue_queue.append(waiting_req)
                    # issue
                    
                    for resource_id in waiting_req.resources_id:
                        atom_instance = self.atom_instance_dict[resource_id] 

                        if waiting_req.resource_type == 'link':
                            assert atom_instance.current_link_request is None 
                            atom_instance.current_link_request = atom_instance.link_request_queue.popleft()

                        elif waiting_req.resource_type == 'compute':
                            assert atom_instance.current_compute_request is None
                            atom_instance.current_compute_request = atom_instance.compute_request_queue.popleft()

                        # notify 
                        waiting_req.acquire_finish_event.notify(SimTime(0))

            for req in issue_queue:
                self.waiting_acquire_request_queue.remove(req) # 不支持中间的元素的删除  emmm 

            

    def handle_acquire_request(self,req:AtomResourceRequest):
        # check
        assert req.access_type == 'acquire'
        assert req.acquire_finish_event is not None 

        self.pending_acquire_request_queue.append(req)
        self.update_event.notify(SimTime(0))

    def handle_release_request(self,req:AtomResourceRequest):
        assert req.access_type == 'release'

        self.pending_release_request_queue.append(req)
        self.update_event.notify(SimTime(0))

    def get_atom_instance(self,atom_id:int) -> AtomInstance:
        return self.atom_instance_dict[atom_id]

    def load_command(self,command_list:list[ComputeCommand]):
        for atom_instance in self.atom_instance_dict.values():
            atom_instance.load_command(command_list)

    def config_connection(self,reduce_memory:ChunkMemory):
        for atom_instance in self.atom_instance_dict.values():
            atom_instance.config_connection(reduce_memory)


class AtomDie(SimModule):
    def __init__(self,atom_id:int=-1):
        super().__init__()

        self.atom_id = atom_id
        
        self.l2_memory:ChunkMemory = ChunkMemory()
        self.external_reduce_memory:Optional[ChunkMemory] = None
        

        # 假设指令一开始就能直接发送到 ATOM Die 中缓存执行
        self.fetch_engine_command_queue:Optional[FIFO] = None
        self.compute_engine_command_queue:Optional[FIFO] = None
        self.store_engine_read_command_queue:Optional[FIFO] = None
        self.store_engine_write_command_queue:Optional[FIFO] = None

        self.fetch_to_compute_fifo:FIFO = FIFO(10)

        self.store_read_to_link_fifo:DelayFIFO = DelayFIFO(10, 0)
        self.store_link_to_write_fifo:FIFO = FIFO(10)

        # self.register_coroutine(self.process)
        self.register_coroutine(self.fetch_engine_handler)
        self.register_coroutine(self.compute_engine_handler)

        self.register_coroutine(self.store_engine_read_handler)
        self.register_coroutine(self.store_engine_write_handler)    
        self.register_coroutine(self.link_handler)



    def fetch_engine_handler(self):
        l2_memory_read_port = ChunkMemoryPort()
        l2_memory_read_port.config_chunk_memory(self.l2_memory)
        # 这个只是从 l2 memory 中读取
        while True:
            if self.compute_engine_command_queue.is_empty():
                return
            
            current_command = self.compute_engine_command_queue.read()

            # TODO check 这个指令的 atom id 是否匹配

            # 执行这一条指令
            for i in range(current_command.src_chunk_num):
                data = l2_memory_read_port.read(current_command.src + i, 1, current_command.src_free,
                                                current_command.src_chunk_size, current_command.batch_size,
                                                element_bytes_dict[current_command.src_dtype])

                chunk_packet = ChunkPacket(
                    payload=data,
                    num_elements=current_command.src_chunk_size,
                    batch_size=current_command.batch_size,
                    element_bytes=element_bytes_dict[current_command.src_dtype]
                )

                self.fetch_to_compute_fifo.write(chunk_packet)


    def compute_engine_handler(self):
        l2_memory_write_port = ChunkMemoryPort()
        l2_memory_write_port.config_chunk_memory(self.l2_memory)
        while True:
            # 获取到指令, 开始执行 
            if self.compute_engine_command_queue.is_empty():
                return 

            current_command:ComputeCommand = self.compute_engine_command_queue.read()
            # 执行这一条指令 , 直接按照算力之类的计算延迟应该是可行的

            for i in range(current_command.src_chunk_num):

                # 读取一次数据
                chunk_packet = self.fetch_to_compute_fifo.read()

                for j in range(current_command.dst_chunk_num):
                    pass #  src_chunk_size * dst_chunk_size 的一个小块

                    # 等待某一个延迟的时间
                    latency = 0
                    SimModule.wait_time(SimTime(latency))


            # 摆了, 就先这样吧
            # 所有计算都已经结束, 结果写入到了 acc buffer中, 等待讲acc buffer的结果写入到l2 中
            if current_command.last_acc:
                # 要进行读出操作, 写入到 L2 中
                for i in range(current_command.dst_chunk_num):
                    chunk_packet = ChunkPacket(
                        payload = None,
                        num_elements = current_command.dst_chunk_size,
                        batch_size = current_command.batch_size,
                        element_bytes = 4
                    )
                    l2_memory_write_port.write(current_command.dst,chunk_packet,True,
                                               current_command.dst_chunk_size,current_command.batch_size,4)



    def store_engine_read_handler(self):
        """
        从l2中读出,写入到 l3中,  需要走 uci-e link
        """
        l2_memory_read_port = ChunkMemoryPort()
        l2_memory_read_port.config_chunk_memory(self.l2_memory)

        while True:
            if self.store_engine_read_command_queue.is_empty():
                return

            current_command:ComputeCommand = self.store_engine_read_command_queue.read()
            # 执行这个指令, 从l2 memory中读取数据,然后通过 delay fifo 发送给 l3 memory

            if not current_command.last_acc:
                continue

            for i in range(current_command.dst_chunk_num):
                data = l2_memory_read_port.read(current_command.dst + i, 1, current_command.dst_free,
                                                current_command.dst_chunk_size, current_command.batch_size,
                                                4)
                
                chunk_packet = ChunkPacket(
                    payload=data,
                    num_elements=current_command.dst_chunk_size,
                    batch_size=current_command.batch_size,
                    element_bytes=4
                )
                self.store_read_to_link_fifo.delay_write(chunk_packet, SimTime(100))

            
    def link_handler(self):
        while True:
            chunk_packet = self.store_read_to_link_fifo.read()
            #TODO 计算时间
            transfer_latency = 10

            SimModule.wait_time(SimTime(transfer_latency))

            self.store_link_to_write_fifo.write(chunk_packet)




    def store_engine_write_handler(self):
        """
        接收 uci-e link 传来的数据, 然后写入到 l3 中
        """
        
        reduce_memory_write_port = ChunkMemoryPort()
        reduce_memory_write_port.config_chunk_memory(self.external_reduce_memory)

        while True:
            if self.store_engine_write_command_queue.is_empty():
                return
            current_command:ComputeCommand = self.store_engine_write_command_queue.read()

            # 写 reduce memory  
            # 需要计算复杂的地址
            reduce_addr = current_command.reddst + current_command.redid[self.atom_id]*current_command.dst_chunk_num
            for i in range(current_command.dst_chunk_num):
                chunk_packet = self.store_link_to_write_fifo.read()

                reduce_memory_write_port.write(reduce_addr+i,chunk_packet,False,
                                               current_command.dst_chunk_size,current_command.batch_size,4)


    def load_command(self,command_list:list[ComputeCommand]):
        command_size = len(command_list)
        self.fetch_engine_command_queue = FIFO(command_size,command_size,command_list)
        self.compute_engine_command_queue = FIFO(command_size,command_size,command_list)
        self.store_engine_read_command_queue = FIFO(command_size,command_size,command_list)
        self.store_engine_write_command_queue = FIFO(command_size,command_size,command_list)


    def config_connection(self,reduce_memory:ChunkMemory):
        self.external_reduce_memory  = reduce_memory


