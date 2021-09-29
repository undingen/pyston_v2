def configuration(parent_package='', top_path=None):
    import numpy
    from numpy.distutils.misc_util import Configuration

    config = Configuration(None,#'numpy_pyston',
                           parent_package,
                           top_path)
    config.add_extension('numpy_pyston', ['aot_numpy_init.c'], extra_objects=['../../build/aot_numpy/aot_numpy_all.o'])

    return config

if __name__ == "__main__":
    from numpy.distutils.core import setup
    setup(configuration=configuration)
