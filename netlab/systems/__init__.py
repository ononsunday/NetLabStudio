"""Headless teaching models. These models never open real network sockets."""

from .binary import LogicCircuit, alu, describe_float, describe_integer, full_adder, half_adder
from .cpu import CPU
from .memory import Cache, MemoryArena, page_replacement
from .os import network_pipeline, schedule_processes
from .integrated import cpu_network_experiment

__all__ = ["CPU", "Cache", "LogicCircuit", "MemoryArena", "alu", "describe_float",
           "describe_integer", "full_adder", "half_adder", "network_pipeline",
           "page_replacement", "schedule_processes", "cpu_network_experiment"]
