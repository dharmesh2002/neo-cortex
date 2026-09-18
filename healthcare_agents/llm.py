import os


def call_llm(prompt: str, system: str = None, image_b64: str = None, image_media_type: str = None) -> str:
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()

    if provider == "nvidia":
        return _call_nvidia(prompt, system)
    else:
        return _call_gemini(prompt, system, image_b64, image_media_type)


def _call_gemini(prompt: str, system: str = None, image_b64: str = None, image_media_type: str = None) -> str:
    import time
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

    contents = []
    if image_b64 and image_media_type and image_media_type.startswith("image/"):
        import base64
        contents.append(types.Part.from_bytes(data=base64.b64decode(image_b64), mime_type=image_media_type))
    contents.append(prompt)

    config = types.GenerateContentConfig(system_instruction=system) if system else None

    for attempt in range(4):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            return response.text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if attempt < 3:
                    time.sleep(5 * (attempt + 1))  # wait 5s, 10s, 15s
                    continue
            raise
    raise Exception("Gemini model unavailable after 4 attempts. Please try again later.")


def _call_nvidia(prompt: str, system: str = None) -> str:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.environ.get("NVIDIA_API_KEY", ""),
    )
    model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(model=model, messages=messages, max_tokens=4096)
    return response.choices[0].message.content
