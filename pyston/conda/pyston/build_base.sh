#!/bin/sh
set -eux

# pyston should not compile llvm and bolt but instead use the conda packages
export PYSTON_USE_SYS_BINS=1

# the conda compiler is named 'x86_64-conda-linux-gnu-cc' but cpython compares
# the name to *gcc*, *clang* in the configure file - so we have to use the real name.
# Code mostly copied from the cpython recipe.
AR=$(basename "${AR}")
CC=$(basename "${GCC}")
CXX=$(basename "${CXX}")
RANLIB=$(basename "${RANLIB}")
READELF=$(basename "${READELF}")

# overwrite default conda build flags else the bolt instrumented binary will not work
CFLAGS="-isystem ${PREFIX}/include"
LDFLAGS="-Wl,-rpath,${PREFIX}/lib -Wl,-rpath-link,${PREFIX}/lib -L${PREFIX}/lib"
CPPFLAGS="-isystem ${PREFIX}/include"

# without this line we can't find zlib and co..
CPPFLAGS=${CPPFLAGS}" -I${PREFIX}/include"

rm -rf build

which clang
clang -E -v - </dev/null
$CC -E -v - </dev/null


# This causes setup.py to query the sysroot directories from the compiler, something which
# IMHO should be done by default anyway with a flag to disable it to workaround broken ones.
# Technically, setting _PYTHON_HOST_PLATFORM causes setup.py to consider it cross_compiling
if [[ -n ${HOST} ]]; then
  if [[ ${HOST} =~ .*darwin.* ]]; then
    # Even if BUILD is .*darwin.* you get better isolation by cross_compiling (no /usr/local)
    IFS='-' read -r host_arch host_os host_kernel <<<"${HOST}"
    export _PYTHON_HOST_PLATFORM=darwin-${host_arch}
  else
    IFS='-' read -r host_arch host_vendor host_os host_libc <<<"${HOST}"
    export _PYTHON_HOST_PLATFORM=${host_os}-${host_arch}
  fi
fi
#export CONFIGURE_EXTRA_FLAGS='--build=${BUILD} --host=${HOST} --enable-ipv6 --with-tzpath=${PREFIX}/share/zoneinfo --with-system-ffi --enable-loadable-sqlite-extensions --with-tcltk-includes="-I${PREFIX}/include" --with-tcltk-libs="-L${PREFIX}/lib -ltcl8.6 -ltk8.6" --with-platlibdir=lib'
CONFIGURE_EXTRA_FLAGS='--build=${BUILD} --host=${HOST} --with-tzpath=${PREFIX}/share/zoneinfo --with-system-ffi --enable-loadable-sqlite-extensions --with-tcltk-includes="-I${PREFIX}/include" --with-tcltk-libs="-L${PREFIX}/lib -ltcl8.6 -ltk8.6" --with-platlibdir=lib'

if [ "${PYSTON_UNOPT_BUILD}" = "1" ]; then
    make -j`nproc` unopt
    make -j`nproc` cpython_testsuite
    OUTDIR=${SRC_DIR}/build/unopt_install/usr
    PYSTON=${OUTDIR}/bin/python3
else
    RELEASE_PREFIX=${PREFIX} make -j`nproc` release
    RELEASE_PREFIX=${PREFIX} make -j`nproc` cpython_testsuite_release
    OUTDIR=${SRC_DIR}/build/release_install${PREFIX}
    PYSTON=${OUTDIR}/bin/python3.bolt
fi

cp $PYSTON ${PREFIX}/bin/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}
ln -s ${PREFIX}/bin/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2} ${PREFIX}/bin/pyston
ln -s ${PREFIX}/bin/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2} ${PREFIX}/bin/pyston3

cp -r ${OUTDIR}/include/* ${PREFIX}/include/
cp -r ${OUTDIR}/lib/* ${PREFIX}/lib/

# remove pip
rm -r ${PREFIX}/lib/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}/site-packages/pip*

# remove pystons site-packages directory and replace it with a symlink to cpythons default site-packages directory
# we copy in our site-package/README.txt and package it to make sure the directory get's created.
mkdir -p ${PREFIX}/lib/python${PYTHON_VERSION2}/site-packages || true
cp ${PREFIX}/lib/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}/site-packages/README.txt ${PREFIX}/lib/python${PYTHON_VERSION2}/site-packages
rm -r ${PREFIX}/lib/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}/site-packages
ln -s ${PREFIX}/lib/python${PYTHON_VERSION2}/site-packages/ ${PREFIX}/lib/python${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}/site-packages
