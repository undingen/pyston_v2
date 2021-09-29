#include "Python.h"
#include "numpy/ndarraytypes.h"
#include "numpy/ufuncobject.h"
#include "numpy/npy_3kcompat.h"

extern void* call_function_ceval_no_kwnumpyProfile_hook;
extern void* call_method_ceval_no_kwnumpyProfile_hook;

PyObject* call_function_ceval_no_kwNumpyProfile(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);
PyObject* call_method_ceval_no_kwNumpyProfile(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "numpy_pyston",
    NULL,
    -1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
};


PyMODINIT_FUNC PyInit_numpy_pyston(void) {
    fprintf(stderr, "PyInit_numpy_pyston: setting up tracing hook\n");

    PyObject *m = PyModule_Create(&moduledef);
    if (!m) {
        return NULL;
    }

    // we have to import this or PyUFunc_Type will not point to the correct place
    import_array();
    import_umath();

    call_function_ceval_no_kwnumpyProfile_hook = call_function_ceval_no_kwNumpyProfile;
    call_method_ceval_no_kwnumpyProfile_hook = call_method_ceval_no_kwNumpyProfile;
    return m;
}

