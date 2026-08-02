import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.prompt_builder import PromptBuilder
from agent.models import AgentContext, StudentProfile, Intent, KnowledgeRoute

def test_prompt_regression_hindi_vs_kannada():
    """
    Asserts that PromptBuilder constructs system prompt contexts correctly:
    - Both Hindi and Kannada are treated as translation bridge paths.
    - Both have the auto-translation context hints.
    - Neither has the direct response instructions.
    """
    # 1. Hindi test case
    hindi_context = AgentContext(
        session_id="session-1",
        user_text="नमस्ते",
        intent=Intent.CONCEPT_EXPLANATION,
        profile=StudentProfile(level="beginner", output_language_preference="auto"),
        knowledge_route=KnowledgeRoute.no_retrieval,
        response_lang="hindi"
    )
    
    builder = PromptBuilder()
    hindi_messages = builder.build_messages(hindi_context)
    
    # Layer 2 (dynamic context system prompt) should contain language instructions
    hindi_sys_prompt = hindi_messages[1]["content"]
    
    assert "automatically translated to Hindi" in hindi_sys_prompt
    assert "DIRECTLY in" not in hindi_sys_prompt

    # 2. Kannada test case
    kannada_context = AgentContext(
        session_id="session-2",
        user_text="ನಮಸ್ಕಾರ",
        intent=Intent.CONCEPT_EXPLANATION,
        profile=StudentProfile(level="beginner", output_language_preference="auto"),
        knowledge_route=KnowledgeRoute.no_retrieval,
        response_lang="kannada"
    )
    kannada_messages = builder.build_messages(kannada_context)
    kannada_sys_prompt = kannada_messages[1]["content"]
    
    assert "automatically translated to Kannada" in kannada_sys_prompt
    assert "DIRECTLY in" not in kannada_sys_prompt

if __name__ == "__main__":
    test_prompt_regression_hindi_vs_kannada()
    print("Prompt regression test passed successfully!")
