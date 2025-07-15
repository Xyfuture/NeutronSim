from typing import Optional

from Desim.Sync import SimOrderedSemaphore


class ResourceBase:
    pass


class IODieResource(ResourceBase):
    def __init__(self):

        self.dma_free_tag:Optional[SimOrderedSemaphore] = SimOrderedSemaphore(4)
        self.recv_engine_free_tag:Optional[SimOrderedSemaphore] = SimOrderedSemaphore(1)



class AtomDieResource(ResourceBase):
    def __init__(self):
        self.atom_compute_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(8)
        ]

        self.iod_to_atom_link_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(8)
        ]

        self.atom_to_iod_link_free_table:list[SimOrderedSemaphore] = [
            SimOrderedSemaphore(1) for i in range(8)
        ]



