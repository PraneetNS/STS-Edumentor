import re

# Non-greedy matching pattern for <speak>...</speak>
SPEAK_RE = re.compile(r"<speak>(.*?)</speak>", re.DOTALL)

# Non-greedy matching pattern for <show type="..." lang="...">...</show>
SHOW_RE = re.compile(r'<show(?:\s+type="([^"]*)")?(?:\s+lang="([^"]*)")?>(.*?)</show>', re.DOTALL)

# Non-greedy matching for <followup>...</followup>
FOLLOWUP_RE = re.compile(r"<followup>(.*?)</followup>", re.DOTALL)


class StreamingDualParser:
    """
    StreamingDualParser parses structured markup tags from the LLM stream.
    Supports <speak>, <show>, and <followup> tags.
    """
    def __init__(self) -> None:
        self.buffer: str = ""

    def feed(self, chunk: str) -> list[dict]:
        """
        Feed a chunk of streamed text to the parser and parse any complete tags.
        """
        if not chunk:
            return []
        self.buffer += chunk
        events: list[dict] = []
        return events
