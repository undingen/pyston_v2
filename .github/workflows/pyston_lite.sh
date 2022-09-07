#!/bin/bash
set -eux

# workaround for setuptools 60
export SETUPTOOLS_USE_DISTUTILS=stdlib

export DEBIAN_FRONTEND=noninteractive

PYTHON_VERSION=$1

# install dependencies
sudo apt-get update

sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y build-essential luajit software-properties-common

if [ $PYTHON_VERSION != "3.8" ] # it's the system python of 20.04 (deadsnakes does not provide it)
then
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update

    #sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y python${PYTHON_VERSION}-full


    if [ $PYTHON_VERSION == "3.9" ]
    then
        # 3.9 does not bundle all files required to run the tests
        export ADDITIONAL_TESTS_TO_SKIP="test_lib2to3 test_peg_generator"
    fi

    if [ $PYTHON_VERSION == "3.10" ]
    then
        # this test is also failing without pyston_lite in the CI
        export ADDITIONAL_TESTS_TO_SKIP="test_sysconfig"
    fi
fi

sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y python${PYTHON_VERSION}-full python${PYTHON_VERSION}-dev python${PYTHON_VERSION}-venv libpython${PYTHON_VERSION}-testsuite python3-lib2to3 python3-distutils python3-pip

sudo --preserve-env=DEBIAN_FRONTEND apt-get install -y virtualenv libssl-dev libsqlite3-dev zlib1g-dev libwebp-dev libjpeg-dev python${PYTHON_VERSION}-gdbm python${PYTHON_VERSION}-tk tk-dev libgdbm-dev libgdbm-compat-dev liblzma-dev libbz2-dev nginx rustc time

#if [ $PYTHON_VERSION != "3.8" ]
#then
#    sudo python${PYTHON_VERSION} -m ensurepip
#fi

# update pip to latest version.
# Run into problems on 3.10 with older pip:
# ImportError: cannot import name 'html5lib' from 'pip._vendor'
sudo python${PYTHON_VERSION} -m pip install --upgrade pip

sudo chown -R `whoami` /pyston_dir

cd /pyston_dir/pyston/pyston_lite

if [ -z ${NOBOLT+x} ]; then
    make -C ../.. -j$(nproc) bolt
fi

PYTHON=python${PYTHON_VERSION} make test -j$(nproc)

# run external testsuites on amd64
if [ `uname -m` == x86_64 ]; then
    PYTHON=python${PYTHON_VERSION} make testsuites -j$(nproc)
fi
