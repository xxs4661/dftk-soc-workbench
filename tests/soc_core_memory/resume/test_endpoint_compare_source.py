"""Source-boundary checks only; no Julia or endpoint arrays are evaluated."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = 'benchmarks/soc-core-memory-v1/endpoint_compare.jl'
PARTIAL = '98781fd0ce6c2f4138ed010e115a13e370410d58'


def region(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


class EndpointCompareSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = (ROOT / RELATIVE).read_text()
        cls.old = subprocess.check_output(
            ['git', '-C', str(ROOT), 'show', PARTIAL + ':' + RELATIVE], text=True)

    def test_original_worker_resource_parent_checks_are_byte_identical(self):
        self.assertEqual(region(self.current, 'function endpoint_worker(', 'function endpoint_main('),
                         region(self.old, 'function endpoint_worker(', 'function endpoint_main('))

    def test_original_density_formula_threshold_and_sources_are_byte_identical(self):
        self.assertEqual(region(self.current, '        accuracy=', '        require_value(arithmetic_source_identity'),
                         region(self.old, '        accuracy=', '        require_value(arithmetic_source_identity'))

    def test_authorization_is_explicit_fifth_argument_before_arrays(self):
        self.assertIn('length(args) in (4,5)', self.current)
        guarded = 'if length(args)==5\n            result["resume_authentication"]=endpoint_resume_authorization(root,args[5],args[2],args[3],execution)\n        end'
        self.assertIn(guarded, self.current)
        self.assertLess(self.current.index(guarded), self.current.index('old=deserialize(oldpath)'))
        source_paths = 'if length(args)==5\n            append!(paths,["benchmarks/soc-core-memory-v1/resume/control.py","benchmarks/soc-core-memory-v1/resume/plan.json"])\n        end'
        self.assertIn(source_paths, self.current)

    def test_bridge_requires_exact_interpreter_and_failure_propagation(self):
        bridge = region(self.current, 'function endpoint_resume_authorization(', 'function endpoint_worker(')
        self.assertIn('get(ENV,"SOC_CORE_PYTHON","")', bridge)
        self.assertIn('isabspath(python) && isfile(python)', bridge)
        self.assertIn('JSON3.read(read(command,String),Dict{String,Any})', bridge)
        self.assertNotIn('ignorestatus', bridge)
        self.assertNotIn('catch', bridge)
        self.assertIn('digest(path)==before', bridge)
        self.assertIn('digest(abspath(args[5]))==result["resume_authentication"]["authorization_sha256"]', self.current)


if __name__ == '__main__':
    unittest.main()
