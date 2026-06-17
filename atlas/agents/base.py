"""
擎天 Atlas — 智能体基类接口
所有智能体（报价/采购/仓储/物流...）必须实现此接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import uuid, time

class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"  
    WAITING_HUMAN = "waiting_human"  # 等待人工审批
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class AgentEvent:
    """智能体间通信事件"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    source_agent: str = ""          # 谁发的
    event_type: str = ""            # 事件类型
    payload: dict = field(default_factory=dict)  # 事件数据
    timestamp: float = field(default_factory=time.time)

@dataclass
class Task:
    """智能体任务"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent_name: str = ""
    action: str = ""                # 要执行的动作
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    status: AgentStatus = AgentStatus.IDLE
    human_approval_required: bool = False
    created_at: float = field(default_factory=time.time)

class BaseAgent(ABC):
    """
    智能体基类
    
    子类必须实现:
    - agent_name: 智能体名称
    - agent_id: 唯一标识
    - on_task(task): 处理任务的主入口
    - capabilities: 声明能力列表
    
    可选覆盖:
    - on_event(event): 接收其他智能体的事件
    - validate(task): 任务前置校验
    """
    
    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.status = AgentStatus.IDLE
        self.tasks: list[Task] = []
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """智能体名称"""
        ...
    
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """唯一标识"""
        ...
    
    @property
    def capabilities(self) -> list[str]:
        """能力列表"""
        return []
    
    def emit(self, event_type: str, payload: dict):
        """向事件总线发送事件"""
        if self.event_bus:
            event = AgentEvent(
                source_agent=self.agent_name,
                event_type=event_type,
                payload=payload,
            )
            self.event_bus.publish(event)
    
    def validate(self, task: Task) -> bool:
        """前置校验，默认通过"""
        return True
    
    @abstractmethod
    def on_task(self, task: Task) -> Task:
        """处理任务（子类必须实现）"""
        ...
    
    def on_event(self, event: AgentEvent):
        """接收其他智能体的事件（子类可选覆盖）"""
        pass
    
    def run(self, task: Task) -> Task:
        """执行任务并返回结果"""
        if not self.validate(task):
            task.status = AgentStatus.FAILED
            return task
        
        self.status = AgentStatus.RUNNING
        task.status = AgentStatus.RUNNING
        
        try:
            result = self.on_task(task)
            result.status = AgentStatus.WAITING_HUMAN if result.human_approval_required else AgentStatus.COMPLETED
            self.status = AgentStatus.IDLE
            return result
        except Exception as e:
            task.status = AgentStatus.FAILED
            task.output_data = {"error": str(e)}
            self.status = AgentStatus.IDLE
            return task


class EventBus:
    """简易事件总线"""
    
    def __init__(self):
        self._subscribers: dict[str, list[BaseAgent]] = {}
        self._events: list[AgentEvent] = []
    
    def subscribe(self, event_type: str, agent: BaseAgent):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(agent)
    
    def publish(self, event: AgentEvent):
        self._events.append(event)
        subs = self._subscribers.get(event.event_type, [])
        for agent in subs:
            agent.on_event(event)
    
    def history(self, event_type: str = None) -> list[AgentEvent]:
        if event_type:
            return [e for e in self._events if e.event_type == event_type]
        return self._events
