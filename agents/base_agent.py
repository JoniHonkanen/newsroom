from abc import ABC, abstractmethod

from schemas.agent_state import AgentState

class BaseAgent(ABC):
    def __init__(self, llm, prompt, name: str = None):
        self.llm = llm
        self.prompt = prompt
        self.name = name or self.__class__.__name__

    @abstractmethod
    def run(self, state: AgentState) -> AgentState:
        return state