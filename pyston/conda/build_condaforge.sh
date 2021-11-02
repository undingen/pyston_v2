set -euxo pipefail

CHANNEL=kmod/label/dev
export CHANNEL

which conda
which anaconda

conda search '*' -c $CHANNEL --override-channels | tail -n +3 | awk '{print $1}' > /tmp/packages.txt

python3 pyston/conda/make_order.py numpy scipy tensorflow | while read pkg; do
    if grep -q -i $pkg /tmp/packages.txt; then
        echo $pkg already built
        continue
    fi
    bash $(dirname $0)/build_feedstock.sh $pkg
    anaconda upload -u kmod --label dev $(find $pkg-feedstock/build_artifacts/ -name '*.tar.bz2' | grep -v broken)
done
