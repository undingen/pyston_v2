#include "Python.h"
extern void* call_function_ceval_no_kwnumpyProfile_hook;
extern void* call_method_ceval_no_kwnumpyProfile_hook;

PyObject* call_function_ceval_no_kwNumpyProfile(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);

PyMODINIT_FUNC PyInit_numpy_pyston_init(void) {
   fprintf(stderr, "PyInit_numpy_pyston_init\n");
   call_function_ceval_no_kwnumpyProfile_hook = call_function_ceval_no_kwNumpyProfile;
   Py_RETURN_NONE;
}

