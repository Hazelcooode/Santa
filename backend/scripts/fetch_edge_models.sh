#!/usr/bin/env bash
# Download the on-device laundry models + runtime into app/static/vendor/ (git-ignored).
#   transformers.js 3.8.1 (Apache-2.0, bundles ONNX Runtime Web)
#   Xenova/owlvit-base-patch32  quantized ONNX (Apache-2.0)   - finds garments
#   Xenova/clip-vit-base-patch32 quantized ONNX (MIT)         - names them
set -euo pipefail
cd "$(dirname "$0")/../app/static"
V=vendor; HF=https://huggingface.co
mkdir -p "$V" && tmp=$(mktemp -d)
(cd "$tmp" && npm pack --silent @huggingface/transformers@3.8.1 >/dev/null && tar xzf huggingface-transformers-3.8.1.tgz)
cp "$tmp"/package/dist/{transformers.min.js,ort-wasm-simd-threaded.jsep.mjs,ort-wasm-simd-threaded.jsep.wasm} "$V/"
cp "$tmp"/package/LICENSE "$V/LICENSE-transformers.js"; rm -rf "$tmp"
get() { mkdir -p "$(dirname "$V/models/$1/$2")"; [ -s "$V/models/$1/$2" ] || curl -fL --retry 3 -o "$V/models/$1/$2" "$HF/$1/resolve/main/$2"; }
for m in Xenova/owlvit-base-patch32 Xenova/clip-vit-base-patch32; do
  for f in config.json tokenizer.json tokenizer_config.json preprocessor_config.json special_tokens_map.json; do get "$m" "$f"; done
done
get Xenova/owlvit-base-patch32 onnx/model_quantized.onnx
get Xenova/clip-vit-base-patch32 onnx/vision_model_quantized.onnx
get Xenova/clip-vit-base-patch32 onnx/text_model_quantized.onnx
du -sh "$V"
