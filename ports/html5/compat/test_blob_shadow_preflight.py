"""Local report contract checks; does not compile UE, load assets or launch browsers."""
from pathlib import Path
import json,re,unittest
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'UT4Html5Compat/Source/UT4Html5Compat/Private/BlobShadowPreflightReport.h'
class BlobReportTests(unittest.TestCase):
 def setUp(self):self.source=SOURCE.read_text()
 def test_exact_read_only_scope(self):
  spec=json.loads((ROOT/'report.blob-shadow.json').read_text())
  self.assertEqual(spec['schema'],'ut4-blob-shadow-report-v1');self.assertIs(spec['read_only'],True)
  self.assertEqual(spec['materials'],['/Game/RestrictedAssets/Effects/Nick/M_Robust_BlobShadow','/Game/RestrictedAssets/Effects/Nick/M_Robust_BlobShadowInverse'])
  self.assertEqual(spec['mesh'],'/Game/RestrictedAssets/Effects/Nick/miniCylinder')
  self.assertEqual(spec['character'],'/Game/RestrictedAssets/Blueprints/BaseUTCharacter')
  self.assertIs(spec['include_loaded_world_components'],False)
  self.assertIn('Materials->Num() != 2',self.source)
  self.assertIn('V->Type != EJson::String',self.source)
  self.assertIn('Paths[0] ==',self.source);self.assertIn('Paths[1] ==',self.source)
 def test_no_mutating_engine_or_save_operations(self):
  self.assertIsNone(re.search(r'\b(SavePackage|SetDirtyFlag|MarkPackageDirty|PreEditChange|PostEditChange|SetMaterial|SetStaticMesh|LoadMap|SpawnActor|CreateDynamicMaterialInstance|SetScalarParameterValue|SetVectorParameterValue|AddGameNameRedirect|NewObject|DuplicateObject)\s*\(',self.source))
  self.assertIn('TEXT("Manifest=")',self.source);self.assertIn('TEXT("Receipt=")',self.source)
 def test_reuses_full_pinned_native_graph_and_records_dirty_without_clearing(self):
  self.assertIn('MRDescribe(M, Registry, J)',self.source)
  self.assertIn('package_dirty_before_description',self.source)
  self.assertIn('FMRDirtyObserver',self.source)
  self.assertIn('MRHashPackage(BSRCharacter()',self.source)
 def test_loaded_components_opt_in_exact_mesh_not_claimed_live(self):
  self.assertIn('LoadedComponents && !C->IsTemplate() && C->GetWorld() && C->GetStaticMesh() == Mesh',self.source)
  self.assertIn('world_begun_play',self.source)
  self.assertIn('Zero live components is not runtime evidence.',self.source)
  for getter in ['GetAttachParent()', 'GetAttachSocketName()', 'GetComponentTransform()', 'GetScalarParameterValue(', 'GetVectorParameterValue(']:self.assertIn(getter,self.source)
 def test_fail_closed_budgets_and_separate_report_option(self):
  for guard in ['Templates + Live >= 128','C->GetNumMaterials() > 16','Names.Num() > 128','8 * 1024 * 1024','32 * 1024 * 1024 - Text.Len()']:self.assertIn(guard,self.source)
  self.assertIn('TEXT("BlobReportSpec=")',self.source)
  self.assertIn('Output.Emit(Done, TEXT("complete")) ? 0 : 1',self.source)
  self.assertIn('!IsInGameThread()',self.source)
if __name__=='__main__':unittest.main()
