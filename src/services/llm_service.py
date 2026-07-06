"""LLM service abstraction supporting Gemini, OpenAI, and NVIDIA NIM providers."""

import os

from google import genai
from google.genai import types
from openai import OpenAI

from src.config import get_settings

settings = get_settings()


class LLMService:
    """Wrapper service to handle LLM completions and embeddings across different providers."""

    def __init__(self) -> None:
        """Initialise LLM settings."""
        self.provider = settings.llm_provider.lower()
        self._client = None
        self.active_provider = self.provider

    @property
    def client(self):
        """Return the API client corresponding to the configured provider, initialized lazily."""
        if self._client is not None:
            return self._client

        if self.provider == "gemini":
            api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
            self._client = genai.Client(api_key=api_key)
        elif self.provider == "openai":
            api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
            self._client = OpenAI(api_key=api_key)
        elif self.provider == "nvidia":
            api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")
            base_url = settings.nvidia_api_base or "https://integrate.api.nvidia.com/v1"
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
            self._client = OpenAI(api_key=api_key)

        # Wrap with LangSmith if tracing is configured
        if self.provider in ("openai", "nvidia"):
            try:
                if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
                    from langsmith import wrap_openai

                    self._client = wrap_openai(self._client)
                    print("LangSmith tracing wrapper applied successfully.")
            except Exception as ls_ex:
                print(f"Failed to apply LangSmith tracing wrapper: {ls_ex}")

        return self._client

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        """Generate text using the configured LLM provider.

        Args:
            prompt: User message prompt.
            system_instruction: Optional system level instructions.

        Returns:
            The generated response content as a string.
        """
        try:
            if self.provider == "gemini":
                # Using gemini-2.5-flash as default
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
                self.active_provider = "Gemini (gemini-2.5-flash)"
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt, config=config
                )
                return response.text or ""

            elif self.provider == "openai":
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                self.active_provider = "OpenAI (gpt-4o-mini)"
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini", messages=messages
                )
                return response.choices[0].message.content or ""

            elif self.provider == "nvidia":
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                model_name = os.environ.get(
                    "NVIDIA_MODEL_NAME", "nvidia/nemotron-3-ultra-550b-a55b"
                )

                try:
                    self.active_provider = f"NVIDIA NIM ({model_name.split('/')[-1]})"
                    # Stream completion to capture reasoning step and content
                    completion = self.client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=1,
                        top_p=0.95,
                        max_tokens=4096,
                        extra_body={
                            "chat_template_kwargs": {"enable_thinking": True},
                            "reasoning_budget": 4096,
                        },
                        stream=True,
                    )

                    full_text = []
                    for chunk in completion:
                        if not chunk.choices:
                            continue
                        reasoning = getattr(
                            chunk.choices[0].delta, "reasoning_content", None
                        )
                        if reasoning:
                            print(reasoning, end="", flush=True)
                        content = chunk.choices[0].delta.content
                        if content is not None:
                            print(content, end="", flush=True)
                            full_text.append(content)
                    print()  # Final newline
                    return "".join(full_text)
                except Exception as nvidia_error:
                    print(
                        f"NVIDIA generation failed ({nvidia_error}). Switching to Pollinations fallback..."
                    )
                    return self._call_pollination(
                        prompt, system_instruction, stream=False
                    )

            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
        except Exception as e:
            # Return descriptive error so background job can record it
            return f"Error during generation via provider {self.provider}: {str(e)}"

    def generate_embedding(self, text: str) -> list[float]:
        """Generate a 4096-dimensional vector embedding for the input text.

        Args:
            text: Input string to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        # Ensure input is not empty
        if not text.strip():
            return [0.0] * 4096

        # Crop input text to a safe character limit (approx 2500-3000 tokens)
        cropped_text = text[:10000]

        try:
            vec = []
            if self.provider == "gemini":
                response = self.client.models.embed_content(
                    model="text-embedding-004", contents=cropped_text
                )
                if hasattr(response, "embeddings") and len(response.embeddings) > 0:
                    vec = response.embeddings[0].values
                elif hasattr(response, "embedding") and hasattr(
                    response.embedding, "values"
                ):
                    vec = response.embedding.values
                else:
                    vec = [0.0] * 768

            elif self.provider == "openai":
                # request 768 dimensions directly from text-embedding-3-small
                response = self.client.embeddings.create(
                    input=[cropped_text], model="text-embedding-3-small", dimensions=768
                )
                vec = response.data[0].embedding

            elif self.provider == "nvidia":
                model_name = os.environ.get(
                    "NVIDIA_EMBED_MODEL_NAME", "nvidia/nv-embedcode-7b-v1"
                )
                response = self.client.embeddings.create(
                    input=[cropped_text],
                    model=model_name,
                    encoding_format="float",
                    extra_body={"input_type": "query", "truncate": "END"},
                )
                vec = response.data[0].embedding

            else:
                raise ValueError(f"Unsupported embedding provider: {self.provider}")

            # Standardize length to exactly 4096 dimensions for PGVector
            if len(vec) > 4096:
                return vec[:4096]
            elif len(vec) < 4096:
                return vec + [0.0] * (4096 - len(vec))
            return vec

        except Exception as e:
            # Log and return empty vector on error
            print(f"Embedding error: {e}. Returning empty 4096-dimensional vector.")
            return [0.0] * 4096

    def generate_text_stream(self, prompt: str, system_instruction: str | None = None):
        """Yield text chunks dynamically using the configured LLM provider."""
        try:
            if self.provider == "gemini":
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
                self.active_provider = "Gemini (gemini-2.5-flash)"
                response = self.client.models.generate_content_stream(
                    model="gemini-2.5-flash", contents=prompt, config=config
                )
                for chunk in response:
                    yield chunk.text or ""

            elif self.provider == "openai":
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                self.active_provider = "OpenAI (gpt-4o-mini)"
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini", messages=messages, stream=True
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

            elif self.provider == "nvidia":
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                model_name = os.environ.get(
                    "NVIDIA_MODEL_NAME", "nvidia/nemotron-3-ultra-550b-a55b"
                )
                self.active_provider = f"NVIDIA NIM ({model_name.split('/')[-1]})"
                try:
                    completion = self.client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=1,
                        top_p=0.95,
                        max_tokens=4096,
                        extra_body={
                            "chat_template_kwargs": {"enable_thinking": True},
                            "reasoning_budget": 4096,
                        },
                        stream=True,
                    )
                    for chunk in completion:
                        if chunk.choices:
                            content = chunk.choices[0].delta.content
                            if content is not None:
                                yield content
                except Exception as nvidia_error:
                    print(
                        f"NVIDIA streaming failed ({nvidia_error}). Switching to Pollinations fallback..."
                    )
                    for chunk in self._call_pollination(
                        prompt, system_instruction, stream=True
                    ):
                        yield chunk
            else:
                # Default fallback
                yield self.generate_text(prompt, system_instruction)
        except Exception as e:
            print(f"Streaming error: {e}")
            yield f"Error during streaming: {str(e)}"

    def _call_pollination(
        self, prompt: str, system_instruction: str | None = None, stream: bool = False
    ):
        """Call Pollinations AI as a backup model."""
        self.active_provider = "Pollinations AI (OpenAI)"
        print("Switching to backup model: Pollinations AI...")
        try:
            api_key = (
                os.getenv("POLLINATIONS_API_KEY") or
                os.getenv("POLLINATION_API_KEY") or
                os.getenv("OPENAI_API_KEY") or
                "pollinations"
            )
            if not os.environ.get("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = api_key

            client = OpenAI(
                base_url="https://gen.pollinations.ai/v1",
                api_key=api_key,
            )
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            if stream:
                completion = client.chat.completions.create(
                    model="openai", messages=messages, stream=True
                )
                for chunk in completion:
                    if chunk.choices:
                        content = chunk.choices[0].delta.content
                        if content is not None:
                            yield content
            else:
                response = client.chat.completions.create(
                    model="openai", messages=messages, stream=False
                )
                return response.choices[0].message.content or ""
        except Exception as e:
            err_msg = f"Pollinations fallback failed: {str(e)}"
            print(err_msg)
            if stream:
                yield err_msg
            else:
                return err_msg
