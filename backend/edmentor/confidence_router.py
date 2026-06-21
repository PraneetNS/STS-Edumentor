class StreamingDualParser:
    """
    StreamingDualParser parses structured markup tags from the LLM stream.
    Supports <speak>, <show>, and <followup> tags.
    """
    def __init__(self) -> None:
        self.buffer: str = ""
