import streamlit as st
import os
import sys

# Ensure the app can import from shorts_generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shorts_generator import generate_shorts

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
    
    mode = st.radio(
        "Processing Mode",
        ["local", "api"],
        index=0,
        help="'local' runs entirely on your machine. 'api' uses MuAPI cloud."
    )
    
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
    
    download_format = st.selectbox(
        "Source Resolution",
        ["360", "480", "720", "1080"],
        index=2,
        help="Quality of the downloaded video before cropping."
    )
    
    language = st.text_input(
        "Language Override (Optional)",
        value="",
        placeholder="e.g. 'en', 'pt'",
        help="Force Whisper language code. Leave empty for auto-detect."
    )

st.divider()

url = st.text_input("🔗 Paste YouTube URL or local file path here", placeholder="https://www.youtube.com/watch?v=...")

if st.button("🚀 Generate Shorts", type="primary", use_container_width=True):
    if not url:
        st.warning("Please enter a valid URL or path.")
    else:
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
                    download_format=download_format,
                    language=lang_param,
                    mode=mode,
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
