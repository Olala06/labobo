import unittest

from genomic_detective.annotations import _vep_input
from genomic_detective.models import Variant

from genomic_detective.dataset import parse_vcf, parse_phenotypes
from genomic_detective.knowledge import load_knowledge
from genomic_detective.models import CaseInput
from genomic_detective.pipeline import analyze_case


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


if __name__ == "__main__":
    unittest.main()
