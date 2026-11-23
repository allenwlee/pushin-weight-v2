"""Read a role only where the source binds the subject, title and employer."""

import re

KNOWN_TITLES = (
    r"chief executive officer|co-founder and CEO|co-founder|founder|CEO|CTO|"
    r"chief scientist|research scientist|researcher|engineer|president|director"
)
_HAN = r"[\u3400-\u9fff]"
_NEGATED = re.compile(
    r"\b(?:not|never|neither|isn['’]t|wasn['’]t)(?:\s+(?:the|a|an))?\s*$"
    r"|\b(?:den(?:y|ies|ied)|disput(?:es?|ed)|false|untrue)\s+(?:that\s+)?$"
    r"|(?:并非|並非|不是|并不是|未曾|否认|否認)\s*$",
    re.IGNORECASE,
)
_OTHER_ROLE_HOLDER = re.compile(
    r"(?:[,，]|\b(?:is|was|became|serves as|served as|works as|worked as))\s*(?:(?:the|an?)\s+)?$",
    re.IGNORECASE,
)
_FOLLOWING_NAME = re.compile(r"\s+[A-Z][\w’'-]*\s+[A-Z][\w’'-]*")
_ARTICLE = r"(?:(?:the|an?)\s+)?"
_PREP = r"\s+(?:of|at|for|with|@)\s+"


def phrase(value):
    return rf"(?<!\w){re.escape(value)}(?!\w)"


def named_employers(subject, passage):
    """Read explicitly named employers even when the catalog has no entry yet."""
    name = phrase(subject)
    org_word = r"[A-Z][\w&-]*"
    org = rf"(?P<org>{org_word}(?:[ \t]+{org_word}){{0,3}})"
    title = rf"(?i:{KNOWN_TITLES})"
    patterns = (
        rf"(?<!\w){org}(?:['’]s)?[ \t]+{title}[ \t]+(?i:{name})",
        rf"(?i:{name}),[ \t]+(?:(?i:the|a|an)[ \t]+)?{title}(?i:{_PREP}){org}",
    )
    return {m['org'] for pattern in patterns for m in re.finditer(pattern, passage)}


def sourced_role(
    subject, organization, passage, title=None, *, own_profile=False, quote=None
):
    """Use literal spellings and grammatical links, including localized source claims."""
    if not (subject and organization and passage):
        return None
    spans = None
    if quote is not None:
        spans = [match.span() for match in re.finditer(re.escape(quote), passage)]
        if not spans:
            return None
    # A biography can place its bilingual spelling between the name and the verb.
    alias = (
        r"(?:\s*[(（]\s*(?:[\u3400-\u9fff·]{2,16}|[A-Za-z][A-Za-z .'-]{1,60})\s*[)）])?"
    )
    name, org = phrase(subject) + alias, phrase(organization)
    titles = re.escape(title) if title else KNOWN_TITLES
    role = rf"(?P<former>former\s+|ex[- ])?(?P<title>{titles})"
    org_role = rf"{org}(?:['’]s)?\s+{role}"
    role_org = rf"{role}{_PREP}{org}"
    patterns = [
        rf"{name}(?:,?\s+(?P<verb>is|was|serves as|served as|works as|worked as)\s+{_ARTICLE}|,\s*{_ARTICLE}|\s+\(){role_org}",
        rf"(?P<before_name>{role_org}),?\s+{name}",
        rf"{org_role}\s+{name}",
        rf"(?P<apposition>{name},\s*{org_role})",
        rf"{name}\s+(?P<verb>works at|worked at)\s+{org}\s+as\s+{_ARTICLE}{role}(?!\w)",
    ]
    if title and re.search(_HAN, passage):
        # Chinese titles may directly adjoin the subject or employer. Python's
        # word boundary would also treat the neighboring Chinese verb as a letter.
        cn_name, cn_org = re.escape(subject) + alias, re.escape(organization)
        cn_role = rf"(?P<title>{re.escape(title)})"
        cn_status = r"(?P<former>曾任|曾担任|曾擔任|原任|前任|原|前)?"
        patterns.extend(
            (
                rf"{cn_name}\s*[，,：:]?\s*{cn_status}(?:现任|現任|现为|現為|担任|擔任|任职于|任職於|是|为|為|任)?\s*{cn_org}\s*的?\s*{cn_role}",
                rf"{cn_org}\s*的?\s*{cn_status}{cn_role}\s*[：:]?\s*{cn_name}",
                rf"{cn_name}\s*(?P<former>曾经|曾經|曾)?(?:目前|现在|現在)?在\s*{cn_org}\s*(?:担任|擔任|任)\s*{cn_role}",
            )
        )
    if own_profile:
        # An employer/title fragment or explicit first person can stand alone on
        # the subject's own profile. A quoted or named colleague cannot fill it.
        bio = r"(?:I\s+(?P<verb>am|was|work as|worked as)|I['’]m)\s+"
        for expression in (role_org, org_role):
            patterns.append(
                rf"(?:^|[\n|;])\s*(?:{bio})?{_ARTICLE}{expression}\s*(?=$|[.!?\n|;])"
            )
    for pattern in patterns:
        for match in re.finditer(pattern, passage, re.IGNORECASE):
            if spans is not None and not any(
                start <= match.start() and match.end() <= end for start, end in spans
            ):
                continue
            before = passage[: match.start()]
            fields = match.groupdict()
            if _NEGATED.search(before):
                continue
            if fields.get("before_name") and _OTHER_ROLE_HOLDER.search(before):
                continue
            if fields.get("apposition") and _FOLLOWING_NAME.match(passage, match.end()):
                continue
            former = (
                fields.get("former")
                or (fields.get("verb") or "").lower()
                in {"was", "served as", "worked as", "worked at"}
                or re.search(r"\b(?:former|ex)[ -]+$", before, re.IGNORECASE)
            )
            return {
                "organization": organization,
                "title": fields["title"],
                "status": "former" if former else "current",
            }
    return None


def grounded_role(subject, organization, title, status, quote, source):
    """Ground the model's verbatim excerpt in its context, including negation."""
    if not (quote and title and organization):
        return False
    parsed = sourced_role(subject, organization, source, title, quote=quote)
    return bool(parsed and status in {"unknown", parsed["status"]})
