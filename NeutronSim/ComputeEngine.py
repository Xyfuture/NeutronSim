from Desim.Core import SimModule

from Desim.memory.Memory import ChunkMemory

from deps.Desim.Desim.memory.Memory import ChunkMemoryPort


class MatrixEngine(SimModule):
    def __init__(self):
        super().__init__()
        
        self.l2_memory = ChunkMemory()

        self.l2_memory_read_port = ChunkMemoryPort()
        self.l2_memory_write_port = ChunkMemoryPort()

        
        self.register_coroutine(self.process)
    
    def process(self):
        pass 

    def config_connection(self):
        pass  
    



class StoreEngine(SimModule):
    def __init__(self):
        super().__init__()

        self.l2_memory:ChunkMemory = ChunkMemory()
        self.l2_memory_port:ChunkMemoryPort = ChunkMemoryPort()


    
