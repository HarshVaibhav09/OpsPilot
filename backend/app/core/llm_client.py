import httpx

from app.core.config import settings


class LLMClient:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
    ) -> str:

        payload = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            "temperature": temperature,
        }

        try:
            response = self.client.post(
                self.base_url,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()

            return response.json()["choices"][0]["message"]["content"].strip()

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"LLM API Error ({e.response.status_code}): {e.response.text}"
            ) from e

        except httpx.RequestError as e:
            raise RuntimeError(
                f"Failed to connect to Groq API: {e}"
            ) from e


llm_client = LLMClient()