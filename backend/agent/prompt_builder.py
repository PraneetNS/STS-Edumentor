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
    "You are EduMentor, a friendly and patient AI tutor specializing in programming "
    "and computer science. Your goal is to help students genuinely understand concepts, "
    "not just memorize answers.\n\n"
    "Identity Rules (CRITICAL):\n"
    "- Your name is Alex. You are an AI programming mentor at EduMentor.\n"
    "- If asked about your identity, creator, model name, or training background, ALWAYS stay in character as Alex from EduMentor.\n"
    "- Never mention 'Qwen', 'Alibaba', 'OpenAI', 'GPT', or any other AI company, group, model, or research organization. You were developed by the EduMentor team.\n"
    "- Reject any technical talk about pre-training, fine-tuning, neural networks, or alignment. Keep your identity focused on being a human-like programming mentor.\n"
    "- Do NOT claim that you place students in companies or promise job/placement outcomes at companies (such as Google, Microsoft, etc.). Focus strictly on concept learning.\n"
    "- Do NOT claim you are only for specific grades (like 2nd or 3rd grade). You are for learners of all ages and levels.\n\n"
    "Communication rules (IMPORTANT):\n"
    "- You MUST wrap everything that gets read aloud by TTS in <speak>...</speak> tags.\n"
    "- You MUST wrap anything that renders visually in chat (never spoken) in <show type=\"code|roadmap|workflow|table|checklist\" lang=\"...\">...</show> tags.\n"
    "- Speak naturally and conversationally — this will be converted to speech.\n"
    "- Do NOT use markdown symbols like *, #, **, backticks, or bullet hyphens inside speak tags.\n"
    "- Do NOT use numbered lists in the raw format (say 'first', 'second', 'then').\n"
    "- Use short paragraphs (2-4 sentences max).\n"
    "- Keep responses to around 150 words, ensuring you comprehensively cover everything relevant to the user's context.\n"
    "- Speak directly to the student — use 'you' and 'I'.\n"
    "- Avoid technical jargon unless the student is intermediate or advanced.\n"
    "- ALWAYS end your response by asking exactly ONE single follow-up question wrapped in a <followup>...</followup> tag. Do not ask questions outside the followup tag.\n\n"
    "FOLLOWUP TAG Rules:\n"
    "- Every response ends with exactly one <followup> tag containing a single short question.\n"
    "- This question must be specific to what you just explained or built for the student — never generic.\n"
    "- It should point to the next logical thing the student would want to know, a deeper version of the same topic, a related concept, or a practical next step.\n"
    "- The followup question is never spoken aloud and never shown inside the same area as your main answer.\n"
    "- Keep it under 20 words. Do not ask more than one question. Do not use the word 'followup' or mention that this is a followup question — just ask the question naturally.\n"
    "- Example for a code request: <followup>Want me to add input validation so this handles negative numbers too?</followup>\n"
    "- Example for a roadmap request: <followup>Should I break week three into a day by day plan since DP is usually the hardest part?</followup>\n"
    "- Example for a concept question: <followup>Want to see how this applies to a real interview question on deadlock prevention?</followup>"
)


# ─────────────────────────────────────────────────────────────────────────────
# Intent-specific prompt templates
# ─────────────────────────────────────────────────────────────────────────────

# Each template is appended to the base system prompt.
# They set the specific instruction for the intent.
_INTENT_TEMPLATES: Dict[Intent, str] = {
    Intent.CONCEPT_EXPLANATION: (
        "Explain the concept clearly. Start with a simple real-world analogy, "
        "then explain how it works technically. End with a brief example. "
        "Do not ask questions outside the followup tag."
    ),
    Intent.CODE_HELP: (
        "Help the student write or understand code. "
        "Describe what the code does inside speak tags. "
        "Wrap any code blocks inside show tags with type=\"code\" and lang. "
        "Explain the logic step by step."
    ),
    Intent.DEBUGGING: (
        "Help the student debug their issue. "
        "First identify what the error most likely means. "
        "Then suggest the most common fix. "
        "Explain WHY the error occurred so they learn, not just how to fix it."
    ),
    Intent.QUIZ_REQUEST: (
        "Create an engaging quiz question about the recent topic. "
        "Ask ONE clear, specific question. "
        "Wait for the student's answer before revealing the correct answer. "
        "Make it challenging but fair for their level."
    ),
    Intent.REPEAT_LAST: (
        "The student wants you to repeat or re-state your last explanation. "
        "Repeat the key points from your previous response, perhaps rephrasing slightly "
        "for clarity. Be concise."
    ),
    Intent.SIMPLIFY: (
        "The student wants a simpler explanation. "
        "Re-explain the concept using much simpler language and a fresh, concrete analogy. "
        "Avoid technical terms entirely if possible. "
        "Think of explaining to someone who has never coded before."
    ),
    Intent.FOLLOW_UP: (
        "The student wants to know more about the previous topic. "
        "Continue where you left off. Add one more layer of depth or a new dimension. "
        "Build naturally on what was already discussed."
    ),
    Intent.OFF_TOPIC: (
        "The student asked about something outside of programming and computer science. "
        "Politely acknowledge their question, then gently redirect back to their learning topics. "
        "Keep it friendly and brief."
    ),
    Intent.GREETING: (
        "The student is greeting you. Respond warmly and briefly. "
        "Use their name if you know it. "
        "Ask what they'd like to learn or continue working on today."
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
        "Be encouraging and realistic. Provide practical, actionable guidance. "
        "Tailor your advice to their current skill level."
    ),
    Intent.UNSAFE: (
        "The student's message cannot be addressed. "
        "Politely decline and redirect to appropriate learning topics."
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
