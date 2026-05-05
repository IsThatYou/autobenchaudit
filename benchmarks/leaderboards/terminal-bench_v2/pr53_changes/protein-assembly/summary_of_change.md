# protein-assembly

## Summary of changes (from PR #53 body)

- Fixed oracle: The oracle's solve.sh used https://www.rcsb.org/fasta/entry/{pdb_id}/download to get protein sequences, which was unreliable

Related PRs: [PR #57](https://github.com/harbor-framework/terminal-bench-2/pull/57).

## Additional changes observed in diff

- `solution/solve.sh`: oracle now hits the JSON polymer-entity endpoint (`https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/1`) instead of the FASTA download endpoint, parses `entity_poly.pdbx_seq_one_letter_code_can`, and additionally **resolves any `X` residues** by walking `rcsb_polymer_entity_feature` modified-monomer entries and mapping their `PARENT_COMP_ID` 3-letter codes via a new `THREE_TO_ONE` dict. This is more substantial than "switched endpoints" — it actually changes the sequence the oracle produces for entries with modified residues.
- `environment/pdb_ids.py` (64 lines): **deleted**. This was the offline data-prep script that originally generated `sequences.csv`; it relied on the same unreliable FASTA endpoint and is no longer needed.
- `task.toml`: docker image bumped from `:20251031` → `:20260403`.

## Issues found

- **PDB data drift broke oracle on 2026-03-18** (addressed by tb2#57) — PDB updated several structures so that chromophore residues now return as `X` (unknown) in FASTA downloads instead of the canonical amino acid. Example: 5WJ2 changed from `...TTFGYGVAC...` to `...TTFXVAC...`. `dnachisel.EnforceTranslation` rejects any non-standard character, so the oracle's codon-optimization step always failed, and `/app/gblock.txt` was never written. Oracle switched to the JSON polymer-entity endpoint and expands `X` residues via `rcsb_polymer_entity_feature` → `PARENT_COMP_ID` mapped through a new `THREE_TO_ONE` dict.
- **Unreliable FASTA endpoint** (addressed by tb2#57) — The `https://www.rcsb.org/fasta/entry/{pdb_id}/download` endpoint was flaky; oracle now uses `https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id}/1`.
- **Stray dev file in environment** (addressed by tb2#57) — `environment/pdb_ids.py` was accidentally committed during task development and relied on the same unreliable FASTA endpoint. Deleted.
- **Non-deterministic `dnachisel` failures** (NOT addressed) — giansegato observed that `dnachisel` can fail with `NoSolutionError: EnforceTranslation[0-2694]` even on valid input and recommends retrying on the same sequence. PR #53/tb2#57 does not add retry logic to the oracle.
- **Hidden chromophore-X-expansion convention** (NOT addressed) — Tests silently rely on the X-to-canonical-AA convention baked into the oracle's `THREE_TO_ONE` expansion. Agents reading the prompt have no way to know this convention. Audit finding `protein-assembly-01` (Major/ambiguity) — not supported (oracle was updated, prompt/test untouched).
- **Tests silently require preserving His6+TEV purification prefix** (NOT addressed) — Tests require the 20-aa purification tag to be preserved, while the prompt forbids content outside linkers/binding-proteins/donor/acceptor/DHFR in the gBlock. No prompt rewording or test tolerance change in this PR. Audit finding `protein-assembly-02` (Major/ambiguity) — not supported.
