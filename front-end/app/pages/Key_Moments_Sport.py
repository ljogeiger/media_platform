import streamlit as st
from google.cloud import aiplatform_v1
from google.cloud import storage
import vertexai, requests, json, math
from datetime import datetime
import utils
from vertexai.generative_models import GenerativeModel, Part, SafetySetting

PROJECT_ID = "videosearch-cloudspace"
REGION = "us-central1"
VIDEO_CLIPS = "key-moment-video-clips"


# Initiatlize variables
gcs_file = None
gemini_output = None

# Define storage client for file uploads
storage_client = storage.Client(project=PROJECT_ID)
st.set_page_config(layout="wide")

st.sidebar.markdown(
    "[GitHub Repo](https://github.com/ljogeiger/media_platform/blob/main/front-end/app/pages/Key_Moments_Sport.py)"
)


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


def generate():
    video1 = Part.from_uri(
        mime_type="video/mp4",
        uri=gcs_file,
    )

    generation_config = {
        "max_output_tokens": 8192,
        "temperature": 0.1,
        "top_p": 0.95,
        "response_mime_type": "application/json",
    }

    safety_settings = [
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=SafetySetting.HarmBlockThreshold.OFF),
        SafetySetting(category=SafetySetting.HarmCategory.
                      HARM_CATEGORY_DANGEROUS_CONTENT,
                      threshold=SafetySetting.HarmBlockThreshold.OFF),
        SafetySetting(category=SafetySetting.HarmCategory.
                      HARM_CATEGORY_SEXUALLY_EXPLICIT,
                      threshold=SafetySetting.HarmBlockThreshold.OFF),
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=SafetySetting.HarmBlockThreshold.OFF),
    ]
    st.text("loading...")
    vertexai.init(project=PROJECT_ID, location=REGION)
    model = GenerativeModel("gemini-1.5-pro-002",
                            system_instruction=[textsi_1])
    response = model.generate_content(
        [
            """You are a sports video analyst. Your task is to extract key moments from a provided sports video.""",
            video1
        ],
        generation_config=generation_config,
        safety_settings=safety_settings,
        stream=False,
    )

    return response.text


def hms_to_seconds(hms_str):
    """Converts a string in HH:MM:SS.000 format to the number of seconds.

  Args:
    hms_str: The string representing the time in HH:MM:SS.000 format.

  Returns:
    The total number of seconds as an integer.
  """
    hours, minutes, seconds_ms = hms_str.split(":")
    seconds, milliseconds = map(int, seconds_ms.split("."))
    total_seconds = (int(hours) * 3600) + (int(minutes) * 60) + seconds
    return total_seconds


def list_files_in_bucket(bucket_name):
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs()
    return [blob.name for blob in blobs]


st.title("Extract Key Moments from Sport Clips")

# Cannot use this on Cloud run due to 32 mib limit
# with st.expander("Upload Video"):
#     st.header("Upload Video File")
#     st.text(
#         "Upload a video file from your local machine to the video database")

#     uploaded_file = st.file_uploader("Choose a video...", type=["mp4"])
#     upload_file_start = st.button("Upload File")

#     if upload_file_start and uploaded_file:
#         upload_video_file(uploaded_file=uploaded_file, bucket_name=VIDEO_CLIPS)

#         print(f"Uploaded file name: {uploaded_file}")

st.header("Select File")
# Get the list of files in the bucket
file_list = list_files_in_bucket(VIDEO_CLIPS)

# Display a dropdown to select a file
selected_file = st.selectbox(label="Selected file",
                             placeholder="Select a file",
                             index=None,
                             options=file_list)

if selected_file:
    gcs_file = f"gs://{VIDEO_CLIPS}/{selected_file}"
    st.video(
        utils.getSignedURL(filename=selected_file,
                           bucket=storage_client.bucket(VIDEO_CLIPS),
                           action="GET"))

st.header("Run Gemini across video")

textsi_1 = """
Instructions:
Identify the sport (Basketball, American Football, etc.)

Key moments are defined as follows:
• Basketball: 3-point shots, 2-point shots, dunks, steals, blocks
• Soccer/Football: Goals, assists, yellow cards, red cards, penalty kicks, shots on goal
• American Football: Touchdowns, field goals, interceptions, sacks
• Baseball: Home runs, hits, strikeouts, stolen bases
• Ice Hockey: Goals, assists, penalties

Include the following output:
• start_time: Timecode of the start of the chapter (in MM:SS format).
• end_time: Timecode of the end of the chapter (in MM:SS format).
• reason: Why you identified this as a key moment
• key_moment_title: Provide a concise title that accurately summarizes the key moment, focusing on the main team or player involved. Include relevant emojis.
• teams: An array of objects representing the teams being discussed in the clip's content. Each object should contain:
  • team_name: The name of the team.
  • relevance_score: A score between 1 and 10 indicating how relevant the team is to the chapter (1 for brief mentions and 10 for chapters that primarily focus on the team).
• players: An array of strings representing the players being discussed in the clip's content.
• league: The league to which the teams belong (e.g., NBA, NFL, EPL).
• sport: The name of the sport to which the chapter belongs (e.g., Football, Basketball, Tennis, etc.).
• social_media_text: The text for a friendly social media post about the video clip. Always include at least one emoji. Also include relevant hashtags.

For example:
{\"key_moments\":[{\"start_time\":\"00:00:00\",\"end_time\":\"00:05:23\",\"key_moment_title\":\"Recap of Team A vs Team B Game\", \"reason\": \"example reason\", \"teams\":[{\"team_name\":\"Team A\",\"relevance_score\":9},{\"team_name\":\"Team B\",\"relevance_score\":8}],\"league\":\"NBA\",\"players\":[\"Lebron James\",\"Michael Jordan\"],\"sport\":\"Basketball\",\"overall_importance_score\":9,\"social_media_text\":\"The atmosphere is electric at Stadium as Team A and Team B prepare for battle in the cup! ⚔️ Who will claim victory tonight? #ARSLIV #NBA #cup #basketball\"},{\"start_time\":\"00:05:24\",\"end_time\":\"00:07:45\", \"reason\": \"example reason\",\"key_moment_title\":\"Interview with Player B from Team A\",\"teams\":[{\"team_name\":\"Team A\",\"relevance_score\":10}],\"league\":\"NBA\",\"players\":[\"Lebron James\",\"Michael Jordan\"],\"sport\":\"Basketball\",\"overall_importance_score\":8,\"social_media_text\":\"The atmosphere is electric at Stadium as Team A and Team B prepare for battle in the cup! ⚔️ Who will claim victory tonight? #ARSLIV #NBA #cup #basketball\"}]}

Think step by step."""

with st.expander("See Prompt"):
    st.text(textsi_1)

run_gemini = st.button("Run Gemini")

if run_gemini and gcs_file:
    gemini_output = json.loads(generate())
    st.json(gemini_output, expanded=False)

result_list = []
if gemini_output:
    for video in gemini_output["key_moments"]:
        signedURL = utils.getSignedURL(selected_file,
                                       storage_client.bucket(VIDEO_CLIPS),
                                       "GET")
        d = {
            "title": f"{video['key_moment_title']}",
            "reason": f"{video['reason']}",
            "team_names":
            f"{', '.join(team['team_name'] for team in video['teams'])}",
            "players": f"{video['players']}",
            "social_media_text": f"{video['social_media_text']}",
            "gcs_file": f"gs://{VIDEO_CLIPS}/{selected_file}",
            "start_sec": video["start_time"],
            "end_sec": video["end_time"],
            "distance": None,
            "signedURL": signedURL,
        }
        result_list.append(d)
    print(result_list)
    num_cols = 3
    cols = st.columns(num_cols)
    try:
        for row in range(math.ceil(len(result_list) / num_cols)):
            for col in range(num_cols):
                item = row * num_cols + col
                cols[col].header(
                    f"Title #{item+1}: **{result_list[item]['title']}**")
                cols[col].markdown(f"Reason: {result_list[item]['reason']}")
                cols[col].video(result_list[item]["signedURL"],
                                start_time=hms_to_seconds(
                                    f"0:{result_list[item]['start_sec']}.000"))
                cols[col].markdown(
                    f"Social Media Text: {result_list[item]['social_media_text']}"
                )
                cols[col].markdown(
                    f"{result_list[item]['start_sec']}->{result_list[item]['end_sec']}"
                )
                cols[col].markdown(f"Teams: {result_list[item]['team_names']}")
                cols[col].markdown(f"Players: {result_list[item]['players']}")
                cols[col].button(label="Post to X!", key=item)
                if d['distance'] != None:
                    cols[col].text(
                        f"Similarity score: {result_list[item]['distance']:.4f}"
                    )
    except IndexError as e:
        print(f"Index out of bounds: {e}")
