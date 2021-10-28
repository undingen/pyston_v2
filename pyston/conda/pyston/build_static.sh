set -eux

# pwd
# find

NAME=libpython${PYTHON_VERSION2}-pyston${PYSTON_VERSION2}.a

find build/releaseunopt_install/ -name $NAME

cp $(find build/releaseunopt_install/ -name $NAME | grep -v config) ${PREFIX}/lib/
