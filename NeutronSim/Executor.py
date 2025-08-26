from __future__ import  annotations
from typing import Optional

from Desim.Core import SimModule, SimTime, SimSession
from Desim.module.FIFO import FIFO

from NeutronSim.Commands import SendCommand, ComputeCommand, CommandGraph, ReceiveCommand, RootCommand, CommandBase
from NeutronSim.Resource import IODieResource, AtomDieResource


class ExecutorBase(SimModule):
    def __init__(self):
        super().__init__()


class SendExecutor(ExecutorBase):
    def __init__(self, command:SendCommand, iod_resource:IODieResource,atom_resource:AtomDieResource):
        super().__init__()


        self.command:SendCommand = command

        self.iod_resource:IODieResource = iod_resource
        self.atom_resource:AtomDieResource = atom_resource


        self.register_coroutine(self.process)

    def process(self):

        # 申请资源
        self.iod_resource.dma_free_tag.wait()
        for group_id in self.command.group_id:
            self.atom_resource.iod_to_atom_link_free_table[group_id].wait()


        # 图中的依赖关系 - 1
        GraphExecuteEngine.current_graph_engine.upcoming_command_fifo.write(self.command)

        # 开始执行

        for i in range(self.command.dshape.num_chunks):
            SimModule.wait_time(SimTime(20))
            for cur_consumer_command,fifo in self.command.output_nodes.items():
                fifo.write(i)



        # 执行结束，释放硬件资源
        for group_id in self.command.group_id:
            self.atom_resource.iod_to_atom_link_free_table[group_id].post()
        self.iod_resource.dma_free_tag.post()


class ComputeExecutor(ExecutorBase):
    def __init__(self, command:ComputeCommand, atom_resource:AtomDieResource):
        super().__init__()

        self.command:ComputeCommand = command


        self.atomd_resource = atom_resource


        self.register_coroutine(self.process)


    def process(self):

        for group_id in self.command.group_id:
            self.atomd_resource.atom_compute_free_table[group_id].wait()
            if self.command.last_acc:
                self.atomd_resource.atom_to_iod_link_free_table[group_id].wait()

        GraphExecuteEngine.current_graph_engine.upcoming_command_fifo.write(self.command)

        # TODO 完成复杂的部分
        for i in range(self.command.src_dshape.num_chunks):
            for j in range(self.command.dst_dshape.num_chunks):
                SimModule.wait_time(SimTime(20))

                print(f'Compute run {(i,j)} at {SimSession.sim_time}')

        if self.command.last_acc:
            for i in range(self.command.dst_dshape.num_chunks):
                SimModule.wait_time(SimTime(20))

                for cur_consumer_command,fifo in self.command.output_nodes.items():
                    fifo.write(i)

        for group_id in self.command.group_id:
            self.atomd_resource.atom_compute_free_table[group_id].post()
            if self.command.last_acc:
                self.atomd_resource.atom_to_iod_link_free_table[group_id].post()



class ReceiveExecutor(ExecutorBase):
    def __init__(self, command:ReceiveCommand, iod_resource:IODieResource):
        super().__init__()

        self.command:ReceiveCommand = command
        self.iod_resource = iod_resource

        self.register_coroutine(self.process)



    def process(self):

        self.iod_resource.recv_engine_free_tag.wait()

        GraphExecuteEngine.current_graph_engine.upcoming_command_fifo.write(self.command)

        for i in range(self.command.dshape.num_chunks):
            SimModule.wait_time(SimTime(20))
            for cur_consumer_command,fifo in self.command.output_nodes.items():
                fifo.write(i)

        print(f"Finish at {SimSession.sim_time}")

        self.iod_resource.recv_engine_free_tag.post()



class GraphExecuteEngine(SimModule):
    current_graph_engine:Optional[GraphExecuteEngine] = None
    def __init__(self,graph:CommandGraph):
        super().__init__()

        self.graph:CommandGraph = graph


        self.iod_resource = IODieResource()
        self.atomd_resource = AtomDieResource()



        self.upcoming_command_fifo:FIFO[CommandBase] = FIFO(100) # 启动运行这指令
        self.pending_command_fifo:FIFO[CommandBase] = FIFO(100)

        self.dep_map = graph.gen_dep_map()

        self.pending_command_fifo.write(graph.root_command)

        self.register_coroutine(self.graph_topo_process)
        self.register_coroutine(self.issue_command)


    def graph_topo_process(self):
        while True:
            upcoming_command = self.upcoming_command_fifo.read()

            # 在这里处理 graph 相关的事情
            for next_command in upcoming_command.next_nodes.keys():
                self.dep_map[next_command] -= 1
                if self.dep_map[next_command] == 0:
                    self.pending_command_fifo.write(next_command)


    def issue_command(self):
        while True:
            pending_command = self.pending_command_fifo.read()

            if isinstance(pending_command,SendCommand):
                SendExecutor(pending_command,self.iod_resource,self.atomd_resource)
            elif isinstance(pending_command,ComputeCommand):
                ComputeExecutor(pending_command,self.atomd_resource)
            elif isinstance(pending_command,ReceiveCommand):
                ReceiveExecutor(pending_command,self.iod_resource)
            elif isinstance(pending_command,RootCommand):
                # 将root command 的子节点添加到pending_command_fifo中
                for child_command in pending_command.output_nodes.keys():
                    self.pending_command_fifo.write(child_command)
            else:
                raise Exception("Unknow command type")

            pass
