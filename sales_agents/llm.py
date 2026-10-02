"""Optional LLM access. Agents fall back to rule-based logic when no key is set."""
import os


class ClaudeCodeLLM:
    """Uses the logged-in Claude Code CLI (works with a Claude Pro/Max login, no API key)."""

    def invoke(self, prompt: str):
        import shutil
        import subprocess
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("claude CLI not found on PATH")
        r = subprocess.run([exe, "-p", prompt], capture_output=True, text=True, timeout=180, encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "claude CLI failed")

        class _R:
            content = r.stdout.strip()
        return _R()


def get_llm():
    """SALES_USE_CLAUDE_CLI=1 uses Claude Code (Pro login). Otherwise the first key found:
    Gemini (free tier), Groq (free tier), then Anthropic."""
    if os.getenv("SALES_USE_CLAUDE_CLI") == "1":
        return ClaudeCodeLLM()
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
        content = llm.invoke(prompt).content
        if isinstance(content, list):  # Gemini/Claude may return a list of content parts
            content = "".join(p if isinstance(p, str) else p.get("text", "") for p in content)
        return str(content)
    except Exception as e:
        if not _warned:
            print(f"WARNING: LLM call failed ({type(e).__name__}) - check your LLM API key (GOOGLE_API_KEY / GROQ_API_KEY / ANTHROPIC_API_KEY). "
                  "Continuing with rule-based fallbacks.")
            _warned = True
        return ""
