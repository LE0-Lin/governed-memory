"""Optional pinned local generation, using the standard Transformers chat interface."""

import asyncio
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class GenerationProfile:
    model: str
    revision: str


GENERATION_PROFILES = {
    "small": GenerationProfile(
        "Qwen/Qwen2.5-0.5B-Instruct", "7ae557604adf67be50417f59c2c2f167def9a775"
    ),
    "standard": GenerationProfile(
        "Qwen/Qwen2.5-1.5B-Instruct", "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
    ),
    "judge": GenerationProfile(
        "Qwen/Qwen3-4B-Instruct-2507", "cdbee75f17c01a7cc42f958dc650907174af0554"
    ),
}


@dataclass(frozen=True)
class GeneratedText:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class TransformersGenerator:
    def __init__(self, profile="small", cache_dir=None, device="cpu", max_input_tokens=4096):
        if profile not in GENERATION_PROFILES:
            raise ValueError(f"unknown generation profile: {profile}")
        if device not in {"cpu", "cuda"}:
            raise ValueError("generation device must be cpu or cuda")
        self.profile = GENERATION_PROFILES[profile]
        self.cache_dir, self.device = cache_dir, device
        self.max_input_tokens = max_input_tokens
        self.model = self.tokenizer = None
        self._tokenizer_data = None
        self.lock = Lock()
        self.metadata = {
            "profile": profile,
            "model": self.profile.model,
            "revision": self.profile.revision,
            "device": device,
            "dtype": "bfloat16" if device == "cuda" else "float32",
            "max_input_tokens": max_input_tokens,
            "decoding": "greedy",
            "concurrency": 1,
        }

    def _load(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("install local generation with: uv sync --extra models") from exc
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA generation was requested but is unavailable")
        dtype = torch.float32
        if self.device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.get_device_capability(0)[0] >= 8 else torch.float16
        self.metadata["dtype"] = str(dtype).removeprefix("torch.")
        torch.set_num_threads(2)
        common = {
            "revision": self.profile.revision,
            "cache_dir": self.cache_dir,
            "token": False,
            "trust_remote_code": False,
        }
        self.tokenizer = AutoTokenizer.from_pretrained(self.profile.model, **common)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.profile.model,
            **common,
            dtype=dtype,
            device_map=self.device,
            use_safetensors=True,
            attn_implementation="sdpa",
        ).eval()

    def _json_constraint(self, schema):
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import (
            build_token_enforcer_tokenizer_data,
            build_transformers_prefix_allowed_tokens_fn,
        )

        if self._tokenizer_data is None:
            self._tokenizer_data = build_token_enforcer_tokenizer_data(self.tokenizer)
        # Tokenizer data is reusable; parser/decoding state belongs to this request only.
        return build_transformers_prefix_allowed_tokens_fn(
            self._tokenizer_data, JsonSchemaParser(schema)
        )

    def _generate(self, messages, max_new_tokens, json_schema):
        # One model instance serves requests sequentially; concurrent decoding is unsupported.
        with self.lock:
            if self.model is None:
                self._load()
            import torch

            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.device)
            prompt_tokens = inputs["input_ids"].shape[-1]
            if prompt_tokens > self.max_input_tokens:
                raise ValueError("generation prompt exceeds the configured input limit")
            constraints = (
                {"prefix_allowed_tokens_fn": self._json_constraint(json_schema)}
                if json_schema is not None
                else {}
            )
            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    do_sample=False,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=self.tokenizer.eos_token_id,
                    **constraints,
                )
            tokens = outputs[0, prompt_tokens:].tolist()
            eos = self.model.generation_config.eos_token_id
            eos = {eos} if isinstance(eos, int) else set(eos or [])
            return GeneratedText(
                self.tokenizer.decode(tokens, skip_special_tokens=True),
                prompt_tokens,
                len(tokens),
                "stop" if tokens and tokens[-1] in eos else "length",
            )

    async def generate(self, messages, max_new_tokens=384, *, json_schema=None):
        if not 1 <= max_new_tokens <= 1024:
            raise ValueError("max_new_tokens must be 1..1024")
        return await asyncio.to_thread(self._generate, messages, max_new_tokens, json_schema)
