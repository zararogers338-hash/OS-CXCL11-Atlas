"""Portable, standard-library research governance.

Append-only logical history is atomically rewritten under an exclusive local lock.
Hashes detect artifact changes, not malicious re-signing or actor impersonation.
An approval records independent review and artifact identity, not scientific truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tempfile
import unicodedata
import uuid

SCHEMA_VERSION = 1
LEDGER_PATH = "docs/private/governance/events.jsonl"
CONFIG_PATH = "config/config.yaml"
POLICY_PATH = Path(__file__).resolve().parents[1] / "assets" / "governance-policy.json"
GATE_IDS = [f"gate{i}" for i in range(7)]
ROLES = {"research-steward", "bioinfo-analyst", "figure-artist", "manuscript-writer",
         "reviewer-2", "reproducibility-auditor"}
ZERO_HASH = "0" * 64
MAX_LEDGER_BYTES = 32 * 1024 * 1024


class GovernanceError(ValueError):
    """Invalid evidence, authorization declaration, state, or ledger."""


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value):
    try:
        return hashlib.sha256(_canonical(value)).hexdigest()
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise GovernanceError(f"Value cannot be canonically hashed: {exc}") from exc


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GovernanceError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(text):
    def invalid_constant(value):
        raise GovernanceError(f"Non-finite JSON number: {value}")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise GovernanceError(f"Non-finite JSON number: {value}")
        return number
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=invalid_constant,
                          parse_float=finite_float)
    except (ValueError, TypeError, RecursionError) as exc:
        raise GovernanceError(f"Malformed JSON: {exc}") from exc


def _keys(obj, expected, context):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        raise GovernanceError(f"Invalid {context} fields")


def _text(value, context, max_length=4096):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise GovernanceError(f"{context} must be nonempty text (max {max_length})")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise GovernanceError(f"Control characters in {context}")
    return value.strip()


def _actor(value):
    return unicodedata.normalize("NFKC", _text(value, "actor", 128)).strip().casefold()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_policy(policy):
    _keys(policy, {"schema_version", "id", "identity_model", "revocation_roles", "gates"}, "policy")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != SCHEMA_VERSION:
        raise GovernanceError("Unsupported policy schema")
    _text(policy["id"], "policy id", 128)
    if policy["identity_model"] != "locally-declared-not-authenticated":
        raise GovernanceError("Unsupported identity model")
    if not isinstance(policy["gates"], list) or len(policy["gates"]) != 7:
        raise GovernanceError("Policy must contain seven ordered gates")
    def check_roles(roles):
        if (not isinstance(roles, list) or not roles or any(not isinstance(r, str) for r in roles)
                or len(roles) != len(set(roles)) or not set(roles) <= ROLES):
            raise GovernanceError("Invalid policy roles")
    check_roles(policy["revocation_roles"])
    seen = set()
    for gate, expected in zip(policy["gates"], GATE_IDS):
        _keys(gate, {"id", "label", "depends_on", "proposer_roles", "reviewer_roles", "required_evidence"}, "gate")
        if gate["id"] != expected:
            raise GovernanceError("Policy gate IDs must be gate0 through gate6, in order")
        _text(gate["label"], "gate label", 128)
        deps = gate["depends_on"]
        if (not isinstance(deps, list) or any(not isinstance(d, str) for d in deps)
                or len(deps) != len(set(deps)) or not set(deps) <= seen):
            raise GovernanceError("Dependencies must form an ordered acyclic graph")
        if gate["id"] != "gate0" and not deps:
            raise GovernanceError("Only gate0 may have no prerequisites")
        check_roles(gate["proposer_roles"])
        check_roles(gate["reviewer_roles"])
        if gate["id"] in {"gate4", "gate6"} and gate["reviewer_roles"] != ["reviewer-2"]:
            raise GovernanceError("Gate4 and Gate6 require reviewer-2")
        required = gate["required_evidence"]
        if not isinstance(required, dict) or not required:
            raise GovernanceError("Every gate needs typed evidence requirements")
        for kind, count in required.items():
            if (not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind) or type(count) is not int
                    or not 1 <= count <= 100):
                raise GovernanceError("Invalid evidence requirement")
        seen.add(gate["id"])
    return policy


def load_policy():
    try:
        return _validate_policy(_json(POLICY_PATH.read_text(encoding="utf-8-sig")))
    except OSError as exc:
        raise GovernanceError(f"Cannot read governance policy: {exc}") from exc


def project_root(root=None):
    if root is not None:
        path = Path(root).resolve()
        if not path.is_dir():
            raise GovernanceError(f"Project root is not a directory: {path}")
        return path
    for path in (Path.cwd(), *Path.cwd().parents):
        if (path / CONFIG_PATH).is_file() and (path / "workflow").is_dir():
            return path.resolve()
    raise GovernanceError("Run in a project directory or provide --root")


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise GovernanceError(f"Use a safe root-relative path with forward slashes: {value!r}")
    if any(ord(ch) < 32 for ch in value):
        raise GovernanceError("Control characters in evidence path")
    return value


def _safe_path(root, relative):
    relative = _relative(relative)
    candidate = root / relative
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise GovernanceError(f"Path escapes project root: {relative}") from exc
    cursor = root
    for part in Path(relative).parts:
        cursor /= part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise GovernanceError(f"Linked paths are not evidence/storage: {relative}")
    if resolved != candidate:
        raise GovernanceError(f"Redirected path is not allowed: {relative}")
    return candidate


def _file_record(root, relative):
    path = _safe_path(root, relative)
    try:
        if not path.is_file() or path.stat().st_size == 0:
            raise GovernanceError(f"Evidence/config must be a nonempty regular file: {relative}")
        initial = path.stat()
        hasher = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
                size += len(chunk)
        final = path.stat()
        if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (final.st_size, final.st_mtime_ns, final.st_ino) or size != final.st_size:
            raise GovernanceError(f"File changed while being hashed: {relative}")
        return {"path": relative, "sha256": hasher.hexdigest(), "size": size}
    except OSError as exc:
        raise GovernanceError(f"Cannot read evidence/config {relative}: {exc}") from exc


def _validate_file_record(record):
    _keys(record, {"path", "sha256", "size"}, "file record")
    _relative(record["path"])
    if not _hash(record["sha256"]) or type(record["size"]) is not int or record["size"] < 1:
        raise GovernanceError("Invalid file fingerprint")


def _evidence_path(relative):
    _relative(relative)
    if relative in {CONFIG_PATH, LEDGER_PATH} or relative.startswith("docs/private/governance/"):
        raise GovernanceError("Configuration and governance storage cannot substitute for evidence")
    return relative


def _evidence_records(root, evidence, gate):
    records = []
    for item in evidence:
        if isinstance(item, str) and "=" in item:
            kind, relative = item.split("=", 1)
        elif isinstance(item, dict) and set(item) == {"kind", "path"}:
            kind, relative = item["kind"], item["path"]
        else:
            raise GovernanceError("Evidence must be KIND=relative/path or {kind, path}")
        records.append({"kind": kind, **_file_record(root, _evidence_path(relative))})
    _validate_evidence(records, gate)
    return sorted(records, key=lambda item: (item["kind"], item["path"]))


def _validate_evidence(records, gate):
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        raise GovernanceError("A proposal requires 1 to 1000 evidence files")
    paths = set()
    counts = Counter()
    for item in records:
        _keys(item, {"kind", "path", "sha256", "size"}, "evidence record")
        _validate_file_record({key: item[key] for key in ("path", "sha256", "size")})
        _evidence_path(item["path"])
        if not isinstance(item["kind"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item["kind"]):
            raise GovernanceError("Invalid evidence kind")
        key = item["path"].casefold() if os.name == "nt" else item["path"]
        if key in paths:
            raise GovernanceError("One file cannot fill multiple evidence slots")
        paths.add(key)
        counts[item["kind"]] += 1
    missing = [f"{kind}>={count}" for kind, count in gate["required_evidence"].items() if counts[kind] < count]
    if missing:
        raise GovernanceError("Missing evidence kinds: " + ", ".join(missing))


def _gate(policy, gate_id):
    if gate_id not in GATE_IDS:
        raise GovernanceError(f"Unknown gate: {gate_id}")
    return policy["gates"][GATE_IDS.index(gate_id)]


def _read_ledger(root):
    path = _safe_path(root, LEDGER_PATH)
    if not path.exists():
        return [], b""
    try:
        if path.stat().st_size > MAX_LEDGER_BYTES:
            raise GovernanceError("Ledger exceeds safety size limit")
        raw = path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise GovernanceError("Ledger has an incomplete trailing record")
        if not raw:
            raise GovernanceError("An existing empty ledger is invalid; preserve it for investigation")
        records = [_json(line.decode("utf-8")) for line in raw.splitlines()]
    except (OSError, UnicodeError) as exc:
        raise GovernanceError(f"Cannot read ledger: {exc}") from exc
    _replay(records)
    return records, raw


def _replay(records):
    """Validate schemas, chain, authorization declarations and state transitions."""
    states, proposals = {}, {}
    previous = ZERO_HASH
    for sequence, event in enumerate(records, 1):
        _keys(event, {"schema_version", "sequence", "previous_hash", "event_hash", "at", "action", "actor", "role", "rationale", "payload"}, "ledger event")
        if (type(event["schema_version"]) is not int or event["schema_version"] != SCHEMA_VERSION
                or type(event["sequence"]) is not int or event["sequence"] != sequence
                or event["previous_hash"] != previous):
            raise GovernanceError(f"Ledger chain/sequence failure at record {sequence}")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if event["event_hash"] != _digest(unsigned):
            raise GovernanceError(f"Ledger hash failure at record {sequence}")
        try:
            timestamp = datetime.fromisoformat(event["at"])
            if timestamp.tzinfo is None:
                raise ValueError("missing timezone")
        except (TypeError, ValueError) as exc:
            raise GovernanceError("Invalid event timestamp") from exc
        _actor(event["actor"])
        _text(event["rationale"], "rationale")
        if not isinstance(event["role"], str) or event["role"] not in ROLES:
            raise GovernanceError("Unknown event role")
        payload, action = event["payload"], event["action"]
        if action == "propose":
            _keys(payload, {"proposal_id", "gate", "policy", "policy_sha256", "config", "dependencies", "evidence"}, "proposal")
            pid = payload["proposal_id"]
            if not isinstance(pid, str) or not re.fullmatch(r"[0-9a-f]{32}", pid) or pid in proposals:
                raise GovernanceError("Invalid/duplicate proposal ID")
            policy = _validate_policy(payload["policy"])
            if payload["policy_sha256"] != _digest(policy):
                raise GovernanceError("Proposal policy binding mismatch")
            gate = _gate(policy, payload["gate"])
            if event["role"] not in gate["proposer_roles"]:
                raise GovernanceError("Proposer role is not permitted for this gate")
            _validate_file_record(payload["config"])
            if payload["config"]["path"] != CONFIG_PATH:
                raise GovernanceError("Unexpected configuration path")
            _validate_evidence(payload["evidence"], gate)
            deps = payload["dependencies"]
            if not isinstance(deps, dict) or set(deps) != set(gate["depends_on"]):
                raise GovernanceError("Proposal dependency declaration mismatch")
            for dep, approval_hash in deps.items():
                parent = states.get(dep)
                if not parent or parent["decision"] != "passed" or parent["approval_hash"] != approval_hash:
                    raise GovernanceError("Proposal lacks a valid upstream approval")
            proposals[pid] = event
            states[payload["gate"]] = {"proposal": event, "decision": "proposed", "approval_hash": None}
        elif action == "review":
            _keys(payload, {"proposal_id", "decision", "report"}, "review")
            pid = payload["proposal_id"]
            if not isinstance(pid, str) or pid not in proposals:
                raise GovernanceError("Review references unknown proposal")
            proposal = proposals[pid]
            gate_id = proposal["payload"]["gate"]
            current = states[gate_id]
            if current["proposal"] is not proposal or current["decision"] != "proposed":
                raise GovernanceError("Review must target the current, unreviewed proposal")
            if _actor(event["actor"]) == _actor(proposal["actor"]):
                raise GovernanceError("A proposer cannot review their own proposal")
            gate = _gate(proposal["payload"]["policy"], gate_id)
            if event["role"] not in gate["reviewer_roles"]:
                raise GovernanceError("Reviewer role is not permitted for this gate")
            _validate_file_record(payload["report"])
            report_path = _evidence_path(payload["report"]["path"])
            if report_path.casefold() in {item["path"].casefold() for item in proposal["payload"]["evidence"]}:
                raise GovernanceError("Independent review report must be separate from proposal evidence")
            if payload["decision"] not in {"pass", "reject"}:
                raise GovernanceError("Review decision must be pass or reject")
            if payload["decision"] == "pass":
                for dep, approval_hash in proposal["payload"]["dependencies"].items():
                    parent = states.get(dep)
                    if not parent or parent["decision"] != "passed" or parent["approval_hash"] != approval_hash:
                        raise GovernanceError("Review references superseded upstream approval")
            current["decision"] = "passed" if payload["decision"] == "pass" else "rejected"
            current["review"] = event
            current["approval_hash"] = event["event_hash"] if payload["decision"] == "pass" else None
        elif action == "revoke":
            _keys(payload, {"gate", "proposal_id", "policy", "policy_sha256"}, "revocation")
            policy = _validate_policy(payload["policy"])
            if payload["policy_sha256"] != _digest(policy) or event["role"] not in policy["revocation_roles"]:
                raise GovernanceError("Revocation role/policy binding mismatch")
            _gate(policy, payload["gate"])
            current = states.get(payload["gate"])
            if (not current or current["proposal"]["payload"]["proposal_id"] != payload["proposal_id"]
                    or current["decision"] not in {"passed", "proposed"}):
                raise GovernanceError("Revocation must target a current proposal or approval")
            current["decision"], current["approval_hash"] = "revoked", None
        else:
            raise GovernanceError("Unknown ledger action")
        previous = event["event_hash"]
    return states


def _historical(root):
    """Historical prose stays advisory, including the user's prior Gate0 decision."""
    result = {}
    path = _safe_path(root, "docs/private/decision_log.md")
    if path.is_file():
        content = path.read_text(encoding="utf-8-sig")
        for match in re.finditer(r"^##\s+Gate\s+([0-6])\b(.*?)(?=^##\s|\Z)", content, re.M | re.S | re.I):
            section, decision = match.group(2), "recorded"
            if re.search(r"(?:决定\s*[:：]\s*通过|Decision\s*:\s*pass(?:ed)?\b)", section, re.I):
                decision = "passed (historical; not machine-verified)"
            elif re.search(r"(?:决定\s*[:：]\s*待定|Decision\s*:\s*pending\b)", section, re.I):
                decision = "pending (historical)"
            result[f"gate{match.group(1)}"] = decision
    return result


def _status(root, policy, records, raw):
    states = _replay(records)
    config, policy_hash = _file_record(root, CONFIG_PATH), _digest(policy)
    historical = _historical(root)
    gates, by_id = [], {}
    for gate in policy["gates"]:
        gid = gate["id"]
        state = states.get(gid)
        blockers, stale = [], []
        item = {"id": gid, "label": gate["label"], "depends_on": gate["depends_on"],
                "status": "ready", "recorded_decision": state["decision"] if state else None,
                "blockers": blockers, "proposal_id": None, "approval_hash": None,
                "evidence": [], "required_evidence": gate["required_evidence"],
                "proposer_roles": gate["proposer_roles"], "reviewer_roles": gate["reviewer_roles"],
                "historical_decision": historical.get(gid)}
        for dep in gate["depends_on"]:
            if by_id[dep]["status"] != "passed":
                blockers.append(f"prerequisite {dep} is {by_id[dep]['status']}")
        if state:
            proposal = state["proposal"]["payload"]
            item["proposal_id"], item["evidence"] = proposal["proposal_id"], proposal["evidence"]
            if proposal["config"] != config:
                stale.append("configuration changed")
            if proposal["policy_sha256"] != policy_hash:
                stale.append("governance policy changed")
            for dep, bound_hash in proposal["dependencies"].items():
                if by_id.get(dep, {}).get("approval_hash") != bound_hash:
                    stale.append(f"upstream approval {dep} changed or is no longer valid")
            files = list(proposal["evidence"])
            if "review" in state:
                item["review_report"] = state["review"]["payload"]["report"]
                files.append(item["review_report"])
            for evidence in files:
                try:
                    current = _file_record(root, evidence["path"])
                    if any(current[key] != evidence[key] for key in current):
                        stale.append(f"evidence/review report changed: {evidence['path']}")
                except GovernanceError as exc:
                    stale.append(str(exc))
            if state["decision"] in {"rejected", "revoked"}:
                item["status"] = state["decision"]
            elif blockers:
                item["status"] = "blocked"
            elif stale:
                item["status"] = "stale"
            else:
                item["status"], item["approval_hash"] = state["decision"], state["approval_hash"]
            blockers.extend(stale)
        elif blockers:
            item["status"] = "blocked"
        gates.append(item)
        by_id[gid] = item
    return {"schema_version": SCHEMA_VERSION, "root": str(root), "ledger_valid": True,
            "ledger_path": LEDGER_PATH, "ledger_sha256": hashlib.sha256(raw).hexdigest(),
            "event_count": len(records), "policy_sha256": policy_hash, "config_sha256": config["sha256"],
            "legacy_advisory": "Historical decisions are preserved as context; they are not machine-verified approvals.",
            "identity_model": "locally-declared-not-authenticated",
            "assurance": "Hashes verify artifact identity, not scientific validity, human identity, or a maliciously rewritten ledger.",
            "gates": gates}


def status(root=None):
    """Return a fail-closed JSON-compatible progress board without writing files."""
    try:
        root = project_root(root)
        policy = load_policy()
        records, raw = _read_ledger(root)
        return _status(root, policy, records, raw)
    except (GovernanceError, OSError, UnicodeError, TypeError, KeyError) as exc:
        return {"schema_version": SCHEMA_VERSION, "ledger_valid": False, "error": str(exc),
                "legacy_advisory": "Historical decisions are advisory; technical validation failed.",
                "gates": [{"id": gid, "status": "invalid", "blockers": [str(exc)],
                           "proposal_id": None, "approval_hash": None, "evidence": []} for gid in GATE_IDS]}


@contextmanager
def _locked(root):
    path = _safe_path(root, LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _safe_path(root, LEDGER_PATH + ".lock")
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise GovernanceError("Governance ledger is locked. Do not remove a lock until its writer has stopped.") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def _append(root, records, raw, action, actor, role, rationale, payload):
    event = {"schema_version": SCHEMA_VERSION, "sequence": len(records) + 1,
             "previous_hash": records[-1]["event_hash"] if records else ZERO_HASH,
             "at": datetime.now(timezone.utc).isoformat(), "action": action,
             "actor": _text(actor, "actor", 128), "role": role,
             "rationale": _text(rationale, "rationale"), "payload": payload}
    event["event_hash"] = _digest(event)
    _replay([*records, event])
    updated = raw + _canonical(event) + b"\n"
    if len(updated) > MAX_LEDGER_BYTES:
        raise GovernanceError("Ledger would exceed safety size limit")
    path = _safe_path(root, LEDGER_PATH)
    descriptor, temporary = tempfile.mkstemp(prefix=".events-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return event


def propose(root, gate, evidence, actor, role, rationale):
    root = project_root(root)
    with _locked(root):
        policy = load_policy()
        specification = _gate(policy, gate)
        records, raw = _read_ledger(root)
        gates = {item["id"]: item for item in _status(root, policy, records, raw)["gates"]}
        if role not in specification["proposer_roles"]:
            raise GovernanceError("Proposer role is not permitted for this gate")
        if any(gates[dep]["status"] != "passed" for dep in specification["depends_on"]):
            raise GovernanceError("All gate prerequisites require current verified approval")
        payload = {"proposal_id": uuid.uuid4().hex, "gate": gate,
                   "policy": policy, "policy_sha256": _digest(policy),
                   "config": _file_record(root, CONFIG_PATH),
                   "dependencies": {dep: gates[dep]["approval_hash"] for dep in specification["depends_on"]},
                   "evidence": _evidence_records(root, evidence, specification)}
        return _append(root, records, raw, "propose", actor, role, rationale, payload)


def review(root, proposal_id, decision, actor, role, rationale, report):
    root = project_root(root)
    with _locked(root):
        policy = load_policy()
        records, raw = _read_ledger(root)
        states = _replay(records)
        state = next((value for value in states.values() if value["proposal"]["payload"]["proposal_id"] == proposal_id), None)
        if state is None or state["decision"] != "proposed":
            raise GovernanceError("Review requires a current unreviewed proposal")
        if decision == "pass":
            gid = state["proposal"]["payload"]["gate"]
            current = next(g for g in _status(root, policy, records, raw)["gates"] if g["id"] == gid)
            if current["status"] != "proposed":
                raise GovernanceError("Cannot approve stale or blocked evidence: " + "; ".join(current["blockers"]))
        return _append(root, records, raw, "review", actor, role, rationale,
                       {"proposal_id": proposal_id, "decision": decision,
                        "report": _file_record(root, _evidence_path(report))})


def revoke(root, gate, actor, role, rationale):
    root = project_root(root)
    with _locked(root):
        policy = load_policy()
        _gate(policy, gate)
        records, raw = _read_ledger(root)
        state = _replay(records).get(gate)
        if state is None:
            raise GovernanceError("There is no machine-governed proposal to revoke")
        return _append(root, records, raw, "revoke", actor, role, rationale,
                       {"gate": gate, "proposal_id": state["proposal"]["payload"]["proposal_id"],
                        "policy": policy, "policy_sha256": _digest(policy)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Project directory (default: discover from cwd)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true")
    proposal = commands.add_parser("propose")
    proposal.add_argument("--gate", choices=GATE_IDS, required=True)
    proposal.add_argument("--evidence", action="append", required=True, metavar="KIND=PATH")
    reviewer = commands.add_parser("review")
    reviewer.add_argument("--proposal", required=True)
    reviewer.add_argument("--decision", choices=["pass", "reject"], required=True)
    reviewer.add_argument("--report", required=True, help="Root-relative independent review report")
    revoker = commands.add_parser("revoke")
    revoker.add_argument("--gate", choices=GATE_IDS, required=True)
    for command in (proposal, reviewer, revoker):
        command.add_argument("--actor", required=True, help="Declared identity; this is not authentication")
        command.add_argument("--role", choices=sorted(ROLES), required=True)
        command.add_argument("--rationale", required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        if args.command in {"status", "verify"}:
            report = status(args.root)
            unresolved = [g for g in report["gates"] if g["status"] in {"stale", "invalid"} or
                          (g.get("recorded_decision") in {"passed", "proposed"}
                           and g["status"] not in {"passed", "proposed"})]
            report["verification_ok"] = report["ledger_valid"] and not unresolved
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"Ledger: {'valid' if report['ledger_valid'] else 'INVALID'}")
                for gate in report["gates"]:
                    print(f"{gate['id']}: {gate['status']}" + ("; " + "; ".join(gate["blockers"]) if gate["blockers"] else ""))
                    if gate.get("historical_decision"):
                        print("  Historical: " + gate["historical_decision"])
                print(report["legacy_advisory"])
                print("Declared actors are not authenticated. Technical verification does not validate scientific conclusions.")
            return 0 if report["ledger_valid"] and (args.command != "verify" or report["verification_ok"]) else 2
        if args.command == "propose":
            event = propose(args.root, args.gate, args.evidence, args.actor, args.role, args.rationale)
        elif args.command == "review":
            event = review(args.root, args.proposal, args.decision, args.actor, args.role, args.rationale, args.report)
        else:
            event = revoke(args.root, args.gate, args.actor, args.role, args.rationale)
        print(json.dumps({"action": event["action"], "event_hash": event["event_hash"],
                          "proposal_id": event["payload"]["proposal_id"]}, ensure_ascii=False, indent=2))
        return 0
    except (GovernanceError, OSError, TypeError, KeyError) as exc:
        print(f"Governance error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
