#!/usr/bin/env bash
# SubSync — Linux başlatıcı
# Bu script nerede olursa olsun doğru dizini bulur

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_BASE="${HOME}/miniconda3"
ENV_NAME="subtitle-pipeline"

if [ -f "${CONDA_BASE}/etc/profile.d/conda.sh" ]; then
    source "${CONDA_BASE}/etc/profile.d/conda.sh"
    conda activate "${ENV_NAME}"
else
    echo "Conda bulunamadı: ${CONDA_BASE}"
    echo "conda init bash çalıştırıp tekrar deneyin."
    exit 1
fi

exec python "${SCRIPT_DIR}/tray.py"
