import os

from anthropic import Anthropic
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
    client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": "In one sentence, what is an AI agent?"}],
    )

    for block in response.content:
        if block.type == "text":
            print(block.text)


if __name__ == "__main__":
    main()
