"""
Базовый класс для всех агентов в системе
"""
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from ..state import CreditApplicationState, add_agent_reasoning, add_error
from ...config.logging import logger
from ...services.llm_service import LLMService


class BaseAgent(ABC):
    """Базовый класс для всех агентов"""

    def __init__(
            self,
            agent_name: str,
            system_prompt: str,
            llm_service: LLMService,
            tools: Optional[List[BaseTool]] = None
    ):
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.llm_service = llm_service
        self.tools = tools or []
        self.logger = logger.bind(agent=agent_name)

    async def __call__(self, state: CreditApplicationState) -> CreditApplicationState:
        """Основная точка входа для выполнения агента"""

        self.logger.info("Agent execution started")
        start_time = time.time()

        try:
            # Валидация входных данных
            await self._validate_input(state)

            # Выполнение основной логики агента
            result = await self._execute(state)

            # Обновление состояния
            updated_state = await self._update_state(state, result)

            execution_time = time.time() - start_time
            self.logger.info(
                "Agent execution completed",
                execution_time=execution_time
            )

            return updated_state

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Agent {self.agent_name} failed: {str(e)}"

            self.logger.error(
                "Agent execution failed",
                error=str(e),
                execution_time=execution_time
            )

            # Добавляем ошибку к состоянию
            error_state = add_error(state, error_msg)

            return error_state

    @abstractmethod
    async def _execute(self, state: CreditApplicationState) -> Dict[str, Any]:
        """Основная логика агента - должна быть переопределена"""
        pass

    async def _validate_input(self, state: CreditApplicationState) -> None:
        """Валидация входных данных - может быть переопределена"""
        if not state.get("application_id"):
            raise ValueError("Application ID is required")

    async def _update_state(
            self,
            state: CreditApplicationState,
            result: Dict[str, Any]
    ) -> CreditApplicationState:
        """Обновление состояния на основе результата"""

        # Добавляем рассуждения агента
        reasoning = result.get("reasoning", "No reasoning provided")
        confidence = result.get("confidence")
        metadata = result.get("metadata", {})

        updated_state = add_agent_reasoning(
            state,
            self.agent_name,
            reasoning,
            confidence,
            metadata
        )

        return updated_state

    async def _call_llm(
            self,
            user_message: str,
            context: Optional[Dict[str, Any]] = None,
            use_tools: bool = True
    ) -> Dict[str, Any]:
        """Вызов LLM с системным промптом и контекстом"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message)
        ]

        # Добавляем контекст если есть
        if context:
            context_message = f"Контекст: {context}"
            messages.insert(-1, HumanMessage(content=context_message))

        # Вызываем LLM
        if use_tools and self.tools:
            response = await self.llm_service.call_with_tools(
                messages=messages,
                tools=self.tools
            )
        else:
            response = await self.llm_service.call(messages=messages)

        return {
            "reasoning": response.content,
            "confidence": getattr(response, "confidence", None),
            "metadata": {
                "model": self.llm_service.model_name,
                "timestamp": datetime.now().isoformat(),
                "tools_used": len(self.tools) if use_tools else 0
            }
        }

    def _extract_data_from_form(
            self,
            form_data: Dict[str, Any],
            required_fields: List[str]
    ) -> Dict[str, Any]:
        """Извлечение необходимых данных из формы"""

        extracted = {}
        missing_fields = []

        for field in required_fields:
            if field in form_data:
                extracted[field] = form_data[field]
            else:
                missing_fields.append(field)

        if missing_fields:
            self.logger.warning(
                "Missing required fields",
                missing_fields=missing_fields
            )

        return extracted

    def _calculate_confidence(
            self,
            factors: List[float],
            weights: Optional[List[float]] = None
    ) -> float:
        """Расчет уверенности на основе факторов"""

        if not factors:
            return 0.0

        if weights:
            if len(weights) != len(factors):
                weights = [1.0] * len(factors)

            weighted_sum = sum(f * w for f, w in zip(factors, weights))
            total_weight = sum(weights)
            return min(max(weighted_sum / total_weight, 0.0), 1.0)
        else:
            return min(max(sum(factors) / len(factors), 0.0), 1.0)


def create_agent_decorator(step_name: str):
    """Декоратор для оборачивания узлов графа"""

    def decorator(agent_class):
        async def node_function(state: CreditApplicationState) -> CreditApplicationState:
            agent = agent_class()
            return await agent(state)

        node_function.__name__ = f"{step_name}_node"
        return node_function

    return decorator