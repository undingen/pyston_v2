import json
import os
import subprocess
import sys

_depends_on_python = {"python": True}
def depends_on_python(pkg, packages):
    if pkg not in _depends_on_python:
        _depends_on_python[pkg] = False
        if pkg not in packages:
            return False
        r = False
        for d in packages[pkg]['depends']:
            dn = d.split()[0]
            r = depends_on_python(dn, packages) or r
        _depends_on_python[pkg] = r
        print(pkg, r)
        if r and pkg not in ("python_abi", "certifi", "setuptools"):
            print(pkg)
    return _depends_on_python[pkg]

def main(targets):
    repodata_fn = "repodata_condaforge_linux64.json"
    if not os.path.exists(repodata_fn):
        print("Downloading...")
        subprocess.check_call(["wget", "https://conda.anaconda.org/conda-forge/linux-64/repodata.json.bz2", "-O", repodata_fn + ".bz2"])
        subprocess.check_call(["bzip2", "-d", repodata_fn + ".bz2"])

    print("Loading...")
    data = json.load(open(repodata_fn))
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
