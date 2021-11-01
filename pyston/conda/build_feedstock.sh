#!/bin/bash

set -exo pipefail

PACKAGE=$1
PYSTON_PKG_VER="3.8.12 *_23_pyston"

if [ -z "$CHANNEL" ]; then
    CHANNEL=pyston/label/dev
fi

MAKE_CONFIG_PY=$(realpath $(dirname $0)/make_config.py)

if [ ! -d ${PACKAGE}-feedstock ]; then
    git clone https://github.com/conda-forge/${PACKAGE}-feedstock.git
fi
# CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build ${PACKAGE}-feedstock/recipe --python="${PYSTON_PKG_VER}" --override-channels -c conda-forge --use-local -c /conda_pkgs
cd ${PACKAGE}-feedstock

# We need a new version of the build scripts that take extra options
if ! grep -q EXTRA_CB_OPTIONS .scripts/build_steps.sh; then
    conda-smithy rerender
fi

if [ "$PACKAGE" == "python-rapidjson" ]; then
    sed -i 's/pytest tests/pytest tests --ignore=tests\/test_memory_leaks.py --ignore=tests\/test_circular.py/g' recipe/meta.yaml
fi
if [ "$PACKAGE" == "numpy" ]; then
    sed -i 's/_not_a_real_test/test_for_reference_leak/g' recipe/meta.yaml
fi

# conda-forge-ci-setup automatically sets add_pip_as_python_dependency=false
CONDA_FORGE_DOCKER_RUN_ARGS="-e EXTRA_CB_OPTIONS" EXTRA_CB_OPTIONS="-c $CHANNEL" python3 build-locally.py $(python3 $MAKE_CONFIG_PY)
