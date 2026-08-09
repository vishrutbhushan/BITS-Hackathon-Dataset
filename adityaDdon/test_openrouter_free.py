import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load .env from the same folder as this script
load_dotenv(Path(__file__).parent / ".env")

api_key = os.getenv("OPENROUTER_API_KEY")
model = os.getenv("OPENROUTER_MODEL")

print("API Key loaded:", api_key[:12] + "..." if api_key else None)
print("Model:", model)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

while True:
    prompt = input("\nYou: ").strip()

    if prompt.lower() in {"exit", "quit"}:
        break

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        print("\nLLM:", response.choices[0].message.content)

    except Exception as e:
        print("\nError:", e)