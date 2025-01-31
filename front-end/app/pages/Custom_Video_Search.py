import streamlit as st
from google.cloud import aiplatform_v1
from google.cloud import storage
import vertexai
import math
import utils
from vertexai.generative_models import GenerativeModel, Part
from vertexai.vision_models import MultiModalEmbeddingModel
import requests

PROJECT_ID = "videosearch-cloudspace"
REGION = "us-central1"
API_ENDPOINT = "1949003250.us-central1-6255484976.vdb.vertexai.goog"
INDEX_ENDPOINT = "projects/6255484976/locations/us-central1/indexEndpoints/4956743553549074432"
DEPLOYED_INDEX_ID = "video_search_endpoint_1710342048921"
INDEX_ID = "7673540028760326144"
DEPLOYED_ENDPOINT_DISPLAY_NAME = "Video Search Endpoint"
VIDEO_SOURCE_BUCKET = "videosearch_source_videos"
TOP_N = 4
EMBEDDINGS_BUCKET = "videosearch_embeddings"

st.sidebar.markdown(
    "[GitHub Repo](https://github.com/ljogeiger/media_platform/blob/main/front-end/app/pages/Custom_Video_Search.py)"
)

# Define storage client for file uploads
storage_client = storage.Client(project=PROJECT_ID)

with st.sidebar:
    model_selection = st.radio(
        "Which Gemini model?",
        options=[
            "Gemini 1.5 Pro", "Gemini 1.5 Flash", "Gemini Pro Vision 1.0"
        ],
        captions=["Use this", "", ""],
    )

vertexai.init(project="videosearch-cloudspace", location="us-central1")

if model_selection == "Gemini 1.5 Pro":
    model_gem = GenerativeModel("gemini-1.5-pro-002")
elif model_selection == "Gemini 1.5 Flash":
    model_gem = GenerativeModel("gemini-1.5-flash-002")
elif model_selection == "Gemini Pro Vision 1.0":
    model_gem = GenerativeModel("gemini-1.0-pro-vision-001")


# Function to parse findNeighbors result
# OUT: list of neighbor dicts
def parse_neighbors(neighbors):
    videos = []
    for n in range(len(neighbors)):
        start_sec = (
            int(neighbors[n].datapoint.datapoint_id.split("_")[-1]) - 1
        ) * 5  # 5 because I set IntervalSecs on Embeddings API to 5. We generate an embedding vector for each 5 second interval
        video_name = "_".join(neighbors[n].datapoint.datapoint_id.split(
            "_")[:-1])  # files stored in 2 minute segements in GCS
        print(f"Getting Signed URL - Video Name: {video_name}")

        # Better than downloading to temp file in Cloud run b/c this makes a direct link to GCS (rather than having Cloud run be proxy)
        signedURL = utils.getSignedURL(
            video_name,
            storage_client.bucket("videosearch_video_source_parts"), "GET")

        print(f"Received Signed URL: {signedURL}")

        d = {
            "result":
            f"Result #{n+1}\nTimestamps:{start_sec}->{start_sec+5}\n{neighbors[n].datapoint.datapoint_id}",  #5 because that's what I set IntervalSec in embeddings api call
            "gcs_file": f"{video_name}",
            "file": f"{neighbors[n].datapoint.datapoint_id}",
            "start_sec": start_sec,
            "distance": neighbors[n].distance,
            "signedURL": signedURL,
        }
        videos.append(d)
    return videos


# Function to upload bytes object to GCS bucket
def upload_video_file(uploaded_file, bucket_name):

    bucket = storage_client.bucket(bucket_name)

    url = utils.getSignedURL(uploaded_file.name, bucket, "PUT")
    # blob.upload_from_string(uploaded_file.read())

    print(f"Upload Signed URL: {url}")

    # encoded_content = base64.b64encode(uploaded_file.read()).decode("utf-8")

    # Again leverage signed URLs here to circumvence Cloud Run's 32 MB upload limit
    response = requests.put(url,
                            uploaded_file,
                            headers={'Content-Type': 'video/mp4'})

    #TODO: review. Returns unsuccessful upon success.
    print(response.status_code)
    print(response.reason)
    if response.status_code == 200:
        st.write("Success")
    else:
        st.write(
            f"Error in uploading content: {response.status_code} {response.reason} {response.text}"
        )
    return


# Function to get embedding from query text
def get_query_embedding(query):
    model = MultiModalEmbeddingModel.from_pretrained(
        model_name="multimodalembedding@001")

    embedding = model.get_embeddings(contextual_text=query)
    query_embedding = embedding.text_embedding
    return query_embedding


st.header("Similarity search through all videos in Cymbal AI's database")

#Search

query = st.text_input("Custom Video Search (ex. Tiger Walking)", key="query")
search_button = st.button("Search")

result_list = []

if search_button and query:
    print(query)
    # Get embeddings from query
    query_embedding = get_query_embedding(query)

    # Perform search

    client_options = {"api_endpoint": API_ENDPOINT}

    vector_search_client = aiplatform_v1.MatchServiceClient(
        client_options=client_options, )

    # Build FindNeighborsRequest object
    datapoint = aiplatform_v1.IndexDatapoint(feature_vector=query_embedding)
    datapoint_query = aiplatform_v1.FindNeighborsRequest.Query(
        datapoint=datapoint,
        # The number of nearest neighbors to be retrieved
        neighbor_count=TOP_N)
    request = aiplatform_v1.FindNeighborsRequest(
        index_endpoint=INDEX_ENDPOINT,
        deployed_index_id=DEPLOYED_INDEX_ID,
        # Request can have multiple queries
        queries=[datapoint_query],
        return_full_datapoint=False,
    )

    # Execute the request
    response = vector_search_client.find_neighbors(request)

    # Parse the response object
    neighbors = response.nearest_neighbors[0].neighbors
    result_list = parse_neighbors(neighbors)

    st.session_state["neighbor_result"] = result_list

    # Display content
    # columnize_videos(result_list, num_col = 2)

if "neighbor_result" in st.session_state:
    utils.columnize_videos(st, st.session_state["neighbor_result"], num_col=2)

# Shot List

st.header("Generate shot list from video")
st.text(
    "Click one of the buttons below to generate an shot list from the video.\nNOTE: Gemini Pro 1.0 does not work well for this task."
)

if "neighbor_result" in st.session_state:
    neighbors = st.session_state[
        "neighbor_result"]  # need to store in session state because otherwises it's not accessible

    prompt_shot_list = f"""
    You are tasked with generating a shot list for the attached video. A shot is a series of frames that runs for an uninterrupted period of time.
    A shot list is a document that maps out everything that will happen in a scene of a video. It describes each shot within the video
    For each shot, make sure to include:
    - A description
    - A timestamp for the duration of the shot
    - Shot type (close-up, wide-shot, etc)
    - Camera angle
    - Location
    You must include each of the element for each shot in the video. If you are uncertain about one of the elements say you are uncertain and explain why.
    """
    generation_config = {
        "max_output_tokens": 2048,
        "temperature": 1,
        "top_p": 0.4
    }

    final_prompt_shot_list = st.text_area(label="Prompt",
                                          value=prompt_shot_list,
                                          height=250)

    buttons_shot_list = []
    for i in range(TOP_N):
        buttons_shot_list.append(
            st.button(
                f"Generate shot list from video: {neighbors[i]['result']}"))

    for i, button_shot_list in enumerate(buttons_shot_list):
        if button_shot_list:
            gcs_uri_shot_list = f"gs://videosearch_video_source_parts/{neighbors[i]['gcs_file']}"

            print(gcs_uri_shot_list)
            input_file_shot_list = [
                Part.from_uri(uri=gcs_uri_shot_list, mime_type="video/mp4"),
                final_prompt_shot_list
            ]
            print(input_file_shot_list)
            response_generate = model_gem.generate_content(
                input_file_shot_list, generation_config=generation_config)
            print(response_generate)
            st.write(response_generate.text)
            st.write(f"{i+1} button was clicked")

# Summarize

st.header("Summarize video")
st.text(
    "Click one of the buttons below to summarize the video. This will summarize the entire video.\nPro 1.5 will take timestamps into account and will only summarize the timestamp specified.\nPro 1.0 will not. Prompt is not editable."
)

if "neighbor_result" in st.session_state:
    neighbors = st.session_state[
        "neighbor_result"]  # need to store in session state because otherwises it's not accessible

    buttons_summarize = []
    for i in range(TOP_N):
        buttons_summarize.append(
            st.button(f"Summarize Video {neighbors[i]['result']}"))

    for i, button_summarize in enumerate(buttons_summarize):
        if button_summarize:
            prompt_summarize = f"""
              Summarize the following video. Only mention items that occur in the video.
              Limit the summarization to the events that occur between start and end timestamps.

              Start:{neighbors[i]['start_sec']} seconds
              End: {neighbors[i]['start_sec']+5} seconds

              {query} might be seen or relate to events between the start and end timestamps. If it does, explain how.
              """
            gcs_uri_summarize = f"gs://videosearch_video_source_parts/{neighbors[i]['gcs_file']}"

            st.text_area(label="Prompt", value=prompt_summarize, height=250)
            input_file_summarize = [
                Part.from_uri(uri=gcs_uri_summarize, mime_type="video/mp4"),
                prompt_summarize
            ]
            print(input_file_summarize)
            response_summarize = model_gem.generate_content(
                input_file_summarize,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.3,
                    "top_p": 0.4
                })
            st.write(response_summarize.text)
            st.write(f"{i+1} button was clicked")

st.header("Generate article from video")
st.text(
    "Click one of the buttons below to generate an article from the video.\nPrompt is editable."
)

if "neighbor_result" in st.session_state:
    neighbors = st.session_state[
        "neighbor_result"]  # need to store in session state because otherwises it's not accessible

    # Allow the user to modify the prompt
    prompt_generate = f"""
    You are a journalist. Your job is to write an article with the provided video as your source.
    Make sure to ground your article only to events occurred in the video.
    If you reference a part of the video you must provide a timestamp.

    In the article, make sure to include:
      1. A summary of what happened in the video.
      2. Your interpretation of events.
      3. Analysis of why these events occurred.
      4. Suggestion of 3-5 books/subjects the journalist should research to write this article.
    """
    generation_config = {
        "max_output_tokens": 4048,
        "temperature": 0.9,
        "top_p": 0.4
    }

    final_prompt_generate = st.text_area(label="Prompt",
                                         value=prompt_generate,
                                         height=250)

    buttons_generate = []
    for i in range(TOP_N):
        buttons_generate.append(
            st.button(
                f"Generate article from video: {neighbors[i]['result']}"))

    for i, button_generate in enumerate(buttons_generate):
        if button_generate:
            gcs_uri_generate = f"gs://videosearch_video_source_parts/{neighbors[i]['gcs_file']}"
            print(gcs_uri_generate)
            input_file_generate = [
                Part.from_uri(uri=gcs_uri_generate, mime_type="video/mp4"),
                final_prompt_generate
            ]
            print(input_file_generate)
            response_generate = model_gem.generate_content(
                input_file_generate, generation_config=generation_config)
            print(response_generate)
            st.write(response_generate.text)
            st.write(f"{i+1} button was clicked")

# QA

st.header("Q&A with videos")
st.text("Ask questions against a video")

if "neighbor_result" in st.session_state:
    neighbors = st.session_state["neighbor_result"]
    file_name_list = [
    ]  # Put file names in list for streamlit radio object options
    name_to_uri_dict = {}  # Map file name to uri to pass into model
    for i, neighbor in enumerate(neighbors):
        file_name = neighbor['file']
        file_name_list.append(file_name)
        name_to_uri_dict[file_name] = neighbor['gcs_file']

    video_selection_name = st.radio(label="Select one video",
                                    options=file_name_list)

    question = st.text_input(label="Question")
    button_qa = st.button(label="Ask")
    if question and button_qa:
        gcs_uri_qa = f"gs://videosearch_video_source_parts/{name_to_uri_dict[video_selection_name]}"

        prompt_qa = f"Your job is to anwswer the following question using the video provided. Question: {question}. If you do not know the answer of the question is unrelated to the video response with 'I don't know'."

        input_file_generate = [
            Part.from_uri(uri=gcs_uri_qa, mime_type="video/mp4"), prompt_qa
        ]
        response_generate = model_gem.generate_content(input_file_generate)
        st.write(response_generate.text)

# Cannot use below because runs into Cloud run 32 mib limit
# st.header("Upload Video File")
# st.text("Upload a video file from your local machine to the video database")

# uploaded_file = st.file_uploader("Choose a video...", type=["mp4"])
# upload_file_start = st.button("Upload File")

# if upload_file_start:
#     upload_video_file(uploaded_file=uploaded_file, bucket_name=VIDEO_SOURCE_BUCKET)


st.title("Delete Video")
st.write("Enter the source video below and it will delete embeddings in Vector Search source video.")

video_name = st.text_input("Enter video name without GCS uri path.")
delete_button = st.button("Delete")

def delete_video(video_name):


    blobs = storage_client.list_blobs(EMBEDDINGS_BUCKET, prefix=f"{video_name}/tmp")

    blob_list = []
    for blob in blobs:
        blob_list.append(blob.name.replace('.json',''))

    print(f"Deleting...{blob_list}")

    response = requests.post(
      url = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{REGION}/indexes/{INDEX_ID}:removeDatapoints",
      json={
        "datapoint_ids": blob_list
      },
      headers={
        'Content-Type': 'application/json',
        "Authorization": f"Bearer {utils.getToken()}"
      }
    )

    if response.status_code == 200:
        st.write("Deletion successful")
    else:
        st.write(f"Deletion unsuccessful: {response.status_code} {response.text}")

    return

if video_name and delete_button:
    delete_video(video_name)
