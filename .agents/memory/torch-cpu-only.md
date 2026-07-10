---
name: torch-cpu-only
description: Why torch/torchvision must be installed as CPU-only wheels in this (and similar) Replit Python containers, and how packages that build against torch (basicsr, facexlib, gfpgan, realesrgan, etc.) need special handling.
---

Installing `torch` (and packages that depend on it, e.g. `basicsr`, `facexlib`, `gfpgan`, `realesrgan`) via the normal package installer or plain `pip install torch` pulls the default CUDA-enabled wheel plus NVIDIA CUDA/cuDNN/NCCL dependencies (700MB+). This reliably fails with `OSError: [Errno 122] Disk quota exceeded` in the Replit container.

**Why:** the container's writable disk quota is too small for the CUDA wheel set, and Replit's project GPUs aren't attached by default anyway — CPU-only torch is both sufficient and necessary here.

**How to apply:**
- Install torch/torchvision explicitly from the CPU wheel index: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`.
- Packages that build against torch at install time (basicsr, facexlib, gfpgan, realesrgan) must be installed with `--no-build-isolation` (so they see the already-installed CPU torch instead of re-resolving/downloading CUDA torch in an isolated build env), and typically also need `--break-system-packages` if using the project venv's pip directly.
- If the project has its own `installLanguagePackages`-driven `requirements.txt`, keep torch and torch-dependent packages commented out of it (with a note) — the standard installer resolves the file directly and will re-trigger the CUDA download otherwise.
