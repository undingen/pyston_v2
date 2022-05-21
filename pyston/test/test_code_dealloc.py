import gc
import resource
import platform

if __name__ == "__main__" and platform.system() == "Linux":
    resource.setrlimit(resource.RLIMIT_AS, (2<<20, 2<<20))

    for i in range(100000):
        # The exec creates a code object, but we also want to create and call a function
        # so that we can test the zombieframe behavior
        exec("""
def f():
    pass
f()
# import sys; sys.path.append(f.__code__)
""")
        if i % 100 == 0:
            gc.collect()
