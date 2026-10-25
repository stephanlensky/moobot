from functools import cache

from agents import OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI

from moobot.settings import get_settings

settings = get_settings()


@cache
def get_client() -> AsyncOpenAI:
    if not settings.litellm_api_key:
        raise ValueError("LITELLM_API_KEY is not set, the agent can't call the model")
    return AsyncOpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)


@cache
def get_model() -> OpenAIChatCompletionsModel:
    set_tracing_disabled(True)
    return OpenAIChatCompletionsModel(model=settings.agent_model, openai_client=get_client())
