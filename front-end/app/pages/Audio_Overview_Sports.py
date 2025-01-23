from google.cloud import texttospeech_v1beta1
import google.auth.transport.requests
from google.auth import impersonated_credentials
import streamlit as st
from google.cloud import aiplatform_v1
from google.cloud import storage
import vertexai, requests, json, math
from datetime import datetime, timedelta
# import utils
from vertexai.preview.generative_models import GenerativeModel, Part, SafetySetting, Tool
from vertexai.preview.generative_models import grounding

PROJECT_ID = "videosearch-cloudspace"
AUDIO_BUCKET = "audio_overview_sports"
VIDEO_CLIPS = "key-moment-video-clips"

st.sidebar.markdown(
    "[GitHub Repo](https://github.com/ljogeiger/media_platform/blob/main/front-end/app/pages/Audio_Overview_Sports.py)"
)

storage_client = storage.Client(project=PROJECT_ID)
vertexai.init(project=PROJECT_ID, location="us-central1")

sample_speaker_json = [{
    "speaker":
    "R",
    "text":
    "I've heard that the Google Cloud multi-speaker audio generation sounds amazing!"
}, {
    "speaker": "S",
    "text": "Oh? What's so good about it?"
}, {
    "speaker": "R",
    "text": "Well.."
}, {
    "speaker": "S",
    "text": "Well what?"
}, {
    "speaker": "R",
    "text": "Well, you should find it out by yourself!"
}, {
    "speaker": "S",
    "text": "Alright alright, let's try it out!"
}]


def getCreds():
    creds, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform'])
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds


# Function to get signed GCS urls
def getSignedURL(filename, bucket, action):

    # creds = service_account.Credentials.from_service_account_file('./credentials.json')
    creds = getCreds()

    signing_credentials = impersonated_credentials.Credentials(
        source_credentials=creds,
        target_principal=
        'videosearch-streamlit-frontend@videosearch-cloudspace.iam.gserviceaccount.com',
        target_scopes='',
        lifetime=500)

    blob = bucket.blob(filename)

    url = blob.generate_signed_url(
        expiration=timedelta(minutes=60),
        method=action,
        credentials=signing_credentials,
        version="v4",
    )
    return url


# Function to upload bytes object to GCS bucket
def upload_audio_file(upload_file, bucket_name, name):
    bucket = storage_client.bucket(bucket_name)

    url = getSignedURL(name, bucket, "PUT")
    # blob.upload_from_string(uploaded_file.read())

    print(f"Upload Signed URL: {url}")

    # encoded_content = base64.b64encode(uploaded_file.read()).decode("utf-8")

    # Again leverage signed URLs here to circumvence Cloud Run's 32 MB upload limit
    response = requests.put(url,
                            upload_file,
                            headers={'Content-Type': 'audio/mpeg'})

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


def text_to_voice(speaker_json, output_file_name):
    # Instantiates a client
    speech_client = texttospeech_v1beta1.TextToSpeechClient()

    multi_speaker_markup = texttospeech_v1beta1.MultiSpeakerMarkup()

    for data in speaker_json["transcript"]:
        turn = texttospeech_v1beta1.MultiSpeakerMarkup.Turn()
        turn.text = data["text"]
        turn.speaker = data["speaker"]
        multi_speaker_markup.turns.append(turn)

    # Set the text input to be synthesized
    synthesis_input = texttospeech_v1beta1.SynthesisInput(
        multi_speaker_markup=multi_speaker_markup)

    # Build the voice request, select the language code ('en-US') and the ssml
    # voice gender ('neutral')
    voice = texttospeech_v1beta1.VoiceSelectionParams(
        language_code="en-US", name="en-US-Studio-MultiSpeaker")

    # Select the type of audio file you want returned
    audio_config = texttospeech_v1beta1.AudioConfig(
        audio_encoding=texttospeech_v1beta1.AudioEncoding.MP3)

    # Perform the text-to-speech request on the text input with the selected
    # voice parameters and audio file type
    response = speech_client.synthesize_speech(input=synthesis_input,
                                               voice=voice,
                                               audio_config=audio_config)

    # The response's audio_content is binary.
    # Upload to cloud storage
    upload_audio_file(response.audio_content, AUDIO_BUCKET, output_file_name)
    # with open(
    #         f"/Users/lukasgeiger/Desktop/videosearch-cloudspace/video_platform/front-end/app/data/{output_file}.mp3",
    #         "wb") as out:
    #     # Write the response to the output file.
    #     out.write(response.audio_content)
    #     print(f'Audio content written to file "{output_file}.mp3"')
    return


def generate_commentary(input_video1, input_video2):
    system_instructions = """
    Your job is to create a interesting an engaging podcast transcript between two speakers about one or more input videos.
    Include vocal fillers (like um and uh) where natural for humans.
    The videos are about sports - make sure to stay on topic and provide insightful analysis.

    Include a brief comaprison between the videos if more than one are provided.

    Include the following in your output:
    Title: Title for the audio file which encapsulated the topic of the podcast
    Transcript: list of objects
      - Speaker: who is speaking, either S or R (if necessary you can add a third speaker Tyler)
      - Text: the text the speaker is going to say

    Example:
    {"title":"Google Cloud Multi-Speaker STT","transcript":[{"speaker":"R","text":"I've heard that the Google Cloud multi-speaker audio generation sounds amazing!"}, {"speaker": "S","text": "Oh? What's so good about it?"}, {"speaker": "R","text": "Well.."}, {"speaker": "S","text": "Well what?"}, {"speaker": "R","text": "Well, you should find it out by yourself!"}, {"speaker": "S","text": "Alright alright, let's try it out!"}]}
    """
    video1 = Part.from_uri(
        mime_type="video/mp4",
        uri=input_video1,
    )
    video2 = Part.from_uri(
        mime_type="video/mp4",
        uri=input_video2,
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

    model = GenerativeModel("gemini-1.5-pro-002",
                            system_instruction=[system_instructions])
    response = model.generate_content(
        [
            """You are a sport analysis experts. Provide insightful and entertaining analysis of the following games.""",
            video1, video2
        ],
        generation_config=generation_config,
        safety_settings=safety_settings,
        stream=False,
    )

    return response.text


def generate_google_search(input_transcript):
    system_instructions_google = """
    Provide a list of follow up questions expanding on the ideas discussed in a podcast about sports. You are given a transcript of the podcast.
    Use Google Search tool to provide links where the user can find answers.
    Include at least 3 questions.

    Include the following in your output:
    - Question (string): a helpful question based on the input files (required)
    - Answer (string): the answer to the question (required)
    - Citation (string): a signle url where the user can find the answer to the question (required)

    Output format:
    {"questions":[{"question":"What was the final score of the game?","answer":"The score of the Bengals vs. Seahawks game on October 15, 2023 was 17-13.","citation":"https://www.espn.com/nfl/game/_/gameId/401547471/seahawks-bengals"}]}
    """

    generation_config = {
        "max_output_tokens": 8192,
        "temperature": 0.1,
        "top_p": 0.95,
        "response_mime_type": "application/json",
    }

    tools = [
        Tool.from_google_search_retrieval(
            google_search_retrieval=grounding.GoogleSearchRetrieval()),
    ]

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

    google_model = GenerativeModel(
        "gemini-1.5-pro-002",
        tools=tools,
        system_instruction=[system_instructions_google])
    response_google = google_model.generate_content(
        [
            f"""Generate a list of cited questions and answers based on the topic of this transcript: {input_transcript}""",
        ],
        generation_config=generation_config,
        safety_settings=safety_settings,
        stream=False,
    )

    return response_google.text


def list_files_in_bucket(bucket_name):
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs()
    return [blob.name for blob in blobs]


# Streamlit section

st.title("Audio Overview - Sports")
st.header("Select Videos Here")
st.text("Video #1")
# Get the list of files in the bucket
file_list1 = list_files_in_bucket(VIDEO_CLIPS)

# Display a dropdown to select a file
selected_file1 = st.selectbox(label="Selected file",
                              placeholder="Select a file",
                              index=None,
                              options=file_list1,
                              key=1)

if selected_file1:
    gcs_file1 = f"gs://{VIDEO_CLIPS}/{selected_file1}"
    st.video(
        getSignedURL(filename=selected_file1,
                     bucket=storage_client.bucket(VIDEO_CLIPS),
                     action="GET"))

st.text("Video #2")
file_list2 = list_files_in_bucket(VIDEO_CLIPS)

# Display a dropdown to select a file
selected_file2 = st.selectbox(label="Selected file",
                              placeholder="Select a file",
                              index=None,
                              options=file_list2,
                              key=2)

if selected_file2:
    gcs_file2 = f"gs://{VIDEO_CLIPS}/{selected_file2}"
    st.video(
        getSignedURL(filename=selected_file2,
                     bucket=storage_client.bucket(VIDEO_CLIPS),
                     action="GET"))
podcast_button = st.button("Generate Podcast")
if podcast_button and selected_file1 and selected_file2:
    st.text("loading...")
    generated_speaker_string = generate_commentary(gcs_file1, gcs_file2)
    generated_speaker_json = json.loads(generated_speaker_string)
    st.json(generated_speaker_json, expanded=False)
    output_name = f"{generated_speaker_json['title']}.mp3"
    text_to_voice(generated_speaker_json, output_name)
    st.audio(
        getSignedURL(filename=output_name,
                     bucket=storage_client.bucket(AUDIO_BUCKET),
                     action="GET"))

    # Grounding google search results to recommend quesitons to ask
    st.header("Suggested Questions")
    input_transcript = "\n".join(
        speaker["text"] for speaker in generated_speaker_json["transcript"])
    question_string = generate_google_search(
        input_transcript)  # Doesn't work well if I pass in the JSON object
    question_json = json.loads(question_string)
    st.json(question_json, expanded=False)
    for question in question_json["questions"]:
        if question["citation"] == None:
            st.markdown(
                f"**Question: {question['question']}**\nAnswer: {question['answer']}"
            )
        else:
            st.link_button(
                f"Question: {question['question']}\nAnswer: {question['answer']}",
                question["citation"]
            )  # TODO: urls are not correct. Might need to get citation object in response.

# Evaluation results for Audio Overview. Could evaluate the text before TTS generations
