#!/usr/bin/python3

import copy
import ctypes
import itertools
import multiprocessing.pool
import os
import sys

cmps = ["PyCmp_LT", "PyCmp_LE", "PyCmp_EQ", "PyCmp_NE",
        "PyCmp_GT", "PyCmp_GE", "PyCmp_IN", "PyCmp_NOT_IN",
        ]

# this functions return an int and we need to wrap it into a python object
funcs_need_res_wrap = [
    "PyObject_DelItem",
    "PyObject_SetItem",
]

VERBOSITY = 0


class NullObjectGuard(object):
    def getGuard(self, variable_name):
        return None

    def getAssumptions(self, variable_name):
        return [f'{variable_name} != NULL', f'((PyObject*){variable_name})->ob_refcnt > 0']
Unspecialized = NullObjectGuard()
NullObjectGuard.__init__ = None

class AttributeGuard(object):
    def __init__(self, accessor, guard_val):
        " accessor is expected to be something like '->ob_type' "
        self.accessor = accessor
        self.guard_val = guard_val

    def getGuard(self, variable_name):
        return f'{variable_name}{self.accessor} == {self.guard_val}'

    def getAssumptions(self, variable_name):
        return Unspecialized.getAssumptions(variable_name)

class TypeGuard(AttributeGuard):
    def __init__(self, guard_val):
        super(TypeGuard, self).__init__("->ob_type", guard_val)

class IdentityGuard(AttributeGuard):
    def __init__(self, guard_val):
        super(IdentityGuard, self).__init__("", guard_val)

# No guard here: this is how we specify that we already know what
# the type of an argument is
class AssumedTypeGuard:
    def __init__(self, type_name):
        self.type_name = type_name

    def getGuard(self, variable_name):
        return None

    def getAssumptions(self, variable_name):
        return Unspecialized.getAssumptions(variable_name) + [f'{variable_name} != NULL', f'Py_TYPE({variable_name}) == &{self.type_name}']

class Tuple1ElementIdentityGuard(IdentityGuard):
    """
    Guards that a tuple has a single entry with a specific guard_val
    """
    def __init__(self, guard_val):
        super(Tuple1ElementIdentityGuard, self).__init__(guard_val)

    def getGuard(self, variable_name):
        return f'PyTuple_CheckExact({variable_name}) && PyTuple_GET_SIZE({variable_name}) == 1 && PyTuple_GET_ITEM({variable_name}, 0){self.accessor} == {self.guard_val}'

class NullGuard(object):
    def getGuard(self, variable_name):
        return None

    def getAssumptions(self, variable_name):
        return []
UnspecializedCLong = NullGuard()
NullGuard.__init__ = None

class ObjectClass(object):
    c_type_name = "PyObject*"
    def __init__(self, name, guard, examples):
        # TODO: do some name-clash detection?
        # We currently have a name clash though between Float as an argument type
        # and Float as a callable value.  They're never used for the same function
        # Maybe it's ok to rely on the c compiler to catch name duplication later
        self.name = name
        self.guard = guard
        self.examples = examples

    def __repr__(self):
        return "<ObjectClass %s>" % self.name

class CLongClass(object):
    c_type_name = "Py_ssize_t"
    def __init__(self, examples):
        self.name = ""
        self.guard = UnspecializedCLong
        self.examples = examples

class Signature(object):
    def __init__(self, argument_classes, always_trace=[], guard_fail_fn_name=""):
        self.argument_classes = argument_classes
        self.nargs = len(argument_classes)
        self.name = "".join([cls.name for cls in argument_classes]) + str(self.nargs)
        self.always_trace = list(always_trace)
        self.guard_fail_fn_name = guard_fail_fn_name

    def getGuard(self, argument_names):
        names = list(argument_names)
        for i in range(len(names), len(self.argument_classes)):
            assert self.argument_classes[i].guard is Unspecialized
            names.append(None)

        assert len(names) == len(self.argument_classes), (len(names), len(self.argument_classes), argument_names)
        guards = [cls.guard.getGuard(name) for (cls, name) in zip(self.argument_classes, names)]
        guards = [g for g in guards if g]

        return " && ".join(guards)

    def getAssumptions(self, argument_names):
        assumptions = []
        for cls, name in zip(self.argument_classes, argument_names):
            assumptions += cls.guard.getAssumptions(name)

        return assumptions

    def getExamples(self):
        for x in itertools.product(*[cls.examples for cls in self.argument_classes]):
            yield copy.deepcopy(x)

    def getSpecialTracingCode(self, argument_names):
        return ()

    def __repr__(self):
        return "<Signature %s>" % self.name

class CompoundSignature(object):
    def __init__(self, signatures):
        self.signatures = signatures

        names = [s.name for s in signatures]
        assert len(set(names)) == 1
        self.name = names[0]

    def getGuard(self, argument_names):
        guards = [s.getGuard(argument_names) for s in self.signatures]
        assert len(set(guards)) == 1, set(guards)
        return guards[0]

    def getAssumptions(self, argument_names):
        assumptions = [s.getAssumptions(argument_names) for s in self.signatures]
        for i in range(1, len(assumptions)):
            assert assumptions[0] == assumptions[i], assumptions
        return assumptions[0]

    def getExamples(self):
        for s in self.signatures:
            yield from s.getExamples()

    def getSpecialTracingCode(self, argument_names):
        return ()

    @property
    def nargs(self):
        nargs = [s.nargs for s in self.signatures]
        assert len(set(nargs)) == 1
        return nargs[0]

    @property
    def always_trace(self):
        res = []
        for s in self.signatures:
            res.extend(s.always_trace)
        return res

# add special cases for 'isinstance'
# we add a fast PyType_FastSubclass() check which just checks tp_flags internally.
class IsInstanceSignature(Signature):
    def getSpecialTracingCode(self, argument_names):
        c = self.argument_classes[2]
        if c.guard != Unspecialized:
            var = argument_names[1]
            if isinstance(c, Tuple1ElementIdentityGuard):
                var = f"PyTuple_GET_ITEM({var}, 0)"
            code = [f"if (__builtin_expect(tstate->use_tracing, 0) == 0 && Py{c.name}_Check({var}))" + "{"]
            for arg in reversed(argument_names):
                code.append(f"  Py_DECREF({arg});")
            code.append("  Py_RETURN_TRUE;")
            code.append("}")
            return code
        return ()

class FunctionCases(object):
    def __init__(self, c_func_name, signatures):
        self.unspecialized_name = c_func_name
        if c_func_name.endswith("_ceval_no_kw"):
            self.specialized_base = c_func_name[:-len("_ceval_no_kw")]
        else:
            self.specialized_base = c_func_name
        self.signatures = signatures

    def getSignatures(self):
        for s in self.signatures:
            yield s, f'{self.specialized_base}{s.name}'

    @property
    def nargs(self):
        nargs = [s.nargs for s in self.signatures]
        assert len(set(nargs)) == 1, nargs
        return nargs[0]

    def __repr__(self):
        return f'<FunctionCases of {self.unspecialized_name} with {len(self.signatures)} cases>'

class Handler(object):
    def __init__(self, case, do_not_trace=[], always_trace=[]):
        self.case = case
        self.do_not_trace = list(do_not_trace)
        self.always_trace = list(always_trace)

    def setTracingOverwrites(self, signature):
        clearDoNotTrace()
        clearAlwaysTrace()
        for name in self.do_not_trace:
            addDoNotTrace(name.encode("ascii"))
        for name in self.always_trace + signature.always_trace:
            addAlwaysTrace(name.encode("ascii"))

    def getGuardFailFuncName(self, signature):
        suffix = getattr(signature, "guard_fail_fn_name", "")
        if suffix:
            return self.case.specialized_base + suffix
        else:
            return self.case.unspecialized_name

class NormalHandler(Handler):
    """
    Handler object for handling "normal" functions that take their arguments normally
    Such as PyNumber_Add
    """

    def __init__(self, case, do_not_trace=[], always_trace=[]):
        super(NormalHandler, self).__init__(case, do_not_trace, always_trace)
        self.need_res_wrap = case.unspecialized_name in funcs_need_res_wrap
        self.nargs = case.nargs

    def writePretraceFunctions(self, f):
        unspecialized_name = self.case.unspecialized_name
        for signature, name in self.case.getSignatures():
            arg_names = [f"o{i}" for i in range(signature.nargs)]
            parameters = [f"{cls.c_type_name} {name}" for (name, cls) in zip(arg_names, signature.argument_classes)]
            pass_args = ", ".join(arg_names)
            guard_fail_fn_name = self.getGuardFailFuncName(signature)
            print(f"{self._get_ret_type()} {name}({', '.join(parameters)})", "{", file=f)
            print(f"  if (unlikely(!({signature.getGuard(arg_names)})))", "{", file=f)
            print(f"    SET_JIT_AOT_FUNC({guard_fail_fn_name});", file=f)
            print(f"    PyObject* ret = {guard_fail_fn_name}({pass_args});", file=f)
            # this makes sure the compiler is not merging the two calls into a single one
            print(f"    __builtin_assume(ret != (PyObject*)0x1);", file=f)
            print(f"    return ret;",  file=f)
            print("  }", file=f)

            for assumption in signature.getAssumptions(arg_names):
                print(f"  __builtin_assume({assumption});", file=f)

            print(f'''  printf("Calling {name}!\\n");''', file=f)
            print(f"  return {unspecialized_name}({pass_args});", file=f)
            print("}", file=f)

    def createJitTarget(self, target_func, ntraces):
        return createJitTarget(target_func, self.case.nargs, ntraces)

    def call(self, target_func, args):
        assert len(args) == self.case.nargs

        target_func.argtypes = []
        converted_args = []
        for a in args:
            if isinstance(a, ctypes._SimpleCData):
                target_func.argtypes.append(type(a))
                converted_args.append(a)
            else:
                target_func.argtypes.append(ctypes.py_object)
                converted_args.append(ctypes.py_object(a))

        if not self.need_res_wrap:
            target_func.restype = ctypes.py_object

        return target_func(*converted_args)

    def _o_args_names(self):
        return [f"o{i}" for i in range(self.nargs)]

    def _args_names(self):
        return [name for (_, name) in self._args()]

    def _args(self):
        types = [ac.c_type_name for ac in self.case.signatures[-1].argument_classes]
        return list(zip(types, self._o_args_names()))

    def _get_func_sig(self, name):
        param = ", ".join([f"{type} {o}" for (type, o) in self._args()])
        return f"{self._get_ret_type()} {name}({param})"

    def _get_ret_type(self):
        if self.need_res_wrap:
            return "int"
        return "PyObject*"

    def write_profile_func(self, traced, header_f, profile_f):
        for signature, name in traced:
            print(f"{self._get_func_sig(name)};", file=profile_f)
            print(f"{self._get_func_sig(name)};", file=header_f)

        unspec_name = self.case.unspecialized_name
        profile_name = self.case.specialized_base + 'Profile'
        profile_func_sig = self._get_func_sig(profile_name)
        print(f"{profile_func_sig};", file=header_f)
        print(f"{profile_func_sig}", "{", file=profile_f)
        func_call_args = ', '.join(self._args_names())

        for spec, name in traced:
            checks = spec.getGuard([f"o{i}" for i in range(self.nargs)])
            print(f"  if ({checks})", "{", file=profile_f)
            print(f"    SET_JIT_AOT_FUNC({name});", file=profile_f)
            print(f"    return {name}({func_call_args});", file=profile_f)
            print("  }", file=profile_f)


        format_str = '%s ' * self.nargs
        dbg_args = ", ".join(
            f'{o}->ob_type->tp_name' for o in self._o_args_names())
        print(
            rf'  DBG("Missing {unspec_name} {format_str}\n", {dbg_args});', file=profile_f)
        print(f"  SET_JIT_AOT_FUNC({unspec_name});", file=profile_f)
        print(f"  return {unspec_name}({', '.join(self._args_names())});", file=profile_f)
        print("}", file=profile_f)

    def trace(self, jit_target, args, signature):
        self.setTracingOverwrites(signature)
        return runJitTarget(jit_target, *args, wrap_result=self.need_res_wrap)

class CallableHandler(Handler):
    """
    Handler object for callables, which have a special calling convention
    """

    def __init__(self, case):
        super(CallableHandler, self).__init__(case)

        for l in open(os.path.join(os.path.dirname(__file__), "numpy_trace_functions.txt")):
            self.always_trace.append(l.strip())

        self._jit_targets = {}

    def writePretraceFunctions(self, f):
        for signature, name in self.case.getSignatures():
            print(
                f"PyObject* {name}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=f)

        for signature, name in self.case.getSignatures():
            arg_names = ["f"] + [f"stack[-oparg+{i}]" for i in range(signature.nargs-1)]
            nargs = signature.nargs
            print(
                f"PyObject* {name}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg)", "{", file=f)
            print(f"  if (unlikely(oparg != {nargs-1}))", "{" , file=f)
            if name.startswith("call_method"):
                # CALL_METHOD can call the function with a different number of args
                # depending if LOAD_METHOD returned true or false which means we need
                # to add this additional guard.
                # we don't use getGuardFailFuncName() here because if the number of args is different
                # it's likely faster to just go to the untraced case.
                print(f"    SET_JIT_AOT_FUNC({self.case.unspecialized_name});", file=f)
                print(f"    PyObject* ret = {self.case.unspecialized_name}(tstate, stack, oparg);", file=f)
                # this makes sure the compiler is not merging the calls into a single one
                print(f"    __builtin_assume(ret != (PyObject*)0x1);", file=f)
                print(f"    return ret;", file=f)
            elif name.startswith("call_function"):
                # CALL_FUNCTION always passes the same number of arguments
                print(f"    __builtin_unreachable();", file=f)
            else:
                assert 0, name
            print("  }", file=f)
            guard_fail_fn_name = self.getGuardFailFuncName(signature)
            print(f"  PyObject* f = stack[-oparg - 1];", file=f)
            print(f"  if (unlikely(!({signature.getGuard(arg_names)})))", "{", file=f)
            print(f"    SET_JIT_AOT_FUNC({guard_fail_fn_name});", file=f)
            print(f"    PyObject* ret = {guard_fail_fn_name}(tstate, stack, oparg);", file=f)
            # this makes sure the compiler is not merging the calls into a single one
            print(f"    __builtin_assume(ret != (PyObject*)0x1);", file=f)
            print(f"    return ret;", file=f)
            print("  }", file=f)

            for assumption in signature.getAssumptions(arg_names):
                print(f"  __builtin_assume({assumption});", file=f)

            for line in signature.getSpecialTracingCode(arg_names):
                print(f"  {line}", file=f)
            print(f'''  printf("Calling {name}!\\n");''', file=f)
            print(f"  return {self.case.unspecialized_name}(tstate, stack, oparg);", file=f)
            print("}", file=f)

    def createJitTarget(self, target_func, ntraces):
        return createJitTarget(target_func, 3, ntraces)

    def call(self, target_func, args):
        # TODO: this shouldn't trace, but we don't yet have a call_helper equivalent that doesn't trace
        # get address of the actual function written in C not the python object
        key = ctypes.cast(target_func, ctypes.c_void_p).value
        if key not in self._jit_targets:
            self._jit_targets[key] = self.createJitTarget(target_func, 0xDEAD)

        return call_helper(self._jit_targets[key], *args)

    def write_profile_func(self, traced, header_f, profile_f):
        func = self.case.unspecialized_name
        profile_func = self.case.specialized_base + 'Profile'
        print(f"PyObject* {func}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=header_f)

        for signature, name in self.case.getSignatures():
            print(
                f"PyObject* {name}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=header_f)
            print(
                f"PyObject* {name}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=profile_f)

        print(
            f"PyObject* {func}NumpyProfile(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=header_f)
        print(
            f"PyObject* (*{func}numpyProfile_hook)(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=header_f)
        print(
            f"PyObject* {func}NumpyProfile(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg)", "{", file=profile_f)
        print("PyObject* f = *(stack - oparg - 1);", file=profile_f)

        for signature, name in traced:
            arg_names = ["f"] + [f"stack[-oparg+{i}]" for i in range(signature.nargs-1)]
            guard = signature.getGuard(arg_names)
            nargs = signature.nargs
            print(f"  if (oparg == {nargs-1} && {guard})", "{", file=profile_f)
            print(f"    SET_JIT_AOT_FUNC({name});", file=profile_f)
            print(f"    return {name}(tstate, stack, oparg);", file=profile_f)
            print("}", file=profile_f)
        
        print(
            rf'  DBG("Missing {func}Numpy %s\n", f->ob_type == &PyType_Type ? ((PyTypeObject*)f)->tp_name : f->ob_type->tp_name);', file=profile_f)
        print(f"  SET_JIT_AOT_FUNC({func});", file=profile_f)
        print(f"  return {func}(tstate, stack, oparg);", file=profile_f)
        print("}", file=profile_f)


    def trace(self, jit_target, args, signature):
        self.setTracingOverwrites(signature)
        return call_helper(jit_target, *args)

# These lambdas have to be defined at the global level.
# If they are defined inside a function (with the rest of the data), they
# are marked as "nested" functions which are called differently (and more slowly)
# than top-level functions.
def foo0():
    return 42
def foo1(x):
    return 42
def foo2(x, y):
    return 42
def foo3(x, y, z):
    return 42
def foo4(x, y, z, w):
    return 42
def foo5(x, y, z, w, v):
    return 42
def foo6(x, y, z, w, v, u):
    return 42
def foo7(x, y, z, w, v, u, a):
    return 42
def foo8(x, y, z, w, v, u, a, b):
    return 42
_function_cases = []
for i in range(0, 9):
    _function_cases.append((globals()[f"foo{i}"], tuple(range(i))))

for i in range(0, 10):
    exec(f"""
class ExampleClass{i}:
    def __init__(self, {', '.join("arg%d" % x for x in range(i))}):
        pass
    """, globals())

def loadCases():
    import numpy as np
    f = 4.4584
    types = {"Long": (0, 1, 4200, -42222),
             "Float": (f,),
             "Unicode": ('string', '', ' alaslas' * 20, 'a'),
             "List": ([1, 2, 3], list(range(100)),),
             "Tuple": ((1, 2, 3), (1., 2., 3.,) * 15,),
             "Range": (range(5), range(100),),
             "Dict": ({"a": 1, "b": 2, 1: 42, f: 0, None: None, 0: 0}, dict(),),
             "Set": ({"a", "b"}, set(),),
             "Bool": (True, False),
             "Slice": (slice(1, 2), slice(1), slice(1, 2, 2)),
             "None": (None,),
             }
    def getCTypeName(s):
        if s == "None":
            return "_PyNone_Type"
        if s == "Object":
            return "PyBaseObject_Type";
        return f"Py{s}_Type"
    type_classes = {k:ObjectClass(k, TypeGuard("&" + getCTypeName(k)), v) for (k, v) in types.items()}

    callables = {
        "UFunc": [(np.sqrt, (1337.,))], # one arg
    }

    cases = []

    call_signatures = []
    for name, l in callables.items():
        signatures = {}
        for example in l:
            func = example[0]
            for args in example[1:]:
                classes = []
                if isinstance(func, type):
                    classes.append(ObjectClass(name, IdentityGuard(f"(PyObject*)&{getCTypeName(name)}"), [func]))
                else:
                    classes.append(ObjectClass(name, TypeGuard(f"&{getCTypeName(name)}"), [func]))

                for arg in args:
                    classes.append(ObjectClass("", Unspecialized, [arg]))

                signatures.setdefault(len(args), []).append(Signature(classes))

        for nargs, sigs in signatures.items():
            if len(sigs) == 1:
                call_signatures.append(sigs[0])
            else:
                call_signatures.append(CompoundSignature(sigs))

    cases.append(CallableHandler(FunctionCases("call_function_ceval_no_kw", call_signatures)))
    cases.append(CallableHandler(FunctionCases("call_method_ceval_no_kw", call_signatures)))

    return cases

cases = loadCases()

def loadLibs():
    # TODO we should probably export a python module instead
    # say that its a pylib because otherwise we will release the gil and we can't access python object
    import ctypes
    nitrous_so = ctypes.PyDLL("libinterp.so")
    pystol_so = ctypes.PyDLL("libpystol.so")

    global initializeJIT
    initializeJIT = nitrous_so.initializeJIT
    initializeJIT.argtypes = [ctypes.c_long, ctypes.c_bool]

    global loadBitcode
    loadBitcode = nitrous_so.loadBitcode
    loadBitcode.argtypes = [ctypes.c_char_p]

    global clearDoNotTrace
    clearDoNotTrace = nitrous_so.clearDoNotTrace
    clearDoNotTrace.argtypes = []

    global addDoNotTrace
    addDoNotTrace = nitrous_so.addDoNotTrace
    addDoNotTrace.argtypes = [ctypes.c_char_p]

    global clearAlwaysTrace
    clearAlwaysTrace = nitrous_so.clearAlwaysTrace
    clearAlwaysTrace.argtypes = []

    global addAlwaysTrace
    addAlwaysTrace = nitrous_so.addAlwaysTrace
    addAlwaysTrace.argtypes = [ctypes.c_char_p]

    global createJitTarget
    createJitTarget = nitrous_so.createJitTarget
    createJitTarget.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_long]
    createJitTarget.restype = ctypes.c_void_p

    global aot_pre_trace_so
    aot_pre_trace_so = ctypes.PyDLL("./aot_numpy_pre_trace.so")

    # umath = ctypes.PyDLL("/home/kmod/pyston2/build/bc_env/lib/python3.8-pyston2.3/site-packages/numpy-1.22.0.dev0+1258.g26ce52951-py3.8-linux-x86_64.egg/numpy/core/_multiarray_umath.pyston-23-x86_64-linux-gnu.so")
    # assert 0, ctypes.c_void_p.in_dll(umath, "PyUFunc_Type")
    # assert 0, umath.PyUFunc_Type

    def makeCType(obj):
        if isinstance(obj, ctypes._SimpleCData):
            return obj
        return ctypes.py_object(obj)

    runJitTargets = {}
    for wrap in ("", "_wrap_result"):
        for arg_num in range(5):
            c = aot_pre_trace_so[f"runJitTarget{arg_num}{wrap}_helper"]
            c.restype = ctypes.py_object
            runJitTargets[(arg_num, bool(len(wrap)))] = c

    # wrap_result: if true wraps c int return value as PyLong
    def runJitTarget_wrapper(target, *args, wrap_result=False):
        py_args = list(map(makeCType, args))
        func = runJitTargets[(len(args), wrap_result)]
        func.argtypes = [ctypes.c_void_p] + list(map(type, py_args))
        return func(target, *py_args)
    global runJitTarget
    runJitTarget = runJitTarget_wrapper

    global pystolGlobalPythonSetup
    pystolGlobalPythonSetup = pystol_so.pystolGlobalPythonSetup

    call_helpers = []
    for arg_num in range(10):
        c = aot_pre_trace_so[f"call_helper{arg_num}"]
        c.argtypes = [ctypes.c_void_p, ctypes.py_object] + \
            ([ctypes.py_object] * arg_num)
        c.restype = ctypes.py_object
        call_helpers.append(c)

    def call_helper_wrapper(target, func, *args):
        return call_helpers[len(args)](target, ctypes.py_object(func), *map(makeCType, args))
    global call_helper
    call_helper = call_helper_wrapper


def specialize_func(handler, header_f, profile_f, async_tracing, only=None):
    unspecialized_name = handler.case.unspecialized_name
    print(f"Generating special versions of {unspecialized_name}")

    num_skipped = 0

    traced = []

    for signature, name in handler.case.getSignatures():
        if only and name != only:
            continue

        target_addr = aot_pre_trace_so[name]
        # we prune specialization which generate an error or inputs which generate one
        train_success = []

        for args in signature.getExamples():
            try:
                # If we set "only", skip this initial call so that we get
                # right to tracing
                if only is None or not isinstance(handler, CallableHandler):
                    handler.call(target_addr, copy.deepcopy(args))
                train_success.append(args)
            except:
                pass

        should_jit = len(train_success) > 0
        if should_jit:
            # create new jit target because we want to make sure we did not train on any error
            # TODO: could skip this if no errors happened
            target = handler.createJitTarget(target_addr, len(train_success))
            async_tracing.append((name, signature, handler, target, copy.deepcopy(train_success)))
            traced.append((signature, name))
        else:
            num_skipped += 1
            #print(f"  {spec_name} errors. skipping...")

    print(f'  going to generate {len(traced)} special versions')
    if only is None:
        handler.write_profile_func(traced, header_f, profile_f)
    return (len(traced), num_skipped)


def do_trace(work):
    (name, signature, handler, target, train_success) = work
    if VERBOSITY >= 1:
        print("tracing", name)

    for args in copy.deepcopy(train_success):
        if VERBOSITY >= 1:
            print("tracing", name, "with args:", args)
        handler.trace(target, args, signature)

def trace_all_funcs(only=None):
    total_num_gen = 0
    total_num_skipped = 0

    if only:
        header_f = profile_f = None
    else:
        header_f = open("aot_numpy.h", "w")
        profile_f = open("aot_numpy_profile.c", "w")
        print("#ifndef AOT_NUMPY_H_", file=header_f)
        print("#define AOT_NUMPY_H_", file=header_f)
        print('', file=header_f)

        print("#define NO_IMPORT_UFUNC", file=header_f)
        print("#define PY_UFUNC_UNIQUE_SYMBOL numpy_pyston_ufunc", file=header_f)

        print_includes(header_f)

        print('#include "aot_numpy.h"', file=profile_f)

        print_helper_funcs(header_f)

        print(f"#define DBG(...) printf(__VA_ARGS__)", file=profile_f)
        print(f"//#define DBG(...)", file=profile_f)

    # list of work items we will later on trace
    async_tracing = []
    for case in cases:
        num_gen, num_skipped = specialize_func(case, header_f, profile_f, async_tracing, only=only)
        total_num_gen += num_gen
        total_num_skipped += num_skipped

    if VERBOSITY:
        list(map(do_trace, async_tracing))
    else:
        print("Starting multiprocess tracing...")
        with multiprocessing.pool.Pool() as tracing_pool:
            tracing_pool.map(do_trace, async_tracing, chunksize=1)

    print(
        f'generated in total {total_num_gen} special versions skipped {total_num_skipped}')

    if header_f:
        print("#endif", file=header_f)

def print_includes(f):
    print('#include "Python.h"', file=f)
    #print('#include "opcode.h"', file=f)
    print('', file=f)

    print('#define likely(x) __builtin_expect(!!(x), 1)', file=f)
    print('#define unlikely(x) __builtin_expect(!!(x), 0)', file=f)
    print('', file=f)

    #print('extern PyCFunctionObject builtin_isinstance_obj, builtin_len_obj, builtin_ord_obj;', file=f)
    
    print('#include "numpy/ndarraytypes.h"', file=f)
    print('#include "numpy/ufuncobject.h"', file=f)
    print('#include "numpy/npy_3kcompat.h"', file=f)

    print('', file=f)

def print_helper_funcs(f):
    for func in ("call_function_ceval_no_kw", "call_method_ceval_no_kw"):
        print(f"PyObject* {func}(PyThreadState *tstate, PyObject **stack, Py_ssize_t oparg);", file=f)

    print("/* this directly modifies the destination of the jit generated call instruction */\\", file=f)
    print("#define SET_JIT_AOT_FUNC(dst_addr) do { \\", file=f)
    print("    /* retrieve address of the instruction following the call instruction */\\", file=f)
    print("    unsigned char* ret_addr = (unsigned char*)__builtin_extract_return_addr(__builtin_return_address(0));\\", file=f)
    print("    if (ret_addr[-2] == 0xff && ret_addr[-1] == 0xd0) { /* abs call: call rax */\\", file=f)
    print("        unsigned long* call_imm = (unsigned long*)&ret_addr[-2-8];\\", file=f)
    print("        *call_imm = (unsigned long)dst_addr;\\", file=f)
    print("    } else { /* relative call */ \\", file=f)
    print("        /* 5 byte call instruction - get address of relative immediate operand of call */\\", file=f)
    print("        unsigned int* call_imm = (unsigned int*)&ret_addr[-4];\\", file=f)
    print("        /* set operand to newly calculated relative offset */\\", file=f)
    print("        *call_imm = (unsigned int)(unsigned long)(dst_addr) - (unsigned int)(unsigned long)ret_addr;\\", file=f)
    print("    } \\", file=f)
    print("} while(0)", file=f)


def create_pre_traced_funcs(output_file):
    with open(output_file, "w") as f:
        print_includes(f)

        print("PyObject* avoid_clang_bug_aotpretrace() { return NULL; }", file=f)

        print_helper_funcs(f)

        print(f"#define Py_BUILD_CORE 1", file=f)
        print(f"#include <interp.h>", file=f)
        print(f"#include <pycore_pystate.h>", file=f)
        print(f"", file=f)

        for num_args in range(10):
            args = ["JitTarget* target", "PyObject *func"] + \
                [f'PyObject *o{i}' for i in range(num_args)]
            print(
                f"PyObject* call_helper{num_args}(", ", ".join(args), "){", file=f)
            print("  _PyRuntimeState * const runtime = &_PyRuntime;", file=f)
            print(
                "  PyThreadState * const tstate = _PyRuntimeState_GetThreadState(runtime);", file=f)
            args = ["func"] + [f'o{i}' for i in range(num_args)] + ["NULL"]
            print(f"  PyObject* array[{num_args}+2] =",
                  "{", ", ".join(args), "};", file=f)
            print(
                f'  for (int i=0;i<({num_args}+1); ++i) Py_INCREF(array[i]);', file=f)
            print(f"  PyObject** sp = &array[{num_args+1}];", file=f)
            print(
                f'  return runJitTarget4(target, tstate, sp, {num_args} /* oparg */, 0);', file=f)
            print('}', file=f)

        print(f"#include <interp.h>", file=f)
        for wrap in ("", "_wrap_result"):
            for num_args in range(5):
                args = ["JitTarget* target", ] + \
                    [f'PyObject *o{i}' for i in range(num_args)]
                print(
                    f"PyObject* runJitTarget{num_args}{wrap}_helper(", ", ".join(args), "){", file=f)
                args = ["target"] + [f'o{i}' for i in range(num_args)]
                ret = f"runJitTarget{num_args}({', '.join(args)})"
                if wrap:
                    ret = f"PyLong_FromLong({ret})"
                print(f'  return {ret};', file=f)
                print('}', file=f)

        for case in cases:
            case.writePretraceFunctions(f)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser("aot_numpy_gen")
    parser.add_argument("--action", action="store", default="all")
    parser.add_argument("-v", action="count", default=0, dest="verbosity")
    parser.add_argument("--only", action="store", default=None)
    parser.add_argument("-o", action="store", default=None)
    parser.add_argument("--pic", action="store_true", default=False)

    args = parser.parse_args()
    assert args.action in ("pretrace", "trace", "all")

    if args.action in ("pretrace", "all"):
        assert args.o
        create_pre_traced_funcs(args.o)

    VERBOSITY = args.verbosity

    if args.action in ("trace", "all"):
        # init JIT
        loadLibs()

        initializeJIT(VERBOSITY, args.pic)
        loadBitcode(b'all_numpy.bc')
        pystolGlobalPythonSetup()

        # start tracing
        trace_all_funcs(only=args.only)
