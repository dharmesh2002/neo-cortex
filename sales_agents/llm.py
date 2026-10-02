"""Optional LLM access. Agents fall back to rule-based logic when no key is set."""
import os


def get_llm():
    """First available provider wins: Gemini (free tier), Groq (free tier), then Anthropic."""
    try:
        if os.getenv("GOOGLE_API_KEY"):
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=os.getenv("SALES_AGENT_MODEL", "gemini-flash-latest"))
        if os.getenv("GROQ_API_KEY"):
            from langchain_groq import ChatGroq
            return ChatGroq(model=os.getenv("SALES_AGENT_MODEL", "llama-3.3-70b-versatile"))
        if os.getenv("ANTHROPIC_API_KEY"):
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=os.getenv("SALES_AGENT_MODEL", "claude-sonnet-5-5"))
    except ImportError as e:
        print(f"WARNING: missing package for the LLM provider ({e}). Running without an LLM.")
    return None


_warned = False


def ask(llm, prompt: str) -> str:
    """Never raises: on a bad key/network error it warns once and returns ''."""
    global _warned
    try:
        return llm.invoke(prompt).content
    except Exception as e:
        if not _warned:
            print(f"WARNING: LLM call failed ({type(e).__name__}) - check your LLM API key (GOOGLE_API_KEY / GROQ_API_KEY / ANTHROPIC_API_KEY). "
                  "Continuing with rule-based fallbacks.")
            _warned = True
        return ""
