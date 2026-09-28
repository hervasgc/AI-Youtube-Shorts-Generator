"""Optional GCS persistence for output clips.

When GCS_OUTPUT_BUCKET is set, renders are uploaded and served via signed URLs.
"""
import datetime
import os

from ..config import GCS_OUTPUT_BUCKET, GCS_SIGNED_URL_EXPIRY_SECONDS


def _signing_kwargs() -> dict:
    """Credentials needed by Blob.generate_signed_url() when running without a
    private key (Cloud Run/GCE service account credentials).

    google-cloud-storage signs the URL itself via the IAM signBlob API as long
    as it's given the signer's email + a valid access token — no need to
    construct a google.auth.iam.Signer by hand. The runtime service account
    needs roles/iam.serviceAccountTokenCreator on itself for this to work
    (already granted, see PROJECT_CONTEXT.md).
    """
    from google.auth import default
    from google.auth.transport.requests import Request

    credentials, _ = default()
    credentials.refresh(Request())

    service_account_email = getattr(credentials, "service_account_email", None)
    if not service_account_email or service_account_email == "default":
        service_account_email = os.getenv("GOOGLE_CLOUD_SERVICE_ACCOUNT_EMAIL", "")

    if not service_account_email:
        # User/local ADC (e.g. `gcloud auth application-default login`) already
        # carries a private key that generate_signed_url() can use directly.
        return {}

    return {
        "service_account_email": service_account_email,
        "access_token": credentials.token,
    }


def generate_gcs_upload_url(bucket_name: str, blob_name: str, max_size_bytes: int = 200 * 1024 * 1024) -> str:
    """Generate a signed URL for uploading a file directly to GCS via PUT (from browser/client).

    This bypasses the Cloud Run 32MB request body limit by allowing the client
    (e.g., JavaScript in the browser) to upload directly to GCS.
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=GCS_SIGNED_URL_EXPIRY_SECONDS),
        method="PUT",
        **_signing_kwargs(),
    )


def upload_and_sign(local_path: str, dest_name: str) -> str:
    """Upload a local file to GCS and return a short-lived signed URL."""
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_OUTPUT_BUCKET)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(local_path)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=GCS_SIGNED_URL_EXPIRY_SECONDS),
        method="GET",
        **_signing_kwargs(),
    )
