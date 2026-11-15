#!/bin/bash
# Simulación local de la integración del apilado. No hace push ni fusiona PR.
set -u
REPO=$(git rev-parse --show-toplevel); SP=${SP:-$(mktemp -d)}; PY312=${PY312:-python3.12}
WT=$SP/integracion; OUT=$SP/integ; mkdir -p $OUT; rm -rf $WT; git -C $REPO worktree prune
git -C $REPO worktree add -q -B integracion-local $WT origin/main
cd $WT; export GIT_AUTHOR_NAME=integracion-local GIT_AUTHOR_EMAIL=ci@local GIT_COMMITTER_NAME=integracion-local GIT_COMMITTER_EMAIL=ci@local
regress() {
  tag=$1
  for PY in $PY312 python3; do
    v=$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])')
    for t in test_suite test_edge test_paper; do
      TEST_DATABASE_URL=postgresql://radar@127.0.0.1:55432/radar timeout 1500 $PY tests/$t.py > $OUT/${tag}_${v}_$t.log 2>&1; rc=$?
      res=$(grep -E "^(Ran|OK|FAILED)" $OUT/${tag}_${v}_$t.log | tr '\n' ' ')
      echo "$tag|$v|$t|rc=$rc|$res"
    done
  done
}
echo "base|$(git rev-parse --short HEAD)"; regress 0_main
i=1
for ref in "PR3:2d72a2b" "PR4:8476715" "PR5:fedb3a1" "PR6:f79b24c" "CIERRE:claude/cierre-riesgos"; do
  n=${ref%%:*}; c=${ref#*:}
  if git merge --no-ff -q -m "Integración local de $n" $c > $OUT/merge_$n.log 2>&1; then
    echo "merge|$n|$(git rev-parse --short $c)|ok|conflictos=0|$(git diff --shortstat HEAD^1 HEAD)"
  else
    echo "merge|$n|CONFLICTO|$(git diff --name-only --diff-filter=U | tr '\n' ' ')"; git merge --abort; break
  fi
  git diff --quiet $c HEAD && echo "arbol|$n|idéntico a la rama" || echo "arbol|$n|DIFIERE de la rama"
  regress ${i}_$n; i=$((i+1))
done
echo "protegido|$(git diff --quiet origin/main HEAD -- research radar/quant radar/edge radar/paper_trading && echo sin cambios || git diff --stat origin/main HEAD -- research radar/quant radar/edge radar/paper_trading | tail -1)"
# Escenario alternativo: squash de #3 en main y luego #4 sin rebase
git checkout -q -B squash-local origin/main
git merge --squash -q 2d72a2b >/dev/null 2>&1; git commit -q -m "squash PR3"
if git merge --no-ff -q -m "PR4 tras squash" 8476715 > $OUT/merge_squash.log 2>&1; then echo "squash|PR4 tras squash de PR3|sin conflictos"
else echo "squash|PR4 tras squash de PR3|CONFLICTOS en $(git diff --name-only --diff-filter=U | wc -l) archivos: $(git diff --name-only --diff-filter=U | head -8 | tr '\n' ' ')"; git merge --abort; fi
git checkout -q --detach; git -C $REPO branch -D squash-local >/dev/null
