from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Literal, Optional, Union
from Desim.Core import SimModule
from Desim.Core import Event

from deps.Desim.Desim.Core import SimTime


class AtomInstance(SimModule):
    def __init__(self):
        super().__init__()

        self.instance_id:int = 0 

        self.link_request_queue:deque[AtomResourceRequest] = deque()
        self.compute_request_queue:deque[AtomResourceRequest] = deque()

        self.current_link_request:Optional[AtomResourceRequest] = None
        self.current_compute_rquest:Optional[AtomResourceRequest] = None 

    def link_in_use(self)->bool:
        return self.current_link_request is not None

    def compute_in_use(self)->bool:
        return self.current_compute_rquest is not None 


@dataclass 
class AtomResourceRequest:
    resource_type:Optional[Literal['link','compute']] = None  # link 仅表示单向的输入带宽,输出 link 自动控制 
    access_type:Optional[Literal['acquire','release']] = None 
    resources_id:list[int] = []
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
                        self.atom_instance_dict[resource_id].current_compute_rquest = None

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
                            assert atom_instance.current_compute_rquest is None 
                            atom_instance.current_compute_rquest = atom_instance.compute_request_queue.popleft()

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


    
