import os
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent
load_dotenv(_project_root / ".env")


def test_dotenv():
    print("=== Testing dotenv ===")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_API_BASE", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    temperature = os.getenv("OPENAI_TEMPERATURE", "0.2").strip()

    print(f"OPENAI_API_KEY: {'*' * 8 + api_key[-4:] if len(api_key) > 4 else 'NOT SET'}")
    print(f"OPENAI_API_BASE: {base_url or 'NOT SET (will use default)'}")
    print(f"OPENAI_MODEL: {model}")
    print(f"OPENAI_TEMPERATURE: {temperature}")

    assert api_key, "OPENAI_API_KEY is not set!"
    print("dotenv test passed!\n")


def test_llm_complete():
    print("=== Testing LLM complete ===")
    from src.clients.llm_client import OpenAIClient

    client = OpenAIClient.build()
    print(f"Model: {client.model}")
    print(f"Temperature: {client.temperature}")

    messages = [{"role": "user", "content": "Say 'hello' in one word."}]
    print(f"Sending message: {messages[0]['content']}")

    response = client.complete(messages)
    print(f"Response: {response.get('content')}")

    assert response.get("content"), "LLM response is empty!"
    print("LLM complete test passed!\n")


if __name__ == "__main__":
    test_dotenv()
    test_llm_complete()
    print("All tests passed!")
