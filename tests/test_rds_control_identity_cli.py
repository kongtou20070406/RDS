"""Real control-check CLI: unresolved identities never qualify cached reuse."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_rds_costs as costs_fixture

ROOT=Path(__file__).resolve().parents[1]


class ControlIdentityCliTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix="RDS control identity ")
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name).resolve()
        fixture=costs_fixture.CostsTests("test_reuse_demands_complete_identity_and_current_artifact_bytes")
        self.control,self.current=fixture.make_control(self.root)

    def check(self, control, current):
        candidate=self.root/"candidate.json"
        expected=self.root/"current.json"
        candidate.write_text(json.dumps(costs_fixture.rehash(deepcopy(control))),encoding="utf-8")
        expected.write_text(json.dumps(current),encoding="utf-8")
        result=subprocess.run([sys.executable,"-B",str(ROOT/"scripts/rds_cli.py"),
            "--root",str(self.root),"project","control-check","--candidate",str(candidate),
            "--current",str(expected)],capture_output=True,text=True,encoding="utf-8",timeout=60,
            env={**os.environ,"RDS_USAGE_DB":str(self.root/"usage.sqlite3")})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.root/".rds").exists())
        answer=json.loads(result.stdout)
        self.assertEqual(answer["scientific_assessment"],"UNKNOWN")
        return answer

    def test_scalar_and_nested_unknown_spellings_refuse_reuse(self):
        for token in ("UNKNOWN"," UNKNOWN ","\tunknown\t","\nUnKnOwN\r","\u00a0UNKNOWN\u00a0"):
            for field,value in (("seed",token),("schedule",{"steps":token}),
                                ("numeric_protocol",{"devices":["cpu",{"dtype":token}]})):
                for side in ("both","candidate","current"):
                    with self.subTest(token=repr(token),field=field,side=side):
                        control,current=deepcopy(self.control),deepcopy(self.current)
                        if side!="current":
                            control["protocol"][field]=value
                        if side!="candidate":
                            current["protocol"][field]=value
                        answer=self.check(control,current)
                        self.assertFalse(answer["reusable"],answer)
                        self.assertIn("missing control identity: "+field,answer["reasons"])

    def test_known_matching_identity_stays_reusable(self):
        self.assertTrue(self.check(self.control,self.current)["reusable"])

    def test_known_identities_keep_exact_comparison(self):
        # Only the missing-value classification is stripped; real values retain
        # their exact identity, even when both are individually known strings.
        for old,new in (("custom-init"," custom-init "),("custom-init","CUSTOM-INIT")):
            control,current=deepcopy(self.control),deepcopy(self.current)
            control["protocol"]["init"]=old
            current["protocol"]["init"]=new
            self.assertFalse(self.check(control,current)["reusable"])


if __name__=="__main__":
    unittest.main()
