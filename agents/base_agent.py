"""
智能体基类 — 从 atlas/agents/base.py 重新导出
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from atlas.agents.base import BaseAgent, AgentEvent, Task, AgentStatus

__all__ = ["BaseAgent", "AgentEvent", "Task", "AgentStatus"]
