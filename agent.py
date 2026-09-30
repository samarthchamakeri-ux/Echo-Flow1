
import asyncio
import os
from dotenv import load_dotenv
load_dotenv(".env")
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    AgentServer,
    JobContext,
    RoomInputOptions,
)
from livekit.plugins import google
from google.genai import types

from kernel import Kernel
from extensions.smart_home import SmartHomeTool
from extensions.employee_planner  import EmployeePlannerTool
from extensions.kitchen_assistant import KitchenAssistantTool
from extensions.study_helper import StudyHelperTool
from extensions.food_ordering import FoodOrderingTool
from extensions.doctor_appointment import DoctorAppointmentTool

# Create the LiveKit server
server = AgentServer()


class Assistant(Agent):

    def __init__(self):
        super().__init__(
            instructions="""
You are a helpful flight booking assistant.

Help the user book flights.

Ask for missing information naturally:
- origin
- destination
- date
- time
- number of passengers
- one-way or round trip

Keep responses short and conversational.

When the user changes information, accept the correction
and continue from the updated information.
"""
        )


@server.rtc_session()
async def entrypoint(ctx: JobContext):

    kernel = Kernel()
    kernel.register_tool(SmartHomeTool())
    kernel.register_tool(EmployeePlannerTool())
    kernel.register_tool(KitchenAssistantTool())
    kernel.register_tool(StudyHelperTool())
    kernel.register_tool(FoodOrderingTool())
    kernel.register_tool(DoctorAppointmentTool())

    # Create Gemini realtime session
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            api_key=os.getenv("GOOGLE_API_KEY"),
            voice="Puck",
            language="en-US",
            input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=["en-US"]
        ),
    )
)

    first_message = True

    async def process_user_text(text: str):

        nonlocal first_message

        print("\n" + "=" * 60)
        print(f"USER: {text}")
        print("=" * 60)

        # -----------------------------------------
        # FIRST USER MESSAGE
        # -----------------------------------------

        if first_message:

            result = kernel.handle_user_input(text)

            print("\n--- INTERRUPTION DETECTION ---")
            print(f"Type: {result.interruption_type}")
            print(f"Interrupted: {result.interrupted}")
            print(f"Changed slots: {result.changed_slots}")
            print(f"New goal: {result.new_goal}")

            kernel.start_task(
                goal=result.new_goal,
                slots=result.changed_slots or {},
            )

            first_message = False

        # -----------------------------------------
        # FOLLOW-UP / CORRECTION
        # -----------------------------------------

        else:

            result = await kernel.handle_user_correction(text)

            print("\n--- INTERRUPTION DETECTION ---")
            print(f"Type: {result.interruption_type}")
            print(f"Interrupted: {result.interrupted}")
            print(f"Changed slots: {result.changed_slots}")
            print(f"New goal: {result.new_goal}")

    # -----------------------------------------
    # USER SPEECH TRANSCRIPTION
    # -----------------------------------------

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):

        text = getattr(event, "transcript", None)

        if not text:
            return

        # Ignore partial transcripts
        if not getattr(event, "is_final", True):
            return

        print(f"\nRAW USER TRANSCRIPT: '{text}'")

        asyncio.create_task(
            process_user_text(text)
        )

    # -----------------------------------------
    # START AGENT SESSION
    # -----------------------------------------

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            close_on_disconnect=True,
        ),
    )

    # -----------------------------------------
    # INITIAL GREETING
    # -----------------------------------------

    await session.generate_reply(
        instructions="Greet the user briefly and ask how you can help."
    )


# ---------------------------------------------
# START LIVEKIT
# ---------------------------------------------

if __name__ == "__main__":
    agents.cli.run_app(server)

