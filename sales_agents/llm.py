"""Optional LLM access. Agents fall back to rule-based logic when no key is set."""
import os


def get_llm():
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        return None
    return ChatAnthropic(model=os.getenv("SALES_AGENT_MODEL", "claude-sonnet-5-5"))


def ask(llm, prompt: str) -> str:
    return llm.invoke(prompt).content
