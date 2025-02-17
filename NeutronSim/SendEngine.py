


from typing import Optional
from NeutronSim.AtomManager import AtomManager,AtomResourceRequest
from NeutronSim.Commands import SendCommand
from deps.Desim.Desim.Core import Event, SimModule, SimTime
from deps.Desim.Desim.module.FIFO import FIFO



class SubSendEngine(SimModule):
    def __init__(self):
        super().__init__()

        self.register_coroutine(self.process)

        self.send_command_queue:Optional[FIFO] = None 
        
        self.atom_manager:AtomManager = None 

        self.sub_send_engine_id = -1 
        
        self.current_command:Optional[SendCommand] = None 

        self.acquire_finish_event:Event = Event()



    def process(self):
        while True:
            # 读取新的指令, 如果指令队列空了,就说明没有新的指令了,退出执行
            if self.send_command_queue.is_empty():
                return

            # 读取新的指令
            command:SendCommand = self.send_command_queue.read()
            # 对指令进行解析,并申请资源 
            acquire_req = AtomResourceRequest(
                resource_type='link',
                access_type='acquire',
                resources_id=command.,
                requester_id=self.sub_send_engine_id,
                acquire_finish_event= self.acquire_finish_event
            )

            self.atom_manager.handle_acquire_request(acquire_req)
            SimModule.wait(self.acquire_finish_event)

            # 构建流水线处理指令

            # 等待流水线结束, 执行完成 

            # 释放释放资源 
            release_req = AtomResourceRequest(
                resource_type='link',
                access_type='release',
                resources_id=command,
                requester_id=self.sub_send_engine_id,
            )
            self.atom_manager.handle_release_request(release_req)
            # 处理结束 等一个周期在处理下一次的请求吧
            SimModule.wait_time(SimTime(1))
        



class SendEngine(SimModule):
    def __init__(self):
        super().__init__()

