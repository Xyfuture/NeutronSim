from dataclasses import dataclass


@dataclass
class Shape:
    pass


@dataclass
class CommandBase:
    pass



@dataclass
class SendCommand(CommandBase):
    pass


@dataclass
class ReceiveCommand(CommandBase):
    pass




@dataclass
class ComputeCommand(CommandBase):
    pass