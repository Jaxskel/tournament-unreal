"""Reporting-only regression; pinned licensed source/evidence stays private."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE/'UT4Html5Compat/Source/UT4Html5Compat/Private/MaterialPreflightReport.h'
PRIVATE = None


class InputNames(unittest.TestCase):
    def test_actual_reporting_expression_keeps_raw_call_names_and_other_display_names(self):
        text = HEADER.read_text()
        expression = re.search(r'P->SetStringField\(TEXT\("name"\), (InputFunction \? .*?)\);', text).group(1)
        self.assertEqual(expression, 'InputFunction ? InputFunction->FunctionInputs[I].Input.InputName : E->GetInputName(I)')
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler, 'Host compiler required')
        program = r'''
#include <cassert>
#include <string>
#include <vector>
struct Expr { virtual std::string GetInputName(int) { return "other display name (V3)"; } virtual ~Expr(){} };
struct Slot { struct { std::string InputName; } Input; };
struct Call : Expr { std::vector<Slot> FunctionInputs; bool Resolved=false;
 std::string GetInputName(int I) override { return FunctionInputs[I].Input.InputName + (Resolved ? " (V2)" : ""); }
};
std::string Report(Expr* E,int I) {
 const auto* InputFunction=dynamic_cast<Call*>(E);
 return EXPRESSION;
}
int main(){
 Call C; C.FunctionInputs={{{"Vector 2"}},{{"Literal name (V2)"}}};
 for(bool Resolved : {false,true}) { C.Resolved=Resolved;
  assert(Report(&C,0)=="Vector 2"); assert(Report(&C,1)=="Literal name (V2)"); }
 Expr E; assert(Report(&E,0)=="other display name (V3)");
}
'''.replace('EXPRESSION', expression)
        with tempfile.TemporaryDirectory(prefix='ut4-input-names-') as tmp:
            root = Path(tmp); cpp = root/'names.cpp'; exe = root/'names'
            cpp.write_text(program)
            result = subprocess.run([compiler,'-std=c++14','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)], capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(exe)],check=True,timeout=10)

    def test_pinned_getinputs_order_and_display_only_suffix(self):
        if PRIVATE is None: self.skipTest('Provide --private-root work/ut4-html5')
        src = PRIVATE/'weapon-fidelity-source/MaterialExpressions.cpp'
        self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(),
                         'aabf83778c557f3e68ff9a8ee003443b42ae12262fb2e87b406244e91f763d27')
        source = src.read_text()
        getinputs = source.split('UMaterialExpressionMaterialFunctionCall::GetInputs()',1)[1].split('UMaterialExpressionMaterialFunctionCall::GetInput(',1)[0]
        self.assertIn('i < FunctionInputs.Num()',getinputs)
        self.assertIn('Result.Add(&FunctionInputs[i].Input)',getinputs)
        name = source.split('UMaterialExpressionMaterialFunctionCall::GetInputName(',1)[1].split('UMaterialExpressionMaterialFunctionCall::IsInputConnectionRequired(',1)[0]
        self.assertIn('FunctionInputs[InputIndex].ExpressionInput != NULL',name)
        self.assertIn('GetInputTypeName(FunctionInputs[InputIndex].ExpressionInput->InputType)',name)
        self.assertIn('return FunctionInputs[InputIndex].Input.InputName;',name)

    def test_captured_blob_nodes_differ_only_in_call_display_names(self):
        if PRIVATE is None: self.skipTest('Provide --private-root work/ut4-html5')
        old = json.loads((PRIVATE/'blob-shadow-review/experiment-baseline.json').read_text())['materials']
        new = json.loads((PRIVATE/'fidelity-rendering-report-1/records.json').read_text())
        count = 0
        for previous in old:
            current = next(r for r in new if r.get('material')==previous['material'])
            nodes = copy.deepcopy(current['nodes'])
            self.assertEqual(len(previous['nodes']),len(nodes))
            for a,b in zip(previous['nodes'],nodes):
                self.assertEqual(len(a['inputs']),len(b['inputs']))
                for x,y in zip(a['inputs'],b['inputs']):
                    if x['name']!=y['name']:
                        self.assertEqual(b['class'],'MaterialExpressionMaterialFunctionCall')
                        self.assertRegex(y['name'][len(x['name']):],r'^ \((S|V2|V3|V4|T2d|TCube|B|MA)\)$')
                        self.assertTrue(y['name'].startswith(x['name']))
                        y['name']=x['name']; count+=1
            self.assertEqual(previous['nodes'],nodes)  # No other node field excluded.
        self.assertEqual(count,16)


if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-root',type=Path)
    args,rest=parser.parse_known_args();PRIVATE=args.private_root
    unittest.main(argv=[__file__,*rest])
