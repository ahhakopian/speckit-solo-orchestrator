"""Conditional proof-plan inputs using actual platform validator and test-only index."""
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch
import test_solo
from test_solo import Fixture, TOOLS, solo, ROOT, GREENFIELD
from specify_cli.presets import PresetManager, PresetResolver

PLATFORM = TOOLS / "verification-platform"

class VerificationInputs(Fixture):
    def snapshot_resources(self, full=False):
        folder = self.project / "snapshot"
        folder.mkdir()
        contents = {
            "integration": (PLATFORM / "contracts/verification-integration.md").read_bytes(),
            "schema": (PLATFORM / "schemas/browser-verification-plan.schema.json").read_bytes(),
            "descriptors": b'{"schemaVersion":1,"providers":[]}',
        }
        identity = {"repository": "https://github.com/ahhakopian/verification-platform",
                    "tag": "v0.1.0", "sourceCommit": "7cbb05c2efb409e7ce42ab576192141b3e47ac03"}
        resources = []
        for name, data in contents.items():
            (folder / name).write_bytes(data)
            resources.append({"id": name, "path": name, "sha256": hashlib.sha256(data).hexdigest(),
                              "formatVersion": 1, "kind": "normative", "dependencies": []})
        if full:
            inventory = subprocess.run(["node", "--input-type=module", "-e",
                "import {requiredExecutionResources,publicEntries} from './dist/src/resources/inventory.js'; console.log(JSON.stringify({requiredExecutionResources,publicEntries}))"],
                cwd=PLATFORM, capture_output=True, text=True, check=True)
            entries = json.loads(inventory.stdout)
            for expected in entries["requiredExecutionResources"]:
                path = folder / expected["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test-only indexed execution asset")
                resource = {**expected, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "formatVersion": 1, "dependencies": []}
                if expected["id"] in entries["publicEntries"]:
                    resource["entry"] = entries["publicEntries"][expected["id"]]
                resources.append(resource)
        index = json.dumps({"schemaVersion": 1, **identity, "resources": resources}).encode()
        (folder / "index.json").write_bytes(index)
        binding = {"schemaVersion": 1, **identity, "index": {"asset": "index.json", "sha256": hashlib.sha256(index).hexdigest()},
                   "resources": {"integration": "integration", "planSchema": "schema", "descriptors": "descriptors"}}
        self.write(".verification/platform.json", json.dumps(binding))
        return patch.dict("os.environ", {"VERIFICATION_PLATFORM_VALIDATOR": str(PLATFORM / "dist/src/validation/cli.js"),
                                        "VERIFICATION_PLATFORM_RESOURCES": str(folder)})

    def adopted(self):
        self.feature()
        self.write("specs/001-first/plan.md", "COMPATIBLE\n## Verification Integration\nApplicability: applicable\nReason: Browser proof required.\n")
        proof = json.loads((PLATFORM / "tests/fixtures/plan.json").read_text())
        proof["configurationReferences"].append({"id": "provider", "path": "declaration.json", "purpose": "provider-declaration", "disposition": "planned"})
        self.write("declaration.json", '{"observation":"actual boundary"}')
        self.write("specs/001-first/browser-verification-plan.json", json.dumps(proof))

    def test_missing_required_artifacts_route_to_plan_before_approval(self):
        self.feature()
        self.write("specs/001-first/plan.md", "COMPATIBLE\n## Verification Integration\nApplicability: applicable\nReason: Browser proof.\n")
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.plan"])
        with self.assertRaisesRegex(Exception, "reconciliation required"):
            self.repo.approve("plan-ux", human=True, verification="PASS")

    def test_plan_inputs_bind_json_binding_and_normative_declaration(self):
        self.adopted()
        with self.snapshot_resources():
            approval = self.repo.approve("plan-ux", human=True, verification="PASS")
            for path in (".verification/platform.json", "specs/001-first/browser-verification-plan.json", "declaration.json"):
                self.assertIn(path, approval["inputs"])
            self.write("declaration.json", '{"observation":"changed boundary"}')
            self.assertEqual(self.commands(self.repo.next()), ["speckit.plan"])

    def test_external_resource_tampering_is_revalidated(self):
        self.adopted()
        with self.snapshot_resources():
            self.repo.approve("plan-ux", human=True, verification="PASS")
            (self.project / "snapshot/schema").write_text("tampered")
            self.assertEqual(self.commands(self.repo.next()), ["speckit.plan"])

    def test_justified_non_applicability_no_empty_json(self):
        self.feature()
        self.write("specs/001-first/plan.md", "COMPATIBLE\n## Verification Integration\nApplicability: not applicable\nReason: Pure domain invariant, established by unit evidence.\n")
        approval = self.repo.approve("plan-ux", human=True, verification="PASS")
        self.assertFalse(any(p.endswith("browser-verification-plan.json") for p in approval["inputs"]))

    def test_shared_binding_does_not_activate_unrelated_legacy_feature_or_load_platform(self):
        self.feature()
        self.write(".verification/platform.json", '{"unrelated":"binding"}')
        with patch.dict("os.environ", {"VERIFICATION_PLATFORM_VALIDATOR":"", "VERIFICATION_PLATFORM_RESOURCES":""}), patch.object(subprocess,"run",wraps=subprocess.run) as run:
            approval=self.repo.approve("plan-ux",human=True,verification="PASS")
            self.assertNotIn(".verification/platform.json",approval["inputs"])
            self.assertFalse(any(call.args[0][0]=="node" for call in run.call_args_list))

    def test_non_applicable_feature_ignores_unrelated_binding_and_uninstalled_platform(self):
        self.feature()
        self.write(".verification/platform.json", '{"unrelated":"binding"}')
        self.write("specs/001-first/plan.md", "COMPATIBLE\n## Verification Integration\nApplicability: not applicable\nReason: Domain-only proof.\n")
        with patch.dict("os.environ", {"VERIFICATION_PLATFORM_VALIDATOR":"", "VERIFICATION_PLATFORM_RESOURCES":""}):
            approval=self.repo.approve("plan-ux",human=True,verification="PASS")
            self.assertNotIn(".verification/platform.json",approval["inputs"])

    def test_only_applicable_proof_boundary_requires_missing_platform_resources(self):
        self.adopted()
        self.write(".verification/platform.json", '{}')
        with patch.dict("os.environ", {"VERIFICATION_PLATFORM_VALIDATOR":"", "VERIFICATION_PLATFORM_RESOURCES":""}):
            self.assertEqual(self.commands(self.repo.next()),["speckit.plan"])

    def test_malformed_applicability_cannot_be_approved(self):
        self.feature()
        for text in ("Applicability: unknown\nReason: Unresolved.\n",
                     "Applicability: applicable\nApplicability: not applicable\nReason: Conflict.\n",
                     "Applicability: not applicable\n",
                     "Applicability: not applicable\nReason:\n"):
            with self.subTest(text=text):
                self.write("specs/001-first/plan.md", "COMPATIBLE\n## Verification Integration\n" + text)
                with self.assertRaisesRegex(Exception, "reconciliation required"):
                    self.repo.approve("plan-ux", human=True, verification="PASS")

    def test_invalid_missing_and_stale_binding_or_plan_fail_at_proof_boundary(self):
        self.adopted()
        with self.snapshot_resources():
            self.repo.approve("plan-ux", human=True, verification="PASS")
            for relative in (".verification/platform.json", "specs/001-first/browser-verification-plan.json"):
                path = self.project / relative
                original = path.read_text()
                for content in (None, "not json", "{}"):
                    with self.subTest(path=relative, content=content):
                        if content is None:
                            path.unlink()
                        else:
                            path.write_text(content)
                        self.assertEqual(self.commands(self.repo.next()), ["speckit.plan"])
                        with self.assertRaisesRegex(Exception, "reconciliation required"):
                            self.repo.approve("plan-ux", human=True, verification="PASS")
                        path.write_text(original)
            binding_path = self.project / ".verification/platform.json"
            original_binding = binding_path.read_text()
            binding_path.write_text(json.dumps(json.loads(original_binding), indent=2))
            self.assertEqual(self.commands(self.repo.next()), ["speckit.plan"])
            binding_path.write_text(original_binding)
            proof_path = self.project / "specs/001-first/browser-verification-plan.json"
            proof = json.loads(proof_path.read_text())
            proof["claims"][0]["expected"] = "Changed approved obligation"
            proof_path.write_text(json.dumps(proof))
            self.assertEqual(self.commands(self.repo.next()), ["speckit.plan"])

    def test_development_readiness_binds_design_without_executable_provider_and_preserves_task_marks(self):
        self.adopted()
        with self.snapshot_resources():
            for boundary in ("plan-ux", "tasks-guard", "implementation-readiness"):
                self.repo.approve(boundary, human=True, verification="PASS")
            data = self.repo.load()
            entry, spec = self.repo.feature()
            before = self.repo.require_review_approval(data, "implementation-readiness", entry, spec)
            self.assertFalse((self.project / "verification-fixtures.ts").exists())
            self.write("specs/001-first/tasks.md", "- [x] T001 Implement approved contract\n")
            after = self.repo.require_review_approval(data, "implementation-readiness", entry, spec)
            self.assertEqual(before["fingerprint"], after["fingerprint"])
            self.write("verification-fixtures.ts", "export const runtime = 'delivered';")
            self.write("evidence/result.json", '{"verdict":"PASS"}')
            self.assertEqual(before["fingerprint"], self.repo.require_review_approval(data, "implementation-readiness", entry, spec)["fingerprint"])

    def test_transient_handoff_binds_current_native_approvals_and_delivered_planned_configuration(self):
        self.adopted()
        with self.snapshot_resources(full=True):
            for boundary in ("plan-ux", "tasks-guard", "implementation-readiness"):
                self.repo.approve(boundary, human=True, verification="PASS")
            relative = "specs/001-first/browser-verification-plan.json"
            original = (self.project / relative).read_bytes()
            digest = hashlib.sha256(original).hexdigest()
            binding = json.loads((self.project / ".verification/platform.json").read_text())
            bound = hashlib.sha256(json.dumps(binding, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            assignment = {
                "schemaVersion":1,"planDigest":digest,"bindingDigest":bound,
                "authorization":{"reference":"explicit fixture-only caller", "planDigest":digest,"bindingDigest":bound,"allowedEffects":[]},
                "environments":[{"id":"assigned-chrome","build":"synthetic","runtimeConfig":"runtime.json","powershell":"synthetic","launch":False,"selection":{"pageUrl":"https://fixture.invalid"},"exclusive":True}],
                "fixtureEntry":"verification-fixtures.ts","runnerConfig":"config.ts","providers":[],"outputDirectory":"output",
                "ownership":{"borrowed":["browser"],"disposable":[],"cleanup":[]},"evidenceConstraints":[]}
            with self.assertRaisesRegex(Exception,"actual existing referenced configuration"):
                self.repo.verification_handoff(assignment)
            self.write("verification-fixtures.ts", "exported fixture delivered by approved task")
            handoff = self.repo.verification_handoff(assignment)
            self.assertEqual(handoff["planPath"], relative)
            self.assertEqual(handoff["planDigest"], digest)
            self.assertIn("current native approvals:",handoff["assignment"]["authorization"]["reference"])
            self.assertEqual((self.project / relative).read_bytes(), original)
            for field in ("planDigest", "bindingDigest"):
                changed = json.loads(json.dumps(assignment))
                changed["authorization"][field] = "0" * 64
                with self.assertRaisesRegex(Exception, "not tied to current plan/binding"):
                    self.repo.verification_handoff(changed)
            self.write("declaration.json", '{"observation":"changed contract"}')
            with self.assertRaisesRegex(Exception,"Stale plan-ux"):
                self.repo.verification_handoff(assignment)

    def test_native_install_reinstall_composes_optional_integration_and_preserves_binding(self):
        self.adopted()
        with self.snapshot_resources():
            for boundary in ("plan-ux", "tasks-guard", "implementation-readiness"):
                self.repo.approve(boundary, human=True, verification="PASS")
            binding = (self.project / ".verification/platform.json").read_bytes()
            registry = (self.project / solo.REGISTRY).read_bytes()
            with patch.dict("os.environ", {"VERIFICATION_PLATFORM_VALIDATOR": "", "VERIFICATION_PLATFORM_RESOURCES": ""}):
                manager = test_solo.InstallationTests.install(self)
                presets = PresetManager(self.project)
                for priority, source in ((10, GREENFIELD / "preset"),
                                         (20, TOOLS / "speckit-feature-governance/preset"),
                                         (30, TOOLS / "greenfield-mvp-governance/preset")):
                    presets.install_from_directory(source, "0.16.2", priority=priority)
                for command in ("speckit.plan", "speckit.tasks", "speckit.analyze"):
                    effective = PresetResolver(self.project).resolve_content(command, "command")
                    self.assertIn("verification-integration.md", effective)
                self.assertEqual([h["command"] for h in solo.hooks(self.project)["hooks"]], list(solo.REQUIRED_HOOKS))
                manager.install_from_directory(ROOT / "extension", "0.16.2", force=True)
                manager.install_from_directory(TOOLS / "speckit-feature-governance/extension", "0.16.2", force=True)
                presets.install_from_directory(TOOLS / "speckit-feature-governance/preset", "0.16.2", priority=20, force=True)
            self.assertEqual((self.project / ".verification/platform.json").read_bytes(), binding)
            self.assertEqual((self.project / solo.REGISTRY).read_bytes(), registry)
            self.repo.require_review_approval(self.repo.load(), "implementation-readiness", *self.repo.feature())
