"""Optional GCS persistence for output clips.

When GCS_OUTPUT_BUCKET is set, renders are uploaded and served via signed URLs.
"""
import datetime

from ..config import GCS_OUTPUT_BUCKET, GCS_SIGNED_URL_EXPIRY_SECONDS


def generate_gcs_upload_url(bucket_name: str, blob_name: str, max_size_bytes: int = 500*1024*1024) -> str:
    """Generate a signed URL for uploading a file directly to GCS via PUT (from browser/client).

    This bypasses the Cloud Run 32MB request body limit by allowing the client
    (e.g., JavaScript in the browser) to upload directly to GCS.
    """
    from google.cloud import storage
    from google.auth.transport.requests import Request
    from google.auth import default
    from google.auth.iam import Signer

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Get credentials and service account email
    credentials, project = default()

    # For Cloud Run: use IAM Signer since Compute Engine credentials don't have private key
    if hasattr(credentials, 'service_account_email'):
        service_account_email = credentials.service_account_email
    else:
        # Fallback: use the service account from the environment
        import os
        service_account_email = os.getenv(
            "GOOGLE_CLOUD_SERVICE_ACCOUNT_EMAIL",
            "github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com"
        )

    # Create an IAM signer
    iam_signer = Signer(Request(), service_account_email)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=GCS_SIGNED_URL_EXPIRY_SECONDS),
        method="PUT",
        signer=iam_signer,
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
    )
