import json
import tempfile
import unittest
from pathlib import Path

from genomic_detective.annotations import _vep_input
from genomic_detective.dataset import parse_vcf, parse_phenotypes, parse_case_files, parse_phenopacket
from genomic_detective.knowledge import load_knowledge
from genomic_detective.models import CaseInput, Variant
from genomic_detective.pipeline import analyze_case
from genomic_detective.reporting import render_html, write_reports
from genomic_detective.web import PAGE
from genomic_detective.gtex import GTExProvider


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.knowledge = load_knowledge()

    def test_vcf_parser_reads_gene_and_genotype(self):
        text = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
15\t48700000\t.\tG\tA\t99\tPASS\tSYMBOL=FBN1;Consequence=missense_variant;CLNSIG=Uncertain_significance\tGT\t0/1
"""
        variants, warnings = parse_vcf(text)
        self.assertFalse(warnings)
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].gene, "FBN1")
        self.assertEqual(variants[0].genotype, "0/1")

    def test_vep_request_uses_documented_vcf_like_format(self):
        variant = Variant("chr7", 100, "A", "G")
        self.assertEqual(_vep_input(variant), "7 100 . A G . . .")

    def test_hpo_id_matching(self):
        hits = parse_phenotypes("HP:0001166", self.knowledge)
        self.assertEqual(hits[0].hpo_id, "HP:0001166")

    def test_vus_does_not_add_molecular_support(self):
        case = CaseInput(
            "test", parse_vcf("""#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
15\t48700000\t.\tG\tA\t99\tPASS\tSYMBOL=FBN1;CLNSIG=Uncertain_significance\tGT\t0/1
""")[0],
            "арахнодактилия эктопия хрусталика расширение корня аорты высокий рост", ["test.vcf"]
        )
        report = analyze_case(case, self.knowledge)
        top = report["candidates"][0]
        self.assertEqual(top["experts"]["molecular"]["score"], 0.0)
        self.assertEqual(top["name"], "Синдром Марфана")

    def test_unknown_phenotype_is_incomplete(self):
        case = CaseInput("test", [], "неизвестные признаки", [])
        report = analyze_case(case, self.knowledge)
        self.assertEqual(report["status"], "incomplete")

    def test_generic_tsv_filename_is_parsed_as_variants(self):
        text = "chrom\tpos\tref\talt\tgene\tgenotype\n17\t43071077\tC\tT\tBRCA1\t0/1\n"
        case = parse_case_files([("patient_upload.tsv", text.encode("utf-8"))], "upload")
        self.assertEqual(len(case.variants), 1)
        self.assertEqual(case.variants[0].gene, "BRCA1")

    def test_phenopacket_parser_separates_positive_and_excluded_features(self):
        packet = {
            "id": "case_01",
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001166", "label": "Arachnodactyly"}},
                {"type": {"id": "HP:0006532", "label": "Recurrent respiratory infections"}, "excluded": True},
            ],
        }
        profile = parse_phenopacket(json.dumps(packet))
        self.assertIn("HP:0001166", profile["positive_text"])
        self.assertIn("HP:0006532", profile["excluded_text"])
        self.assertEqual(profile["features"][1]["excluded"], True)

    def test_two_file_case_finds_exact_vcf_record_and_ad_context(self):
        phenotype = {
            "id": "case_01",
            "phenotypicFeatures": [
                {"type": {"id": "HP:0001166", "label": "Arachnodactyly"}},
                {"type": {"id": "HP:0006532", "label": "Recurrent respiratory infections"}, "excluded": True},
            ],
        }
        vcf = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
15\t48412568\t.\tC\tA\t99\tPASS\tSYMBOL=FBN1\tGT\t0/1
"""
        case = parse_case_files([
            ("case_01.vcf", vcf.encode("utf-8")),
            ("case_01_phenotype.json", json.dumps(phenotype).encode("utf-8")),
        ], "upload")
        report = analyze_case(case, self.knowledge)
        self.assertEqual(report["case_id"], "case_01")
        self.assertEqual(report["variant_candidates"][0]["variant"], "chr15:48412568:C:A")
        self.assertEqual(report["variant_candidates"][0]["genotype"], "0/1")
        self.assertIn("AD:", report["variant_candidates"][0]["inheritance_assessment"])
        self.assertIn("согласуется с опубликованным heterozygous", report["variant_candidates"][0]["published_reference_check"])
        self.assertEqual(report["prediction"], "chr15:48412568:C:A")
        self.assertIn("3′-конца", report["variant_candidates"][0]["mechanism"])
        self.assertEqual(report["excluded_phenotypes"][0]["id"], "HP:0006532")
        rendered = render_html(report)
        self.assertIn("chr15:48412568:C:A", rendered)
        self.assertIn("excluded HPO", rendered)

    def test_predictions_tsv_has_two_column_benchmark_contract(self):
        report = analyze_case(CaseInput(
            "case_01", [Variant("15", 48412568, "C", "A", gene="FBN1", genotype="0/1")],
            "HP:0001166", ["case_01.vcf"]
        ), self.knowledge)
        with tempfile.TemporaryDirectory() as tmp:
            write_reports([report], Path(tmp))
            lines = (Path(tmp) / "predictions.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "case_id\tprediction")
        self.assertEqual(lines[1].split("\t")[0], "case_01")

    def test_upload_page_asks_for_two_files_without_manual_phenotype_input(self):
        self.assertIn('id="phenotype-file"', PAGE)
        self.assertIn('name="phenotype_file"', PAGE)
        self.assertIn('id="variant-file"', PAGE)
        self.assertIn('name="variant_file"', PAGE)
        self.assertNotIn('id="hpo-search"', PAGE)
        self.assertNotIn('id="phenotype"', PAGE)
        self.assertNotIn('case-select', PAGE)
        self.assertNotIn('demo_case', PAGE)

    def test_pyhpo_search_and_gene_ranking(self):
        from genomic_detective.hpo import get_hpo_engine
        engine = get_hpo_engine()
        results = engine.search("scoliosis")
        self.assertTrue(any(item["id"] == "HP:0002650" for item in results))
        profile = engine.resolve("HP:0002650, HP:0001166")
        self.assertEqual({item["id"] for item in profile["recognized"]},
                         {"HP:0002650", "HP:0001166"})
        gene = next(iter(engine.ontology.genes))
        term = next(iter(gene.hpo_set()))
        variant = Variant("1", 100, "A", "G", gene=str(gene.name))
        ranked = engine.rank_genes([variant], [term])
        self.assertTrue(any(item["gene"] == str(gene.name) for item in ranked))
        self.assertTrue(all(0.0 <= item["hpo_similarity"] <= 1.0 for item in ranked))

    def test_gtex_tissue_rows_are_sorted_and_are_context_only(self):
        provider = GTExProvider()
        provider._versioned_gene_id = lambda symbol, ids: "ENSG000001.1"
        provider._request_json = lambda path, params: {
            "data": [
                {"tissueSiteDetail": "Blood", "median": 1.5},
                {"tissueSiteDetail": "Liver", "median": 12.0},
            ]
        }
        result = provider.expression_for_gene("TEST")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["top_tissues"][0]["tissue"], "Liver")
        self.assertEqual(result["dataset"], "gtex_v10")


if __name__ == "__main__":
    unittest.main()
