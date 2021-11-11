set -euxo pipefail

CHANNEL=kmod/label/dev
export CHANNEL

which conda
which anaconda

conda search '*' -c $CHANNEL -c undingen/label/dev --override-channels | tail -n +3 | awk '{print $1}' > /tmp/packages.txt

python3 pyston/conda/make_order.py $@ | while read pkg; do
    echo "########################################"
    echo "$pkg"
    echo "########################################"
    if grep -q -i $pkg /tmp/packages.txt; then
        echo $pkg already built
        continue
    fi
    CI=1 bash $(dirname $0)/build_feedstock.sh $pkg
    anaconda upload -u undingen --label dev $(find $pkg-feedstock/build_artifacts/ -name '*.tar.bz2' | grep -v broken)
    rm -rfv $pkg-feedstock/build_artifacts
done
