"""Optional GCS persistence for local-mode output clips.

Cloud Run's filesystem is ephemeral, so when GCS_OUTPUT_BUCKET is set the
rendered mp4s are uploaded to that bucket and served back as short-lived
signed URLs instead of local paths. Signing uses the runtime service
account's IAM signBlob permission (roles/iam.serviceAccountTokenCreator on
itself) — no private key file needed on Cloud Run.
"""
import datetime

from ..config import GCS_OUTPUT_BUCKET, GCS_SIGNED_URL_EXPIRY_SECONDS


def upload_and_sign(local_path: str, dest_name: str) -> str:
    from google.cloud import storage
    from google.auth.iam import Signer
    from google.auth.transport.requests import Request
    import google.auth

    credentials, project = google.auth.default()

    if not hasattr(credentials, 'service_account_email'):
        raise ValueError("Credentials must have a service_account_email (use service account credentials)")

    signer = Signer(Request(), credentials.service_account_email)

    client = storage.Client()
    bucket = client.bucket(GCS_OUTPUT_BUCKET)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(local_path)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=GCS_SIGNED_URL_EXPIRY_SECONDS),
        method="GET",
        signing_credentials=signer,
    )


def generate_upload_url(dest_name: str, expiry_seconds: int = 1800) -> str:
    """Signed PUT URL so the browser can upload straight to GCS, bypassing
    Cloud Run's ~32MB request body limit entirely.

    On Cloud Run, uses IAM signBlob API via iam.Signer to sign without
    requiring a private key file.
    """
    from google.cloud import storage
    from google.auth.iam import Signer
    from google.auth.transport.requests import Request
    import google.auth

    credentials, project = google.auth.default()

    if not hasattr(credentials, 'service_account_email'):
        raise ValueError("Credentials must have a service_account_email (use service account credentials)")

    # iam.Signer uses IAM signBlob API to sign (no private key needed on Cloud Run)
    signer = Signer(Request(), credentials.service_account_email)

    client = storage.Client()
    bucket = client.bucket(GCS_OUTPUT_BUCKET)
    blob = bucket.blob(dest_name)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=expiry_seconds),
        method="PUT",
        signing_credentials=signer,
    )


def download_to_file(dest_name: str, local_path: str) -> str:
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_OUTPUT_BUCKET)
    bucket.blob(dest_name).download_to_filename(local_path)
    return local_path
