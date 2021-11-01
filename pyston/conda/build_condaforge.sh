set -euxo pipefail

CHANNEL=kmod/label/dev
export CHANNEL

while read pkg; do
    if conda search $pkg -c $CHANNEL --override-channels; then
        echo $pkg already built
        continue
    fi
    bash $(dirname $0)/build_feedstock.sh $pkg
    anaconda upload -u kmod --label dev $(find $pkg-feedstock/build_artifacts/ -name '*.tar.bz2' | grep -v broken)
done < $(dirname $0)/pyston-python-order.txt
