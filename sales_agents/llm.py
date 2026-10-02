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
_last_call = 0.0
_fail_streak = 0
MIN_GAP = float(os.getenv("SALES_LLM_DELAY", "5"))  # seconds between calls (free tiers ~10-15/min)


def _is_rate_limit(e: Exception) -> bool:
    t = (type(e).__name__ + str(e)).lower()
    return "ratelimit" in t or "429" in t or "resource_exhausted" in t or "quota" in t


def ask(llm, prompt: str) -> str:
    """Throttled, retries on rate limits, never raises. Gives up (returns '') after repeated failures."""
    import time
    global _warned, _last_call, _fail_streak
    if _fail_streak >= 5:  # quota probably exhausted: stop hammering, use fallbacks
        return ""
    for attempt in range(4):
        wait = MIN_GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            content = llm.invoke(prompt).content
            _fail_streak = 0
            if isinstance(content, list):  # providers may return a list of content parts
                content = "".join(p if isinstance(p, str) else p.get("text", "") for p in content)
            return str(content)
        except Exception as e:
            if _is_rate_limit(e) and attempt < 3:
                delay = 20 * (attempt + 1)
                print(f"Rate limit hit - waiting {delay}s and retrying...")
                time.sleep(delay)
                continue
            _fail_streak += 1
            if not _warned:
                kind = "rate limit / free quota used up" if _is_rate_limit(e) else "check your LLM API key"
                print(f"WARNING: LLM call failed ({type(e).__name__}: {kind}). Using rule-based fallbacks for failed calls.")
                _warned = True
            return ""
    return ""
