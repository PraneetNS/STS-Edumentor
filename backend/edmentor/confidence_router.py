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

        while True:
            speak_match = SPEAK_RE.search(self.buffer)
            show_match = SHOW_RE.search(self.buffer)
            followup_match = FOLLOWUP_RE.search(self.buffer)

            # Find which complete tag starts first in the buffer
            best_match = None
            best_start = len(self.buffer)
            match_type = None

            if speak_match and speak_match.start() < best_start:
                best_match = speak_match
                best_start = speak_match.start()
                match_type = "speak"

            if show_match and show_match.start() < best_start:
                best_match = show_match
                best_start = show_match.start()
                match_type = "show"

            if followup_match and followup_match.start() < best_start:
                best_match = followup_match
                best_start = followup_match.start()
                match_type = "followup"

            if not best_match:
                break

            # Placeholder to process best_match, then advance buffer
            break

        return events
