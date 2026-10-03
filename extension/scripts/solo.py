"""Repository-derived routing and current human declarations; no agent dispatcher."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REGISTRY = ".specify/governance/hitl.json"
READINESS = "implementation-readiness"
FOUNDATION_APPROVALS = {"architecture", "project-ready"}
FEATURE_APPROVALS = {"spec", "plan-ux", "tasks-guard", READINESS,
                     "post-implementation", "human-acceptance"}
REQUIRED_HOOKS = (
    "speckit.feature-governance-guard.review",
    "speckit.mvp-complexity-guard.preflight",
    "speckit.solo-orchestrator.readiness",
)


def installed(project: Path, extension: str, script: str):
    path = project / ".specify/extensions" / extension / "scripts" / script
    if not path.is_file() or not path.resolve().is_relative_to(project.resolve()):
        raise ValueError(f"Missing installed interface: {extension}/{script}")
    name = "solo_dependency_" + extension.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses in the installed lifecycle module
    spec.loader.exec_module(module)
    return module


def native_constitution_scaffold():
    """Read Core's init scaffold, never a project override or composed preset."""
    try:
        from specify_cli._assets import _locate_core_pack, _repo_root
    except ModuleNotFoundError as exc:
        if exc.name != "specify_cli":
            raise
        # Match the isolated native console launcher supported by hooks().
        launcher = shutil.which("specify")
        first = Path(launcher).read_text().splitlines()[0] if launcher else ""
        interpreter = Path(first[2:]) if first.startswith("#!/") else None
        if not interpreter or not interpreter.is_file() or interpreter.absolute() == Path(sys.executable).absolute():
            raise ValueError("Use the Python interpreter exposing installed SpecKit for Constitution scaffold identity") from exc
        script = (
            "import sys; from specify_cli._assets import _locate_core_pack, _repo_root; "
            "sys.stdout.buffer.write(((_locate_core_pack() or _repo_root()) / "
            "'templates/constitution-template.md').read_bytes())"
        )
        result = subprocess.run([str(interpreter), "-B", "-c", script], capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr.decode().strip())
        return result.stdout
    return ((_locate_core_pack() or _repo_root()) / "templates/constitution-template.md").read_bytes()


class Repository:
    def __init__(self, project: Path):
        self.project = project.resolve()
        self.facts = installed(self.project, "greenfield-foundation", "governance_facts.py")
        self.lifecycle = installed(self.project, "greenfield-roadmap-lifecycle", "roadmap_lifecycle.py")

    def load(self):
        return self.validate(self.facts.load_facts(self.project, REGISTRY))

    def validate(self, data):
        self.facts.validate_facts(data)
        for approval in data["approvals"]:
            boundary, subject = approval["boundary"], approval["subject"]
            if boundary not in FOUNDATION_APPROVALS | FEATURE_APPROVALS | {"prd"}:
                raise ValueError("Unsupported Solo approval boundary: " + boundary)
            if (subject == "foundation") != (boundary not in FEATURE_APPROVALS):
                raise ValueError("Invalid Solo approval subject/category: " + boundary)
            if approval["human"] is not True:
                raise ValueError("Solo facts require an explicit human declaration")
            expected = "PROJECT READY" if boundary == "project-ready" else "PASS"
            if approval["verification"] != expected:
                raise ValueError("Invalid Solo approval verification/category: " + boundary)
            if boundary == "prd" and (approval["decision"] != "approve" or approval["verification"] != "PASS"):
                raise ValueError("Canonical PRD is an already-approved input fact")
        return data

    def save(self, data):
        self.validate(data)
        destination = self.project / REGISTRY
        if not destination.resolve().is_relative_to(self.project):
            raise ValueError("Approval registry escapes the project")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".hitl-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def require(self, data, boundary, **kwargs):
        return self.facts.require_approval(self.project, data, boundary, **kwargs)

    def roadmap(self):
        path = self.facts.project_file(self.project, "ROADMAP.md")
        return self.lifecycle.Roadmap(path.read_text(encoding="utf-8"))

    def feature(self):
        """Use Core's existing context, then cross-check the installed ROADMAP parser."""
        candidates = (
            [sys.executable, "-B", ".specify/scripts/python/check_prerequisites.py"],
            ["bash", ".specify/scripts/bash/check-prerequisites.sh"],
        )
        command = next((c for c in candidates if (self.project / c[-1]).is_file()), None)
        if command is None:
            raise ValueError("Missing native Feature context interface")
        result = subprocess.run(command + ["--json", "--paths-only"], cwd=self.project,
                                capture_output=True, text=True)
        if result.returncode:
            raise ValueError("Native Feature context unavailable: " + result.stderr.strip())
        folder = Path(json.loads(result.stdout)["FEATURE_DIR"])
        if not folder.is_absolute():
            raise ValueError("Native Feature context must return an absolute directory")
        spec = (folder / "spec.md").resolve().relative_to(self.project).as_posix()
        self.facts.project_file(self.project, spec)
        roadmap = self.roadmap()
        matching = [e for e in roadmap.entries.values() if e.fields["Feature spec"] == spec]
        active = [e for e in roadmap.entries.values() if e.fields["Status"] == "active"]
        if (len(matching) != 1 or len(active) > 1 or
                (active and active[0].id != matching[0].id)):
            raise ValueError("Ambiguous or conflicting current Feature context")
        entry = matching[0]
        if self.lifecycle.SPEC_ID.findall((self.project / spec).read_text()) != [entry.id]:
            raise ValueError("Current spec does not identify its linked ROADMAP entry")
        if entry.fields["Status"] not in {"active", "done"}:
            raise ValueError("Current Feature is neither active nor done")
        return entry, spec

    def human_mode(self):
        config = self.lifecycle.lifecycle_config(self.project)
        if config != {"completion_mode": "human", "approval_registry": REGISTRY}:
            raise ValueError("Solo Feature routing requires existing Greenfield human completion mode and the shared registry")

    def feature_inputs(self, data, spec, evidence=()):
        inputs = self.facts.required_inputs("human-acceptance", data["canonical_prd"], spec)
        inputs.update(evidence)
        return sorted(inputs)

    def spec_fingerprint(self, spec):
        # Reuse the shared single-document fingerprint mode; this does not grant
        # PRD authority to the Spec. Current foundation authorization is separate.
        return self.facts.fingerprint(self.project, "prd", "foundation", spec, [spec])

    def require_spec_approval(self, data, entry, spec):
        self.require(data, "project-ready")
        found = [a for a in data["approvals"] if a["boundary"] == "spec" and a["subject"] == entry.id]
        if (not found or found[0]["human"] is not True or
                found[0]["decision"] != "approve" or found[0]["verification"] != "PASS"):
            raise self.facts.FactError("Current human Spec approval required")
        approval = found[0]
        if approval["inputs"] != [spec] or approval["fingerprint"] != self.spec_fingerprint(spec):
            raise self.facts.FactError("Stale Spec approval")
        return approval

    def plan_ux_inputs(self, data, spec):
        folder = Path(spec).parent
        inputs = self.facts.required_inputs("project-ready", data["canonical_prd"])
        inputs.update({spec, (folder / "plan.md").as_posix()})
        for relative in ("DESIGN.md", folder / "ux-design.md", folder / "research.md",
                         folder / "data-model.md", folder / "quickstart.md", folder / "backward-exception.md"):
            if (self.project / relative).is_file():
                inputs.add(Path(relative).as_posix())
        for name in ("contracts", "design"):
            for path in (self.project / folder / name).rglob("*"):
                if path.is_file():
                    inputs.add(path.relative_to(self.project).as_posix())
        return sorted(inputs)

    def review_inputs(self, data, boundary, spec):
        inputs = self.plan_ux_inputs(data, spec)
        if boundary in {"tasks-guard", READINESS}:
            inputs = sorted(inputs + [(Path(spec).parent / "tasks.md").as_posix()])
        return inputs

    def review_fingerprint(self, boundary, subject, inputs, spec):
        # Aggregate the installed helper's document fingerprints in the existing
        # approval field; no review result or procedural progress is stored.
        values = {p: self.spec_fingerprint(p) for p in inputs}
        if boundary in {"tasks-guard", READINESS}:
            relative = (Path(spec).parent / "tasks.md").as_posix()
            content = self.facts.authority_bytes(relative, self.facts.project_file(self.project, relative)).decode()
            # Native completion marks are progress, not changes to approved task scope.
            content = self.lifecycle.TASK.sub(
                lambda m: m.group(0)[:m.start(1) - m.start()] + " " + m.group(0)[m.end(1) - m.start():], content)
            values[relative] = hashlib.sha256(content.encode()).hexdigest()
        body = dict(boundary=boundary, subject=subject, inputs=values)
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def require_review_approval(self, data, boundary, entry, spec):
        self.require(data, "project-ready")
        found = [a for a in data["approvals"] if a["boundary"] == boundary and a["subject"] == entry.id]
        if (not found or found[0]["human"] is not True or
                found[0]["decision"] != "approve" or found[0]["verification"] != "PASS"):
            raise self.facts.FactError(f"Current human {boundary} approval required")
        approval = found[0]
        inputs = self.review_inputs(data, boundary, spec)
        if (approval["inputs"] != inputs or
                approval["fingerprint"] != self.review_fingerprint(boundary, entry.id, inputs, spec)):
            raise self.facts.FactError(f"Stale {boundary} approval")
        return approval

    def require_post_implementation(self, data, entry, spec):
        self.require(data, "project-ready")
        found = [a for a in data["approvals"] if a["boundary"] == "post-implementation" and a["subject"] == entry.id]
        if (not found or found[0]["human"] is not True or
                found[0]["decision"] != "approve" or found[0]["verification"] != "PASS"):
            raise self.facts.FactError("Current human post-implementation approval required")
        approval = found[0]
        if not set(self.feature_inputs(data, spec)).issubset(approval["inputs"]):
            raise self.facts.FactError("Post-Implementation approval omits current Feature authorities")
        current = self.facts.fingerprint(self.project, "human-acceptance", entry.id,
                                        data["canonical_prd"], approval["inputs"], spec)
        if current != approval["fingerprint"]:
            raise self.facts.FactError("Stale post-implementation approval")
        return approval

    def readiness(self):
        self.human_mode()
        data = self.load()
        self.require(data, "project-ready")
        entry, spec = self.feature()
        if entry.fields["Status"] != "active":
            raise ValueError("Implementation Readiness requires the current active Feature")
        found = [a for a in data["approvals"] if a["boundary"] == READINESS and a["subject"] == entry.id]
        if not found or not found[0]["human"] or found[0]["decision"] != "approve" or found[0]["verification"] != "PASS":
            raise ValueError("Current human Implementation Readiness approval required")
        approval = found[0]
        inputs = self.review_inputs(data, READINESS, spec)
        if approval["inputs"] != inputs:
            raise ValueError("Stale Implementation Readiness approval: authority input set changed")
        # Approval authorizes task scope; implementation outputs are not authorities.
        current = self.review_fingerprint(READINESS, entry.id, inputs, spec)
        if current != approval["fingerprint"]:
            raise ValueError("Stale Implementation Readiness approval")
        return {"result": "IMPLEMENTATION READINESS: PASS"}

    def approve(self, boundary, *, human, verification, reject=False, evidence=()):
        if human is not True:
            raise ValueError("An explicit human declaration is required")
        data = self.load()
        subject, spec = "foundation", None
        if boundary in FEATURE_APPROVALS:
            self.human_mode()
            self.require(data, "project-ready")
            entry, spec = self.feature()
            if entry.fields["Status"] != "active":
                raise ValueError("Feature approval requires the current active Feature")
            subject = entry.id
            if boundary == "spec":
                inputs = [spec]
            elif boundary in {"plan-ux", "tasks-guard", READINESS}:
                inputs = self.review_inputs(data, boundary, spec)
            else:
                if boundary == "post-implementation":
                    self.lifecycle.require_clean_tasks(self.project, spec)
                inputs = self.feature_inputs(data, spec, evidence)
        else:
            if boundary not in {"architecture", "project-ready"}:
                raise ValueError("Use declare-prd for an already approved input")
            self.require(data, "prd")
            if boundary == "project-ready":
                self.require(data, "architecture")
            inputs = sorted(self.facts.required_inputs(boundary, data["canonical_prd"]))
        expected = "PROJECT READY" if boundary == "project-ready" else "PASS"
        if verification != expected:
            raise ValueError(f"Approval requires current {expected} verification")
        fingerprint_boundary = "human-acceptance" if boundary == "post-implementation" else boundary
        if boundary == "spec":
            fingerprint = self.spec_fingerprint(spec)
        elif boundary in {"plan-ux", "tasks-guard", READINESS}:
            fingerprint = self.review_fingerprint(boundary, subject, inputs, spec)
        else:
            fingerprint = self.facts.fingerprint(self.project, fingerprint_boundary, subject,
                                                 data["canonical_prd"], inputs, spec)
        approval = dict(boundary=boundary, subject=subject, decision="reject" if reject else "approve",
                        human=True, verification=verification, inputs=inputs,
                        fingerprint=fingerprint)
        data["approvals"] = [a for a in data["approvals"] if (a["boundary"], a["subject"]) != (boundary, subject)] + [approval]
        if not reject and boundary != READINESS:
            if boundary == "spec":
                self.require_spec_approval(data, entry, spec)
            elif boundary in {"plan-ux", "tasks-guard"}:
                self.require_review_approval(data, boundary, entry, spec)
            elif boundary == "post-implementation":
                self.require_post_implementation(data, entry, spec)
            else:
                self.require(data, boundary, subject=subject, spec=spec, evidence=list(evidence))
        self.save(data)
        return approval

    def declare_prd(self, canonical_prd, *, human):
        if human is not True:
            raise ValueError("An explicit already-approved PRD input declaration is required")
        path = self.facts.project_file(self.project, canonical_prd)
        if (self.project / REGISTRY).exists():
            data = self.load()
            if data["canonical_prd"] != canonical_prd or data["product_gaps"]:
                raise ValueError("Preserve Canonical PRD identity and resolve PRODUCT GAP through the installed interface")
        else:
            data = dict(schema_version=1, canonical_prd=canonical_prd, product_gaps=[], approvals=[])
        data["prd_revision"] = hashlib.sha256(path.read_bytes()).hexdigest()
        approval = dict(boundary="prd", subject="foundation", decision="approve", human=True,
                        verification="PASS", inputs=[canonical_prd],
                        fingerprint=self.facts.fingerprint(self.project, "prd", "foundation", canonical_prd, [canonical_prd]))
        data["approvals"] = [a for a in data["approvals"] if a["boundary"] != "prd"] + [approval]
        self.require(data, "prd")
        self.save(data)
        return approval

    def next(self):
        if not (self.project / REGISTRY).exists():
            return {"result": "APPROVED PRD INPUT REQUIRED", "commands": []}
        data = self.load()
        self.require(data, "prd")  # stale PRD or PRODUCT GAP escalates; never auto-approve
        common = dict(canonical_prd=data["canonical_prd"], authorization="native")
        try:
            self.require(data, "architecture")
        except self.facts.FactError:
            if (self.project / "ROADMAP.md").exists():
                command = "speckit.greenfield-foundation.architecture-reconcile"
                self.facts.project_file(self.project,
                    f".specify/extensions/greenfield-foundation/commands/{command}.md")
                return dict(commands=[dict(command=command, inputs=common)], boundary="architecture")
            return dict(commands=[dict(command="speckit.greenfield-foundation.architecture", inputs=common)], boundary="architecture")
        if not (self.project / "ROADMAP.md").exists():
            return dict(commands=[dict(command="speckit.greenfield-foundation.roadmap", inputs=common)])
        constitution = self.project / ".specify/memory/constitution.md"
        if not constitution.exists() or constitution.read_bytes() == native_constitution_scaffold():
            return dict(commands=[dict(command="speckit.greenfield-foundation.project-ready", inputs=dict(common, operation="prepare"))], boundary="project-ready")
        try:
            self.require(data, "project-ready")
        except self.facts.FactError:
            return dict(commands=[dict(command="speckit.greenfield-foundation.project-ready", inputs=dict(common, operation="verify"))], boundary="project-ready")
        roadmap = self.roadmap()
        active = [e for e in roadmap.entries.values() if e.fields["Status"] == "active"]
        if len(active) > 1:
            raise ValueError("Ambiguous current Feature context: multiple active entries")
        if not active:
            # Existing native context controls completed Feature reporting; no new selector.
            if (self.project / ".specify/feature.json").exists() or os.environ.get("SPECIFY_FEATURE_DIRECTORY"):
                entry, _ = self.feature()
                if entry.fields["Status"] == "done":
                    return {"result": "FEATURE DONE", "subject": entry.id, "commands": []}
            ready = [e for e in roadmap.entries.values() if e.fields["Status"] == "ready"]
            if not ready and any(e.fields["Status"] == "planned" for e in roadmap.entries.values()):
                return dict(commands=[dict(interface="greenfield-roadmap-lifecycle", argv=["initial", "--registry", REGISTRY])], result="PROJECT READY")
            if len(ready) != 1:
                raise ValueError("No unambiguous ready Feature; use existing native context")
            self.human_mode()
            return dict(commands=[dict(command="speckit.specify", inputs={"roadmap_entry": ready[0].id})])
        self.human_mode()
        entry, spec = self.feature()
        folder = (self.project / spec).parent
        if not (folder / "plan.md").exists():
            try:
                self.require_spec_approval(data, entry, spec)
            except self.facts.FactError:
                return dict(commands=[dict(command="speckit.clarify")], boundary="spec", subject=entry.id)
            return dict(commands=[dict(command="speckit.clarify"), dict(command="speckit.plan")])
        try:
            self.require_review_approval(data, "plan-ux", entry, spec)
        except self.facts.FactError:
            return dict(commands=[], boundary="plan-ux", subject=entry.id)
        if not (folder / "tasks.md").exists():
            return dict(commands=[dict(command="speckit.tasks")], boundary="tasks-guard", subject=entry.id)
        try:
            self.require_review_approval(data, "tasks-guard", entry, spec)
        except self.facts.FactError:
            return dict(commands=[dict(command="speckit.feature-governance-guard.review")],
                        boundary="tasks-guard", subject=entry.id)
        try:
            self.lifecycle.require_clean_tasks(self.project, spec)
        except self.lifecycle.LifecycleError as exc:
            if str(exc) != "tasks.md has incomplete tasks":
                raise
            return dict(commands=[dict(command="speckit.analyze"), dict(command="speckit.implement")],
                        boundary="post-implementation", subject=entry.id)
        try:
            self.require_post_implementation(data, entry, spec)
        except self.facts.FactError:
            return dict(commands=[dict(command="speckit.mvp-complexity-guard.simplify")],
                        boundary="post-implementation", subject=entry.id)
        try:
            self.require(data, "human-acceptance", subject=entry.id, spec=spec)
        except self.facts.FactError:
            return dict(commands=[dict(command="speckit.converge"), dict(command="speckit.greenfield-roadmap-lifecycle.verify")], boundary="human-acceptance")
        return dict(commands=[dict(command="speckit.converge"), dict(command="speckit.greenfield-roadmap-lifecycle.complete", inputs={"operation": "complete"})], result="FEATURE DONE")


def hooks(project):
    try:
        from specify_cli.agents import CommandRegistrar
        from specify_cli.extensions import HookExecutor
        from specify_cli.presets import PresetResolver
    except ModuleNotFoundError as exc:
        if exc.name != "specify_cli":
            raise
        # uv/pipx console scripts expose the already-installed native interpreter.
        launcher = shutil.which("specify")
        first = Path(launcher).read_text().splitlines()[0] if launcher else ""
        interpreter = Path(first[2:]) if first.startswith("#!/") else None
        if not interpreter or not interpreter.is_file() or interpreter.absolute() == Path(sys.executable).absolute():
            raise ValueError("Use the Python interpreter exposing installed SpecKit for native hooks") from exc
        result = subprocess.run([str(interpreter), "-B", str(Path(__file__).resolve()),
                                 "--project", str(project.resolve()), "hooks"], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(result.stderr.strip())
        return json.loads(result.stdout)
    prepend = project / ".specify/presets/solo-orchestrator/commands/speckit.implement.md"
    resolver = PresetResolver(project)
    layers = resolver.collect_all_layers("speckit.implement", "command")
    base = next((i for i, layer in enumerate(layers) if layer["strategy"] == "replace"), None)
    solo_layers = [i for i, layer in enumerate(layers) if layer["path"].resolve() == prepend.resolve()]
    if (not prepend.is_file() or len(solo_layers) != 1 or base is None or
            solo_layers[0] >= base or layers[solo_layers[0]]["strategy"] != "prepend" or
            layers[base]["source"] not in {"core", "core (bundled)"} or
            any(layer["strategy"] not in {"prepend", "append"} for layer in layers[:base])):
        raise ValueError("The native Solo Implement prepend preset must be installed and effective")
    effective = resolver.resolve_content("speckit.implement", "command")
    solo_body = CommandRegistrar.parse_frontmatter(prepend.read_text())[1].strip()
    core_body = CommandRegistrar.parse_frontmatter(layers[base]["path"].read_text())[1].strip()
    if (not effective or not solo_body or not core_body or
            effective.count(solo_body) != 1 or effective.count(core_body) != 1 or
            effective.index(solo_body) + len(solo_body) > effective.index(core_body)):
        raise ValueError("Cannot prove Solo prepend precedes Core implementation")
    executor = HookExecutor(project)
    result = executor.check_hooks_for_event("before_implement")
    commands = [h["command"] for h in result["hooks"]]
    positions = []
    for command in REQUIRED_HOOKS:
        matching = [h for h in result["hooks"] if h.get("command") == command]
        if len(matching) != 1 or matching[0].get("optional", True) or matching[0].get("condition"):
            raise ValueError("Required unconditional mandatory native hook missing: " + command)
        positions.append(commands.index(command))
    if positions != sorted(positions):
        raise ValueError("Native hook order must be Guard → Preflight → HITL")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("next", "readiness", "hooks"):
        actions.add_parser(action)
    declaration = actions.add_parser("declare-prd")
    declaration.add_argument("canonical_prd")
    declaration.add_argument("--human", action="store_true")
    approval = actions.add_parser("approve")
    approval.add_argument("boundary", choices=sorted(FOUNDATION_APPROVALS | FEATURE_APPROVALS))
    approval.add_argument("--human", action="store_true")
    approval.add_argument("--reject", action="store_true")
    approval.add_argument("--verification", required=True)
    approval.add_argument("--evidence", action="append", default=[])
    storage = actions.add_parser("store-facts")
    storage.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "hooks":
            result = hooks(args.project)
        else:
            repo = Repository(args.project)
            if args.action in {"next", "readiness"}:
                result = getattr(repo, args.action)()
            elif args.action == "declare-prd":
                result = repo.declare_prd(args.canonical_prd, human=args.human)
            elif args.action == "approve":
                result = repo.approve(args.boundary, human=args.human, verification=args.verification,
                                      reject=args.reject, evidence=args.evidence)
            else:
                result = json.loads(args.path.read_text())
                repo.save(result)
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
