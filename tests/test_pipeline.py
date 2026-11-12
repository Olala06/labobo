import unittest

from genomic_detective.annotations import _vep_input
from genomic_detective.dataset import parse_vcf, parse_phenotypes, parse_case_files
from genomic_detective.knowledge import load_knowledge
from genomic_detective.models import CaseInput, Variant
from genomic_detective.pipeline import analyze_case
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

    def test_upload_page_has_no_preselected_cases(self):
        self.assertIn('id="files"', PAGE)
        self.assertIn('multiple required', PAGE)
        self.assertIn('id="hpo-search"', PAGE)
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
