# Phenotype-guided Genomic Explorer

A research/educational prototype inspired by [Synth_Hack / Genomic Detective](https://github.com/NursuUwU/Synth_Hack). Upload a VCF file, describe a phenotype, and receive a transparent ranked list of candidate genes with evidence notes and literature links.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Inputs
- VCF (`.vcf` or `.vcf.gz`): variants are parsed from columns CHROM, POS, REF, ALT, INFO and optional FORMAT/sample genotype.
- Phenotype: free text in English or Russian. This MVP uses curated keyword-to-HPO mappings in `knowledge.json`; unmatched phrases are shown as unmatched rather than silently treated as evidence.

## Output
- Ranked candidate conditions/genes with a heuristic compatibility score (not a calibrated probability or diagnosis).
- Evidence breakdown: phenotype matches, observed variants, variant annotations if present, and literature references.
- Source links point to PubMed queries and HPO/ClinVar records; the app does not fabricate article titles or PMID identifiers.

## Important limitations
This is an educational research prototype, not a clinical decision-support device. Scores are ranking heuristics, not clinical probabilities. The bundled knowledge base is deliberately small and must be expanded and independently reviewed before research use. A VCF alone cannot establish pathogenicity; phase, inheritance, coverage, phenotype quality, ancestry, transcript choice and clinical context matter. Do not upload identifiable patient data to an untrusted deployment.

## Architecture
- `app.py`: Streamlit interface, VCF parsing, phenotype matching, ranking and report rendering.
- `knowledge.json`: explicit, reviewable phenotype-condition-gene records and source identifiers/links.
