import json
import os
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
    "argon2-cffi": "argon2_cffi",
    "atk-1.0": "atk",
    "pybind11-abi": "pybind11",
    "pybind11-global": "pybind11",
}
def getFeedstockName(pkg):
    return _feedstock_overrides.get(pkg, pkg)

def getBuildRequirements(pkg):
    reponame = pkg + "-feedstock"

    if not os.path.exists(reponame):
        subprocess.check_call(["git", "clone", "https://github.com/conda-forge/" + reponame], stdin=open("/dev/null"))
    with open(reponame + "/recipe/meta.yaml") as f:
        return f.read().split()

verbose = 0
_depends_on_python = {"python": True}
def depends_on_python(pkg, packages):
    pkg = getFeedstockName(pkg)
    if pkg not in _depends_on_python:
        _depends_on_python[pkg] = False
        if pkg not in packages:
            return False
        r = False
        for d in packages[pkg]['depends']:
            dn = d.split()[0]
            subdepends = depends_on_python(dn, packages)
            r = subdepends or r
            if subdepends and verbose:
                print(pkg, "run depends on", d)
        _depends_on_python[pkg] = r
        # print(pkg, r)

        if r and pkg not in ("python_abi", "certifi", "setuptools"):
            for b in getBuildRequirements(pkg):
                if b in ("conda", "conda-smithy"):
                    continue
                subdepends = depends_on_python(b, packages)
                if subdepends and verbose:
                    print(pkg, "build depends on", b)
            print(pkg)
    return _depends_on_python[pkg]

def main(targets):
    repodata_fn = "repodata_condaforge_linux64.json"
    if not os.path.exists(repodata_fn):
        print("Downloading...")
        subprocess.check_call(["wget", "https://conda.anaconda.org/conda-forge/linux-64/repodata.json.bz2", "-O", repodata_fn + ".bz2"])
        subprocess.check_call(["bzip2", "-d", repodata_fn + ".bz2"])

    if verbose:
        print("Loading...")
    data = json.load(open(repodata_fn))
    if verbose:
        print("Analyzing...")
    packages = data["packages"]

    packages_by_name = {}
    for k, v in packages.items():
        packages_by_name[v['name']] = v

    for name in targets:
        depends_on_python(name, packages_by_name)

if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        targets = ["Pillow", "urllib3", "numpy", "scipy", "pandas", "tensorflow", "pytorch"]
    main(targets)
