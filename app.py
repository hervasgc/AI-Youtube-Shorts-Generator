import streamlit as st
import os
import sys
import uuid
import json

# Ensure the app can import from shorts_generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shorts_generator import generate_shorts
from shorts_generator.config import LOCAL_OUTPUT_DIR, GCS_OUTPUT_BUCKET

st.set_page_config(
    page_title="AI YouTube Shorts Generator",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 AI YouTube Shorts Generator")
st.markdown("Transform long YouTube videos into viral-ready 9:16 shorts instantly.")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    mode = "local"

    num_clips = st.number_input(
        "Number of Clips",
        min_value=1,
        max_value=10,
        value=3,
        help="How many shorts to generate."
    )

    aspect_ratio = st.selectbox(
        "Aspect Ratio",
        ["9:16", "1:1", "16:9"],
        index=0,
        help="9:16 for TikTok/Reels, 1:1 for square."
    )


    language = st.text_input(
        "Language Override (Optional)",
        value="",
        placeholder="e.g. 'en', 'pt'",
        help="Force Whisper language code. Leave empty for auto-detect."
    )

st.divider()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
uploaded_file = None
uploaded_blob_name = None

# If GCS bucket is available, use direct-to-GCS upload
if GCS_OUTPUT_BUCKET:
    st.markdown("### 📤 Upload Video (Direct to Cloud Storage)")

    from shorts_generator.local.storage import generate_gcs_upload_url

    # A file already staged in GCS from a previous rerun (round-trip via
    # query param — components.v1.html runs in a sandboxed iframe and can't
    # write back into Python state any other way).
    uploaded_blob_name = st.query_params.get("uploaded_blob")

    if uploaded_blob_name:
        st.success(f"✅ Vídeo enviado: `{uploaded_blob_name.rsplit('/', 1)[-1]}`. Pronto para gerar os shorts.")
        if st.button("🔄 Enviar outro vídeo"):
            st.query_params.clear()
            st.rerun()
    else:
        # Generate a unique blob name for this upload
        upload_blob_name = f"uploads/sources/{uuid.uuid4().hex}.mp4"
        try:
            signed_url = generate_gcs_upload_url(GCS_OUTPUT_BUCKET, upload_blob_name, max_size_bytes=MAX_UPLOAD_BYTES)

            # HTML/JS component for direct GCS upload. On success it navigates
            # the parent page to include ?uploaded_blob=<name>, which Streamlit
            # picks up as a normal query param on the next rerun.
            upload_html = f"""
            <div id="upload-container">
                <input type="file" id="file-input" accept="video/*" />
                <button id="upload-btn" style="margin-top: 10px; padding: 10px 20px; background-color: #FF4B4B; color: white; border: none; border-radius: 5px; cursor: pointer;">
                    📤 Upload Video
                </button>
                <div id="progress" style="margin-top: 10px; display: none;">
                    <p id="status">Uploading...</p>
                    <div style="width: 100%; background-color: #e0e0e0; border-radius: 5px; overflow: hidden; height: 20px;">
                        <div id="progress-bar" style="height: 100%; background-color: #FF4B4B; width: 0%; transition: width 0.3s;"></div>
                    </div>
                    <p id="progress-text">0%</p>
                </div>
                <div id="success" style="margin-top: 10px; display: none; color: green;">
                    ✅ Upload complete! Reloading...
                </div>
                <div id="error" style="margin-top: 10px; display: none; color: red;"></div>
            </div>

            <script>
            const fileInput = document.getElementById('file-input');
            const uploadBtn = document.getElementById('upload-btn');
            const progressDiv = document.getElementById('progress');
            const statusText = document.getElementById('status');
            const successDiv = document.getElementById('success');
            const errorDiv = document.getElementById('error');
            const MAX_BYTES = {MAX_UPLOAD_BYTES};

            uploadBtn.addEventListener('click', async () => {{
                const file = fileInput.files[0];
                if (!file) {{
                    errorDiv.textContent = '❌ Please select a file first';
                    errorDiv.style.display = 'block';
                    return;
                }}
                if (file.size > MAX_BYTES) {{
                    errorDiv.textContent = `❌ File is ${{(file.size / 1024 / 1024).toFixed(0)}}MB, max allowed is 200MB`;
                    errorDiv.style.display = 'block';
                    return;
                }}

                uploadBtn.disabled = true;
                progressDiv.style.display = 'block';
                successDiv.style.display = 'none';
                errorDiv.style.display = 'none';

                try {{
                    const response = await fetch('{signed_url}', {{
                        method: 'PUT',
                        headers: {{'Content-Type': file.type}},
                        body: file
                    }});

                    if (!response.ok) {{
                        throw new Error(`Upload failed: ${{response.status}} ${{response.statusText}}`);
                    }}

                    progressDiv.style.display = 'none';
                    successDiv.style.display = 'block';

                    // Round-trip the blob name back to Streamlit via a full
                    // page navigation with a query param (same-origin iframe).
                    const target = window.parent;
                    const url = new URL(target.location.href);
                    url.searchParams.set('uploaded_blob', '{upload_blob_name}');
                    target.location.href = url.toString();
                }} catch (error) {{
                    errorDiv.textContent = '❌ ' + error.message;
                    errorDiv.style.display = 'block';
                    progressDiv.style.display = 'none';
                }} finally {{
                    uploadBtn.disabled = false;
                }}
            }});

            fileInput.addEventListener('change', () => {{
                if (fileInput.files[0]) {{
                    statusText.textContent = `Selected: ${{fileInput.files[0].name}}`;
                }}
            }});
            </script>
            """

            st.components.v1.html(upload_html, height=250)

        except Exception as e:
            st.error(f"Error generating upload URL: {e}")
            # Fallback to regular file uploader
            uploaded_file = st.file_uploader(
                "📤 Selecione o vídeo (fallback)",
                type=["mp4", "mov", "mkv", "webm", "m4v"],
            )
else:
    # Fallback: local file uploader when GCS not configured
    uploaded_file = st.file_uploader(
        "📤 Selecione o vídeo",
        type=["mp4", "mov", "mkv", "webm", "m4v"],
    )

if st.button("🚀 Generate Shorts", type="primary", use_container_width=True):
    has_file = False
    local_path = None

    # Check if file was uploaded via direct GCS or via file uploader
    if uploaded_blob_name:
        # File was uploaded directly to GCS via JavaScript
        has_file = True
        st.info(f"Using file from GCS: {uploaded_blob_name}")

        # Download from GCS to local temp file
        os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
        local_path = os.path.join(LOCAL_OUTPUT_DIR, f"gcs_download_{uuid.uuid4().hex}.mp4")

        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(GCS_OUTPUT_BUCKET)
            blob = bucket.blob(uploaded_blob_name)
            blob.download_to_filename(local_path)
            st.success("Downloaded from GCS")
        except Exception as e:
            st.error(f"Failed to download from GCS: {e}")
            has_file = False

    elif uploaded_file:
        # File was uploaded via regular Streamlit file uploader
        has_file = True
        os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
        ext = os.path.splitext(uploaded_file.name)[1] or ".mp4"
        local_path = os.path.join(LOCAL_OUTPUT_DIR, f"upload_{uuid.uuid4().hex}{ext}")

        with open(local_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

    if not has_file:
        st.warning("Selecione um arquivo de vídeo para continuar.")
    else:
        url = local_path
        # Provide feedback
        status_text = st.empty()
        status_text.info("Downloading and processing... this may take a few minutes. Check the terminal for detailed logs.")
        
        try:
            # We must configure env properly since streamlit doesn't load .profile
            if mode == "local":
                # Ensure ffmpeg from brew is found
                if "/opt/homebrew/bin" not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"
            
            lang_param = language.strip() if language.strip() else None
            
            with st.spinner("Analyzing audio and searching for viral hooks..."):
                result = generate_shorts(
                    youtube_url=url,
                    num_clips=int(num_clips),
                    aspect_ratio=aspect_ratio,
                    language=lang_param,
                )
                
            status_text.success("Generation complete!")
            
            st.header("✨ Your Viral Shorts")
            
            if not result.get("shorts"):
                st.warning("No shorts were generated. Check the logs for errors.")
            else:
                # Display shorts in columns
                cols = st.columns(min(len(result["shorts"]), 3))
                
                for i, short in enumerate(result["shorts"]):
                    col_idx = i % 3
                    with cols[col_idx]:
                        st.subheader(f"#{i+1} - Score: {short.get('score', 'N/A')}")
                        st.markdown(f"**Title:** {short.get('title')}")
                        st.markdown(f"**Hook:** _{short.get('hook_sentence')}_")
                        
                        clip_url = short.get("clip_url")
                        if clip_url:
                            # Render video
                            try:
                                st.video(clip_url)
                            except Exception as e:
                                st.error(f"Could not load video: {e}")
                                st.code(clip_url)
                        else:
                            st.error(f"Failed to clip: {short.get('error', 'Unknown Error')}")
                            
        except Exception as e:
            status_text.error(f"An error occurred: {e}")
            st.exception(e)
