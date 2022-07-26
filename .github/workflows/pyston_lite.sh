#!/bin/bash
set -eux

# workaround for setuptools 60
export SETUPTOOLS_USE_DISTUTILS=stdlib

export DEBIAN_FRONTEND=noninteractive

PYTHON_VERSION=$1

# install dependencies
sudo apt-get update

sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y build-essential luajit software-properties-common

if [ $PYTHON_VERSION == "3.8" ] # it's the system python of 20.04 (deadsnakes does not provide it)
then
    sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y python3.8-full python3.8-dev libpython3.8-testsuite python3-pip
else
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
    # deadsnakes packages have slightly different name
    sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y python${PYTHON_VERSION}-full python${PYTHON_VERSION}-dev python${PYTHON_VERSION}-venv libpython${PYTHON_VERSION}-testsuite
    sudo python${PYTHON_VERSION} -m ensurepip
fi

sudo python${PYTHON_VERSION} -m pip install virtualenv

sudo chown -R `whoami` /pyston_dir

cd /pyston_dir/pyston/pyston_lite

if [ -z ${NOBOLT+x} ]; then
    make -C ../.. -j$(nproc) bolt
fi

PYTHON=python${PYTHON_VERSION} make test -j$(nproc)
