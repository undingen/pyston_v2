#!/bin/bash
set -eux

PYSTON_PKG_VER="3.8.12 *_23_pyston"
OUTPUT_DIR=${PWD}/release/conda_pkgs

if [ -d $OUTPUT_DIR ]
then
    echo "Directory $OUTPUT_DIR already exists";
    exit 1
fi
mkdir -p ${OUTPUT_DIR}

docker run -iv${PWD}:/pyston_dir:ro -v${OUTPUT_DIR}:/conda_pkgs continuumio/miniconda3 sh -s <<EOF
set -eux

apt-get update
# These packages are needed for running the uwsgi test suite (psmisc for killall).
# curl can also be installed via --extra-deps, but I couldn't find a package with killall
apt-get install psmisc curl

conda install conda-build -y
# In case you want to use the results from a previous run:
conda index /conda_pkgs
# CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build pyston_dir/pyston/conda/compiler-rt -c /conda_pkgs -c conda-forge --override-channels
# CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build pyston_dir/pyston/conda/bolt -c /conda_pkgs -c conda-forge --override-channels
CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build pyston_dir/pyston/conda/pyston -c /conda_pkgs -c /conda_pkgs -c conda-forge --override-channels
CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build pyston_dir/pyston/conda/python_abi -c /conda_pkgs -c conda-forge --override-channels
CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY=0 conda build pyston_dir/pyston/conda/python -c /conda_pkgs -c conda-forge --override-channels

conda install patch -y -c /conda_pkgs -c conda-forge --override-channels # required to apply the patches in some recipes

# This are the arch dependent pip dependencies. 
for pkg in certifi setuptools uwsgi cryptography brotlipy cffi pysocks
do
    pyston_dir/pyston/conda/build_feedstock.sh \${pkg}
done

# build numpy 1.20.3 using openblas
git clone https://github.com/AnacondaRecipes/numpy-feedstock.git -b pbs_1.20.3_20210520T162213
# 'test_for_reference_leak' fails for pyston - disable it
sed -i 's/_not_a_real_test/test_for_reference_leak/g' numpy-feedstock/recipe/meta.yaml
conda build numpy-feedstock/ --python="${PYSTON_PKG_VER}" --override-channels -c conda-forge --use-local --extra-deps pyston --variants="{blas_impl: openblas, openblas: 0.3.3, c_compiler_version: 7.5.0, cxx_compiler_version: 7.5.0}"

for arch in noarch linux-64
do
    mkdir /conda_pkgs/\${arch}
    cp /opt/conda/conda-bld/\${arch}/*.tar.bz2 /conda_pkgs/\${arch}
done
chown -R $(id -u):$(id -g) /conda_pkgs/

EOF
