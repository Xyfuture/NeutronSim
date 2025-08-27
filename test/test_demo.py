from Desim.Core import SimSession
from Desim.module.FIFO import FIFO

from NeutronSim.Commands import SendCommand, ComputeCommand, ReceiveCommand, RootCommand, CommandGraph, MemoryShape
from NeutronSim.Executor import GraphExecuteEngine
from NeutronSim.utils.tracer import PerfettoTracer



SimSession.reset()
SimSession.init()


root_command = RootCommand()
send_command = SendCommand(
    group_id=[i for i in range(8)],
    dshape=MemoryShape(
        shape = [16,1024],
        chunk_dim=1,
        elements_per_chunk_dim= 128,
        dtype = 'int8',
    )
)
compute_command = ComputeCommand(
    group_id=[i for i in range(8)],
    src_dshape= MemoryShape(
        shape = [16,1024],
        chunk_dim=1,
        elements_per_chunk_dim=128,
        dtype='int8'
    ),
    dst_dshape= MemoryShape(
        shape=[16,2048],
        chunk_dim=1,
        elements_per_chunk_dim=128,
        dtype='fp16'
    ),
    first_acc = True,
    last_acc = True,
)
recv_command = ReceiveCommand(
    dshape=MemoryShape(
        shape=[16,2048],
        chunk_dim=1,
        elements_per_chunk_dim=128,
        dtype='fp16'
    )
)


send_command.input_nodes[root_command] = FIFO(10)
compute_command.input_nodes[send_command] = FIFO(10)
recv_command.input_nodes[compute_command] = FIFO(10)


graph = CommandGraph()
graph.add_command(root_command)
graph.add_command(send_command)
graph.add_command(compute_command)
graph.add_command(recv_command)
graph.root_command = root_command

graph.build_graph()


tracer = PerfettoTracer(ns_per_cycle=1000)


graph_executor = GraphExecuteEngine(graph,tracer)

GraphExecuteEngine.current_graph_engine = graph_executor


SimSession.scheduler.run()

tracer.save("./trace.json")

print(f"Simulation Finished {SimSession.sim_time}")




