import google.generativeai as genai
from google.api_core import exceptions
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
import threading


class AsyncGeminiClient:
    """
    High-throughput async Gemini client that rotates keys immediately after sending requests
    """

    def __init__(
        self,
        api_keys: List[str],
        model_name: str = "gemini-2.5-flash-lite-preview-06-17",
    ):
        if not api_keys:
            raise ValueError("API key list cannot be empty.")

        self.api_keys = api_keys
        self.model_name = model_name
        self.current_key_index = 0
        self.lock = threading.Lock()

        # Pre-configure all models
        self.models = {}
        for i, api_key in enumerate(api_keys):
            genai.configure(api_key=api_key)
            self.models[i] = genai.GenerativeModel(self.model_name)

        self.generation_config = genai.types.GenerationConfig(
            candidate_count=1,
            temperature=0.7,
        )

        print(f"AsyncGeminiClient initialized with {len(self.api_keys)} keys.")

    def _get_next_key_and_model(self):
        """Get the next key/model and immediately rotate for high throughput"""
        with self.lock:
            current_index = self.current_key_index
            # Rotate immediately for next request
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

            # Re-configure for the current key (needed for thread safety)
            genai.configure(api_key=self.api_keys[current_index])
            return current_index, self.models[current_index]

    def ask_async(self, prompt: str) -> Dict[str, Any]:
        """
        Send a request asynchronously and return immediately with future
        """
        key_index, model = self._get_next_key_and_model()

        # Create a future for this request
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._make_request, prompt, model, key_index)

        return {"future": future, "key_index": key_index, "prompt": prompt}

    def _make_request(self, prompt: str, model, key_index: int) -> Dict[str, Any]:
        """Internal method to make the actual API request"""
        try:
            response = model.generate_content(
                prompt, generation_config=self.generation_config
            )
            return {
                "status": "success",
                "response": response.text,
                "key_index": key_index,
                "prompt": prompt,
            }
        except exceptions.ResourceExhausted as e:
            return {
                "status": "rate_limited",
                "error": str(e),
                "key_index": key_index,
                "prompt": prompt,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "key_index": key_index,
                "prompt": prompt,
            }

    def ask_batch_async(self, prompts: List[str]) -> List[Dict[str, Any]]:
        """
        Send multiple requests asynchronously, rotating keys for each
        """
        requests = []

        for prompt in prompts:
            request = self.ask_async(prompt)
            requests.append(request)

        return requests

    def collect_results(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Collect results from async requests
        """
        results = []
        for request in requests:
            try:
                result = request["future"].result()
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "status": "error",
                        "error": str(e),
                        "key_index": request["key_index"],
                        "prompt": request["prompt"],
                    }
                )
        return results


class GeminiClient:
    """
    A class to interact with Google's Gemini API that automatically rotates API keys
    when a rate limit is encountered.
    """

    def __init__(
        self,
        api_keys: list[str],
        model_name: str = "gemini-2.5-flash-lite-preview-06-17",
    ):
        """
        Initializes the key rotator with a list of API keys.

        Args:
            api_keys (list[str]): A list of your Gemini API keys.
            model_name (str): The name of the Gemini model to use. Defaults to the latest Flash-Lite preview.

        Raises:
            ValueError: If the api_keys list is empty.
        """
        if not api_keys:
            raise ValueError("API key list cannot be empty.")

        self.api_keys = api_keys
        self.model_name = model_name
        self.current_key_index = 0
        self._initialize_client()
        print(
            f"GeminiClient initialized with {len(self.api_keys)} keys. Using model: '{self.model_name}'."
        )

    def _initialize_client(self):
        """Initializes the Gemini client with the current API key."""
        current_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=current_key)
        self.model = genai.GenerativeModel(self.model_name)

    def _rotate_key(self) -> bool:
        """
        Rotates to the next API key in the list.

        Returns:
            bool: True if rotation was successful, False if all keys have been tried.
        """
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._initialize_client()
        return True

    def ask(
        self, prompt: str, disable_thinking: bool = True, max_retries: int = None
    ) -> str:
        """
        Sends a prompt to the Gemini model and handles rate limit errors by rotating keys.
        Now rotates keys after every successful query to distribute load evenly.

        Args:
            prompt (str): The question or prompt to send to the model.
            disable_thinking (bool): If True, disables the 'thinking' feature for faster, cheaper responses [2].
            max_retries (int): The maximum number of keys to try before giving up. Defaults to the total number of keys.

        Returns:
            str: The text response from the Gemini model.

        Raises:
            RuntimeError: If all API keys are rate-limited or invalid.
        """
        if max_retries is None:
            max_retries = len(self.api_keys)

        generation_config = None
        if disable_thinking:
            generation_config = genai.types.GenerationConfig(
                candidate_count=1,
                temperature=0.7,
            )

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt, generation_config=generation_config
                )

                # Rotate key after successful query
                self._rotate_key()

                return response.text
            except exceptions.ResourceExhausted as e:
                if attempt < max_retries - 1:
                    self._rotate_key()
                    time.sleep(1)
                else:
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    self._rotate_key()
                else:
                    break

        raise RuntimeError("All API keys failed or are currently rate-limited.")
