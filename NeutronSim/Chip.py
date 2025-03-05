from Desim.Core import SimModule
from Desim.memory.Memory import ChunkMemory

from NeutronSim.Atom import AtomManager
from NeutronSim.Commands import ReceiveBaseCommand, SendCommand, ComputeCommand
from NeutronSim.Config import LinkConfig, MemoryConfig, AtomConfig
from NeutronSim.ReceiveEngine import ReceiveEngine
from NeutronSim.SendEngine import SendEngine


class Chip(SimModule):
    def __init__(self,d2d_link_config:LinkConfig,
                    l2_memory_config:MemoryConfig,l3_memory_config:MemoryConfig,reduce_memory_config:MemoryConfig,
                    atom_config:AtomConfig):
        super().__init__()

        self.d2d_link_config = d2d_link_config
        self.l2_memory_config = l2_memory_config
        self.l3_memory_config = l3_memory_config
        self.reduce_memory_config = reduce_memory_config
        self.atom_config = atom_config



        self.l3_memory = ChunkMemory(self.l3_memory_config.bandwidth)
        self.reduce_memory = ChunkMemory(self.reduce_memory_config.bandwidth)

        self.atom_manager:AtomManager = AtomManager(self,self.d2d_link_config,self.l2_memory_config,atom_config)
        self.send_engine = SendEngine(self,self.d2d_link_config)
        self.receive_engine = ReceiveEngine(self)


        self.atom_manager.config_connection(self.reduce_memory)

        self.send_engine.config_connection(self.atom_manager,self.l3_memory)

        self.receive_engine.config_connection(self.l3_memory,self.reduce_memory)


    def load_command(self,send_command_list:list[SendCommand],receive_command_list:list[ReceiveBaseCommand],compute_command_list:list[ComputeCommand]):
        self.send_engine.load_command(send_command_list)
        self.receive_engine.load_command(receive_command_list)
        self.atom_manager.load_command(compute_command_list)

