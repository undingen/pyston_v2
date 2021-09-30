import glob
import os
def configuration(parent_package='', top_path=None):
    import numpy
    from numpy.distutils.misc_util import Configuration

    config = Configuration(None,#'numpy_pyston',
                           parent_package,
                           top_path)

    umath_so = max(glob.glob( "../../build/unopt_env/lib/python3.8-pyston2.3/site-packages/numpy-*/numpy/core/_multiarray_umath.pyston-23-x86_64-linux-gnu.so"))
    config.add_extension('numpy_pyston', ['aot_numpy_init.c'], extra_objects=['../../build/aot_numpy/aot_numpy_all.o', os.path.abspath(os.path.join(os.path.dirname(__file__), umath_so))])

    return config

if __name__ == "__main__":
    from numpy.distutils.core import setup
    setup(configuration=configuration)
