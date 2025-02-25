from deps.Desim.Desim.Core import SimModule
from deps.Desim.Desim.memory.Memory import ChunkMemory


class IODie(SimModule):
    def __init__(self):
        super().__init__()

        self.l3_memory = ChunkMemory()
        self.reduce_memory = ChunkMemory()

        pass


