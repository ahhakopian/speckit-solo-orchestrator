"""Deterministic native installation and repository-derived routing fixtures."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml
import specify_cli
from specify_cli.extensions import ExtensionManager, HookExecutor
from specify_cli.presets import PresetManager, PresetResolver

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent
GREENFIELD = TOOLS / "speckit-solo-governance"
spec = importlib.util.spec_from_file_location("solo", ROOT / "extension/scripts/solo.py")
solo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solo)


class Fixture(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.environment = patch.dict("os.environ", {"SPECIFY_FEATURE_DIRECTORY": "", "SPECIFY_FEATURE": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.write(".specify/init-options.json", json.dumps({"ai": "codex", "ai_skills": True}))
        for name, folder in (("greenfield-foundation", "foundation"), ("greenfield-roadmap-lifecycle", "extension")):
            shutil.copytree(GREENFIELD / folder, self.project / ".specify/extensions" / name)
        core = Path(specify_cli.__file__).parent / "core_pack/scripts/python"
        shutil.copytree(core, self.project / ".specify/scripts/python")
        self.write(".specify/extensions/greenfield-roadmap-lifecycle/greenfield-roadmap-lifecycle-config.yml",
                   "completion_mode: human\napproval_registry: .specify/governance/hitl.json\n")
        self.write("prd.md", "Approved product input.\n")
        self.repo = solo.Repository(self.project)

    def write(self, name, text):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def foundation(self):
        self.repo.declare_prd("prd.md", human=True)
        self.write("architecture/baseline.md", "Status: Draft\nRevision: 1\nApproved contract.\n")
        self.repo.approve("architecture", human=True, verification="PASS")
        self.write("architecture/baseline.md", "Status: Approved\nRevision: 1\nApproved contract.\n")
        self.write("ROADMAP.md", "<!-- roadmap-entry: RM-01 -->\nStatus: planned\nStatus reason: pending approval\nDepends on: none\nFeature spec: none\nOutcome: First approved contract.\n")
        self.write(".specify/memory/constitution.md", "# Constitution\nDurable invariant.\n")
        self.repo.approve("project-ready", human=True, verification="PROJECT READY")

    def feature(self, tasks="- [ ] T001 Implement approved contract\n"):
        self.foundation()
        lifecycle = self.repo.lifecycle
        args = lifecycle.parser().parse_args(["initial", "--registry", solo.REGISTRY])
        lifecycle.apply(self.project, args)
        self.write("specs/001-first/spec.md", "ROADMAP entry: RM-01\nApproved local behavior.\n")
        self.write("specs/001-first/checklists/requirements.md", "- [x] Quality\n")
        self.write(".specify/feature.json", json.dumps({"feature_directory": "specs/001-first"}))
        args = lifecycle.parser().parse_args(["start", "RM-01", "specs/001-first/spec.md"])
        lifecycle.apply(self.project, args)
        self.repo.approve("spec", human=True, verification="PASS")
        self.write("specs/001-first/plan.md", "COMPATIBLE\nApproved design.\n")
        self.repo.approve("plan-ux", human=True, verification="PASS")
        self.write("specs/001-first/tasks.md", tasks)
        self.repo.approve("tasks-guard", human=True, verification="PASS")

    def commands(self, route):
        return [c.get("command", c.get("interface")) for c in route["commands"]]

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}


class RoutingTests(Fixture):
    def test_approved_draft_architecture_with_existing_roadmap_routes_to_roadmap(self):
        self.repo.declare_prd("prd.md", human=True)
        self.write("architecture/baseline.md", "Status: Draft\nRevision: 1\nApproved contract.\n")
        self.repo.approve("architecture", human=True, verification="PASS")
        self.write("ROADMAP.md", "<!-- roadmap-entry: RM-01 -->\nStatus: planned\nStatus reason: pending\nDepends on: none\nFeature spec: none\n")
        before = self.snapshot()
        route = solo.Repository(self.project).next()
        self.assertEqual(self.commands(route), ["speckit.greenfield-foundation.roadmap"])
        self.assertEqual(route["commands"][0]["inputs"], {"canonical_prd": "prd.md", "authorization": "native"})
        self.assertNotIn("boundary", route)
        self.assertEqual(before, self.snapshot())

    def test_foundation_actions_delegate_and_stop_at_existing_boundaries(self):
        self.assertEqual(self.repo.next()["result"], "APPROVED PRD INPUT REQUIRED")
        self.repo.declare_prd("prd.md", human=True)
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.greenfield-foundation.architecture"])
        self.assertEqual(route["boundary"], "architecture")
        self.write("architecture/baseline.md", "Status: Draft\nApproved contract.\n")
        self.repo.approve("architecture", human=True, verification="PASS")
        self.assertEqual(self.commands(self.repo.next()), ["speckit.greenfield-foundation.roadmap"])
        self.write("architecture/baseline.md", "Status: Approved\nApproved contract.\n")
        self.write("ROADMAP.md", "<!-- roadmap-entry: RM-01 -->\nStatus: planned\nStatus reason: pending\nDepends on: none\nFeature spec: none\n")
        self.assertEqual(self.repo.next()["commands"][0]["inputs"]["operation"], "prepare")
        self.write(".specify/memory/constitution.md", "# Native Constitution\n")
        self.assertEqual(self.repo.next()["commands"][0]["inputs"]["operation"], "verify")
        self.repo.approve("project-ready", human=True, verification="PROJECT READY")
        route = solo.Repository(self.project).next()
        self.assertEqual(route["result"], "PROJECT READY")
        self.assertEqual(route["commands"][0]["argv"], ["initial", "--registry", solo.REGISTRY])

    def test_fresh_invocations_continue_from_artifacts_and_approvals_alone(self):
        self.feature()
        expected = ["speckit.analyze", "speckit.implement"]
        before = self.snapshot()
        self.assertEqual(self.commands(solo.Repository(self.project).next()), expected)
        self.assertEqual(self.commands(solo.Repository(self.project).next()), expected)
        self.assertEqual(before, self.snapshot())
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        solo.Repository(self.project).readiness()
        (self.project / "specs/001-first/tasks.md").unlink()
        self.assertEqual(self.commands(solo.Repository(self.project).next()), ["speckit.tasks"])
        (self.project / "specs/001-first/plan.md").unlink()
        self.repo.approve("spec", human=True, verification="PASS")
        self.assertEqual(self.commands(solo.Repository(self.project).next()), ["speckit.clarify", "speckit.plan"])

    def test_ready_feature_routes_despite_planned_dependents(self):
        self.foundation()
        roadmap = self.project / "ROADMAP.md"
        original = roadmap.read_text()
        self.write("ROADMAP.md", original + original.replace("RM-01", "RM-02").replace("Depends on: none", "Depends on: RM-01"))
        self.repo.approve("project-ready", human=True, verification="PROJECT READY")
        self.repo.lifecycle.apply(self.project, self.repo.lifecycle.parser().parse_args(["initial", "--registry", solo.REGISTRY]))
        route = solo.Repository(self.project).next()
        self.assertEqual(self.commands(route), ["speckit.specify"])
        self.assertEqual(route["commands"][0]["inputs"], {"roadmap_entry": "RM-01"})

    def test_approvals_persist_replace_and_bind_current_content(self):
        self.feature()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        data = self.repo.load()
        self.assertEqual(set(data), self.repo.facts.ROOT_FIELDS)
        self.assertEqual(sum(a["boundary"] == solo.READINESS for a in data["approvals"]), 1)
        solo.Repository(self.project).readiness()
        for name in ("specs/001-first/tasks.md", "specs/001-first/plan.md", "DESIGN.md",
                     "specs/001-first/design/ux.md"):
            with self.subTest(name=name):
                self.repo.approve(solo.READINESS, human=True, verification="PASS")
                self.write(name, "Changed current content.\n")
                with self.assertRaisesRegex(ValueError, "Stale|omits"):
                    solo.Repository(self.project).readiness()

    def test_readiness_binds_optional_authority_additions_and_deletions(self):
        self.feature()
        self.write("specs/001-first/design/ux.md", "Current UX authority.\n")
        self.write("DESIGN.md", "Current design.\n")
        approval = self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.assertEqual(approval["inputs"], self.repo.review_inputs(
            self.repo.load(), solo.READINESS, "specs/001-first/spec.md"))
        (self.project / "specs/001-first/design/ux.md").unlink()
        with self.assertRaisesRegex(ValueError, "Stale|omits"):
            self.repo.readiness()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        (self.project / "DESIGN.md").unlink()
        with self.assertRaisesRegex(ValueError, "Stale|omits"):
            self.repo.readiness()

    def test_registry_accepts_only_approved_fact_boundaries_and_subject_categories(self):
        self.feature()
        template = self.repo.approve(solo.READINESS, human=True, verification="PASS")
        expected = {"architecture", "project-ready", "spec", "plan-ux", "tasks-guard",
                    "implementation-readiness", "post-implementation", "human-acceptance"}
        self.assertEqual(solo.FOUNDATION_APPROVALS | solo.FEATURE_APPROVALS, expected)
        for boundary in sorted(expected):
            with self.subTest(boundary=boundary):
                data = self.repo.load()
                subject = "foundation" if boundary in solo.FOUNDATION_APPROVALS else "RM-01"
                approval = dict(template, boundary=boundary, subject=subject,
                                verification="PROJECT READY" if boundary == "project-ready" else "PASS")
                data["approvals"] = [a for a in data["approvals"] if a["boundary"] != boundary] + [approval]
                self.repo.save(data)
                self.assertIn(approval, self.repo.load()["approvals"])
                approval["verification"] = "PROJECT READY" if boundary != "project-ready" else "PASS"
                with self.assertRaisesRegex(ValueError, "verification/category"):
                    self.repo.save(data)
                approval["verification"] = "PROJECT READY" if boundary == "project-ready" else "PASS"
                approval["subject"] = "RM-01" if subject == "foundation" else "foundation"
                with self.assertRaisesRegex(ValueError, "subject/category"):
                    self.repo.save(data)
        # PRD remains a shared approved-input declaration, outside Solo HITL vocabulary.
        data = self.repo.load()
        prd = next(a for a in data["approvals"] if a["boundary"] == "prd")
        self.assertEqual((prd["subject"], prd["decision"]), ("foundation", "approve"))
        prd["decision"] = "reject"
        with self.assertRaisesRegex(ValueError, "already-approved input"):
            self.repo.save(data)

    def test_registry_rejects_stage_ledger_boundaries_on_write_and_read(self):
        self.feature()
        template = self.repo.approve(solo.READINESS, human=True, verification="PASS")
        original = (self.project / solo.REGISTRY).read_bytes()
        for boundary in ("analyze-completed", "clarify-completed", "checklist-completed", "checklist-skipped",
                         "plan-completed", "tasks-completed", "implement-completed", "converge-completed",
                         "tasks-done", "current-stage", "next-stage", "unknown"):
            with self.subTest(boundary=boundary):
                data = json.loads(original)
                data["approvals"].append(dict(template, boundary=boundary))
                with self.assertRaisesRegex(ValueError, "Unsupported Solo approval boundary"):
                    self.repo.save(data)
                self.assertEqual((self.project / solo.REGISTRY).read_bytes(), original)
                self.write(solo.REGISTRY, json.dumps(data))
                with self.assertRaisesRegex(ValueError, "Unsupported Solo approval boundary"):
                    self.repo.load()
                (self.project / solo.REGISTRY).write_bytes(original)

    def test_missing_rejected_nonhuman_and_invalid_approvals_block(self):
        self.feature()
        with self.assertRaisesRegex(ValueError, "approval required"):
            self.repo.readiness()
        with self.assertRaisesRegex(ValueError, "human declaration"):
            self.repo.approve(solo.READINESS, human=False, verification="PASS")
        self.repo.approve(solo.READINESS, human=True, verification="PASS", reject=True)
        with self.assertRaisesRegex(ValueError, "approval required"):
            self.repo.readiness()
        with self.assertRaisesRegex(ValueError, "PROJECT READY"):
            self.repo.approve("project-ready", human=True, verification="PASS")

    def test_greenfield_validation_fingerprint_and_lifecycle_are_reused(self):
        self.feature()
        with patch.object(self.repo.facts, "fingerprint", wraps=self.repo.facts.fingerprint) as fingerprint:
            self.repo.approve(solo.READINESS, human=True, verification="PASS")
            self.repo.readiness()
            self.assertNotIn("human-acceptance", [c.args[1] for c in fingerprint.call_args_list])
            self.assertIn("prd", [c.args[1] for c in fingerprint.call_args_list])
        with patch.object(self.repo.facts, "require_approval", wraps=self.repo.facts.require_approval) as require:
            with patch.object(self.repo.lifecycle, "require_clean_tasks", wraps=self.repo.lifecycle.require_clean_tasks) as tasks:
                self.repo.next()
                self.assertIn("project-ready", [c.args[2] for c in require.call_args_list])
                tasks.assert_called_once()
        data = self.repo.load()
        data["current_stage"] = "implement"
        before = (self.project / solo.REGISTRY).read_bytes()
        with self.assertRaisesRegex(ValueError, "schema"):
            self.repo.save(data)
        self.assertEqual(before, (self.project / solo.REGISTRY).read_bytes())

    def test_stale_upstream_authority_and_product_gap_never_authorize(self):
        self.feature()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.write("prd.md", "Changed product authority.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.repo.next()
        with self.assertRaisesRegex(ValueError, "stale"):
            self.repo.readiness()
        self.repo.declare_prd("prd.md", human=True)
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.greenfield-foundation.architecture-reconcile"])
        self.assertEqual(route["boundary"], "architecture")
        data = self.repo.load()
        data["product_gaps"] = [dict(gap_id="gap-a", question="Which approved behavior?", options=["A", "B"],
            recommended_option=1, rationale="Limited scope.", status="unresolved", discovered_on_revision=data["prd_revision"])]
        self.repo.save(data)
        with self.assertRaisesRegex(ValueError, "PRODUCT GAP"):
            self.repo.declare_prd("prd.md", human=True)

    def test_ambiguity_conflicting_context_and_automatic_mode_stop(self):
        self.feature()
        roadmap = self.project / "ROADMAP.md"
        original = roadmap.read_text()
        self.write("ROADMAP.md", original + original.replace("RM-01", "RM-02"))
        # Refresh upstream declaration for the changed authority, without selecting a Feature.
        self.repo.approve("project-ready", human=True, verification="PROJECT READY")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.repo.next()
        self.write("ROADMAP.md", original)
        self.repo.approve("project-ready", human=True, verification="PROJECT READY")
        self.write(".specify/feature.json", json.dumps({"feature_directory": "specs/other"}))
        with self.assertRaises(ValueError):
            self.repo.next()
        self.write(".specify/feature.json", json.dumps({"feature_directory": "specs/001-first"}))
        self.write(".specify/extensions/greenfield-roadmap-lifecycle/greenfield-roadmap-lifecycle-config.yml", "completion_mode: automatic\n")
        with self.assertRaisesRegex(ValueError, "human completion mode"):
            self.repo.next()

    def test_human_acceptance_delegates_completion_and_fresh_verification(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        self.write("evidence/result.txt", "Current verified implementation.\n")
        self.repo.approve("post-implementation", human=True, verification="PASS")
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.converge", "speckit.greenfield-roadmap-lifecycle.verify"])
        self.assertEqual(route["boundary"], "human-acceptance")
        self.repo.approve("human-acceptance", human=True, verification="PASS", evidence=["evidence/result.txt"])
        self.assertEqual(self.commands(solo.Repository(self.project).next()), ["speckit.converge", "speckit.greenfield-roadmap-lifecycle.complete"])
        lifecycle = self.repo.lifecycle
        args = lifecycle.parser().parse_args(["complete", "RM-01", "--converge", "clean", "--compatibility", "COMPATIBLE",
            "--feature-after-tasks", "PASS", "--feature-before-implement", "PASS", "--mvp-before-implement", "PASS",
            "--mvp-after-implement", "PASS", "--verification", "PASS", "--blockers", "none", "--evidence", "evidence/result.txt"])
        # Fixed native verification fixture, never agent dispatch or live acceptance.
        result = lifecycle.apply(self.project, args)
        self.assertEqual(result["status"], "done")
        self.assertEqual(solo.Repository(self.project).next()["result"], "FEATURE DONE")

    def test_stale_acceptance_cannot_complete_or_mutate_roadmap(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        self.write("evidence/result.txt", "Current verification.\n")
        self.repo.approve("human-acceptance", human=True, verification="PASS", evidence=["evidence/result.txt"])
        self.write("src/service.py", "Changed implementation.\n")
        self.repo.approve("post-implementation", human=True, verification="PASS")
        self.assertEqual(solo.Repository(self.project).next()["boundary"], "human-acceptance")
        before = (self.project / "ROADMAP.md").read_bytes()
        lifecycle = self.repo.lifecycle
        args = lifecycle.parser().parse_args(["complete", "RM-01", "--converge", "clean", "--compatibility", "COMPATIBLE",
            "--feature-after-tasks", "PASS", "--feature-before-implement", "PASS", "--mvp-before-implement", "PASS",
            "--mvp-after-implement", "PASS", "--verification", "PASS", "--blockers", "none", "--evidence", "evidence/result.txt"])
        with self.assertRaisesRegex(ValueError, "Stale human-acceptance"):
            lifecycle.apply(self.project, args)
        self.assertEqual(before, (self.project / "ROADMAP.md").read_bytes())

    def test_runtime_has_no_procedural_state_or_handwritten_skill(self):
        self.feature()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.repo.next()
        self.repo.readiness()
        self.assertFalse((self.project / ".specify/workflows").exists())
        self.assertEqual(list((self.project / ".specify/governance").iterdir()), [self.project / solo.REGISTRY])
        self.assertEqual(set(self.repo.load()), self.repo.facts.ROOT_FIELDS)
        self.assertEqual(list(ROOT.rglob("SKILL.md")), [])
        runtime = (ROOT / "extension/scripts/solo.py").read_text()
        for forbidden in ("WorkflowEngine", "RunState", "run_id", "current_stage", "sqlite", ".specify/workflows"):
            self.assertNotIn(forbidden, runtime)


class ArchitectureReconciliationRoutingTests(Fixture):
    def setUp(self):
        super().setUp()
        self.foundation()
        self.write("prd.md", "Explicitly approved changed product authority.\n")
        self.repo.declare_prd("prd.md", human=True)

    def test_fresh_cli_delegates_only_reconciliation_and_stops_at_architecture(self):
        before = self.snapshot()
        result = subprocess.run([sys.executable, "-B", str(ROOT / "extension/scripts/solo.py"),
                                 "--project", str(self.project), "next"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = {"commands": [{"command": "speckit.greenfield-foundation.architecture-reconcile",
                                  "inputs": {"canonical_prd": "prd.md", "authorization": "native"}}],
                    "boundary": "architecture"}
        self.assertEqual(json.loads(result.stdout), expected)
        # The owning command's proposal is response-only. No human decision or
        # artifact write is inferred; a later fresh invocation still needs HITL.
        self.assertEqual(solo.Repository(self.project).next(), expected)
        self.assertEqual(before, self.snapshot())
        command = (ROOT / "extension/commands/speckit.solo-orchestrator.route.md").read_text()
        self.assertIn("When the response names a `boundary`, stop there", command)
        self.assertIn("do not record its proposal as approval of the unchanged", command)

    def test_missing_installed_reconciliation_contract_fails_closed(self):
        path = self.project / ".specify/extensions/greenfield-foundation/commands/speckit.greenfield-foundation.architecture-reconcile.md"
        path.unlink()  # An older installed foundation does not supply this command.
        before = self.snapshot()
        result = subprocess.run([sys.executable, "-B", str(ROOT / "extension/scripts/solo.py"),
                                 "--project", str(self.project), "next"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED:", result.stderr)
        self.assertIn("architecture-reconcile.md", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(before, self.snapshot())


class FeatureHitlRoutingTests(Fixture):
    def drop(self, boundary):
        data = self.repo.load()
        data["approvals"] = [a for a in data["approvals"] if a["boundary"] != boundary]
        self.repo.save(data)

    def test_plan_ux_approval_is_required_before_tasks(self):
        self.feature()
        (self.project / "specs/001-first/tasks.md").unlink()
        self.drop("plan-ux")
        before = self.snapshot()
        for _ in range(2):
            route = solo.Repository(self.project).next()
            self.assertEqual(route, {"commands": [], "boundary": "plan-ux", "subject": "RM-01"})
        self.assertEqual(before, self.snapshot())
        self.repo.approve("plan-ux", human=True, verification="PASS")
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.tasks"])
        self.assertEqual(route["boundary"], "tasks-guard")

    def test_plan_ux_freshness_binds_design_and_native_plan_documents(self):
        self.feature()
        (self.project / "specs/001-first/tasks.md").unlink()
        for relative in ("specs/001-first/plan.md", "specs/001-first/ux-design.md", "DESIGN.md",
                         "specs/001-first/contracts/api.md", "specs/001-first/design/panel.md",
                         "specs/001-first/research.md", "specs/001-first/data-model.md",
                         "specs/001-first/quickstart.md"):
            with self.subTest(relative=relative):
                self.repo.approve("plan-ux", human=True, verification="PASS")
                self.write(relative, "Materially changed governed design.\n")
                self.assertEqual(self.repo.next()["boundary"], "plan-ux")
                self.assertNotIn("speckit.tasks", self.commands(self.repo.next()))
                self.repo.approve("plan-ux", human=True, verification="PASS")
                self.assertIn("speckit.tasks", self.commands(self.repo.next()))
        (self.project / "specs/001-first/ux-design.md").unlink()
        self.assertEqual(self.repo.next()["boundary"], "plan-ux")

    def test_tasks_guard_approval_is_required_before_analyze(self):
        self.feature()
        self.drop("tasks-guard")
        before = self.snapshot()
        for _ in range(2):
            route = solo.Repository(self.project).next()
            self.assertEqual(self.commands(route), ["speckit.feature-governance-guard.review"])
            self.assertEqual(route["boundary"], "tasks-guard")
            self.assertNotIn("speckit.analyze", self.commands(route))
        self.assertEqual(before, self.snapshot())
        self.repo.approve("tasks-guard", human=True, verification="PASS")
        self.assertIn("speckit.analyze", self.commands(self.repo.next()))
        self.write("specs/001-first/tasks.md", "- [ ] T002 Changed approved work\n")
        self.assertEqual(self.repo.next()["boundary"], "tasks-guard")

    def test_readiness_still_blocks_core_implementation_at_native_hook(self):
        self.feature()
        with self.assertRaisesRegex(ValueError, "Implementation Readiness approval required"):
            self.repo.readiness()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.repo.readiness()
        self.write("specs/001-first/tasks.md", "- [ ] T001 Changed governing scope\n")
        with self.assertRaisesRegex(ValueError, "Stale Implementation Readiness"):
            self.repo.readiness()

    def test_native_task_completion_marks_preserve_tasks_scope_approval(self):
        self.feature()
        self.write("specs/001-first/tasks.md", "- [X] T001 Implement approved contract\n")
        self.assertEqual(self.repo.next()["boundary"], "post-implementation")
        self.write("specs/001-first/tasks.md", "- [x] T001 Changed task scope\n")
        self.assertEqual(self.repo.next()["boundary"], "tasks-guard")

    def test_post_implementation_approval_is_required_before_converge(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        route = self.repo.next()
        self.assertEqual(self.commands(route), ["speckit.mvp-complexity-guard.simplify"])
        self.assertEqual(route["boundary"], "post-implementation")
        self.assertNotIn("speckit.converge", self.commands(route))
        self.repo.approve("post-implementation", human=True, verification="PASS")
        self.assertIn("speckit.converge", self.commands(self.repo.next()))
        self.write("src/service.py", "Material implementation change.\n")
        self.assertEqual(self.repo.next()["boundary"], "post-implementation")
        self.assertNotIn("speckit.converge", self.commands(self.repo.next()))

    def test_post_implementation_cannot_be_approved_with_incomplete_tasks(self):
        self.feature()
        with self.assertRaisesRegex(ValueError, "incomplete tasks"):
            self.repo.approve("post-implementation", human=True, verification="PASS")

    def test_no_human_acceptance_keeps_done_unavailable(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        self.write("evidence/result.txt", "Current verification.\n")
        self.repo.approve("post-implementation", human=True, verification="PASS")
        route = self.repo.next()
        self.assertEqual(route["boundary"], "human-acceptance")
        self.assertNotIn("speckit.greenfield-roadmap-lifecycle.complete", self.commands(route))
        before = (self.project / "ROADMAP.md").read_bytes()
        args = self.repo.lifecycle.parser().parse_args(["complete", "RM-01", "--converge", "clean",
            "--compatibility", "COMPATIBLE", "--feature-after-tasks", "PASS", "--feature-before-implement", "PASS",
            "--mvp-before-implement", "PASS", "--mvp-after-implement", "PASS", "--verification", "PASS",
            "--blockers", "none", "--evidence", "evidence/result.txt"])
        with self.assertRaisesRegex(ValueError, "human-acceptance approval"):
            self.repo.lifecycle.apply(self.project, args)
        self.assertEqual(before, (self.project / "ROADMAP.md").read_bytes())

    def test_all_feature_categories_are_recordable_via_cli_without_stage_state(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        for boundary in sorted(solo.FEATURE_APPROVALS):
            with self.subTest(boundary=boundary):
                result = subprocess.run([sys.executable, "-B", str(ROOT / "extension/scripts/solo.py"),
                    "--project", str(self.project), "approve", boundary, "--human", "--verification", "PASS"],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["boundary"], boundary)
        before = self.snapshot()
        self.repo.next()
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.project / ".specify/workflows").exists())
        self.assertEqual(set(self.repo.load()), self.repo.facts.ROOT_FIELDS)
        self.assertEqual(list((self.project / ".specify/governance").iterdir()), [self.project / solo.REGISTRY])

    def test_rejected_missing_inputs_or_wrong_subject_do_not_authorize(self):
        self.feature(tasks="- [x] T001 Implement approved contract\n")
        for boundary in ("plan-ux", "tasks-guard", "post-implementation"):
            with self.subTest(boundary=boundary):
                self.repo.approve(boundary, human=True, verification="PASS", reject=True)
                self.assertEqual(self.repo.next()["boundary"], boundary)
                self.repo.approve(boundary, human=True, verification="PASS")
                saved = self.repo.load()
                for field, value in (("subject", "RM-02"), ("inputs", ["prd.md"])):
                    data = json.loads(json.dumps(saved))
                    next(a for a in data["approvals"] if a["boundary"] == boundary)[field] = value
                    self.repo.save(data)
                    self.assertEqual(self.repo.next()["boundary"], boundary)
                self.repo.save(saved)


class ReadinessFreshnessTests(Fixture):
    def setUp(self):
        super().setUp()
        self.feature(tasks="- [ ] T001 Implement approved contract\n- [ ] T002 Verify contract\n")

    def test_implementation_outputs_do_not_invalidate_readiness(self):
        for name in ("src/service.py", "tests/test_service.py", "evidence/browser.txt", "build/output.js"):
            self.write(name, "Before implementation.\n")
        approval = self.repo.approve(solo.READINESS, human=True, verification="PASS",
                                     evidence=["evidence/browser.txt"])
        self.assertNotIn("evidence/browser.txt", approval["inputs"])
        for name in ("src/service.py", "tests/test_service.py", "evidence/browser.txt", "build/output.js"):
            with self.subTest(name=name):
                self.write(name, "Normal implementation increment.\n")
                self.assertEqual(solo.Repository(self.project).readiness()["result"],
                                 "IMPLEMENTATION READINESS: PASS")
                (self.project / name).unlink()
                solo.Repository(self.project).readiness()

    def test_governing_authority_changes_invalidate_readiness(self):
        for name in ("DESIGN.md", "specs/001-first/ux-design.md", "specs/001-first/research.md",
                     "specs/001-first/data-model.md", "specs/001-first/quickstart.md",
                     "specs/001-first/backward-exception.md", "specs/001-first/contracts/api.md",
                     "specs/001-first/design/flow.md"):
            self.write(name, "Approved authority.\n")
        for name in ("specs/001-first/spec.md", "specs/001-first/plan.md", "specs/001-first/tasks.md",
                     "DESIGN.md", "specs/001-first/ux-design.md", "specs/001-first/research.md",
                     "specs/001-first/data-model.md", "specs/001-first/quickstart.md",
                     "specs/001-first/backward-exception.md", "specs/001-first/contracts/api.md",
                     "specs/001-first/design/flow.md", "prd.md", "architecture/baseline.md",
                     "ROADMAP.md", ".specify/memory/constitution.md"):
            with self.subTest(name=name):
                original = (self.project / name).read_text()
                self.repo.approve(solo.READINESS, human=True, verification="PASS")
                self.write(name, original + "Changed governing scope.\n")
                with self.assertRaisesRegex(ValueError, "[Ss]tale"):
                    solo.Repository(self.project).readiness()
                self.write(name, original)

    def test_normal_increment_preserves_fresh_routing_and_mandatory_hook(self):
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        before = (self.project / solo.REGISTRY).read_bytes()
        self.write("src/service.py", "Implemented first task.\n")
        self.write("tests/test_service.py", "Regression coverage.\n")
        self.write("evidence/browser.txt", "Browser verification.\n")
        self.write("specs/001-first/tasks.md",
                   "- [x] T001 Implement approved contract\n- [ ] T002 Verify contract\n")
        fresh = solo.Repository(self.project)
        route = fresh.next()
        self.assertEqual(self.commands(route), ["speckit.analyze", "speckit.implement"])
        self.assertNotEqual(route.get("boundary"), solo.READINESS)
        # Routing delegates Readiness to before_implement; exercise that actual gate too.
        self.assertEqual(fresh.readiness()["result"], "IMPLEMENTATION READINESS: PASS")
        self.assertEqual(before, (self.project / solo.REGISTRY).read_bytes())
        self.write("specs/001-first/tasks.md",
                   "- [x] T001 Implement different scope\n- [ ] T002 Verify contract\n")
        with self.assertRaisesRegex(ValueError, "Stale"):
            fresh.readiness()
        self.assertEqual(fresh.next()["boundary"], "tasks-guard")

    def test_legacy_tree_fingerprint_requires_one_explicit_renewal(self):
        entry, spec = self.repo.feature()
        data = self.repo.load()
        inputs = self.repo.feature_inputs(data, spec)
        data["approvals"].append(dict(boundary=solo.READINESS, subject=entry.id,
            decision="approve", human=True, verification="PASS", inputs=inputs,
            fingerprint=self.repo.facts.fingerprint(self.project, "human-acceptance", entry.id,
                                                   data["canonical_prd"], inputs, spec)))
        self.repo.save(data)
        with self.assertRaisesRegex(ValueError, "Stale|omits"):
            self.repo.readiness()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        self.repo.readiness()


class SpecApprovalRoutingTests(Fixture):
    def setUp(self):
        super().setUp()
        self.feature()
        for name in ("plan.md", "tasks.md"):
            (self.project / "specs/001-first" / name).unlink()
        data = self.repo.load()
        data["approvals"] = [a for a in data["approvals"] if a["boundary"] != "spec"]
        self.repo.save(data)

    def assert_spec_boundary(self):
        route = solo.Repository(self.project).next()
        self.assertEqual(self.commands(route), ["speckit.clarify"])
        self.assertEqual(route["boundary"], "spec")
        self.assertEqual(route["subject"], "RM-01")
        self.assertNotIn("speckit.plan", self.commands(route))

    def test_missing_approval_delegates_clarify_then_stops_at_spec_hitl(self):
        self.assert_spec_boundary()

    def test_current_approval_makes_plan_eligible_and_reuses_shared_fingerprint(self):
        with patch.object(self.repo.facts, "fingerprint", wraps=self.repo.facts.fingerprint) as fingerprint:
            approval = self.repo.approve("spec", human=True, verification="PASS")
            self.assertIn((self.project, "prd", "foundation", "specs/001-first/spec.md",
                           ["specs/001-first/spec.md"]), [c.args for c in fingerprint.call_args_list])
        self.assertEqual((approval["boundary"], approval["subject"], approval["inputs"]),
                         ("spec", "RM-01", ["specs/001-first/spec.md"]))
        route = solo.Repository(self.project).next()
        self.assertEqual(self.commands(route), ["speckit.clarify", "speckit.plan"])
        self.assertNotIn("boundary", route)

    def test_changed_post_clarify_spec_requires_renewed_approval_before_plan(self):
        self.repo.approve("spec", human=True, verification="PASS")
        self.assertIn("speckit.plan", self.commands(self.repo.next()))
        # A Clarify edit after the returned batch must invalidate its Plan authorization.
        self.write("specs/001-first/spec.md", "ROADMAP entry: RM-01\nClarified local behavior.\n")
        entry, spec = self.repo.feature()
        with self.assertRaisesRegex(ValueError, "Stale Spec approval"):
            self.repo.require_spec_approval(self.repo.load(), entry, spec)
        self.assert_spec_boundary()
        self.repo.approve("spec", human=True, verification="PASS")
        self.assertIn("speckit.plan", self.commands(solo.Repository(self.project).next()))

    def test_noop_clarify_and_fresh_routes_create_no_completion_state(self):
        for approved in (False, True):
            if approved:
                self.repo.approve("spec", human=True, verification="PASS")
            before = self.snapshot()
            for _ in range(2):
                self.repo.next()  # A read-only Clarify leaves precisely this same content.
            self.assertEqual(before, self.snapshot())
            self.assertFalse((self.project / ".specify/workflows").exists())
            self.assertEqual(set(self.repo.load()), self.repo.facts.ROOT_FIELDS)
            self.assertEqual(list((self.project / ".specify/governance").iterdir()),
                             [self.project / solo.REGISTRY])

    def test_optional_checklist_is_not_automatically_selected_or_persisted(self):
        self.assert_spec_boundary()
        self.write("specs/001-first/checklists/optional.md", "- [ ] Explicitly applicable review\n")
        self.assert_spec_boundary()
        self.repo.approve("spec", human=True, verification="PASS")
        self.assertEqual(self.commands(self.repo.next()), ["speckit.clarify", "speckit.plan"])
        command = (ROOT / "extension/commands/speckit.solo-orchestrator.route.md").read_text()
        self.assertIn("explicitly call for it", command)
        self.assertIn("Immediately before invoking any returned Plan command", command)
        self.assertIn("again and confirm it still selects `speckit.plan` with no boundary", command)
        self.assertNotIn("checklist-skipped", [a["boundary"] for a in self.repo.load()["approvals"]])

    def test_rejected_and_wrong_feature_approvals_never_select_plan(self):
        self.repo.approve("spec", human=True, verification="PASS", reject=True)
        self.assert_spec_boundary()
        approval = self.repo.approve("spec", human=True, verification="PASS")
        data = self.repo.load()
        next(a for a in data["approvals"] if a["boundary"] == "spec")["subject"] = "RM-02"
        self.repo.save(data)
        self.assert_spec_boundary()
        self.assertEqual(approval["subject"], "RM-01")

    def test_cli_records_spec_approval(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "extension/scripts/solo.py"),
                                 "--project", str(self.project), "approve", "spec", "--human",
                                 "--verification", "PASS"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["boundary"], "spec")
        self.assertIn("speckit.plan", self.commands(solo.Repository(self.project).next()))


class ProjectReadyRoutingTests(Fixture):
    def setUp(self):
        super().setUp()
        self.foundation()
        data = self.repo.load()
        data["approvals"] = [a for a in data["approvals"] if a["boundary"] != "project-ready"]
        self.repo.save(data)

    def assert_operation(self, operation):
        before = self.snapshot()
        for _ in range(2):
            route = solo.Repository(self.project).next()
            self.assertEqual(route["boundary"], "project-ready")
            self.assertEqual(self.commands(route), ["speckit.greenfield-foundation.project-ready"])
            self.assertEqual(route["commands"][0]["inputs"]["operation"], operation)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.project / ".specify/workflows/runs").exists())
        self.assertEqual(set(self.repo.load()), self.repo.facts.ROOT_FIELDS)

    def test_missing_constitution_prepares(self):
        (self.project / ".specify/memory/constitution.md").unlink()
        self.assert_operation("prepare")

    def test_native_init_scaffold_prepares_without_state(self):
        (self.project / ".specify/memory/constitution.md").unlink()
        result = subprocess.run(
            ["specify", "init", "--here", "--force", "--integration", "codex",
             "--integration-options=--skills", "--ignore-agent-tools"],
            cwd=self.project, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.project / ".specify/memory/constitution.md").read_bytes(),
                         solo.native_constitution_scaffold())
        self.assert_operation("prepare")

    def test_authored_constitution_verifies_without_modification(self):
        self.assert_operation("verify")

    def test_partially_authored_scaffold_is_not_disposable(self):
        scaffold = solo.native_constitution_scaffold().decode()
        for content in (scaffold.replace("[PROJECT_NAME]", "Authored Project", 1),
                        scaffold + "\n## Authored invariant\nPreserve this policy.\n"):
            with self.subTest(content=content[:40]):
                self.write(".specify/memory/constitution.md", content)
                # Even an identical project override cannot redefine native identity.
                self.write(".specify/templates/constitution-template.md", content)
                self.assert_operation("verify")


class InstallationTests(Fixture):
    def install(self):
        # Only disposable projects: native managers generate commands/skills, no agents run.
        manager = ExtensionManager(self.project)
        for source in (ROOT / "extension", TOOLS / "greenfield-mvp-governance/extension",
                       TOOLS / "speckit-feature-governance/extension"):
            manager.install_from_directory(source, "0.16.2")
        PresetManager(self.project).install_from_directory(ROOT / "preset", "0.16.2", priority=5)
        return manager

    def test_installation_generation_preset_and_registry_survival(self):
        self.feature()
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        registry = (self.project / solo.REGISTRY).read_bytes()
        manager = self.install()
        # Exercise native composition with the documented prerequisite presets.
        presets = PresetManager(self.project)
        for priority, source in ((10, GREENFIELD / "preset"),
                                 (20, TOOLS / "speckit-feature-governance/preset"),
                                 (30, TOOLS / "greenfield-mvp-governance/preset")):
            presets.install_from_directory(source, "0.16.2", priority=priority)
        skills = list((self.project / ".agents/skills").rglob("SKILL.md"))
        route = next(p.read_text() for p in skills if "# Solo Orchestrator" in p.read_text())
        self.assertIn(".specify/extensions/solo-orchestrator/scripts/solo.py", route)
        self.assertTrue(any("# Solo Implementation Readiness" in p.read_text() for p in skills))
        implement = PresetResolver(self.project).resolve_content("speckit.implement", "command")
        self.assertIsInstance(implement, str)
        self.assertLess(implement.index("## Solo Implementation Hook Ordering"), implement.index("## Pre-Execution Checks"))
        self.assertIn("processing and executing all tasks", implement)
        generated = self.project / ".agents/skills/speckit-implement/SKILL.md"
        generated_content = generated.read_text()
        self.assertLess(generated_content.index("## Solo Implementation Hook Ordering"),
                        generated_content.index("## Pre-Execution Checks"))
        self.assertIn("processing and executing all tasks", generated_content)
        self.assertEqual([h["command"] for h in solo.hooks(self.project)["hooks"]], list(solo.REQUIRED_HOOKS))
        manager.install_from_directory(ROOT / "extension", "0.16.2", force=True)
        manager.remove("solo-orchestrator")
        self.assertEqual((self.project / solo.REGISTRY).read_bytes(), registry)

    def test_native_priority_order_and_readiness_blocks_missing_approval(self):
        self.feature()
        self.install()  # reverse registration order to prove native priority sorting
        result = solo.hooks(self.project)
        self.assertEqual([h["command"] for h in result["hooks"]], list(solo.REQUIRED_HOOKS))
        native = HookExecutor(self.project)
        self.assertEqual(result, native.check_hooks_for_event("before_implement"))
        for command in solo.REQUIRED_HOOKS:
            self.assertIn(command, result["message"])
        with self.assertRaisesRegex(ValueError, "approval required"):
            solo.Repository(self.project).readiness()
        cli = self.project / ".specify/extensions/solo-orchestrator/scripts/solo.py"
        denied = subprocess.run([sys.executable, "-B", str(cli), "readiness"], cwd=self.project, capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("approval required", denied.stderr)
        self.repo.approve(solo.READINESS, human=True, verification="PASS")
        allowed = subprocess.run([sys.executable, "-B", str(cli), "readiness"], cwd=self.project, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(json.loads(allowed.stdout)["result"], "IMPLEMENTATION READINESS: PASS")
        # A disabled hook or invalid native ordering must fail closed.
        config = self.project / ".specify/extensions.yml"
        original = yaml.safe_load(config.read_text())
        altered = json.loads(json.dumps(original))
        altered["hooks"]["before_implement"][0]["enabled"] = False
        config.write_text(yaml.safe_dump(altered))
        with self.assertRaisesRegex(ValueError, "hook missing"):
            solo.hooks(self.project)
        original["hooks"]["before_implement"][0]["priority"] = 1
        config.write_text(yaml.safe_dump(original))
        with self.assertRaisesRegex(ValueError, "hook order"):
            solo.hooks(self.project)

    def test_missing_or_overridden_prepend_blocks_native_implementation(self):
        self.install()
        prepend = self.project / ".specify/presets/solo-orchestrator/commands/speckit.implement.md"
        content = prepend.read_text()
        prepend.unlink()
        with self.assertRaisesRegex(ValueError, "prepend preset"):
            solo.hooks(self.project)
        prepend.write_text(content)
        self.write(".specify/templates/overrides/speckit.implement.md", "# Project replacement\n")
        with self.assertRaisesRegex(ValueError, "prepend preset"):
            solo.hooks(self.project)

    def test_native_append_and_unprovable_composition_are_rejected(self):
        self.install()
        manifest = self.project / ".specify/presets/solo-orchestrator/preset.yml"
        original = yaml.safe_load(manifest.read_text())
        for strategy in ("append", "replace", "wrap"):
            with self.subTest(strategy=strategy):
                changed = json.loads(json.dumps(original))
                changed["provides"]["templates"][0]["strategy"] = strategy
                manifest.write_text(yaml.safe_dump(changed))
                if strategy == "append":
                    effective = PresetResolver(self.project).resolve_content("speckit.implement", "command")
                    self.assertLess(effective.index("## Pre-Execution Checks"),
                                    effective.index("## Solo Implementation Hook Ordering"))
                with self.assertRaisesRegex(ValueError, "prepend preset"):
                    solo.hooks(self.project)

    def test_displaced_solo_content_after_core_is_rejected(self):
        self.install()
        resolver = PresetResolver(self.project)
        layers = resolver.collect_all_layers("speckit.implement", "command")
        core = next(layer["path"].read_text() for layer in layers if layer["source"] in {"core", "core (bundled)"})
        prepend = (self.project / ".specify/presets/solo-orchestrator/commands/speckit.implement.md").read_text()
        # Even plausible source metadata cannot authorize displaced resolved content.
        with patch.object(PresetResolver, "resolve_content", return_value=core + "\n\n" + prepend):
            with self.assertRaisesRegex(ValueError, "precedes Core"):
                solo.hooks(self.project)
        with patch.object(PresetResolver, "collect_all_layers", return_value=[]):
            with self.assertRaisesRegex(ValueError, "prepend preset"):
                solo.hooks(self.project)

    def test_isolated_native_launcher_can_supply_hook_runtime(self):
        self.install()
        cli = self.project / ".specify/extensions/solo-orchestrator/scripts/solo.py"
        system_python = shutil.which("python3")
        result = subprocess.run([system_python, "-B", str(cli), "hooks"], cwd=self.project,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([h["command"] for h in json.loads(result.stdout)["hooks"]], list(solo.REQUIRED_HOOKS))
