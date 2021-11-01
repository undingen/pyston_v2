import os
import sys

def rewrite_config(config_str):
    lines = config_str.split('\n')

    for i in range(len(lines)):
        if lines[i] == "python:":
            lines[i + 1] = "- 3.8.* *_pyston"
            break
    else:
        raise Exception("didn't find 'python' line")

    return '\n'.join(lines)

def main():
    configs = os.listdir(".ci_support")

    possible_configs = []

    given_substr = os.environ.get("BASE_CONFIG", "")

    cwd = os.getcwd()

    for c in configs:
        if "aarch64" in c or "ppc" in c:
            continue
        if "win" in c or "osx" in c:
            continue
        if "3." in c and "3.8" not in c:
            continue
        if c in ("migrations", "README"):
            continue
        if given_substr and given_substr not in c:
            continue

        if "pyston" in c:
            continue

        if "numpy" in cwd and "mkl" not in c:
            continue

        possible_configs.append(c)

    assert len(possible_configs) == 1, possible_configs
    config, = possible_configs

    config_str = open(".ci_support/" + config).read()
    new_config_str = rewrite_config(config_str)

    open(".ci_support/linux-pyston.yaml", 'w').write(new_config_str)
    print("linux-pyston")

if __name__ == "__main__":
    try:
        main()
    except:
        print("make_config.py-failed")
        raise
