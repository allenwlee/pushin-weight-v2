"""Collect public TwitterAPI.io announcements independently of harvest."""
import json
import re
import time
from datetime import timedelta
from html.parser import HTMLParser

import requests
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.collection_capture import begin_request, finish_request
from core.collection_jobs import register_job, set_job_state
from core.collection_scheduling import schedule_slot
from core.collection_state import claim_job, fenced_run, finish_run
from core.models import CollectionJob, CollectionRequest, CollectionRun, DataSource

PREVIEW = "https://t.me/s/twitterapiio"
MAX_BYTES = 512 * 1024
OPERATION = "provider_announcements"


def _now():
    return timezone.now()


class _PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.messages = {}
        self.depth = 0
        self.message_depth = self.text_depth = None
        self.message = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "div":
            self.depth += 1
            match = re.fullmatch(r"twitterapiio/([0-9]{1,20})", attrs.get("data-post", ""))
            if self.message is None and match and "tgme_widget_message" in classes:
                identity = match[1]
                self.message = {"id": identity, "url": f"https://t.me/twitterapiio/{identity}"}
                self.message_depth = self.depth
                self.parts = []
            if self.message is not None and "tgme_widget_message_text" in classes:
                self.text_depth = self.depth
        elif tag == "br" and self.text_depth is not None:
            self.parts.append("\n")
        elif tag == "time" and self.message is not None and "datetime" in attrs:
            stamp = parse_datetime(attrs["datetime"])
            if stamp is not None and timezone.is_aware(stamp):
                key = "edited_at" if "edited" in classes else "published_at"
                self.message.setdefault(key, attrs["datetime"])

    def handle_endtag(self, tag):
        if tag != "div":
            return
        if self.depth == self.text_depth:
            self.text_depth = None
        if self.depth == self.message_depth:
            text = "".join(self.parts).strip()
            if text and self.message.get("published_at"):
                self.message["text"] = text
                self.messages[self.message["id"]] = self.message
            self.message_depth = self.message = None
        self.depth = max(self.depth - 1, 0)

    def handle_data(self, data):
        if self.text_depth is not None:
            self.parts.append(data)


def parse_preview(html):
    parser = _PreviewParser()
    parser.feed(html)
    parser.close()
    if not parser.messages:
        raise ValueError("Telegram preview contains no timestamped announcements")
    return sorted(parser.messages.values(), key=lambda message: int(message["id"]))


def fetch_preview():
    started = time.monotonic()
    with requests.get(PREVIEW, stream=True, timeout=(5, 8), allow_redirects=False) as response:
        if response.status_code != 200:
            raise requests.HTTPError(response=response)
        body = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            body.extend(chunk)
            if time.monotonic() - started > 15 or len(body) > MAX_BYTES:
                raise ValueError("Telegram preview exceeded a response limit")
        return bytes(body)


@transaction.atomic
def _claim(interval):
    source = DataSource.objects.select_for_update().get(pk="twitterapi")
    job_key = f"twitterapi:telegram-announcements:{interval}"
    existing = CollectionJob.objects.select_for_update().filter(job_key=job_key).first()
    job = existing or register_job(
        job_key=job_key, source=source,
        purpose="content", operation=OPERATION, mode="recurring",
        definition={"version": 2, "options": {}},
        settings={
            "owner_kind": "source", "schedule_kind": "interval", "schedule_driver": "external_render_cron",
            "interval_seconds": interval, "max_requests": 1, "max_items": 50,
            "max_seconds": 30, "max_bytes": MAX_BYTES,
        },
    )
    if existing is None:
        job = set_job_state(job.pk, "ready")
    if job.state != "ready":
        return None, "paused"
    job = CollectionJob.objects.select_for_update().get(pk=job.pk)
    now = _now()
    slot, next_slot = schedule_slot(job, now)
    if job.last_attempt_id and job.last_attempt.scheduled_slot_at == slot:
        return None, "already_polled"
    return claim_job(
        job.pk, invocation_id=f"telegram-preview:{slot.isoformat()}",
        manual_authorized=True, typed=True, now=now,
    ), next_slot


def _previous_messages():
    archive = (
        CollectionRequest.objects.filter(
            attempt__run__job__operation=OPERATION, attempt__run__status="success",
            archive__isnull=False,
        ).order_by("-started_at", "-pk").values_list("archive__body", flat=True).first()
    )
    return {message["id"]: message for message in json.loads(bytes(archive))} if archive else {}


def poll(interval):
    claim, next_slot = _claim(interval)
    if claim is None:
        return {"status": next_slot, "announcements": []}
    previous = _previous_messages()
    with fenced_run(claim) as (_, run):
        scope = run.scopes.get(scope_key="execution")
        request = begin_request(run.attempts.get(pk=claim.attempt_id), scope, endpoint_url=PREVIEW)
    status = error = None
    size = None
    messages = []
    outcome = "received"
    try:
        page = fetch_preview()
        size = len(page)
        status = 200
        messages = parse_preview(page.decode("utf-8"))
    except requests.Timeout:
        outcome, error = "timeout", "telegram_timeout"
    except requests.HTTPError as exc:
        status = exc.response.status_code
        error = "telegram_http_error"
    except requests.RequestException:
        outcome, error = "transport_error", "telegram_transport_error"
    except (ValueError, UnicodeError):
        outcome = "received" if status else "transport_error"
        error = "telegram_preview_invalid"
    archive_body = json.dumps(messages, sort_keys=True, ensure_ascii=False).encode() if messages else None
    with fenced_run(claim):
        finish_request(
            request, outcome=outcome, body=archive_body, http_status=status, error_code=error,
            response_bytes=size, returned_count=len(messages) if messages else None,
            body_encoding="selected-json-canonical-v1",
        )
        run = finish_run(
            claim, typed=True, status="failed" if error else "success", request_count=1,
            physical_accounting_complete=outcome == "received", error_code=error, next_due_at=next_slot,
            selected_count=len(messages), success_count=len(messages),
        )
    return {
        "status": "unavailable" if error else "ok", "error": error,
        "observed_at": run.completed_at.isoformat(),
        "announcements": [message for message in messages if previous.get(message["id"]) != message],
    }


def poll_status(interval):
    runs = CollectionRun.objects.filter(job__operation=OPERATION)
    latest = runs.filter(completed_at__isnull=False).order_by("-completed_at").first()
    last_ok = runs.filter(status="success").order_by("-completed_at").first()
    unavailable = (
        latest is None or latest.status != "success" or last_ok is None
        or _now() - last_ok.completed_at > timedelta(seconds=2 * interval)
    )
    return {
        "in_progress": runs.filter(status="running", lease_expires_at__gt=_now()).exists(),
        "status": "unavailable" if unavailable else "ok",
        "last_success_at": last_ok.completed_at.isoformat() if last_ok else None,
        "latest_error": latest.error_code if latest else None,
    }
