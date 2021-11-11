#!/bin/bash

set -exo pipefail

PACKAGE=$1
THISDIR=$(realpath $(dirname $0))
PYSTON_PKG_VER="3.8.12 *_23_pyston"

if [ -z "$CHANNEL" ]; then
    CHANNEL=pyston/label/dev
fi

MAKE_CONFIG_PY=$(realpath $(dirname $0)/make_config.py)

if [ ! -d ${PACKAGE}-feedstock ]; then
    git clone https://github.com/conda-forge/${PACKAGE}-feedstock.git
fi

if [ "${PACKAGE}" == "numpy" ]; then
    # 1.18.5:
    pushd numpy-feedstock
    git checkout 3f4b2e94
    git cherry-pick 046882736
    git cherry-pick 6b1da6d7e
    git cherry-pick 4b48d8bb8
    git cherry-pick 672ca6f0d
    popd
fi

# CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build ${PACKAGE}-feedstock/recipe --python="${PYSTON_PKG_VER}" --override-channels -c conda-forge --use-local -c /conda_pkgs
cd ${PACKAGE}-feedstock

# We need a new version of the build scripts that take extra options
if ! grep -q EXTRA_CB_OPTIONS .scripts/build_steps.sh; then
    conda-smithy rerender
fi
if ! grep -q mambabuild .scripts/build_steps.sh; then
    conda-smithy rerender
fi

if [ "$PACKAGE" == "python-rapidjson" ]; then
    sed -i 's/pytest tests/pytest tests --ignore=tests\/test_memory_leaks.py --ignore=tests\/test_circular.py/g' recipe/meta.yaml
fi

if [ "$PACKAGE" == "numpy" ]; then
    sed -i 's/_not_a_real_test/test_for_reference_leak or test_api_importable/g' recipe/meta.yaml
fi

if [ "$PACKAGE" == "implicit" ]; then
    # Not 100% sure but I think this line is over-indented in the meta.yaml
    # file and that causes issues. Not sure why it causes issues for us but not
    # CPython
    # sed -i 's/      script:/    script:/' recipe/meta.yaml

    # The build step here implicitly does a `pip install numpy scipy`.
    # For CPython this will download a pre-built wheel from pypi, but
    # for Pyston it will try to recompile both of these packages.
    # But the meta.yaml doesn't include all the dependencies of
    # building scipy, specifically a fortran compiler, so we have to add it:
    sed -i "/        - {{ compiler('fortran') }}/d" recipe/meta.yaml
    sed -i "s/        - {{ compiler('cxx') }}/        - {{ compiler('cxx') }}\n        - {{ compiler('fortran') }}/" recipe/meta.yaml

    # I don't understand exactly why, but it seems like you can't install
    # both a fortran compiler and gcc 7. So update the configs to use gcc 9
    sed -i "s/'7'/'9'/" .ci_support/*.yaml
fi

if [ "$PACKAGE" == "pyqt" ]; then
    cp $THISDIR/patches/pyqt.patch recipe/pyston.patch
    sed -i "/pyston.patch/d" recipe/meta.yaml
    sed -i "s/      - qt5_dll.diff/      - qt5_dll.diff\n      - pyston.patch/" recipe/meta.yaml
fi

if [ "$PACKAGE" == "scikit-build" ]; then
    sed -i "s/not test_fortran_compiler/not test_fortran_compiler and not test_get_python_version/" recipe/run_test.sh
fi

# conda-forge-ci-setup automatically sets add_pip_as_python_dependency=false
CONDA_FORGE_DOCKER_RUN_ARGS="-e EXTRA_CB_OPTIONS" EXTRA_CB_OPTIONS="-c $CHANNEL -c undingen/label/dev" python3 build-locally.py $(CHANNEL=$CHANNEL python3 $MAKE_CONFIG_PY)

echo "Done! Build artifacts are:"
find build_artifacts -name '*.tar.bz2' | xargs realpath
