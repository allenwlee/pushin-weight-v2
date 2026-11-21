"""Durable search circuit shared between scheduled and on-demand processes."""
import hashlib
import re
import threading
from datetime import timedelta
from uuid import uuid4

from django.db import transaction

from core.models import SearchProviderCircuit as CircuitRow


class SearchProviderCircuit:
    def __init__(self, purpose, *, threshold=2, cooldown=180, probe_lease=60):
        self.purpose = purpose
        self.threshold = max(1, threshold)
        self.cooldown = cooldown
        self.probe_lease = probe_lease
        self.probe_claimed = False
        self._probe_local = threading.local()
        self._fallback_local = threading.local()

    def _locked_row(self):
        CircuitRow.objects.get_or_create(purpose=self.purpose)
        return CircuitRow.objects.select_for_update().get(purpose=self.purpose)

    def primary_permitted(self, now):
        with transaction.atomic():
            row = self._locked_row()
            if row.open_until is None:
                return True
            if row.open_until > now or (row.probe_lease_until and row.probe_lease_until > now):
                return False
            row.probe_lease_until = now + timedelta(seconds=self.probe_lease)
            row.probe_owner = uuid4()
            row.save(update_fields=["probe_lease_until", "probe_owner", "updated_at"])
            self._probe_local.owner = row.probe_owner
            self.probe_claimed = True
            return True

    def is_probe(self):
        return bool(getattr(self._probe_local, "owner", None))

    def record_failure(self, now):
        with transaction.atomic():
            row = self._locked_row()
            owner = getattr(self._probe_local, "owner", None)
            if row.open_until is not None and (owner is None or owner != row.probe_owner):
                return
            row.consecutive_failures += 1
            if row.consecutive_failures >= self.threshold:
                row.open_until = now + timedelta(seconds=self.cooldown)
                row.probe_lease_until = None
                row.probe_owner = None
            row.save(update_fields=["consecutive_failures", "open_until", "probe_lease_until", "probe_owner", "updated_at"])
            self.probe_claimed = False
            self._probe_local.owner = None

    def record_success(self, now):
        with transaction.atomic():
            row = self._locked_row()
            owner = getattr(self._probe_local, "owner", None)
            if row.open_until is not None and (owner is None or owner != row.probe_owner):
                return
            row.consecutive_failures = 0
            row.open_until = None
            row.probe_lease_until = None
            row.probe_owner = None
            row.save(update_fields=["consecutive_failures", "open_until", "probe_lease_until", "probe_owner", "updated_at"])
            self.probe_claimed = False
            self._probe_local.owner = None

    def acquire_fallback(self, now, lease_seconds):
        with transaction.atomic():
            CircuitRow.objects.get_or_create(purpose="twexapi-global-pacing")
            row = CircuitRow.objects.select_for_update().get(purpose="twexapi-global-pacing")
            if row.fallback_lease_until and row.fallback_lease_until > now:
                return (row.fallback_lease_until - now).total_seconds()
            if row.next_fallback_request_at and row.next_fallback_request_at > now:
                return (row.next_fallback_request_at - now).total_seconds()
            self._fallback_local.owner = uuid4()
            row.fallback_owner = self._fallback_local.owner
            row.fallback_lease_until = now + timedelta(seconds=lease_seconds)
            row.save(update_fields=["fallback_owner", "fallback_lease_until", "updated_at"])
            return 0

    def release_fallback(self, now, interval):
        with transaction.atomic():
            row = CircuitRow.objects.select_for_update().get(purpose="twexapi-global-pacing")
            if row.fallback_owner != getattr(self._fallback_local, "owner", None):
                return
            row.fallback_owner = None
            row.fallback_lease_until = None
            row.next_fallback_request_at = now + timedelta(seconds=interval)
            row.save(update_fields=["fallback_owner", "fallback_lease_until", "next_fallback_request_at", "updated_at"])

    def fallback_owned(self, now):
        return CircuitRow.objects.filter(purpose="twexapi-global-pacing", fallback_owner=getattr(self._fallback_local, "owner", None),
                                         fallback_lease_until__gt=now).exists()

    def observe_query(self, query, *, nonempty, now, minimum=3, within_seconds=2700):
        base = re.sub(r"\s+(?:since_time|until_time):\d+", "", query).strip()
        key = "q:" + hashlib.sha256(base.encode()).hexdigest()[:28]
        with transaction.atomic():
            CircuitRow.objects.get_or_create(purpose=key)
            row = CircuitRow.objects.select_for_update().get(purpose=key)
            expected = bool(row.observed_nonempty_streak >= minimum and row.last_nonempty_at
                            and row.last_nonempty_at >= now - timedelta(seconds=within_seconds))
            if nonempty:
                row.observed_nonempty_streak = min(row.observed_nonempty_streak + 1, minimum)
                row.last_nonempty_at = now
            elif not expected:
                row.observed_nonempty_streak = 0
            row.save(update_fields=["observed_nonempty_streak", "last_nonempty_at", "updated_at"])
            return expected
