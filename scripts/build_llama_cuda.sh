#!/usr/bin/env bash
# BRUCE RAG – llama.cpp CUDA Build via Ninja
# RFC-001 v1.1 §0: CUDA >= 12.1 erforderlich
# Compiler: nvcc (CUDA) + gcc (Host), Build-System: Ninja

set -euo pipefail

LLAMA_DIR="${HOME}/llama.cpp"
BUILD_DIR="${LLAMA_DIR}/build"

# --- 0. Voraussetzungen prüfen ---
echo "[BUILD] Checking prerequisites..."
command -v nvcc   || { echo "ERROR: nvcc not found. Install CUDA >= 12.1"; exit 1; }
command -v ninja  || { echo "ERROR: ninja not found. Install: apt install ninja-build"; exit 1; }
command -v cmake  || { echo "ERROR: cmake not found. Install: apt install cmake"; exit 1; }
nvcc --version | grep -E "release (12|13)" || echo "WARNING: CUDA < 12.1 detected!"

# --- 1. llama.cpp klonen oder updaten ---
if [ ! -d "${LLAMA_DIR}" ]; then
    echo "[BUILD] Cloning llama.cpp..."
    git clone https://github.com/ggml-org/llama.cpp.git "${LLAMA_DIR}"
else
    echo "[BUILD] Updating llama.cpp..."
    cd "${LLAMA_DIR}" && git pull
fi

cd "${LLAMA_DIR}"

# --- 2. CMake konfigurieren: Ninja + CUDA ---
# GPU Architectures:
#   sm_86 = RTX 3080 (Ampere)
#   sm_89 = RTX 4060 Ti (Ada Lovelace)
echo "[BUILD] Configuring CMake with Ninja + CUDA..."
cmake -B "${BUILD_DIR}" \
    -G Ninja \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES="86;89" \
    -DGGML_CUDA_F16=ON \
    -DGGML_NATIVE=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=ON

# --- 3. Bauen mit Ninja (parallel) ---
echo "[BUILD] Building with Ninja (parallel)..."
cmake --build "${BUILD_DIR}" --config Release --parallel "$(nproc)"

echo ""
echo "[BUILD] ✅ llama.cpp gebaut!"
echo "[BUILD]    Binaries: ${BUILD_DIR}/bin/"
echo "[BUILD]    Server:   ${BUILD_DIR}/bin/llama-server"
echo ""
echo "[BUILD] Nächster Schritt: Granite Modell herunterladen"
echo "[BUILD]   Ollama Pull: ollama pull granite4:350m-h-q8_0"
echo "[BUILD]   Oder GGUF direkt: siehe scripts/download_granite.sh"
