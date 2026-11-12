# Recorded local GPU environment

The full cleaned-S runs use Windows 11, CPython 3.12.0, one RTX 4080 Laptop GPU
with 12 GB VRAM and NVIDIA driver 581.80. Generation uses bfloat16; retrieval
and generation share the same device, with one sequential caller. The laptop
has 16 GB system RAM. Test containers are stopped during timed inference.
Per-history indexing, query time, generation tokens and failures are recorded
separately. This is a local measurement, not a throughput or serving-capacity
claim.

The default `uv.lock` uses CPU PyTorch. The measured GPU environment is separate:
PyTorch 2.8.0+cu128, Transformers 5.22.2, Sentence Transformers 5.7.0,
accelerate 1.15.0 and NumPy 2.5.4. Full Windows-only exports:

- [Unconstrained v1](environments/windows-cu128-v1.txt).
- [Structured v2](environments/windows-cu128-v2.txt): the same packages plus
  interegular 0.3.3 and LM Format Enforcer at upstream commit
  `2597936f55da0e3cab8a6047eba91b2ecdfe888a`.

To recreate the v2 environment with uv 0.12.5, from the matching source commit:

```powershell
uv venv --python 3.12 .local/reproduce-gpu
uv pip install --python .local/reproduce-gpu/Scripts/python.exe --no-sources --torch-backend cu128 -r eval/environments/windows-cu128-v2.txt
uv pip install --python .local/reproduce-gpu/Scripts/python.exe --no-deps -e .
& .local/reproduce-gpu/Scripts/python.exe -m eval.full_run --device cuda --dataset .local/longmemeval/longmemeval_s_cleaned.json --output .local/reproduction --model-cache .local/model-cache --generation-cache .local/generation-cache
```

The exports intentionally omit the editable application itself. Install it from
the inference commit recorded in `provenance.json`. `--no-sources` bypasses the
project's CPU-wheel mapping; uv's [PyTorch backend support](https://docs.astral.sh/uv/guides/integration/pytorch/)
selects CUDA wheels. Do not run `uv sync` into this measured environment: that
would restore the CPU lock. The v1 run uses source commit `54b2593` and the v1
requirements, before the format constraint existed.

The original CUDA wheel was downloaded from the official PyTorch index and
verified before installation. Its filename is
`torch-2.8.0+cu128-cp312-cp312-win_amd64.whl`, SHA-256
`0ad925202387f4e7314302a1b4f8860fa824357f9b1466d7992bf276370ebcff`.
Weights use the exact model revisions in the manifests. No model weights or
local credentials are distributed in this repository.
