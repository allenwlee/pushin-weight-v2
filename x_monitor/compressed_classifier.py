"""Compressed extraction + Jev classification, with injectable transport.

No database/network activity on import. The saved experimental baseline remains
available to offline replay; the runtime passes an explicit release vocabulary.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache

from core.classification_contract import (
    AUDIENCE_TOPIC_KEYS,
    COMPRESSED_CLASSIFIER_REVISIONS,
    GEOPOLITICAL_MODE_KEYS,
    POST_TYPE_KEYS,
    PRODUCT_LABEL_KEYS,
    UNTRACKED_BRAND_PROMOTION_KEYS,
)
from core.product_release_findings import SCHEMA, FindingLimits, parse_release_findings
from monitor.promotion_subject_matcher import PromotionSubjectMatcher
from x_monitor import attribution as parser
from x_monitor.compressed_classifier_prompts import (
    CHANNEL_MEANINGS,
    EXTRACTION,
    QUESTIONS,
    RELEASE_EXTRACTION,
    RULES,
    STANCE_CRITERIA,
)
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, DeepInfraChatCompletionsClient
from x_monitor.jev_classifier import MODEL

PROFILE = "compressed8_pulse_v1"
REVISIONS = COMPRESSED_CLASSIFIER_REVISIONS
COMBINED_MODEL = DEEPSEEK_0731_MODEL + "+" + MODEL
FIELDS = tuple(f"{prefix}:{key}" for prefix, keys in (
    ("type", POST_TYPE_KEYS), ("topic", AUDIENCE_TOPIC_KEYS),
    ("product", PRODUCT_LABEL_KEYS), ("geo", GEOPOLITICAL_MODE_KEYS),
    ("promotion", UNTRACKED_BRAND_PROMOTION_KEYS),
) for key in keys) + ("outcome", "sentiment", "china_national_stance", "us_national_stance")
PROMOTION_KEYS = UNTRACKED_BRAND_PROMOTION_KEYS
POST_QUESTIONS = ("untracked_pitch", "promotion:spam", "promotion:scam", "promotion:crypto", "promotion:unauthorized")
# Structural safeguards only; these do not select quality/spend acceptance.
RELEASE_LIMITS = FindingLimits(max_findings=8, max_assertions=8, max_text_chars=4096)

def norm(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().strip(' "\'').split())

def sources(state):
    result = [{'id': 'post', 'text': state['source_text'], 'author': state.get('author_handle')}]
    if state.get('english_translation'):
        result.append({'id': 'translation', 'text': state['english_translation'], 'author': state.get('author_handle')})
    context = state.get('context', {})
    if isinstance(context, dict):
        for key, label in [('stored_quote','quote'), ('local_parent','parent')]:
            if context.get(key):
                result.append({'id': label, 'text': context[key], 'author': context.get('quoted_author') if label == 'quote' else None})
    elif isinstance(context, list):
        for i, row in enumerate(context):
            if isinstance(row, dict) and row.get('text'):
                result.append({'id': f'context_{i}', 'text': row['text'], 'author': row.get('author_handle')})
    return result

def entities(document, state, matcher):
    """Discard invalid individual entries, retaining exact provenance and errors."""
    source_map = {s['id']: s['text'] for s in sources(state)}
    rows, errors, seen = [], [], set()
    if not isinstance(document, dict) or not isinstance(document.get('entities'), list):
        return [], ['invalid_entity_list']
    for i, row in enumerate(document['entities']):
        if not isinstance(row, dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('name','source','evidence')):
            errors.append(f'{i}:invalid_fields'); continue
        text = source_map.get(row['source'], '')
        # Exact text or whitespace-only normalization; never paraphrase repair.
        evidence = row['evidence']
        match = re.search(r'\s+'.join(re.escape(s) for s in evidence.split()), text)
        if not match or norm(row['name']) not in norm(match.group()):
            errors.append(f'{i}:unsupported_name_or_evidence'); continue
        if norm(row['name']) in seen:
            continue
        seen.add(norm(row['name']))
        matched = matcher.match({'name':row['name']})
        identities = list(matched.owners) if matched else []
        rows.append({'name':row['name'], 'source':row['source'], 'evidence':match.group(),
                     'catalog_matches':identities, 'tracked':bool(identities),
                     'match_tier':matched.tier if matched else None})
    return rows, errors


def _state(case):
    state = deepcopy(case["state"])
    targets = case.get("target_brands") or [state["target_brand"]]
    if not targets or any(not isinstance(x, str) or not x for x in targets) or len(set(targets)) != len(targets):
        raise ValueError("invalid_target_brand_slots")
    if not isinstance(state.get("source_text"), str):
        raise TypeError("invalid_source_text")
    state.setdefault("tracked_brands", [])
    state.setdefault("context", {})
    state.setdefault("author_affiliations", [])
    state["target_brand"] = targets[0]
    return state, list(targets)


@lru_cache(maxsize=8)
def _catalog_matcher(serialized):
    return PromotionSubjectMatcher(json.loads(serialized))


def _matcher(state):
    rows = [
        {**{k: v for k, v in entry.items() if k != "source_matched_product_candidates"},
         "products": list(dict.fromkeys([*entry.get("products", []), *entry.get("source_matched_product_candidates", [])]))}
        for entry in state["tracked_brands"]
    ]
    return _catalog_matcher(json.dumps(rows, sort_keys=True, ensure_ascii=False))


def make_extraction_request(case, *, release_channels=None, max_tokens=parser.CLASSIFIER_MAX_TOKENS):
    state, _ = _state(case)
    packet = {"sources": sources(state)}
    system = EXTRACTION
    if release_channels is not None:
        if any(code not in CHANNEL_MEANINGS for code in release_channels):
            raise ValueError("unsupported_release_channel_vocabulary")
        system = system.replace("No classifications, owners or explanations.", "No inferred owners or explanations.")
        system += RELEASE_EXTRACTION
        packet["access_channels"] = {code: CHANNEL_MEANINGS[code] for code in release_channels}
        packet["source_published_at"] = case.get("source", {}).get("created_at")
        packet["limits"] = {"findings": RELEASE_LIMITS.max_findings, "assertions_per_finding": RELEASE_LIMITS.max_assertions}
    client = DeepInfraChatCompletionsClient(api_key="offline", model=DEEPSEEK_0731_MODEL, request_profile="deepseek_0731")
    return client.build_request(
        system=system,
        messages=[{"role": "user", "content": json.dumps(packet, ensure_ascii=False, separators=(",", ":"))}],
        max_tokens=max_tokens,
    )


def parse_extraction_response(document):
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except ValueError:
            return {"invalid_extraction_response": True}
    if isinstance(document, dict) and "choices" in document:
        # Parse captured provider replies through the real transport parser,
        # with an injected response; this never performs an HTTP request.
        from x_monitor.deepinfra import DeepInfraPermanentError, DeepInfraRetryableError

        try:
            client = DeepInfraChatCompletionsClient(
                api_key="offline", model=DEEPSEEK_0731_MODEL, request_profile="deepseek_0731",
                transport=lambda _request, _timeout: document,
            )
            return dict(client.messages_create(system="", messages=[], max_tokens=parser.CLASSIFIER_MAX_TOKENS))
        except (ValueError, TypeError, KeyError, IndexError, DeepInfraPermanentError, DeepInfraRetryableError):
            return {"invalid_extraction_response": True}
    return document


def _prepare(state, rows, errors):
    brand = state["target_brand"]
    questions = {
        key: {"type": "noul", "instructions": text.format(b=brand)}
        for key, text in QUESTIONS.items()
    }
    for key in ("china_national_stance", "us_national_stance"):
        questions[key].update(type="choice", criteria=dict(STANCE_CRITERIA))
    compact = {k: v for k, v in state.items() if k != "tracked_brands"}
    compact["entities"] = [
        {"name": r["name"], "possible_tracked_owners": r["catalog_matches"], "match_kind": r["match_tier"]}
        for r in rows
    ]
    compact["untracked_candidates"] = [r["name"] for r in rows if not r["tracked"]]
    compact["rules"] = RULES
    compact["tracked_brand_ids"] = [r["brand_id"] for r in state["tracked_brands"]]
    compact["author_is_target_official"] = any(
        r.get("reviewed") is True and r.get("brand_id") == brand
        and r.get("role") in ("official", "staff")
        for r in state.get("author_affiliations", []) if isinstance(r, dict)
    )
    speakers = [("post", state.get("author_handle"))]
    if isinstance(state.get("context"), dict):
        speakers.append(("quote", state["context"].get("quoted_author")))
    compact["catalog_speaker_relationships"] = [
        {"source": source, "handle": handle, "brand_id": entry["brand_id"], "role": account.get("role")}
        for source, handle in speakers if handle
        for entry in state["tracked_brands"] for account in entry.get("accounts", [])
        if account.get("handle", "").lstrip("@").casefold() == handle.lstrip("@").casefold()
    ]
    target = next((r for r in state["tracked_brands"] if r["brand_id"] == brand), {})
    compact["target_model_candidates"] = target.get("source_matched_product_candidates", [])
    return {"model": MODEL, "state": compact, "questions": questions}


def _context_limits(request):
    import tiktoken

    encoder = tiktoken.get_encoding("cl100k_base")

    def count(value):
        return len(encoder.encode(json.dumps(value, ensure_ascii=False, separators=(",", ":")), disallowed_special=()))

    total = count(request)
    state_question = count(request["state"]) + max((count(q) for q in request["questions"].values()), default=0)
    return {"estimated_request_tokens": total, "estimated_state_question_tokens": state_question,
            "context_valid": total < 48000 and state_question < 24000,
            "limits": {"request": 48000, "state_plus_question": 24000}}


def _umbrella(request, state, targets, question_map):
    visible = "\n".join(source["text"] for source in sources(state))
    facts = {}
    for brand in targets:
        entry = next((r for r in state["tracked_brands"] if r["brand_id"] == brand), {})
        terms = []
        for raw in [*entry.get("aliases", []), *entry.get("products", [])]:
            term = raw.strip('"').strip()
            if len(term) < 3 or "/" in term:
                continue
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", visible, re.IGNORECASE) and term.casefold() not in {v.casefold() for v in terms}:
                terms.append(term)
        facts[brand] = terms
        scope = (
            "the post and its discussed offerings [unattributed discovery: no known owner; a tracked-brand connection is not required]"
            if brand == "_unattributed" else
            brand + " [tracked umbrella; post-matched catalog names: " + (", ".join(terms) if terms else "none") + "]"
        )
        for key, qid in question_map[brand].items():
            if key not in POST_QUESTIONS:
                question = request["questions"][qid]
                question["instructions"] = question["instructions"].replace(brand, scope)
    request["state"]["umbrella_meaning"] = (
        "Each target ID is a database key for a tracked company and its product umbrella. "
        "The matched names are members of that target, not separate targets. Judge the relevant company or product mentioned in the source; "
        "avoid transferring opinions or promotion between offerings."
    )
    request["state"]["target_umbrella_post_matched_names"] = facts
    if "_unattributed" in targets:
        request["state"]["unattributed_meaning"] = (
            "_unattributed is the existing discovery slot for this post, not a brand or company. "
            "Classify the source and its offerings without requiring a tracked-brand connection or inventing ownership."
        )
    request["state"]["rules"] = request["state"]["rules"].replace(
        "target_brand means the AI company/model family.", "target_brand is a database key for the tracked company and product umbrella.",
    )


def _release_questions(request, findings, targets):
    request["state"]["release_findings"] = findings
    for index, finding in enumerate(findings):
        prefix = f"release:{index}"
        request["questions"][prefix + ":novelty"] = {
            "type": "choice", "instructions": f"For release_findings[{index}], what does the visible source establish? Do not infer unseen sources or use post date as release date.",
            "criteria": {
                "new_release": "This specific product/version/preview is reported newly released or introduced. An existing component merely named within a suite launch is not a separate release; a component explicitly introduced in that same announcement is.",
                "historical_release": "A real earlier release is reported, including a recap; database presence is unknown.",
                "availability_update": "Access/distribution/weights/API or another milestone of an existing product; no new product established.",
                "unresolved": "A plausible release claim remains uncertain, unnamed, rumored or future.",
                "nonrelease": "No product release/access milestone claim: ordinary use, opinion, lineup, comparison, joke or unrelated item.",
            },
        }
        request["questions"][prefix + ":category"] = {
            "type": "choice", "instructions": f"Category of the offering in release_findings[{index}], from supplied evidence only?",
            "criteria": {"model-llm": "A language model itself",
                         "model-other": "A model itself, such as an image, audio or embedding model; an application feature using a model is not itself evidence of a model",
                         "agent": "Agent product", "harness": "Agent/model harness or orchestration tooling",
                         "other": "Other product or feature, including hardware and application features", "unknown": "Insufficient evidence"},
        }
        for brand in targets:
            request["questions"][prefix + ":concerns:" + brand] = {
                "type": "noul", "instructions": (
                    f"Is release_findings[{index}] a release/access milestone discussed in this source? The _unattributed slot does not require a tracked brand or known owner."
                    if brand == "_unattributed" else
                    f"Does the release/access milestone in release_findings[{index}] actually concern tracked brand {brand} or its offering? Comparator, credit or incidental keyword alone is insufficient. This is topic attribution, not verified ownership."
                ),
            }


def build_jev(case, extraction_document, *, release_channels=None):
    state, targets = _state(case)
    matcher = _matcher(state)
    document = parse_extraction_response(extraction_document)
    rows, errors = entities(document, state, matcher)
    requests = {brand: _prepare({**state, "target_brand": brand}, rows, errors) for brand in targets}
    request = deepcopy(requests[targets[0]])
    question_map = {}
    if len(targets) == 1:
        question_map[targets[0]] = {key: key for key in request["questions"]}
    else:
        shared = request["state"]
        target_keys = ("target_brand", "target_model_candidates", "author_is_target_official")
        shared["target_brands"] = targets
        shared["target_facts"] = {
            brand: {k: requests[brand]["state"].get(k) for k in target_keys if k != "target_brand"}
            for brand in targets
        }
        for key in target_keys:
            shared.pop(key, None)
        request["questions"] = {}
        for index, brand in enumerate(targets):
            mapping = {}
            for key, question in requests[brand]["questions"].items():
                actual = "post:" + key if key in POST_QUESTIONS else f"b{index}:" + key
                if actual in request["questions"] and request["questions"][actual] != question:
                    raise ValueError("conflicting_shared_question")
                request["questions"][actual] = question
                mapping[key] = actual
            question_map[brand] = mapping
    source_map = {source["id"]: source["text"] for source in sources(state)}
    bindings = []
    for row in rows:
        if row["tracked"]:
            continue
        evidence = source_map[row["source"]]
        sid = f"S{len(bindings)}"
        binding = {"id": sid, "name": row["name"], "source": row["source"],
                   "evidence": evidence, "start": 0, "end": len(evidence), "questions": {}}
        scope = f"In the complete supplied source {json.dumps(row['source'])}, for {json.dumps(row['name'], ensure_ascii=False)}'s own offering: "
        texts = {
            "pitch": "does this passage actively promote it? Preserve speaker attribution; mere mention, credits, criticism, unendorsed quotation, rejected pitches or another provider's offer are insufficient.",
            "spam": "does this passage repeat or substantially duplicate its promotional sales text? A feature list, quote repetition or one invitation is insufficient.",
            "scam": "does this passage show deceptive-fraud or scam evidence in promotion of this same offering? An allegation about another subject is insufficient.",
            "crypto": "does this passage promote this same offering as a crypto/token/blockchain asset? Model inference credits or ordinary crypto payments alone are insufficient.",
            "unauthorized": "does this passage show this same offering's promotion is unauthorized through denied permission or impersonation? Unstated permission, independent services and referrals alone are insufficient.",
        }
        for kind, text in texts.items():
            qid = f"binding:{sid}:{kind}"
            request["questions"][qid] = {"type": "noul", "instructions": scope + text}
            binding["questions"][kind] = qid
        bindings.append(binding)
    missing = "binding:missing_subject"
    request["questions"][missing] = {
        "type": "noul", "instructions": "Does any supplied source actively promote an untracked offering whose identity is absent from binding_subjects? Catalog-tracked offerings, mere mentions and duplicate names for a listed subject do not qualify.",
    }
    request["state"]["binding_subjects"] = [{k: b[k] for k in ("id", "name", "source", "start", "end")} for b in bindings]
    source_fields = {"post": "source_text", "translation": "english_translation", "quote": "context.stored_quote", "parent": "context.local_parent"}
    request["state"]["binding_source_fields"] = {
        source["id"]: source_fields.get(source["id"], f"context[{source['id'].removeprefix('context_')}].text")
        for source in sources(state)
    }
    _umbrella(request, state, targets, question_map)
    findings, release_error = None, None
    if release_channels is not None:
        try:
            findings = parse_release_findings(
                document.get("release_findings") if isinstance(document, dict) else None,
                source={"kind": "post", "id": str(case["case_id"])}, passages=source_map,
                allowed_channels=release_channels, limits=RELEASE_LIMITS,
            )
        except (TypeError, ValueError):
            release_error = "invalid_release_findings"
        if findings is not None:
            _release_questions(request, findings, targets)
            for index, finding in enumerate(findings):
                for relation_index, relation in enumerate(finding["lineage_evidence"]):
                    request["questions"][f"release:{index}:lineage:{relation_index}:supported"] = {
                        "type": "noul", "instructions": (
                            f"Does the supplied excerpt explicitly state that {finding['observed_name']!r} "
                            f"has this relationship to the named parent: {json.dumps(relation, ensure_ascii=False)}? "
                            "new_version means a successor version, finetune a fine-tune of the parent, adapter an "
                            "adapter for it, quantized its quantized derivative, and merge an explicit merge input. "
                            "A comparison, similar name, shared publisher or version number alone is insufficient. "
                            "Confirm only the reported relationship, not canonical Product identity or family membership."
                        ),
                    }
                family = finding.get("family_evidence")
                if family is not None:
                    request["questions"][f"release:{index}:family_supported"] = {
                        "type": "noul", "instructions": (
                            f"Does the supplied source explicitly identify {family['name']!r} as the "
                            f"publisher-named family or series containing {finding['observed_name']!r}? "
                            "A brand, broad company catalog, technical parent or similar name alone is insufficient."
                        ),
                    }
                issuer = finding.get("issuer_evidence")
                if issuer is not None:
                    request["questions"][f"release:{index}:issuer_supported"] = {
                        "type": "noul", "instructions": (
                            f"For release finding {index} ({finding['observed_name']!r}), does the supplied source "
                            f"support this issuer assertion: {json.dumps(issuer, ensure_ascii=False)}? "
                            "source_author means the primary post author explicitly presents this as their own release. "
                            "A quote, parent, comparison, redistribution, use, credit or third-party announcement does not. "
                            "attributed_party requires the exact named party explicitly issuing this offering. "
                            "Validate only the reported source statement, not canonical ownership or account authenticity."
                        ),
                    }
                    profile = state.get("author_profile_evidence")
                    if (issuer["relation"] == "source_author" and isinstance(profile, dict)
                            and isinstance(profile.get("display_name"), str) and profile["display_name"].strip()
                            and profile.get("sources")):
                        request["questions"][f"release:{index}:profile_publisher_supported"] = {
                            "type": "noul", "instructions": (
                                f"Does the supplied author profile identify {profile['display_name']!r} "
                                f"as the organization publishing {finding['observed_name']!r} in this post? "
                                "The name must identify the publishing organization, not an individual, "
                                "reporter, reseller, customer, unrelated company, or product."
                            ),
                        }
                    for brand in targets:
                        if brand != "_unattributed":
                            request["questions"][f"release:{index}:publisher:{brand}"] = {
                                "type": "noul", "instructions": (
                                    f"Does the supplied post and author profile identify tracked brand {brand!r} "
                                    f"as the issuer of {finding['observed_name']!r} in the reported release? "
                                    "For a third-party report, require that the report attributes the release "
                                    "to that brand. For a source-author claim, use the supplied profile and "
                                    "post together. Shared use, comparison, hosting or incidental mentions "
                                    "alone do not identify the publisher."
                                ),
                            }
    metadata = {"target_brands": targets, "question_map": question_map, "bindings": bindings,
                "missing_subject_question": missing, "extraction_rows": rows, "extraction_errors": errors,
                "original_question_count": 52, "question_count": len(request["questions"]),
                "catalog_revision": matcher.revision, "release_findings": findings,
                "release_error": release_error, **_context_limits(request)}
    return {"request": request, "metadata": metadata}


def _probability(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("invalid_jev_probability")
    return value


def _decode(document, request):
    if not isinstance(document, dict):
        document = {}
    answers = document.get("answers")
    if not isinstance(answers, dict):
        answers = {}
    decoded = {}
    for key, question in request["questions"].items():
        try:
            answer = answers[key]
            if document.get("model") != MODEL or answer["type"] != question["type"]:
                raise ValueError("jev_response_mismatch")
            if question["type"] == "noul":
                p = _probability(answer["noul"])
                value = {"assigned": p >= 0.5, "p_yes": p, "selected_probability": p if p >= 0.5 else 1 - p}
            else:
                probs = answer["probabilities"]
                if not isinstance(probs, dict) or set(probs) != set(question["criteria"]):
                    raise ValueError("jev_choice_mismatch")
                for p in probs.values():
                    _probability(p)
                choice = answer["choice"]
                if abs(sum(probs.values()) - 1) > 0.015 or choice not in probs or probs[choice] != max(probs.values()):
                    raise ValueError("invalid_jev_choice")
                value = {"assigned": choice, "selected_probability": probs[choice],
                         "probabilities": probs, "provider_confidence": _probability(answer["confidence"])}
            decoded[key] = {"valid": True, **value}
        except (KeyError, TypeError, ValueError):
            decoded[key] = {"valid": False, "assigned": None}
    return decoded, sorted(set(answers) - set(request["questions"]))


def _or(values):
    values = list(values)
    return True if True in values else None if None in values else False


def _and(values):
    values = list(values)
    return False if False in values else None if None in values else True


def combine(decoded, state, rows, errors, fields=FIELDS):
    """Flattened selected Cycle 8 assembly; no earlier experiment overrides."""
    def v(key):
        answer = decoded.get(key, {})
        return answer.get("assigned") if answer.get("valid") else None

    final = {key: v(key) for key in fields}
    incidental = v("target_incidental_only")
    final["type:advertising_marketing"] = _and([v("target_pitch"), None if incidental is None else not incidental])
    final["product:ideas_requests"] = _and([_or(v(k) for k in ("need_capability", "need_improvement", "need_unmet", "need_idea")), v("need_change")])
    supported = _or(final[k] for k in fields if k.startswith("type:") and k != "type:other")
    final["outcome"] = "classified" if supported is True or v("relevant") is True else None if supported is None or v("relevant") is None else "context_missing"
    final["type:other"] = False if supported is True else None if supported is None else final["outcome"] == "classified"
    pos, neg = v("positive"), v("negative")
    if None in (pos, neg):
        final["sentiment"] = None
    elif pos and neg:
        final["sentiment"] = "mixed"
    elif pos:
        final["sentiment"] = "positive"
    elif neg:
        final["sentiment"] = "negative"
    elif v("relevant") or final["outcome"] == "classified":
        final["sentiment"] = "neutral"
    else:
        final["sentiment"] = "unknown"
    final["geo:framework"] = _or(v(k) for k in ("geo_systems", "geo_policy", "geo_competition", "geo_security"))
    final["geo:nationalism"] = _and([_or([v("national_evaluation"), v("origin_evaluation")]), v("national_adoption")])
    for key in ("china_national_stance", "us_national_stance"):
        if final["geo:nationalism"] is False:
            final[key] = "none" if final["outcome"] == "classified" or v("relevant") else "unknown"
        elif final["geo:nationalism"] is None:
            final[key] = None
    specifics = _or(final["promotion:" + key] for key in PROMOTION_KEYS[1:])
    final["promotion:general"] = False if specifics is True else None if specifics is None else v("untracked_pitch")
    wrong = any(decoded.get(k, {}).get("valid") and decoded[k].get("p_yes", 0) >= .5
                for k in ("identity_namesake_only", "identity_keyword_only", "identity_word_only"))
    if wrong:
        for key in final:
            if key.startswith(("type:", "topic:", "product:", "geo:")):
                final[key] = False
        final["outcome"] = "context_missing"
        final["sentiment"] = final["china_national_stance"] = final["us_national_stance"] = "unknown"
    elsewhere = decoded.get("evaluation_elsewhere", {})
    if final["outcome"] == "classified" and elsewhere.get("valid") and elsewhere.get("p_yes", 0) >= .7:
        final["sentiment"] = "neutral"
    return final


def _role_documents(case, by_brand, promotions, subjects):
    state, targets = _state(case)
    case_id = str(case["case_id"])
    source = {"tweet_id": case_id, "text": state["source_text"],
              "english_translation": state.get("english_translation", ""),
              "context": state.get("context", {}), "brand_ids": targets}
    decisions = {f"D{i + 1:02d}": (case_id, brand) for i, brand in enumerate(targets)}
    contract = ([source], decisions, {"P01": case_id}, {})
    content = {"decisions": {}, "post_promotions": {"P01": promotions or ["none"]}, "promoted_subjects": {"P01": subjects}}
    brand_document = {"decisions": {}}
    for slot, (_, brand) in decisions.items():
        fields = by_brand[brand]
        def selected(prefix, fields=fields):
            return [k.split(":", 1)[1] for k, value in fields.items() if k.startswith(prefix + ":") and value is True]
        missing = fields["outcome"] == "context_missing"
        content["decisions"][slot] = {
            "outcome": fields["outcome"], "post_types": [] if missing else selected("type"),
            "audience_topics": ["unavailable"] if missing else selected("topic") or ["none"],
        }
        brand_document["decisions"][slot] = {
            "product_labels": ["none"] if missing else selected("product") or ["none"],
            "sentiment": "unknown" if missing else fields["sentiment"],
            "geopolitical_modes": ["unavailable"] if missing else selected("geo") or ["none"],
            "china_national_stance": "unknown" if missing else fields["china_national_stance"],
            "us_national_stance": "unknown" if missing else fields["us_national_stance"],
        }
    return contract, {"content": content, "brand_interpretation": brand_document}

def finish(case, prepared, raw_jev_document):
    state, targets = _state(case)
    matcher = _matcher(state)
    meta = prepared["metadata"]
    decoded, extra = _decode(raw_jev_document, prepared["request"])
    rows, extraction_errors = meta["extraction_rows"], meta["extraction_errors"]
    by_brand = {}
    errors = []
    invalid = [key for key, answer in decoded.items() if not answer["valid"]]
    if invalid:
        errors.append("invalid_jev_answers")
    if extra:
        errors.append("unexpected_jev_answers")
    if not meta["context_valid"]:
        errors.append("jev_context_overflow")
    for brand in targets:
        local = {key: decoded[actual] for key, actual in meta["question_map"][brand].items()}
        by_brand[brand] = combine(local, {**state, "target_brand": brand}, rows, extraction_errors, FIELDS)
    findings = meta.get("release_findings")
    selected_findings = []
    if meta.get("release_error"):
        errors.append(meta["release_error"])
    release_valid = (findings is not None and not meta.get("release_error") and meta["context_valid"]
                     and all(answer["valid"] for key, answer in decoded.items() if key.startswith("release:")))
    if findings is not None and not release_valid:
        errors.append("release_questions_invalid")
    if release_valid:
        for index, finding in enumerate(findings):
            prefix = f"release:{index}"
            novelty = decoded[prefix + ":novelty"]["assigned"]
            category = decoded[prefix + ":category"]["assigned"]
            if novelty == "nonrelease":
                continue
            issuer = finding.get("issuer_evidence")
            # An exact tie supplies no affirmative issuer evidence. Keep the
            # release itself; downstream ownership still needs account evidence.
            if issuer is not None and decoded[prefix + ":issuer_supported"]["p_yes"] <= 0.5:
                issuer = None
            family = finding.get("family_evidence")
            if family is not None and decoded[f"{prefix}:family_supported"]["p_yes"] <= 0.5:
                family = None
            lineage = [relation for relation_index, relation in enumerate(finding["lineage_evidence"])
                       if decoded[f"{prefix}:lineage:{relation_index}:supported"]["p_yes"] > 0.5]
            publishers = [brand for brand in targets if brand != "_unattributed" and issuer is not None
                          and decoded[f"{prefix}:publisher:{brand}"]["p_yes"] > 0.5]
            profile_key = f"{prefix}:profile_publisher_supported"
            profile = state.get("author_profile_evidence")
            selected_profile = None
            if (issuer is not None and not publishers and profile_key in decoded
                    and decoded[profile_key]["p_yes"] > 0.5):
                issuer = {**issuer, "observed_name": profile["display_name"].strip()}
                selected_profile = deepcopy(profile)
            selected = {**finding, "novelty": novelty, "issuer_evidence": issuer,
                        "lineage_evidence": lineage, "family_evidence": family,
                        "brand_id": publishers[0] if len(publishers) == 1 else None,
                        "category": None if category == "unknown" else category}
            if selected_profile is not None:
                selected["publisher_profile"] = selected_profile
            selected_findings.append(selected)
            for brand in targets:
                if brand != "_unattributed" and decoded[prefix + ":concerns:" + brand]["assigned"] is not True:
                    continue
                fields = by_brand[brand]
                local = {key: decoded[actual] for key, actual in meta["question_map"][brand].items()}
                if brand != "_unattributed" and any(local[key].get("p_yes", 0) >= .5 for key in ("identity_namesake_only", "identity_keyword_only", "identity_word_only")):
                    errors.append("release_brand_identity_disagreement")
                    continue
                fields["type:releases_updates"] = True
                fields["type:other"] = False
                fields["outcome"] = "classified"
                if fields["sentiment"] == "unknown":
                    fields["sentiment"] = "neutral"
                if fields["geo:nationalism"] is False:
                    fields["china_national_stance"] = fields["us_national_stance"] = "none"
    frozen_flags = [[key for key in PROMOTION_KEYS if by_brand[brand]["promotion:" + key] is True] for brand in targets]
    if any(flags != frozen_flags[0] for flags in frozen_flags[1:]):
        errors.append("inconsistent_post_promotions_across_brands")
    promotions = frozen_flags[0]
    if any(by_brand[brand]["promotion:" + key] is None for brand in targets for key in PROMOTION_KEYS):
        errors.append("unresolved_post_promotion")
    assigned = lambda key: decoded[key]["assigned"] if decoded[key]["valid"] else None
    if assigned(meta["missing_subject_question"]) is not False:
        errors.append("unresolved_promoted_subject")
    subjects, evidence_records, specific = [], [], set()
    for binding in meta["bindings"]:
        q = binding["questions"]
        if assigned(q["pitch"]) is not True:
            continue
        source = next((s["text"] for s in sources(state) if s["id"] == binding["source"]), "")
        evidence = binding["evidence"]
        if (not evidence or source[binding["start"]:binding["end"]] != evidence
                or norm(binding["name"]) not in norm(evidence)):
            errors.append("unsupported_subject_evidence")
            continue
        subject = {"name": binding["name"], "handle": None, "domain": None,
                   "account_handle": None, "evidence": evidence}
        # Only an exact visible @handle used as the actual extracted name is
        # assigned; other handles/domains would require an unsupported linkage.
        if re.fullmatch(r"@[A-Za-z0-9_]{1,64}", binding["name"]):
            subject["handle"] = binding["name"].removeprefix("@")
        if matcher.match(subject):
            errors.append("promoted_subject_is_tracked")
            continue
        subjects.append(subject)
        flags = [key for key in PROMOTION_KEYS[1:] if assigned(q[key]) is True]
        specific.update(flags)
        evidence_records.append({**binding, "promotion_keys": flags or ["general"]})
    bound_promotions = [key for key in PROMOTION_KEYS[1:] if key in specific]
    if subjects and not bound_promotions:
        bound_promotions = ["general"]
    if promotions != bound_promotions:
        errors.append("post_flags_subject_binding_disagreement")
    if promotions and not subjects:
        errors.append("promoted_subject_missing")
    contract, role_documents = _role_documents(case, by_brand, promotions, subjects)
    parsed = {}
    for role, document in role_documents.items():
        try:
            parsed[role] = parser._two_role_parse_fixed_slots(document, contract, role, request_profile="deepseek_0731")
        except (ValueError, TypeError, KeyError):
            parsed[role] = {}
        if str(case["case_id"]) not in parsed[role]:
            errors.append(role + "_parser_rejected")
    canonical = None
    if all(str(case["case_id"]) in parsed[role] for role in parsed):
        merged = [{"brand_id": brand, **parsed["content"][str(case["case_id"])]["by_brand"][brand],
                   **parsed["brand_interpretation"][str(case["case_id"])]["by_brand"][brand]} for brand in targets]
        canonical = parser.parse_stage1_v4_classifications(merged, targets)
        if canonical is None:
            errors.append("canonical_classification_rejected")
    errors = list(dict.fromkeys(errors))
    publication = {"by_brand": canonical or {}, "untracked_brand_promotions": promotions,
                   "promoted_subjects": subjects, "valid": not errors}
    if release_valid:
        publication["release_findings"] = tuple(selected_findings)
        publication["release_findings_version"] = SCHEMA
        publication["release_independent_valid"] = True
    return {"by_brand_fields": by_brand, "post_promotions": promotions, "promoted_subjects": subjects,
            "bound_post_promotions": bound_promotions, "bound_evidence": evidence_records,
            "extraction_rows": rows, "extraction_errors": extraction_errors,
            "contract_valid": not errors, "contract_errors": errors, "decoded": decoded,
            "invalid_answer_ids": invalid, "extra_answer_ids": extra,
            "parsed_roles": parsed, "role_documents": role_documents, "publication_result": publication}

def run_case(case, call, *, release_channels=None, max_tokens=parser.CLASSIFIER_MAX_TOKENS):
    """call(provider, request, stage) owns accounting and transport; never retry."""
    request = make_extraction_request(case, release_channels=release_channels, max_tokens=max_tokens)
    return _run_prepared_case(case, request, call, release_channels=release_channels)


def _run_prepared_case(case, request, call, *, release_channels):
    extraction = call("ds", request, "extraction")
    prepared = build_jev(case, extraction, release_channels=release_channels)
    if not prepared["metadata"]["context_valid"] or prepared["metadata"]["release_error"]:
        result = finish(case, prepared, {})
        result["request_stages"] = ["extraction"]
        return result
    result = finish(case, prepared, call("jev", prepared["request"], "classification"))
    result["request_stages"] = ["extraction", "classification"]
    return result


def _case_for_tweet(tweet, catalog):
    """Use the saved post packet and one batch catalog; no further lookup."""
    state = {
        "source_text": tweet.get("text") or "",
        "english_translation": tweet.get("english_translation") or "",
        "context": tweet.get("context") or [],
        "source_language": tweet.get("source_language") or "",
        "author_handle": tweet.get("author_handle"),
        "author_affiliations": tweet.get("affiliations") or [],
        "author_profile_evidence": tweet.get("author_profile_evidence"),
        "target_brand": tweet["brand_ids"][0],
    }

    def normalize(value):
        return re.sub(r"[^\w]", "", str(value).casefold())

    context = state["context"]
    texts = list(context.values()) if isinstance(context, dict) else [r.get("text", "") for r in context if isinstance(r, dict)]
    visible = normalize(state["source_text"] + " " + " ".join(str(text) for text in texts))
    state["tracked_brands"] = [
        {**entry, "aliases": sorted({v.strip() for v in entry.get("aliases", []) if v and v.strip()}),
         "source_matched_product_candidates": sorted({value for value in entry.get("products", [])
             if value and len(normalize(value)) >= 4 and normalize(value) in visible})}
        for entry in catalog["brands"]
    ]
    return {"case_id": str(tweet["tweet_id"]), "target_brands": list(tweet["brand_ids"]),
            "state": state, "source": {"created_at": tweet.get("created_at")}}


def classify_batch(tweets, brand_registry, client, *, max_tokens, on_batch_error=None, deadline=None,
                   max_workers=3, telemetry_context=None, tracked_catalog_snapshot=None):
    """The shared entry point's selected route: one extraction/Jev pair per post.

    The same wrapper reserves and accounts for every physical attempt. It does
    not run the former batched role calls or a release-only detection call.
    """
    try:
        catalog = (parser._validated_tracked_brand_catalog_snapshot(tracked_catalog_snapshot)
                   if tracked_catalog_snapshot is not None else parser._tracked_brand_catalog(brand_registry, tweets))
        channels = tuple(client.release_channels)
    except (TypeError, ValueError, AttributeError) as exc:
        if on_batch_error:
            on_batch_error(tweets, exc)
        return [parser._stage1_empty() for _ in tweets]
    registry = {brand.brand_id for brand in brand_registry} if brand_registry else None

    def classify(tweet):
        pair = (None, None)
        try:
            targets = tweet.get("brand_ids") or []
            if not targets or (registry is not None and not set(targets) <= registry):
                return parser._stage1_empty()
            case = _case_for_tweet(tweet, catalog)
            tweet["_classification_pipeline"] = PROFILE
            tweet["_classification_channels"] = channels
            tweet["_classification_matcher_revision"] = _matcher(case["state"]).revision
            fingerprint = parser._two_role_fingerprint(tweet, tracked_catalog=catalog)
            first = make_extraction_request(case, release_channels=channels, max_tokens=max_tokens)
            second_bound = {"model": MODEL, "max_tokens": 1, "messages": [{"role": "user", "content": json.dumps({
                "model": MODEL, "state": "", "questions": {"bound": {"type": "noul"}},
            })}]}
            reserve = getattr(client, "reserve_pair", None)
            if callable(reserve):
                options = {"request_bounds": [first, second_bound]} if getattr(client, "requires_pair_bounds", False) else {}
                pair = reserve(attempts_per_role=parser._MAX_RETRIES, **options)
                if pair is None:
                    raise parser.LLMCallBudgetExhausted("classifier_pair_budget_exhausted")
            elif getattr(client, "remaining_calls", None) is not None and client.remaining_calls < 2:
                raise parser.LLMCallBudgetExhausted("classifier_pair_budget_exhausted")

            def call(provider, request, stage):
                if provider == "ds":
                    system = request["messages"][0]["content"]
                    prompt = request["messages"][1]["content"]
                    model, output, reservation = DEEPSEEK_0731_MODEL, request["max_tokens"], pair[0]
                else:
                    system, prompt = None, json.dumps(request, ensure_ascii=False, separators=(",", ":"))
                    model, output, reservation = MODEL, 1, pair[1]
                return parser._call_signal_with_retry(
                    client, prompt, system=system, model=model, max_tokens=output, deadline=deadline,
                    transport_reservation=reservation,
                    telemetry_context={**(telemetry_context or {}), "stage": "classification." + stage,
                                       "batch_key": fingerprint[:16] + ":" + stage, "batch_size": 1,
                                       "request_identity": str(getattr(client, "request_identity", PROFILE)) + ":" + stage},
                    batch_context={"post_ids": [case["case_id"]], "stage": "classification", "role": stage,
                                   "input_fingerprints": {case["case_id"]: fingerprint}},
                )

            output = _run_prepared_case(case, first, call, release_channels=channels)
            if not output["contract_valid"]:
                partial = output["publication_result"]
                if partial.get("release_independent_valid"):
                    return {"valid": False, "release_only": True,
                            "release_findings": partial["release_findings"],
                            "release_findings_version": partial["release_findings_version"],
                            "classification_model": COMBINED_MODEL}
                raise ValueError("classification_compressed_invalid:" + ",".join(output["contract_errors"]))
            result = output["publication_result"]
            result["classification_model"] = COMBINED_MODEL
            result["classification_trace"] = parser._two_role_trace(
                content=output["parsed_roles"]["content"][case["case_id"]],
                brand=output["parsed_roles"]["brand_interpretation"][case["case_id"]],
                final=result["by_brand"], fingerprint=fingerprint, model=COMBINED_MODEL,
                request_identity=getattr(client, "request_identity", None), request_profile=PROFILE,
            )
            return result
        except Exception as exc:  # noqa: BLE001 - One failed post remains pending; sibling posts continue.
            if on_batch_error:
                on_batch_error([tweet], exc)
            return parser._stage1_empty()
        finally:
            release = getattr(client, "release_reservations", None)
            if callable(release) and pair is not None:
                release(*pair)

    with ThreadPoolExecutor(max_workers=min(max(1, max_workers), len(tweets))) as executor:
        return list(executor.map(classify, tweets))
