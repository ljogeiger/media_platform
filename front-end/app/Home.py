import streamlit as st

st.sidebar.markdown(
    "[GitHub Repo](https://github.com/ljogeiger/media_platform)")

st.title("Cymbal AI - Video Platform")

st.markdown("""
        Welcome to Cymbal AI's Video Platform!

        This demo site has 4 features:
        1. **Custom video search:** semantic search for videos using multimodal embeddings and vector search
        2. **Managed video search:** semantic search through videos using vision warehouse
        3. **Key Moment Extraction:** extract key moments from videos
        4. **Audio Overview Sports:** create an audio podcast from two videos.

        Find architecture diagrams and details for each feature below.

        For custom/managed video search, we have pre-uploaded the following videos:
          - animals.mp4 (search for "tiger walking")
          - chicago.mp4 (search fro "taxi in chicago")
          - JaneGoodall.mp4
          - googlework_short.mp4

        If you want to upload a custom video, reach out to lukasgeiger@google.com
        """)
st.header("Custom Video Search")
st.markdown("""
        Custom Video Search generates 5 second interval embeddings using Google's
        multimodal embeddings API and stores them in Vector Search. This generates embeddings
        on the video frames. The semantic search does not support audio (but it is possible
        using speech-to-text model and embedding the text). Gemini 1.5 API does support audio.

        Here are some things you can do on this page:
        1. Similarity search through all videos in Cymbal AI's database (start here)
        2. Summarize video
        3. Generate analytical article based on video
        4. Ask questions of video
        5. Upload a video file to database

        Below you will find an architecture diagram:
        """)
st.image('app/video_platform_architecture.png')

st.header("Managed Video Search")
st.markdown("""
        Managed Video Search is powered by GCP's Vision Warehouse product.
        The product generates and manages embeddings for you so you can focus on building your
        application.

        Currently this doesn't support audio, but it is coming soon.

        The architecture is pictured below:

        """)
st.image('app/Managed_Video_Search.png')

st.header("Key Moment Extraction")
st.markdown("""
        Key Moment Extraction uses Gemini 1.5 Pro to extract key moments from sport videos.
        This can be used to create social media posts, automatically send users notifications on subscribed games,
        and create highlight reels.

        This is a simple call to Gemini API.
        I utilize JSON mode for Gemini to then display each video in a columnized format.

        See the prompt used in the Key Moment Extraction pages.
        """)
st.header("Audio Overview Sports")
st.markdown("""
        Audio Overviews generates a two-person podcast (think NotebookLM) commentary from two videos.
        Some applications of this tech can be generating a week in review podcast or even creating analysis reels to
        help users with their fantasy football teams.

        To do this I utilize Gemini 1.5 Pro multimodal capabilities and Cloud Text-to-Speech (TTS) API.
        1. Gemini: Create transcript analyzing and comparing the two videos. First summarize what happened, the provide insight.
        2. Cloud TTS: Convert transcript to speech using Cloud TTS multi-speaker.
        """)
