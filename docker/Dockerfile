# The PrismML executable, GGUF and upstream scripts are mounted read-only
# from the user's existing Bonsai-demo; do not use a stock llama.cpp image.
FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         ca-certificates curl libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /bonsai
