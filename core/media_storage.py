"""Private R2 storage shared by staff originals and editorial derivatives."""

import re

from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from storages.backends.s3 import S3Storage
from storages.utils import clean_name

MAX_URL_SECONDS = 300


class PrivateR2Storage(S3Storage):
    """Use project-specific credentials and bounded, uncached download links."""

    def get_default_settings(self):
        account = getattr(settings, "R2_ACCOUNT_ID", "")
        return {
            **super().get_default_settings(),
            "access_key": getattr(settings, "R2_ACCESS_KEY_ID", ""),
            "secret_key": getattr(settings, "R2_SECRET_ACCESS_KEY", ""),
            "security_token": None,
            "session_profile": None,
            "bucket_name": "",
            "location": "",
            "endpoint_url": f"https://{account}.r2.cloudflarestorage.com",
            "region_name": "auto",
            "signature_version": "s3v4",
            "addressing_style": "path",
            "use_ssl": True,
            "verify": True,
            "custom_domain": None,
            "cloudfront_key": None,
            "cloudfront_key_id": None,
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": MAX_URL_SECONDS,
            "file_overwrite": True,
            "object_parameters": {"CacheControl": "private, no-store"},
            "max_memory_size": 2 * 1024 * 1024,
            "gzip": False,
            "client_config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=30,
                retries={"mode": "standard", "total_max_attempts": 3},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        }

    def __init__(self, **options):
        for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            if not getattr(settings, name, ""):
                raise ImproperlyConfigured(f"{name} is required for R2 media storage")
        if not re.fullmatch(r"[a-fA-F0-9]{32}", settings.R2_ACCOUNT_ID):
            raise ImproperlyConfigured("R2_ACCOUNT_ID must be a Cloudflare account ID")
        super().__init__(**options)
        if (
            self.access_key != settings.R2_ACCESS_KEY_ID
            or self.secret_key != settings.R2_SECRET_ACCESS_KEY
            or self.security_token
            or self.session_profile
        ):
            raise ImproperlyConfigured(
                "R2 media must use the configured R2 credentials"
            )
        expected_endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        if (
            not self.bucket_name
            or self.endpoint_url != expected_endpoint
            or not self.querystring_auth
            or self.custom_domain
            or self.default_acl is not None
            or "ACL" in self.object_parameters
            or self.verify is False
            or not self.use_ssl
            or self.signature_version != "s3v4"
            or not isinstance(self.querystring_expire, int)
            or not 0 < self.querystring_expire <= MAX_URL_SECONDS
        ):
            raise ImproperlyConfigured(
                "R2 media requires a bucket and private HTTPS delivery"
            )
        self.object_parameters = {
            **self.object_parameters,
            "CacheControl": "private, no-store",
        }

    def save_if_absent(self, name, data, *, content_type):
        """Atomically create a migration object; never replace a concurrent write."""
        key = self._normalize_name(clean_name(name))
        try:
            self.connection.meta.client.put_object(
                **{
                    **self.get_object_parameters(name),
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "Body": data,
                    "ContentLength": len(data),
                    "ContentType": content_type,
                    "IfNoneMatch": "*",
                }
            )
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412:
                return False
            raise
        return True

    def url(self, name, parameters=None, expire=None, http_method=None):
        lifetime = self.querystring_expire if expire is None else expire
        if not isinstance(lifetime, int) or not 0 < lifetime <= MAX_URL_SECONDS:
            raise ValueError("R2 media URLs must expire within 300 seconds")
        return super().url(
            name,
            parameters={
                **(parameters or {}),
                "ResponseCacheControl": "private, no-store",
            },
            expire=lifetime,
            http_method=http_method,
        )
