import os
import sys
import asyncio
import uuid

import gradio as gr


# ─────────────────────────────────────────────────────────────
# Import paths
# ─────────────────────────────────────────────────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, BACKEND_DIR)


# ─────────────────────────────────────────────────────────────
# Cloud LLM adapter
# ─────────────────────────────────────────────────────────────

from cloud.cloud_llm_engine import CloudLLMEngine


# ─────────────────────────────────────────────────────────────
# Existing EduMentor agent components
# ─────────────────────────────────────────────────────────────

from agent import (
    AgentController,
    InterruptManager,
    MemoryManager,
    SessionSummarizer,
    StudentProfileManager,
    get_backend,
)

from agent.database import DatabaseManager


# ─────────────────────────────────────────────────────────────
# Global application objects
# ─────────────────────────────────────────────────────────────

llm_engine = None
agent_controller = None
db_manager = None


async def initialize_agent():

    global llm_engine
    global agent_controller
    global db_manager

    if agent_controller is not None:
        return

    print("Initializing EduMentor Cloud Agent...")

    # Cloud LLM
    llm_engine = CloudLLMEngine()

    # Database disabled for first integration test.
    #
    # We intentionally do NOT connect Neon yet.
    db_manager = DatabaseManager()
    db_manager.enabled = False

    # Existing EduMentor components
    interrupt_manager = InterruptManager()

    memory_backend = get_backend("in_memory")

    memory_manager = MemoryManager(
        max_turns=10,
        backend=memory_backend,
    )

    session_summarizer = SessionSummarizer(
        llm_engine=llm_engine,
        summary_dir="/tmp/edumentor_summaries",
    )

    profile_manager = StudentProfileManager(
        profile_path="/tmp/student_profile.json",
    )

    agent_controller = AgentController(
        llm_engine=llm_engine,
        memory_manager=memory_manager,
        session_summarizer=session_summarizer,
        profile_manager=profile_manager,
        interrupt_manager=interrupt_manager,
        intent_enabled=False,
        safety_enabled=True,
        db_manager=db_manager,
    )

    print("EduMentor Cloud Agent initialized.")


async def run_agent(
    message: str,
    session_id: str,
):

    await initialize_agent()

    if not message or not message.strip():
        return "Please enter a question."

    chunks = []

    async for item in agent_controller.stream(
        user_text=message,
        session_id=session_id,
        user_id=session_id,
        ip_address="cloud-space",
    ):

        if isinstance(item, dict):
            planned = item.get("planned", "")

            if planned:
                chunks.append(planned)

    return "".join(chunks).strip()


def chat(
    message: str,
    session_id: str,
):

    return asyncio.run(
        run_agent(
            message,
            session_id,
        )
    )


# ─────────────────────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────────────────────

with gr.Blocks() as demo:

    gr.Markdown("# EduMentor Cloud Agent Test")

    gr.Markdown(
        "Existing EduMentor AgentController + ZeroGPU Cloud LLM"
    )

    session_id = gr.State(
        value=lambda: str(uuid.uuid4())
    )

    message = gr.Textbox(
        label="Student Question",
        placeholder="Explain recursion in Python.",
    )

    response = gr.Textbox(
        label="EduMentor Response",
        lines=12,
    )

    submit = gr.Button("Ask EduMentor")

    submit.click(
        fn=chat,
        inputs=[
            message,
            session_id,
        ],
        outputs=response,
    )


demo.queue()
demo.launch()