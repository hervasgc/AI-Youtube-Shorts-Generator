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

    client = storage.Client()
    bucket = client.bucket(GCS_OUTPUT_BUCKET)
    blob = bucket.blob(dest_name)
    blob.upload_from_filename(local_path)

    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=GCS_SIGNED_URL_EXPIRY_SECONDS),
        method="GET",
    )
