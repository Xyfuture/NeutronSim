from itertools import batched

from Desim.Core import SimSession

from NeutronSim.Chip import Chip
from NeutronSim.Commands import ReceiveCommand, SendCommand, ComputeCommand

"""
大致是仿真一个 (4,2) 的场景
需要4条输入指令，两个 atom die 使用相同的数据
一条计算指令， redid 有两个， 四个 atom die 需要进行 reduce 操作 
一条receive指令，将结果进行汇总
"""



def gen_compute_command_list():
    compute_command_list = [
        ComputeCommand(
            opcode='COMPUTE',
            group_id=[0,1,2,3,4,5,6,7],
            batch_size=16,

            dst = 200,
            dst_chunk_num=16,
            dst_chunk_size=128,

            dst_free = True,

            reddst=100,
            redid=[0,1,0,1,0,1,0,1],

            src=100,
            src_chunk_num=8,
            src_chunk_size=128,
            src_dtype='fp16',
            src_free=False,

            first_acc=True,
            last_acc=True,
        )
    ]

    return compute_command_list


def gen_send_command_list():
    send_command_list:list[SendCommand] = [
        SendCommand(
            opcode='SEND',
            group_id=[0,1],

            chunk_size=128,
            batch_size=16,
            chunk_num=8,

            dtype='fp16',

            dst=100,
            src=100,
            free=False,
        ),
        SendCommand(
            opcode='SEND',
            group_id=[2,3],

            chunk_size=128,
            batch_size=16,
            chunk_num=8,

            dtype='fp16',

            dst=100,
            src=108,
            free=False,
        ),
        SendCommand(
            opcode='SEND',
            group_id=[4,5],

            chunk_size=128,
            batch_size=16,
            chunk_num=8,

            dtype='fp16',

            dst=100,
            src=116,
            free=False,
        ),
        SendCommand(
            opcode='SEND',
            group_id=[6,7],

            chunk_size=128,
            batch_size=16,
            chunk_num=8,

            dtype='fp16',

            dst=100,
            src=124,
            free=False,
        )
    ]

    return send_command_list


# 写入到 500 开头的地址上
def gen_receive_command_list():
    receive_command_list:list[ReceiveCommand] = [ReceiveCommand(
        opcode='RECEIVE_MONO',
        bdcst=[],

        chunk_size = 128,
        batch_size = 16,
        chunk_num = 32,


        dst0=500,
        dst0_type='fp16',

        dst1_flag=False,

        src0=100,
        src0_dtype='fp32',
        src0_loc='reduce',
        free0=True,


        redcount=4, # 需要写4次

        act=0,
        mul=False,
        add=False,

    )]


    return receive_command_list

if __name__ == '__main__':
    SimSession.reset()
    SimSession.init()

    chip = Chip()

    chip.load_command(
        send_command_list=gen_send_command_list(),
        receive_command_list=gen_receive_command_list(),
        compute_command_list=gen_compute_command_list()
    )

    # 预先写入一定内容的数据
    for i in range(32):
        chip.l3_memory.direct_write(
            100+i,None,check_write_tag=False,
            num_elements=128,num_batch_size=16,
            element_bytes=2
        )


    SimSession.scheduler.run()


    print(chip.atom_manager.atom_instance_dict[0].atom_die.l2_memory.memory_tag)
    print(f'reduce memory tag -> {chip.reduce_memory.memory_tag}')
    print(f'l3 memory tag -> {chip.l3_memory.memory_tag}')

    print(f"finish time at {SimSession.sim_time}")