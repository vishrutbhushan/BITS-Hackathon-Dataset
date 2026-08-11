import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

def main():
    """Run an optional interactive OpenRouter smoke test."""
    load_dotenv(Path(__file__).parent / ".env")
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    if not api_key or not model:
        raise SystemExit("OPENROUTER_API_KEY and OPENROUTER_MODEL are required")

    print("OpenRouter credentials loaded.")
    print("Model:", model)
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    while True:
        prompt = input("\nYou: ").strip()
        if prompt.lower() in {"exit", "quit"}:
            break
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            print("\nLLM:", response.choices[0].message.content)
        except Exception as exc:
            print("\nError:", exc)


if __name__ == "__main__":
    main()
