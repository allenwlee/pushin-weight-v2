"""Bounded public HF proof for the owner's automatic approval exception.

Discovery matches are hints. Approval needs a verified publisher, an official
account connection and a pinned model card naming the publisher as developer.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import closing
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from django.core import signing
from django.utils import timezone

from core.hf_metadata_client import NAMESPACE, REPO_ID
from core.official_company_accounts import digest

VERSION = "official-hf-model-developer-v3"
SALT = "official-company-hf-approval-v1"
KEY_ENV = "PUSHINWEIGHT_OFFICIAL_COMPANY_HF_SIGNING_KEY"
SHA = re.compile(r"^[0-9a-f]{40}$")
URL = re.compile(r"https?://[^\s<>\"\)]+")


class ProfileLinks(HTMLParser):
    """Only HF's organization profile fields, excluding model-card links."""

    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and "leading-snug" in values.get("class", "").split():
            self.urls.append(values.get("href", ""))


class PublicHF:
    def __init__(self, client, *, seconds=20, max_requests=12):
        self.client = client
        self.deadline = time.monotonic() + seconds
        self.max_requests = max_requests
        self.observations = []

    def get(self, path, *, params=None, text=False):
        if len(self.observations) >= self.max_requests or time.monotonic() >= self.deadline:
            return None
        observation = {"url": "https://huggingface.co" + path, "parameters": params,
                       "observed_at": timezone.now().isoformat(), "outcome": "pending"}
        self.observations.append(observation)
        try:
            request = self.client.build_request(
                "GET", observation["url"], params=params,
                timeout=min(5, max(.001, self.deadline - time.monotonic())),
            )
            request.headers.pop("authorization", None)
            request.headers.pop("cookie", None)
            with closing(self.client.send(request, stream=True, auth=None, follow_redirects=False)) as response:
                observation["http_status"] = response.status_code
                if response.status_code != 200:
                    observation["outcome"] = f"http_{response.status_code}"
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= self.deadline or len(body) + len(chunk) > 1024 * 1024:
                        observation["outcome"] = "response_cap"
                        return None
                    body.extend(chunk)
                value = body.decode() if text else json.loads(body)
                observation["outcome"] = "ok"
                return value
        except (httpx.HTTPError, ValueError, UnicodeError):
            observation["outcome"] = "request_or_parse_error"
            return None


def _domain(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return ""
    return (parsed.hostname or "").casefold().removeprefix("www.")


def _compact(text):
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def development_quote(card, organization, namespace, *, identity_name="", publisher_urls=()):
    """A narrow positive proof; unsupported writing styles remain reviewable."""
    name = re.sub(r"[,\s]+(?:inc\.?|ltd\.?|llc|corporation)\s*$", "", organization, flags=re.IGNORECASE)
    aliases = {_compact(name), _compact(namespace), _compact(identity_name)} - {""}

    def credited(value, names):
        return any(re.search(
            r"(?:^|,\s*|\band\s+)" + r"[. _-]*".join(map(re.escape, alias))
            + r"(?=$|[\s,.;:])", value, re.IGNORECASE,
        ) for alias in names)

    for line in card.splitlines():
        if len(line) > 2000:
            continue
        # Name must immediately follow the development credit. A mirrored card
        # crediting Meta, with the host's name elsewhere, cannot pass.
        clean = re.sub(r"[*#]", "", line)
        # Preserve the original quote, but match the visible link label. A
        # research publisher may explicitly credit its parent company via the
        # same company website shown on its verified HF profile.
        links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", clean)
        clean = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", clean)
        names = aliases.copy()
        for label, url in links:
            alias = _compact(label)
            if len(alias) >= 4 and _compact(name).startswith(alias) and _domain(url) in {_domain(site) for site in publisher_urls}:
                names.add(alias)
        match = re.search(r"(?:developed|trained|fine[- ]?tuned|finetuned|quantized|quantised)\s+by\s*:?\s*(.+)", clean, re.IGNORECASE)
        if match and re.search(r"\b(?:not|never)\s*$", clean[:match.start()], re.IGNORECASE):
            continue
        if match and credited(match[1], names):
            return line
        # Common model-card field: "Model developer: Cohere and Cohere Labs".
        match = re.search(r"^\s*[-|]?\s*model\s+developer\s*:\s*(.+)", clean, re.IGNORECASE)
        if match and credited(match[1], names):
            return line
    return ""


def verify(evidence, decision, *, client=None, seconds=20):
    result = {"version": VERSION, "outcome": "review_needed",
              "evidence_hash": evidence["identity"], "observed_at": timezone.now().isoformat()}
    if client is None:
        with httpx.Client(trust_env=False) as public_client:
            return verify(evidence, decision, client=public_client, seconds=seconds)
    api = PublicHF(client, seconds=seconds)
    result["requests"] = api.observations
    hints = []
    for source in evidence["sources"]:
        for url in URL.findall(source["text"]):
            if _domain(url) == "huggingface.co":
                name = urlparse(url).path.strip("/").split("/")[0]
                if NAMESPACE.fullmatch(name):
                    hints.append(name)
    handle = (evidence.get("handle") or "").removeprefix("@")
    if not handle:
        return result
    if NAMESPACE.fullmatch(handle):
        hints.append(handle)
    query = next((value for value in (decision.get("organization_name"), evidence.get("display_name"), handle) if isinstance(value, str) and value.strip()), handle)
    search = api.get("/api/quicksearch", params={"q": query[:100]})
    if isinstance(search, dict):
        for org in (search.get("orgs") if isinstance(search.get("orgs"), list) else [])[:6]:
            name = org.get("name") if isinstance(org, dict) else None
            if isinstance(name, str) and NAMESPACE.fullmatch(name):
                hints.append(name)
    names = list(dict.fromkeys(name.casefold() for name in hints))[:2]
    publishers = []
    bindings = []
    shared_hosts = {"x.com", "twitter.com", "huggingface.co", "t.co", "github.com", "linkedin.com", "linktr.ee"}
    for namespace in names:
        org = api.get(f"/api/organizations/{namespace}/overview")
        if not isinstance(org, dict) or org.get("isVerified") is not True or not isinstance(org.get("name"), str) or org["name"].casefold() != namespace or not isinstance(org.get("fullname", ""), str):
            continue
        namespace = org["name"]
        html = api.get(f"/{namespace}", text=True)
        if not isinstance(html, str):
            continue
        links = ProfileLinks()
        links.feed(html)
        websites = [url for url in links.urls if _domain(url) and _domain(url) not in shared_hosts]
        account_links = [url for url in links.urls if (
            _domain(url) in {"twitter.com", "x.com"}
            and urlparse(url).path.strip("/").casefold() == handle.casefold()
        )]
        publisher = {"namespace": namespace, "org": org, "websites": websites, "account_links": account_links}
        publishers.append(publisher)
        if account_links:
            bindings.append(publisher)
    for publisher in publishers:
        namespace, org = publisher["namespace"], publisher["org"]
        ownership = publisher["account_links"][:]
        identity_publisher = namespace
        identity_name = org.get("fullname") or org["name"]
        if not ownership:
            # A verified parent HF organization may point to the company X
            # account while its verified research namespace publishes models.
            # Shared domains alone cannot bind an arbitrary X account.
            for binding in bindings:
                common = {_domain(url) for url in binding["websites"]} & {_domain(url) for url in publisher["websites"]}
                parent_name = _compact(binding["org"].get("fullname", ""))
                child_name = _compact(org.get("fullname", ""))
                related_name = min(len(parent_name), len(child_name)) >= 4 and (child_name.startswith(parent_name) or parent_name.startswith(child_name))
                if common and related_name:
                    ownership = binding["account_links"] + [url for url in publisher["websites"] if _domain(url) in common]
                    identity_publisher = binding["namespace"]
                    identity_name = binding["org"].get("fullname") or binding["org"]["name"]
                    break
        if not ownership:
            continue
        models = api.get("/api/models", params={"author": namespace, "limit": 3, "full": "true", "sort": "downloads", "direction": -1})
        if not isinstance(models, list):
            continue
        for model in models[:3]:
            if not isinstance(model, dict):
                continue
            repo, sha = model.get("id", ""), model.get("sha", "")
            if not isinstance(repo, str) or not REPO_ID.fullmatch(repo) or repo.split("/")[0].casefold() != namespace.casefold() or not isinstance(sha, str) or not SHA.fullmatch(sha) or model.get("private") is not False or model.get("disabled"):
                continue
            artifacts = [row.get("rfilename", "") for row in (model.get("siblings") if isinstance(model.get("siblings"), list) else []) if isinstance(row, dict) and isinstance(row.get("rfilename"), str) and row["rfilename"].lower().endswith((".safetensors", ".bin", ".onnx", ".pt", ".pth", ".h5", ".hdf5", ".ckpt", ".tflite", ".mlmodel", ".pkl", ".joblib", ".gguf"))]
            if not artifacts:
                continue
            card = api.get(f"/{repo}/raw/{sha}/README.md", text=True)
            quote = development_quote(card, org.get("fullname", ""), namespace, identity_name=identity_name, publisher_urls=publisher["websites"]) if isinstance(card, str) else ""
            if quote:
                result.update(outcome="passed", namespace=org["name"],
                              publisher_name=org.get("fullname"), ownership_urls=ownership,
                              identity_namespace=identity_publisher, organization_name=identity_name,
                              publisher_profiles=[{"namespace": p["namespace"], "is_verified": True, "account_links": p["account_links"], "websites": p["websites"]} for p in publishers],
                              repo_id=repo, sha=sha, model_artifacts=artifacts[:20], model_url=f"https://huggingface.co/{repo}",
                              card_url=f"https://huggingface.co/{repo}/blob/{sha}/README.md",
                              development_quote=quote)
                return result
    return result


def _binding(state):
    return {"account_id": str(state.account_id), "evidence_hash": state.evidence_hash,
            "decision_hash": digest({k: v for k, v in state.decision.items() if k != "hf_verification"})}


def approved(state):
    key = os.environ.get(KEY_ENV)
    if not key:
        return False
    receipt = state.decision.get("hf_verification", {})
    if not isinstance(receipt, dict) or receipt.get("outcome") != "passed":
        return False
    try:
        proof = signing.loads(receipt.get("signature", ""), key=key, salt=SALT, fallback_keys=[])
    except (signing.BadSignature, TypeError, ValueError):
        return False
    return proof == {**_binding(state), "verification_hash": digest({k: v for k, v in receipt.items() if k != "signature"})}


def verify_review_candidates(*, limit=1, deadline=None, state_ids=None):
    """One check per current evidence/version; failures remain human review."""
    from django.db import transaction
    from django.db.models import F, Q
    from django.db.models.fields.json import KT

    from core.models import OfficialCompanyAccountState

    key = os.environ.get(KEY_ENV)
    if not key:
        return {"checked": 0, "approved": 0, "status": "signing_key_unavailable"}
    candidates = (OfficialCompanyAccountState.objects.filter(
        status="review_needed",
    ).exclude(last_error="already_tracked").exclude(model="owner-attestation"
    ).filter(Q(decision__contradictions=[]) | Q(decision__contradictions__isnull=True),
    ).alias(hf_evidence_hash=KT("decision__hf_verification__evidence_hash"))
        .filter(~Q(decision__hf_verification__version=VERSION)
             | ~Q(hf_evidence_hash=F("evidence_hash"))
             | Q(decision__hf_verification__isnull=True)
             | Q(decision__hf_verification__version__isnull=True)
             | Q(hf_evidence_hash__isnull=True)))
    if state_ids is not None:
        if len(state_ids) > 2000:
            raise ValueError("HF candidate set exceeds bound")
        candidates = candidates.filter(pk__in=state_ids)
    ids = list(candidates.order_by("candidate_priority", "updated_at", "pk").values_list("pk", flat=True)[:limit])
    result = {"checked": 0, "approved": 0}
    for state_id in ids:
        remaining = deadline - time.monotonic() if deadline is not None else 20
        if remaining < 2:
            break
        state = OfficialCompanyAccountState.objects.get(pk=state_id)
        proof = verify(state.evidence, state.decision, seconds=min(20, remaining))
        with transaction.atomic():
            current = OfficialCompanyAccountState.objects.select_for_update().get(pk=state_id)
            if current.status != "review_needed" or _binding(current) != _binding(state):
                continue
            if proof["outcome"] == "passed":
                # Preserve the immutable evaluator attempt. Registration uses
                # the externally established identity rather than a guessed name.
                current.decision = {**current.decision, "outcome": "accepted",
                                    "organization_name": proof["organization_name"],
                                    "model_types": current.decision.get("model_types") or ["other"],
                                    "rationale": "Verified official HF publisher and own model-development card.",
                                    "contradictions": current.decision.get("contradictions", []),
                                    "claims": current.decision.get("claims", {})}
                proof["signature"] = signing.dumps({**_binding(current), "verification_hash": digest(proof)}, key=key, salt=SALT)
                current.status = "accepted"
                current.last_error = ""
                result["approved"] += 1
            current.decision = {**current.decision, "hf_verification": proof}
            current.save(update_fields=["status", "last_error", "decision", "updated_at"])
            result["checked"] += 1
    return result
