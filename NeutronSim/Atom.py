from __future__ import annotations
from collections import deque
from dataclasses import dataclass,field
from typing import Literal, Optional, Union
from Desim.Core import SimModule
from Desim.Core import Event

from NeutronSim.Commands import ComputeCommand
from NeutronSim.Config import MemoryConfig
from Desim.Core import SimTime
from Desim.memory.Memory import DepMemory

from Desim.memory.Memory import ChunkMemory

from Desim.module.FIFO import FIFO

from deps.Desim.Desim.Sync import SimSemaphore


class AtomInstance(SimModule):
    def __init__(self):
        super().__init__()

        self.instance_id:int = 0

        self.atom_module = None

        self.link_request_queue:deque[AtomResourceRequest] = deque()
        self.compute_request_queue:deque[AtomResourceRequest] = deque()

        self.current_link_request:Optional[AtomResourceRequest] = None
        self.current_compute_request:Optional[AtomResourceRequest] = None


        self.l2_memory_config:MemoryConfig = MemoryConfig()
        self.l2_memory = DepMemory()



    def link_in_use(self)->bool:
        return self.current_link_request is not None

    def compute_in_use(self)->bool:
        return self.current_compute_request is not None





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
                                (not AtomInstance.link_request_queue[0] == waiting_req):
                            can_issue = False
                            break
                    elif waiting_req.resource_type == 'compute':
                        if  atom_instance.compute_in_use() or \
                                (not AtomInstance.compute_request_queue[0] == waiting_req):
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



class AtomModule(SimModule):
    def __init__(self,atom_id:int=-1):
        super().__init__()

        self.atom_id = atom_id
        
        self.l2_memory = ChunkMemory()
        

        # 假设指令一开始就能直接发送到 ATOM Die 中缓存执行
        self.compute_command_queue:Optional[FIFO] = None


        # 内部使用
        self.compute_start_semaphore = SimSemaphore(0)
        self.compute_finish_semaphore = SimSemaphore(0)
        self.store_start_semaphore = SimSemaphore(0)
        self.store_finish_semaphore = SimSemaphore(0)

        self.current_command:Optional[ComputeCommand] = None 

        self.register_coroutine(self.processs)
        self.register_coroutine(self.compute_handler)
        self.register_coroutine(self.store_handler)
    
    def processs(self):
        while True:
            if self.compute_command_queue.is_empty():
                return

            # 取一条指令
            self.current_command = self.compute_command_queue.read()
            
            # 驱动 compute 和 store 操作
            self.compute_start_semaphore.post()
            self.store_start_semaphore.post()

            # 等待上述两个子操作结束
            self.compute_finish_semaphore.wait()
            self.store_finish_semaphore.wait()

            # 执行完毕 
            SimModule.wait_time(SimTime(1))


    def compute_handler(self):
        while True:
            self.compute_start_semaphore.wait()

            # 获取到指令, 开始执行 
            

            # 执行完毕
            self.compute_finish_semaphore.post()


    def store_handler(self):
        while True:
            self.store_start_semaphore.wait()


            # 执行完毕 
            self.store_finish_semaphore.post()


    def l2_read_dma_helper(self):
        pass

    def l2_write_dma_helper(self):
        pass

    def link_handler(self):
        pass 

    def reduce_write_dma_helper(self):
        pass