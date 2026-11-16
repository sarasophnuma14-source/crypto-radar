"""Particiones para validación sin fuga: walk-forward, k-fold purgado con embargo y CPCV (López de Prado, 2018).
Todas devuelven índices posicionales (entrenamiento, prueba). `horizonte` = barras que tarda en resolverse una etiqueta
o una posición: se purgan del entrenamiento las observaciones cuyo horizonte se solapa con la prueba."""
from __future__ import annotations
import itertools
import numpy as np


def walk_forward(n, entrenamiento, prueba, paso=None, expansivo=False, embargo=0):
    paso = paso or prueba; out = []; ini = 0
    while True:
        fin_tr = (ini + entrenamiento) if not expansivo else entrenamiento + len(out) * paso
        a = fin_tr + embargo; b = a + prueba
        if b > n:
            break
        tr = np.arange(0 if expansivo else ini, fin_tr)
        out.append((tr, np.arange(a, b)))
        ini += paso
    return out


def _purga(tr, te, horizonte, embargo, n):
    lo, hi = te.min(), te.max()
    malo = ((tr + horizonte) >= lo) & (tr <= hi + embargo)
    return tr[~malo]


def kfold_purgado(n, k=5, horizonte=1, embargo=0):
    folds = np.array_split(np.arange(n), k); out = []
    for te in folds:
        tr = np.setdiff1d(np.arange(n), te)
        out.append((_purga(tr, te, horizonte, embargo, n), te))
    return out


def cpcv(n, grupos=6, prueba=2, horizonte=1, embargo=0):
    """Combinatorial purged CV: C(grupos, prueba) particiones; cada grupo de prueba se purga por separado."""
    g = np.array_split(np.arange(n), grupos); out = []
    for comb in itertools.combinations(range(grupos), prueba):
        te = np.concatenate([g[i] for i in comb]); tr = np.setdiff1d(np.arange(n), te)
        for i in comb:
            tr = _purga(tr, g[i], horizonte, embargo, n)
        out.append((tr, te, comb))
    return out


def sin_solape(particiones, horizonte=0, embargo=0):
    """Comprobación: ningún índice de entrenamiento cae a menos de horizonte/embargo de su prueba."""
    for p in particiones:
        tr, te = p[0], p[1]
        if len(np.intersect1d(tr, te)):
            return False
    return True
