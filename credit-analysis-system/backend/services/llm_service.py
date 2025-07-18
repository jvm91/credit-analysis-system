"""
Сервис для работы с языковыми моделями
"""
import asyncio
from typing import List, Dict, Any, Optional, Union
from abc import ABC, abstractmethod

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from ..config.settings import settings
from ..config.logging import logger


class LLMProvider(ABC):
    """Абстрактный провайдер LLM"""
    
    @abstractmethod
    async def call(self, messages: List[BaseMessage]) -> Any:
        """Базовый вызов LLM"""
        pass
    
    @abstractmethod
    async def call_with_tools(
        self, 
        messages: List[BaseMessage], 
        tools: List[BaseTool]
    ) -> Any:
        """Вызов LLM с инструментами"""
        pass


class OpenAIProvider(LLMProvider):
    """Провайдер для OpenAI"""
    
    def __init__(self, model: str = "gpt-4", temperature: float = 0.1):
        self.model = model
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout
        )
    
    async def call(self, messages: List[BaseMessage]) -> Any:
        """Вызов OpenAI без инструментов"""
        return await self.llm.ainvoke(messages)
    
    async def call_with_tools(
        self, 
        messages: List[BaseMessage], 
        tools: List[BaseTool]
    ) -> Any:
        """Вызов OpenAI с инструментами"""
        llm_with_tools = self.llm.bind_tools(tools)
        return await llm_with_tools.ainvoke(messages)


class LLMService:
    """Основной сервис для работы с LLM"""
    
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider_name = provider or settings.default_llm_provider
        self.model_name = model or settings.default_model
        self.provider = self._create_provider()
        self.logger = logger.bind(
            service="llm",
            provider=self.provider_name,
            model=self.model_name
        )
    
    def _create_provider(self) -> LLMProvider:
        """Создание провайдера на основе конфигурации"""
        
        if self.provider_name.lower() == "openai":
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key is not configured")
            return OpenAIProvider(self.model_name)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider_name}")
    
    async def call(
        self, 
        messages: List[BaseMessage],
        retry_attempts: int = 3
    ) -> Any:
        """Базовый вызов LLM с повторными попытками"""
        
        last_exception = None
        
        for attempt in range(retry_attempts):
            try:
                self.logger.info("LLM call started", attempt=attempt + 1)

                response = await self.provider.call(messages)

                self.logger.info("LLM call completed successfully")
                return response

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "LLM call failed",
                    attempt=attempt + 1,
                    error=str(e)
                )

                if attempt < retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        self.logger.error(
            "LLM call failed after all retries",
            error=str(last_exception)
        )
        raise last_exception

    async def call_with_tools(
        self,
        messages: List[BaseMessage],
        tools: List[BaseTool],
        retry_attempts: int = 3
    ) -> Any:
        """Вызов LLM с инструментами"""

        last_exception = None

        for attempt in range(retry_attempts):
            try:
                self.logger.info(
                    "LLM call with tools started",
                    attempt=attempt + 1,
                    tools_count=len(tools)
                )

                response = await self.provider.call_with_tools(messages, tools)

                self.logger.info("LLM call with tools completed successfully")
                return response

            except Exception as e:
                last_exception = e
                self.logger.warning(
                    "LLM call with tools failed",
                    attempt=attempt + 1,
                    error=str(e)
                )

                if attempt < retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)

        self.logger.error(
            "LLM call with tools failed after all retries",
            error=str(last_exception)
        )
        raise last_exception

    async def batch_call(
        self,
        messages_list: List[List[BaseMessage]],
        max_concurrent: int = 5
    ) -> List[Any]:
        """Batch вызов нескольких запросов"""

        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_call(messages):
            async with semaphore:
                return await self.call(messages)

        tasks = [bounded_call(messages) for messages in messages_list]
        return await asyncio.gather(*tasks)

    def get_model_info(self) -> Dict[str, Any]:
        """Получение информации о модели"""
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "capabilities": {
                "tools": True,
                "async": True,
                "batch": True
            }
        }


# Глобальный экземпляр сервиса
llm_service = LLMService()