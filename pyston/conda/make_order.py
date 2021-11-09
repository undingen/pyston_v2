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
    "poppler-qt": "poppler",
    "cross-r-base": "r-base",
    "tensorflow-base": "tensorflow",
    "tensorflow-estimator": "tensorflow",
    "libtensorflow": "tensorflow",
    "libtensorflow_cc": "tensorflow",
}
def getFeedstockName(pkg):
    return _feedstock_overrides.get(pkg, pkg)

def getBuildRequirements(pkg):
    reponame = getFeedstockName(pkg) + "-feedstock"

    if not os.path.exists(reponame):
        subprocess.check_call(["git", "clone", "https://github.com/conda-forge/" + reponame], stdin=open("/dev/null"))

    with open(reponame + "/recipe/meta.yaml") as f:
        return f.read().split()

verbose = 0
_depends_on_python = {"python": True}
listed = set()

packages_by_name = {}
noarch_packages = set()

def depends_on_python(pkg):
    if pkg not in _depends_on_python:
        _depends_on_python[pkg] = False
        if pkg not in packages_by_name:
            return False
        if pkg in noarch_packages:
            # print(pkg, "is noarch")
            return False
        if pkg in ("glib",):
            return False
        r = False
        for d in packages_by_name[pkg]['depends']:
            dn = d.split()[0]
            subdepends = depends_on_python(dn)
            r = subdepends or r
            if subdepends and verbose:
                print(pkg, "run depends on", d)
        _depends_on_python[pkg] = r
        # print(pkg, r)

        if r and pkg not in ("python_abi", "certifi", "setuptools"):
            for b in getBuildRequirements(pkg):
                if b in ("conda", "conda-smithy", "conda-build", "conda-verify", "flaky", "nose", "rejected"):
                    continue
                subdepends = depends_on_python(b)
                if subdepends and verbose:
                    print(pkg, "build depends on", b)

            name = getFeedstockName(pkg)
            if name not in listed:
                print(name)
                listed.add(name)
    return _depends_on_python[pkg]

def main(targets):
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
    if verbose:
        print("Analyzing...")
    packages = data["packages"]

    for k, v in packages.items():
        packages_by_name[v['name']] = v

    for k, v in data_noarch["packages"].items():
        noarch_packages.add(v['name'])

    for name in targets:
        depends_on_python(name)

if __name__ == "__main__":
    targets = sys.argv[1:]

    if "-v" in targets:
        verbose = True
        targets.remove("-v")

    if not targets:
        targets = ["Pillow", "urllib3", "numpy", "scipy", "pandas", "tensorflow", "pytorch"]

    main(targets)
