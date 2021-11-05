#!/bin/bash
set -eux

# pyston should not compile llvm and bolt but instead use the conda packages
export PYSTON_USE_SYS_BINS=1

rm -rf build

#########################################################################################
# Following code is mostly copied from the cpython recipe with some changes
# https://github.com/AnacondaRecipes/python-feedstock/blob/master-3.8/recipe/build_base.sh

# Remove bzip2's shared library if present,
# as we only want to link to it statically.
# This is important in cases where conda
# tries to update bzip2.
#find "${PREFIX}/lib" -name "libbz2*${SHLIB_EXT}*" | xargs rm -fv {}

# Prevent lib/python${VER}/_sysconfigdata_*.py from ending up with full paths to these things
# in _build_env because _build_env will not get found during prefix replacement, only _h_env_placeh ...
AR=$(basename "${AR}")

# the conda compiler is named 'x86_64-conda-linux-gnu-cc' but cpython compares
# the name to *gcc*, *clang* in the configure file - so we have to use the real name.
CC=$(basename "${GCC}")
CXX=$(basename "${CXX}")
RANLIB=$(basename "${RANLIB}")
READELF=$(basename "${READELF}")

CPPFLAGS="-isystem ${PREFIX}/include"

CFLAGS=" -pipe"
#CFLAGS=" -march=nocona -mtune=haswell -ftree-vectorize -ffunction-sections -pipe"
#CFLAGS=" -march=nocona -mtune=haswell -ftree-vectorize -O2 -ffunction-sections -pipe"


#asdadas
export CPPFLAGS CFLAGS CXXFLAGS LDFLAGS

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
declare -a _common_configure_args
_common_configure_args+=(--build=${BUILD})
_common_configure_args+=(--host=${HOST})
_common_configure_args+=(--enable-ipv6)
_common_configure_args+=(--with-computed-gotos)
_common_configure_args+=(--with-system-ffi)
_common_configure_args+=(--enable-loadable-sqlite-extensions)
_common_configure_args+=(--with-openssl="${PREFIX}")
_common_configure_args+=(--with-tcltk-includes="-I${PREFIX}/include")
_common_configure_args+=("--with-tcltk-libs=-L${PREFIX}/lib -ltcl8.6 -ltk8.6")

#########################################################################################

# overwrite default conda build flags else the bolt instrumented binary will not work
#CFLAGS="-isystem ${PREFIX}/include"
#LDFLAGS="-Wl,-rpath,${PREFIX}/lib -Wl,-rpath-link,${PREFIX}/lib -L${PREFIX}/lib"

# without this line we can't find zlib and co..
CPPFLAGS=${CPPFLAGS}" -I${PREFIX}/include"

export CONFIGURE_EXTRA_FLAGS='${_common_configure_args[@]} --oldincludedir=${BUILD_PREFIX}/${HOST}/sysroot/usr/include'

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

#########################################################################################
# Following code is mostly copied from the cpython recipe with some changes
# https://github.com/AnacondaRecipes/python-feedstock/blob/master-3.8/recipe/build_base.sh

VER=${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}
VERABI=${VER}

# Remove test data to save space
# Though keep `support` as some things use that.
# TODO :: Make a subpackage for this once we implement multi-level testing.
pushd ${PREFIX}/lib/python${VER}
  mkdir test_keep
  mv test/__init__.py test/support test/test_support* test/test_script_helper* test_keep/
  rm -rf test */test
  mv test_keep test
popd

# Size reductions:
# pushd ${PREFIX}
#   if [[ -f lib/libpython${VERABI}.a ]]; then
#     chmod +w lib/libpython${VERABI}.a
#     ${STRIP} -S lib/libpython${VERABI}.a
#   fi
#   CONFIG_LIBPYTHON=$(find lib/python${VER}/config-${VERABI}* -name "libpython${VERABI}.a")
#   if [[ -f lib/libpython${VERABI}.a ]] && [[ -f ${CONFIG_LIBPYTHON} ]]; then
#     chmod +w ${CONFIG_LIBPYTHON}
#     rm ${CONFIG_LIBPYTHON}
#   fi
# popd
#########################################################################################
