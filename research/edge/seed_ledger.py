"""Siembra (una sola vez) el registro con la evaluación final ya ejecutada el 2026-11-15T03:55:17Z (commit 8868070).

El registro se creó después de ese holdout, así que esta entrada se reconstruye a partir de lo que quedó guardado:
el código exacto de ese commit (su hash se calcula con `git show`) y los resultados versionados en
research/edge/results/holdout_results.json. Se marca `seeded_retroactively: true` para que nadie la confunda con
una ejecución nueva. Si el registro ya tiene un final_holdout, no hace nada."""
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from radar.edge import ledger

COMMIT = "88680702ac74e0157122d5cee85950ffa4889c62"


def code_hash_at(commit):
    files = subprocess.run(["git", "ls-tree", "--name-only", commit, "radar/edge/"], cwd=ROOT, capture_output=True,
                           text=True).stdout.split()
    files = sorted([f for f in files if f.endswith(".py")] + ["research/edge/run.py"])
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode()); h.update(subprocess.run(["git", "show", f"{commit}:{f}"], cwd=ROOT, capture_output=True).stdout)
    return h.hexdigest(), files


if __name__ == "__main__":
    if ledger.final_holdout():
        raise SystemExit("El registro ya contiene el final_holdout; no se siembra de nuevo.")
    res_path = ROOT / "research" / "edge" / "results" / "holdout_results.json"
    reg = json.loads(res_path.read_text())
    ch, files = code_hash_at(COMMIT)
    e = ledger.append("final_holdout", seeded_retroactively=True, original_at=reg["generated"], original_commit=COMMIT,
                      original_code_hash=ch, original_code_files=files, period=["2024-07-01", "2026-11-14"],
                      selection=reg["frozen_selection"], verdicts={f: v["verdict"] for f, v in reg["frozen"].items()},
                      results_file="research/edge/results/holdout_results.json",
                      results_sha256=hashlib.sha256(res_path.read_bytes()).hexdigest(),
                      headline={"D_volmom_L28": reg["all"]["D_volmom_L28"]["base"]["net_return_pct"]},
                      note="Evaluación final original, ejecutada una vez. Entrada reconstruida al crear el registro.")
    print(json.dumps(e, indent=1, ensure_ascii=False))
