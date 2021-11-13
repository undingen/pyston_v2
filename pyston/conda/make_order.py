import json
import os
import pickle
import re
import subprocess
import sys

_feedstock_overrides = {
    "typing-extensions": "typing_extensions",
    "py-lief": "lief",
    "matplotlib-base": "matplotlib",
    "g-ir-build-tools": "gobject-introspection",
    "g-ir-host-tools": "gobject-introspection",
    "libgirepository": "gobject-introspection",
    "gst-plugins-good": "gstreamer",
    "postgresql-plpython": "postgresql",
    "pyqt5-sip": "pyqt",
    "pyqt-impl": "pyqt",
    "pyqtwebengine": "pyqt",
    "pyqtchart": "pyqt",
    "pytorch": "pytorch-cpu",
    "argon2-cffi": "argon2_cffi",
    "atk-1.0": "atk",
    "pybind11-abi": "pybind11",
    "pybind11-global": "pybind11",
    "poppler-qt": "poppler",
    "cross-r-base": "r-base",
    "tensorflow-base": "tensorflow",
    "tensorflow-estimator": "tensorflow",
    "libtensorflow": "tensorflow",
    "libtensorflow_cc": "tensorflow",
    "llvm-openmp": "openmp",
}
def getFeedstockName(pkg):
    return _feedstock_overrides.get(pkg, pkg)

def getBuildRequirements(pkg):
    reponame = getFeedstockName(pkg) + "-feedstock"

    if not os.path.exists(reponame):
        subprocess.check_call(["git", "clone", "https://github.com/conda-forge/" + reponame], stdin=open("/dev/null"))

    with open(reponame + "/recipe/meta.yaml") as f:
        s = f.read()

    return re.findall("- ([^\w><={]+)", s)

verbose = 0
_depends_on_python = {"python": True}
listed = set()

packages_by_name = {}
noarch_packages = set()

def _dependsOnPython(pkg):
    if pkg not in packages_by_name:
        if verbose:
            print(pkg, "not a package we know about")
        return False

    for pattern in ("lib", "gcc", "gxx"):
        if re.match(pattern, pkg):
            return False

    r = False
    dependencies = set(packages_by_name[pkg]['depends'])
    if pkg not in noarch_packages and pkg not in ("python_abi", "certifi", "setuptools", "mkl"):
        dependencies.update(getBuildRequirements(pkg))

    if verbose:
        print(pkg, dependencies)

    for d in sorted(dependencies):
        dn = d.split()[0]
        subdepends = dependsOnPython(dn)
        r = subdepends or r
        if subdepends and verbose:
            print(pkg, "depends on", d)

    _depends_on_python[pkg] = r

    if not r:
        return False

    if pkg in ("glib", "python_abi", "certifi", "setuptools"):
        return False

    if pkg in noarch_packages:
        if verbose:
            print(pkg, "is noarch")
    else:
        name = getFeedstockName(pkg)
        if name not in listed:
            print(name)
            listed.add(name)

    return r

def dependsOnPython(pkg):
    if pkg not in _depends_on_python:
        _depends_on_python[pkg] = False # for circular dependencies
        _depends_on_python[pkg] = _dependsOnPython(pkg)
    return _depends_on_python[pkg]

def main(targets):
    global packages_by_name, noarch_packages
    if not os.path.exists("repo.pkl"):
        repodata_fn = "repodata_condaforge_linux64.json"
        if not os.path.exists(repodata_fn):
            print("Downloading...")
            subprocess.check_call(["wget", "https://conda.anaconda.org/conda-forge/linux-64/repodata.json.bz2", "-O", repodata_fn + ".bz2"])
            subprocess.check_call(["bzip2", "-d", repodata_fn + ".bz2"])

        repodata_noarch_fn = "repodata_condaforge_noarch.json"
        if not os.path.exists(repodata_noarch_fn):
            print("Downloading...")
            subprocess.check_call(["wget", "https://conda.anaconda.org/conda-forge/noarch/repodata.json.bz2", "-O", repodata_noarch_fn + ".bz2"])
            subprocess.check_call(["bzip2", "-d", repodata_noarch_fn + ".bz2"])

        if verbose:
            print("Loading...")
        data = json.load(open(repodata_fn))
        data_noarch = json.load(open(repodata_noarch_fn))

        for k, v in data["packages"].items():
            packages_by_name[v['name']] = v

        for k, v in data_noarch["packages"].items():
            if "pypy" in k:
                continue
            packages_by_name[v['name']] = v
            noarch_packages.add(v['name'])

        pickle.dump((packages_by_name, noarch_packages), open("_repo.pkl", "wb"))
        os.rename("_repo.pkl", "repo.pkl")

    packages_by_name, noarch_packages = pickle.load(open("repo.pkl", "rb"))

    if verbose:
        print("Analyzing...")
    for name in targets:
        dependsOnPython(name)

if __name__ == "__main__":
    targets = sys.argv[1:]

    if "-v" in targets:
        verbose = True
        targets.remove("-v")

    if not targets:
        targets = ["Pillow", "urllib3", "numpy", "scipy", "pandas", "tensorflow"]

    main(targets)
