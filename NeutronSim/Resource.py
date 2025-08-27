from typing import Optional

from Desim.Sync import SimOrderedSemaphore
from NeutronSim.utils.tracer import PerfettoTracer

class ResourceBase:
    pass


class IODieResource(ResourceBase):
    def __init__(self,tracer:PerfettoTracer):

        self.num_dma=4
        self.dma_free_tag:Optional[SimOrderedSemaphore] = SimOrderedSemaphore(self.num_dma)
        self.dma_free_table:list[bool] = [True for i in range(self.num_dma)]
        self.recv_engine_free_tag:Optional[SimOrderedSemaphore] = SimOrderedSemaphore(1)

        self.tracer =  tracer
        for i in range(self.num_dma):
            self.tracer.register_unit(f'dma-{i}')
        self.tracer.register_unit('recv-engine')

    def acquire_dma(self)->int:
        self.dma_free_tag.wait() # pyright: ignore[reportOptionalMemberAccess]
        for i in range(self.num_dma):
            if self.dma_free_table[i]:
                self.dma_free_table[i] = False
                return i
        return -1

    def release_dma(self,dma_id:int)->None:
        assert self.dma_free_table[dma_id] == False
        self.dma_free_table[dma_id] = True
        self.dma_free_tag.post() # pyright: ignore[reportOptionalMemberAccess]

    def acquire_recv_engine(self)->None:
        self.recv_engine_free_tag.wait() # pyright: ignore[reportOptionalMemberAccess]
        

    def release_recv_engine(self,tag:int)->None:
        self.recv_engine_free_tag.post() # pyright: ignore[reportOptionalMemberAccess]

class AtomDieResource(ResourceBase):
    def __init__(self,tracer:PerfettoTracer):

        self.num_atom_die = 8 

        self.atom_compute_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(self.num_atom_die)
        ]

        self.iod_to_atom_link_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(self.num_atom_die)
        ]

        self.atom_to_iod_link_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(self.num_atom_die)
        ]

        self.tracer = tracer
        for i in range(self.num_atom_die):
            self.tracer.register_unit(f'atom-die-{i}')
            self.tracer.register_unit(f'iod-to-atom-link-{i}')
            self.tracer.register_unit(f'atom-to-iod-link-{i}')
        

        


