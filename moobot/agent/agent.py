from agents import Agent, RunContextWrapper, Runner, RunResult, TResponseInputItem

from moobot.agent.context import AgentContext
from moobot.agent.model import get_model
from moobot.agent.prompts import get_instructions
from moobot.agent.tools import TOOLS
from moobot.settings import get_settings

settings = get_settings()


def _get_instructions(context: RunContextWrapper[AgentContext], agent: Agent[AgentContext]) -> str:
    return get_instructions()


def get_agent() -> Agent[AgentContext]:
    return Agent[AgentContext](
        name="Moobot",
        instructions=_get_instructions,
        model=get_model(),
        tools=TOOLS,
    )


async def run_turn(
    transcript: list[TResponseInputItem], user_input: str, context: AgentContext
) -> RunResult:
    return await Runner.run(
        get_agent(),
        [*transcript, {"role": "user", "content": user_input}],
        context=context,
        max_turns=settings.agent_max_turns,
    )
