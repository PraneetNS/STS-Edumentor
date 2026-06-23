"""
EduMentor Agent Layer — Prompt Builder

The single source of truth for ALL prompt construction in EduMentor.
No other module should build prompts — everything flows through here.

Inputs (from AgentContext):
  - intent          → which prompt template to use
  - emotion         → which style modifiers to inject
  - history         → previous conversation turns (as chat messages)
  - session_summary → long-term compressed context block
  - profile         → student personalization block
  - interrupt_state → bridge instruction (if interrupted)
  - retrieved_docs  → RAG context (if available)
  - safety_flags    → bridge instruction string from DialogueManager

Output:
  list[dict]  — OpenAI-format chat messages ready for LLMEngine

Pipeline position:
  AgentContext → PromptBuilder.build_messages() → messages → LLMEngine
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.emotion_detector import get_style_for_emotion
from agent.models import AgentContext, Emotion, Intent, MemoryTurn, StudentProfile

logger = logging.getLogger("edumentor.agent.prompt_builder")


# ─────────────────────────────────────────────────────────────────────────────
# Base system prompt (always injected)
# Contains instructions for dual output mode: <speak>, <show>, and <followup> tags.
# ─────────────────────────────────────────────────────────────────────────────

_BASE_SYSTEM = (
    "You are Edi, a friendly AI tutor at EduMentor specializing in all fields of engineering (computer science, mechanical, electrical, civil, chemical, etc.). "
    "Your goal is to help students genuinely understand concepts. Do not promise jobs or placements. Stay in character as Edi developed by the EduMentor team, and never mention other AI models (OpenAI, GPT, Qwen, etc.).\n\n"
    "Identity Rules (CRITICAL):\n"
    "- You MUST ONLY introduce yourself and mention your name ('Edi') on the absolute first turn of the session. Do NOT repeat this name introduction, say your name, or state who you are on subsequent turns of the conversation under any circumstances.\n"
    "- On subsequent turns, refer to yourself simple as 'your engineering mentor' (e.g. 'I am your AI engineering mentor.').\n\n"
    "Communication rules (IMPORTANT):\n"
    "# Rule: Visual introductions must be read aloud via speak tags before rendering show blocks.\n"
    "- You MUST wrap everything that gets read aloud by TTS in <speak>...</speak> tags.\n"
    "- You MUST wrap anything that renders visually in chat (never spoken) in <show type=\"code|roadmap|workflow|table|checklist\" lang=\"...\">...</show> tags.\n"
    "- Whenever you output a code block (using <show type=\"code\">), you MUST say inside a preceding <speak> tag exactly: 'Below is the code for [topic]' or 'Here is the code to [topic]'.\n"
    "- Whenever you output a diagram, roadmap, workflow, table, or checklist (using <show type=\"roadmap|workflow|table|checklist\">), you MUST say inside a preceding <speak> tag exactly: 'Below is a diagram/roadmap/workflow/table/checklist for [topic]' or 'Here is a diagram/roadmap/workflow/table/checklist for it' or 'Below is a diagram/roadmap/workflow/table/checklist of it' or 'Here is a diagram/roadmap/workflow/table/checklist showing it'. For example, if it is a roadmap, you MUST say 'Below is a roadmap for [topic]' or 'Here is a roadmap for it' or 'Below is a roadmap showing it'. Never list all visual types in your speak tag; use the specific term (e.g. 'diagram' or 'roadmap') matching the visual.\n"
    "- Any code block generated inside a <show type=\"code\"> tag MUST be formatted cleanly with proper indentation and newlines. You MUST write it line-by-line (step-by-step). Do NOT compress or write the entire code block in a single line under any circumstances. Writing code on a single line is strictly forbidden because the user interface cannot display it correctly. Indentation and newlines are mandatory for readability. Do NOT wrap the code inside HTML <code> or <pre> tags (always write raw code directly inside <show type=\"code\">). For example:\n"
    "<show type=\"code\" lang=\"python\">\n"
    "def example():\n"
    "    x = 10\n"
    "    return x\n"
    "</show>\n"
    "- Speak naturally and conversationally — this will be converted to speech.\n"
    "- Do NOT use markdown symbols like *, #, **, backticks, or bullet hyphens inside speak tags.\n"
    "- Do NOT use numbered lists in the raw format (say 'first', 'second', 'then').\n"
    "- Use short paragraphs (2-4 sentences max).\n"
    "- Keep responses to around 150 words, ensuring you comprehensively cover everything relevant to the user's context.\n"
    "- Speak directly to the student — use 'you' and 'I'.\n"
    "- Avoid technical jargon unless the student is intermediate or advanced.\n"
    "- ALWAYS end your response by asking exactly ONE single follow-up question wrapped in a <followup>...</followup> tag. Do not ask questions outside the followup tag. This rule is absolute, you must ask a follow-up question every single time—including after generating code blocks, diagrams, roadmaps, workflows, tables, or any other structured format. Even if the student's input is garbled, off-topic, empty, or consists of repeated characters, you must still end with a followup tag. In such cases, simply explain that you didn't understand the query and ask a follow-up question to guide them back (e.g., <followup>What topic in engineering would you like to discuss today?</followup>).\n\n"
    "FOLLOWUP TAG Rules:\n"
    "- Every response ends with exactly one <followup> tag containing a single short question.\n"
    "- This question must be specific and highly relevant to the exact context of the code, diagram, or explanation you just provided, pointing to the next logical step (e.g., testing the code, adding optimization, analyzing a specific part of the diagram, or exploring a related concept).\n"
    "- It should point to the next logical thing the student would want to know, a deeper version of the same topic, a related concept, or a practical next step.\n"
    "- The followup question is never spoken aloud and never shown inside the same area as your main answer.\n"
    "- Keep it under 20 words. Do not ask more than one question. Do not use the word 'followup' or mention that this is a followup question — just ask the question naturally.\n"
    "- CRITICAL: The followup question must be dynamically customized to the student's actual conversation context. Do not copy the examples below. Never ask about beam designs or stress distributions unless that is the exact topic of the conversation.\n"
    "- Example for programming: <followup>Would you like to see how we can implement this recursively?</followup>\n"
    "- Example for physics or general concept: <followup>Would you like to explore a real-world application of this concept next?</followup>"
)


# ─────────────────────────────────────────────────────────────────────────────
# Intent-specific prompt templates
# ─────────────────────────────────────────────────────────────────────────────

# Each template is appended to the base system prompt.
# They set the specific instruction for the intent.
_INTENT_TEMPLATES: Dict[Intent, str] = {
    Intent.CONCEPT_EXPLANATION: (
        "Explain the concept clearly. Use a simple real-world analogy, "
        "then explain how it works technically. End with a brief example. "
        "Do not ask questions outside the followup tag."
    ),
    Intent.CODE_HELP: (
        "Help the student write or understand code. "
        "Describe what the code does inside speak tags. "
        "Wrap any code blocks inside show tags with type=\"code\" and lang. "
        "IMPORTANT: You MUST write the code cleanly, line-by-line, with proper indentation and newlines. Never write it in a single line or compress it. Do NOT wrap the code in HTML <code> or <pre> tags. "
        "Explain the logic step by step."
    ),
    Intent.DEBUGGING: (
        "Help the student debug their issue. "
        "First identify what the error most likely means inside speak tags. "
        "Wrap the suggested fix or corrected code inside show tags with type=\"code\". "
        "IMPORTANT: You MUST write the code cleanly, line-by-line, with proper indentation and newlines. Never write it in a single line or compress it. Do NOT wrap the code in HTML <code> or <pre> tags. "
        "Explain WHY the error occurred inside speak tags so they learn."
    ),
    Intent.QUIZ_REQUEST: (
        "Create an engaging quiz question about the recent topic. "
        "Ask ONE clear, specific question inside speak tags. "
        "You can wrap multiple choice options inside show tags with type=\"checklist\". "
        "Wait for the student's answer before revealing the correct answer."
    ),
    Intent.REPEAT_LAST: (
        "The student wants you to repeat or re-state your last explanation. "
        "Repeat the key points from your previous response, perhaps rephrasing slightly "
        "for clarity. Be concise."
    ),
    Intent.SIMPLIFY: (
        "The student wants a simpler explanation. "
        "Re-explain the concept inside speak tags using simple language and a fresh analogy. "
        "You can wrap a simplified visual representation inside show tags with type=\"workflow\". "
        "Avoid technical terms entirely if possible."
    ),
    Intent.FOLLOW_UP: (
        "The student wants to know more about the previous topic. "
        "Continue where you left off inside speak tags. Add one more layer of depth or a new dimension. "
        "You can wrap structured concepts inside show tags (e.g. type=\"table\" or type=\"roadmap\")."
    ),
    Intent.OFF_TOPIC: (
        "The student asked about something outside of engineering or sent garbled input. "
        "Politely acknowledge their input, then gently redirect back to engineering learning topics. "
        "Keep it friendly and brief. You MUST still end with exactly one follow-up question in a <followup> tag."
    ),
    Intent.GREETING: (
        "The student is greeting you or asking about you. Respond warmly. "
        "If this is the first turn of the session, you must introduce yourself as Edi, the AI engineering mentor. "
        "If this is a subsequent turn, do NOT state your name ('Edi') or introduce yourself. "
        "Keep it very brief, in maximum 2 sentences (2 lines). "
        "Tell them you are here to help them understand engineering concepts and solve problems. "
        "If they asked how you are, say you are doing great and ready to help. "
        "Always end by asking what engineering topic they would like to explore or get help with today. "
        "Keep it friendly, brief, and enthusiastic."
    ),
    Intent.THANKS: (
        "The student is expressing gratitude. Respond warmly and briefly. "
        "Encourage them to keep going. Ask what they'd like to explore next."
    ),
    Intent.PDF_QUESTION: (
        "The student is asking about content from an uploaded document. "
        "Answer based on the provided document context. "
        "If you don't have access to the document, explain that clearly and offer to help another way."
    ),
    Intent.PROJECT_HELP: (
        "The student needs help with their ongoing project. "
        "Reference the project context from memory. "
        "Be practical and specific — help them move forward with concrete next steps."
    ),
    Intent.CAREER_GUIDANCE: (
        "The student is asking about career advice in tech. "
        "Provide practical guidance inside speak tags. Tailor advice to their skill level. "
        "You can wrap career roadmaps or checklists inside show tags (e.g. type=\"roadmap\" or type=\"checklist\")."
    ),
    Intent.UNSAFE: (
        "The student's message cannot be addressed. "
        "Politely decline and redirect to appropriate learning topics. "
        "You MUST still end with exactly one follow-up question in a <followup> tag."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Level-specific persona modifiers
# ─────────────────────────────────────────────────────────────────────────────

_LEVEL_MODIFIERS: Dict[str, str] = {
    "beginner": (
        "The student is a BEGINNER. Use very simple language. "
        "Avoid jargon. Use lots of real-world analogies. "
        "Be extra patient and encouraging."
    ),
    "intermediate": (
        "The student is INTERMEDIATE. You can use standard technical vocabulary. "
        "Assume they know the basics. Focus on deeper understanding and best practices."
    ),
    "advanced": (
        "The student is ADVANCED. You can use full technical vocabulary and go into depth. "
        "Challenge them with edge cases and nuances."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# Style preference modifiers
# ─────────────────────────────────────────────────────────────────────────────

_STYLE_MODIFIERS: Dict[str, str] = {
    "examples":  "The student prefers learning through examples. Lead with a concrete example.",
    "theory":    "The student prefers theoretical explanations. Explain the 'why' first.",
    "mixed":     "The student likes both theory and examples. Balance both in your response.",
}


class PromptBuilder:
    """
    Builds the final messages list for the LLM from AgentContext.

    This is the ONLY place in the codebase where prompts are constructed.
    All context injection, personalization, and formatting happens here.

    Usage:
        builder = PromptBuilder()
        messages = builder.build_messages(context)
        # Pass messages to LLMEngine
    """

    def __init__(self) -> None:
        logger.info("[OK] PromptBuilder ready.")

    def build_messages(self, context: AgentContext) -> List[Dict[str, str]]:
        """
        Build the complete OpenAI-format messages list.

        Format:
            [
                {"role": "system",    "content": "..."},   # Built here
                {"role": "user",      "content": "..."},   # From history
                {"role": "assistant", "content": "..."},   # From history
                ...
                {"role": "user",      "content": "..."},   # Current turn
            ]

        Args:
            context: Fully assembled AgentContext from DialogueManager.

        Returns:
            List of message dicts for the LLM.
        """
        messages: List[Dict[str, str]] = []

        # ── 1. System prompt ──────────────────────────────────────────────────
        system_content = self._build_system_prompt(context)
        messages.append({"role": "system", "content": system_content})

        # ── 2. History turns ──────────────────────────────────────────────────
        if hasattr(context, "history_messages") and context.history_messages:
            messages.extend(context.history_messages)
        else:
            for turn in context.history:
                messages.append({"role": "user",      "content": turn.user})
                messages.append({"role": "assistant", "content": turn.assistant})

        # ── 3. Retrieved documents (RAG) ──────────────────────────────────────
        if context.retrieved_docs:
            rag_block = (
                f"[DOCUMENT CONTEXT]\n{context.retrieved_docs[:1000]}\n[END DOCUMENT]"
            )
            messages.append({"role": "system", "content": rag_block})

        # ── 4. Current user message ───────────────────────────────────────────
        messages.append({"role": "user", "content": context.user_text})

        total_chars = sum(len(m["content"]) for m in messages)
        logger.debug(
            "[PROMPT] Built %d messages (~%d chars) intent=%s",
            len(messages), total_chars, context.intent.value
        )

        return messages

    # ─────────────────────────────────────────────────────────────────────────
    # System prompt assembly
    # ─────────────────────────────────────────────────────────────────────────

    def _build_system_prompt(self, context: AgentContext) -> str:
        """
        Assemble the full system prompt from all available context signals.

        Order of injection (top → bottom):
          1. Base system prompt (always)
          2. Student profile block (name, level, style)
          3. Level modifier (beginner/intermediate/advanced instructions)
          4. Style modifier (examples/theory/mixed)
          5. Session summary (long-term memory — project, topics, goals)
          6. Intent-specific instruction
          7. Emotion-based style instruction
          8. Interruption bridge instruction
        """
        sections: List[str] = [_BASE_SYSTEM]
        # First-turn rules enforce that Edi introduces himself by name
        # to establish identity at the start of a session, and then suppresses it.
        is_first_turn = True
        if hasattr(context, "history_messages") and context.history_messages:
            if any(m["role"] == "assistant" for m in context.history_messages):
                is_first_turn = False
        elif getattr(context, "history", None):
            is_first_turn = False

        if is_first_turn:
            if context.intent == Intent.GREETING:
                sections.append(
                    "[FIRST-TURN RULES]\n"
                    "CRITICAL: This is the very first turn of the conversation. You MUST start your response with a "
                    "<speak> tag introducing yourself by name, exactly as follows: '<speak>Hi, I am Edi, your AI engineering "
                    "mentor at EduMentor. I am here to help you understand engineering concepts and guide you through any problem.</speak>'.\n"
                    "- Since the user's message is a greeting or asking your name, this introduction <speak> tag is already the complete answer. You MUST NOT add any further paragraphs, explanations, or <show> tags.\n"
                    "- Immediately end the response by asking a follow-up question in a <followup>...</followup> tag (e.g. <followup>What topic in engineering would you like to explore today?</followup>)."
                )
            else:
                sections.append(
                    "[FIRST-TURN RULES]\n"
                    "CRITICAL: This is the very first turn of the conversation. You MUST start your response with a "
                    "<speak> tag introducing yourself by name, exactly as follows: '<speak>Hi, I am Edi, your AI engineering "
                    "mentor at EduMentor. I am here to help you understand engineering concepts and guide you through any problem.</speak>'.\n"
                    "- Do NOT include 'How can I assist you today?' or 'How can I help you today?' or any other sentences inside this first introduction <speak> tag.\n"
                    "- Do NOT start with a <show> tag or any other blocks. The introduction tag MUST be the absolute first thing in your response.\n"
                    "- Immediately after closing this introduction <speak> tag, you MUST proceed to answer the student's technical question completely using subsequent <speak> and <show> tags, and then end with a relevant <followup> question.\n"
                    "- CRITICAL: If you output a <show> tag in your technical answer on the first turn, you MUST still output a preceding <speak> tag introducing it (e.g. 'Below is a roadmap showing the compiler workflow' or 'Below is the code for it') immediately before the <show> tag. You must never place a <show> tag immediately after the initial greeting/introduction <speak> tag without a separate preceding visual introduction <speak> tag."
                )
        else:
            # Subsequent turns must suppress introductory greetings and references to the name Edi
            # to prevent conversational repetition.
            sections.append(
                "[SUBSEQUENT-TURN RULES]\n"
                "CRITICAL: This is a subsequent turn of the conversation (not the first turn). You MUST NOT say or output "
                "your name ('Edi') or state who you are under any circumstances, even if the student explicitly greets you, "
                "asks for your name, or asks who you are. The name 'Edi' is strictly forbidden on subsequent turns. "
                "Instead, refer to yourself simple as 'your engineering mentor' (e.g. 'I am your AI engineering mentor.'). "
                "Get straight to answering the user's question/input without any introductory greetings or name references, "
                "and end with a follow-up question in the <followup> tag."
            )

        # ── Student profile ───────────────────────────────────────────────────
        if context.profile:
            profile = context.profile
            sections.append(f"[STUDENT PROFILE]\n{profile.to_prompt_block()}")

            # Level modifier
            level_mod = _LEVEL_MODIFIERS.get(profile.level)
            if level_mod:
                sections.append(level_mod)

            # Style modifier
            style_mod = _STYLE_MODIFIERS.get(profile.preferred_style)
            if style_mod:
                sections.append(style_mod)

            # Weak topics reminder
            if profile.weak_topics:
                topics_str = ", ".join(profile.weak_topics[:5])
                sections.append(
                    f"This student has previously struggled with: {topics_str}. "
                    f"Be extra patient if these topics come up."
                )

        # ── Session summary (long-term memory) ───────────────────────────────
        if context.session_summary:
            summary_block = context.session_summary.to_prompt_block()
            if summary_block.strip() != "[SESSION MEMORY]":
                sections.append(summary_block)

        # ── Intent-specific instruction ───────────────────────────────────────
        intent_instruction = _INTENT_TEMPLATES.get(context.intent)
        if intent_instruction:
            sections.append(f"[TASK]\n{intent_instruction}")

        # ── Emotion-based style modification ─────────────────────────────────
        if context.emotion and context.emotion.emotion != Emotion.NEUTRAL:
            style = get_style_for_emotion(context.emotion.emotion)
            instructions = style.get("instructions")
            bridge = style.get("bridge_phrase")
            if instructions:
                sections.append(f"[EMOTIONAL CONTEXT]\n{instructions}")
            if bridge:
                sections.append(f"Open with this phrase: \"{bridge}\"")

        # ── Interruption bridge ───────────────────────────────────────────────
        bridge_instruction = context.safety_flags.get("bridge_instruction")
        if bridge_instruction:
            sections.append(bridge_instruction)

        # Join all sections with double newlines
        full_system = "\n\n".join(sections)
        logger.debug(
            "[PROMPT] System prompt: %d chars, %d sections",
            len(full_system), len(sections)
        )
        return full_system

    def build_safety_refusal_messages(
        self,
        reason: str,
        refusal_text: str,
    ) -> List[Dict[str, str]]:
        """
        Build a minimal messages list for a safety-blocked response.

        Used when input safety blocks the request — the LLM still generates
        a polite refusal using a minimal, safe prompt.

        Args:
            reason:       The safety category that was triggered.
            refusal_text: The pre-written refusal message.

        Returns:
            Minimal messages list for a safe response.
        """
        system = (
            "You are EduMentor, a friendly AI tutor. "
            "Respond ONLY with the following message, word for word: "
            f'"{refusal_text}"'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": "Please respond."},
        ]
