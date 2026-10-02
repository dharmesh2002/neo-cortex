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


_warned = False


def ask(llm, prompt: str) -> str:
    """Never raises: on a bad key/network error it warns once and returns ''."""
    global _warned
    try:
        return llm.invoke(prompt).content
    except Exception as e:
        if not _warned:
            print(f"WARNING: LLM call failed ({type(e).__name__}) - check ANTHROPIC_API_KEY. "
                  "Continuing with rule-based fallbacks.")
            _warned = True
        return ""
