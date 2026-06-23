import re
from typing import Generator, Dict, Optional

class RealtimeStreamingParser:
    """
    State-based real-time streaming parser for LLM responses.
    Parses <speak>, <show>, <followup> tags, <code>, </code>, and standard markdown code fences (```)
    character-by-character to allow immediate streaming to the UI and TTS engines.
    Also supports curly-brace formats like {speak}, {show}, and {followup}.
    """
    def __init__(self) -> None:
        self.buffer = ""
        self.state = "OUTSIDE"  # OUTSIDE, SPEAK, SHOW, FOLLOWUP, CODE_MD
        self.verbalized_show = False
        self.show_buffer = ""
        self.show_type = "code"
        self.show_lang = "python"

    def feed(self, chunk: str) -> Generator[Dict[str, str], None, None]:
        """
        Feed a token chunk to the parser and yield parsed events:
        {"raw": text_for_frontend, "planned": text_for_tts}

        Processes incoming text streams incrementally, identifying tags and text blocks,
        and manages transitions between speak, show, and followup states.
        """
        if not chunk:
            return
        
        self.buffer += chunk

        while self.buffer:
            # Check if the buffer starts with a potential tag
            if self._is_potential_tag_start(self.buffer):
                matched_tag = self._check_complete_tag()
                if matched_tag:
                    yield from self._handle_tag(matched_tag)
                    continue
                else:
                    # It's a prefix of a tag but not complete yet, wait for more tokens
                    break
            
            # If it's not a tag prefix, consume the first character as regular text
            char = self.buffer[0]
            self.buffer = self.buffer[1:]
            yield from self._handle_char(char)

    def finalize(self) -> Generator[Dict[str, str], None, None]:
        """
        Flush any remaining buffer at the end of the stream.
        """
        while self.buffer:
            matched_tag = self._check_complete_tag()
            if matched_tag:
                yield from self._handle_tag(matched_tag)
                continue
                
            char = self.buffer[0]
            self.buffer = self.buffer[1:]
            yield from self._handle_char(char)

        # Flush any remaining show buffer if we end in the middle of a show block
        if self.state == "SHOW" and self.show_buffer:
            yield from self._yield_show_content()

    def _is_potential_tag_start(self, text: str) -> bool:
        """
        Determine if the beginning of the text could be the start of a tag.
        """
        if text.startswith("<"):
            if ">" not in text:
                templates = ["<speak>", "</speak>", "<show", "</show>", "<followup>", "</followup>", "<code>", "</code>"]
                for t in templates:
                    if t.startswith(text) or text.startswith(t):
                        return True
                return False
            else:
                tag_match = re.match(r"^</?([a-zA-Z]+)(?:\s+[^>]*)?>", text)
                if tag_match:
                    tag_name = tag_match.group(1).lower()
                    return tag_name in ("speak", "show", "followup", "code")
                return False

        if text.startswith("{"):
            if "}" not in text:
                templates = ["{speak}", "{/speak}", "{show", "{/show}", "{followup}", "{/followup}", "{code}", "{/code}"]
                for t in templates:
                    if t.startswith(text) or text.startswith(t):
                        return True
                return False
            else:
                tag_match = re.match(r"^\{/?([a-zA-Z]+)(?:\s+[^}]*)?\}", text)
                if tag_match:
                    tag_name = tag_match.group(1).lower()
                    return tag_name in ("speak", "show", "followup", "code")
                return False

        if text.startswith("`"):
            return len(text) < 3

        return False

    def _check_complete_tag(self) -> Optional[str]:
        """
        Check if the buffer starts with a complete known tag or code fence.
        """
        # Angle bracket tags
        if self.buffer.startswith("<speak>"):
            return "<speak>"
        if self.buffer.startswith("</speak>"):
            return "</speak>"
        if self.buffer.startswith("</show>"):
            return "</show>"
        if self.buffer.startswith("<followup>"):
            return "<followup>"
        if self.buffer.startswith("</followup>"):
            return "</followup>"
        if self.buffer.startswith("<code>"):
            return "<code>"
        if self.buffer.startswith("</code>"):
            return "</code>"

        # Curly brace tags
        if self.buffer.startswith("{speak}"):
            return "{speak}"
        if self.buffer.startswith("{/speak}"):
            return "{/speak}"
        if self.buffer.startswith("{/show}"):
            return "{/show}"
        if self.buffer.startswith("{show}"):
            return "{show}"
        if self.buffer.startswith("{followup}"):
            return "{followup}"
        if self.buffer.startswith("{/followup}"):
            return "{/followup}"
        if self.buffer.startswith("{code}"):
            return "{code}"
        if self.buffer.startswith("{/code}"):
            return "{/code}"

        if self.buffer.startswith("```"):
            return "```"
        
        # Match <show type="..." lang="...">
        if self.buffer.startswith("<show"):
            match = re.match(r"^<show(?:\s+[^>]*)?>", self.buffer)
            if match:
                return match.group(0)

        # Match {show type="..." lang="..."}
        if self.buffer.startswith("{show"):
            match = re.match(r"^\{show(?:\s+[^}]*)?\}", self.buffer)
            if match:
                return match.group(0)
                
        return None

    def _handle_tag(self, tag: str) -> Generator[Dict[str, str], None, None]:
        """
        Consume the matched tag and transition states accordingly.
        """
        self.buffer = self.buffer[len(tag):]

        if tag in ("<speak>", "{speak}"):
            self.state = "SPEAK"
            yield {"raw": "", "planned": ""}
        elif tag in ("</speak>", "{/speak}"):
            self.state = "OUTSIDE"
            yield {"raw": "", "planned": ""}
        elif tag in ("<followup>", "{followup}"):
            # Transition to FOLLOWUP state — followup text is hidden from chat and TTS
            self.state = "FOLLOWUP"
            yield {"raw": "", "planned": ""}
        elif tag in ("</followup>", "{/followup}"):
            self.state = "OUTSIDE"
            yield {"raw": "", "planned": ""}
        elif tag in ("<code>", "</code>", "{code}", "{/code}"):
            # Ignore and strip code tags entirely
            yield {"raw": "", "planned": ""}
        elif tag.startswith("<show") or tag.startswith("{show"):
            if tag in ("<show>", "{show}"):
                if self.state == "SHOW":
                    # Ignore redundant/duplicate show tag inside show state
                    yield {"raw": "", "planned": ""}
                else:
                    self.state = "SHOW"
                    self.show_type = "code"
                    self.show_lang = "python"
                    self.show_buffer = ""
                    yield {"raw": "", "planned": ""}
            else:
                self.state = "SHOW"
                type_match = re.search(r'type="([^"]*)"', tag)
                self.show_type = type_match.group(1) if type_match else "code"
                
                lang_match = re.search(r'lang="([^"]*)"', tag)
                self.show_lang = lang_match.group(1) if lang_match else "python"
                self.show_buffer = ""
                yield {"raw": "", "planned": ""}
        elif tag in ("</show>", "{/show}"):
            if self.state == "SHOW":
                yield from self._yield_show_content()
            else:
                yield {"raw": "", "planned": ""}
        elif tag == "```":
            if self.state == "CODE_MD":
                self.state = "OUTSIDE"
                yield {"raw": "\n```\n\n", "planned": ""}
            else:
                self.state = "CODE_MD"
                yield {
                    "raw": "\n\n```python\n",
                    "planned": "" if self.verbalized_show else "[I have shown a code example on the screen.] "
                }
                self.verbalized_show = True

    def _yield_show_content(self) -> Generator[Dict[str, str], None, None]:
        cleaned = self.show_buffer.strip()

        # Strip any XML-style tags the LLM placed inside the show block
        # e.g. <checklist>...</checklist>, <item>...</item>, <step>...</step>
        cleaned = re.sub(r"</?(?:checklist|item|step|li|ul|ol|entry|pre|code)>", "", cleaned, flags=re.IGNORECASE)
        
        # Strip leading/trailing JSON/string wrappers
        if cleaned.startswith("{") and cleaned.endswith("}"):
            cleaned = cleaned[1:-1].strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1].strip()
        if cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1].strip()
            
        # Unescape newlines and tabs
        cleaned = cleaned.replace("\\n", "\n").replace("\\t", "\t")
        cleaned = cleaned.strip()
        
        if self.show_type == "roadmap":
            lines_raw = cleaned.split("\n")
            non_empty = [l.strip() for l in lines_raw if l.strip()]
            
            # Extract an optional title from the first non-step line
            roadmap_title = "Roadmap"
            start_idx = 0
            if non_empty and not re.match(r"^(?:Step\s+)?\d+", non_empty[0], re.IGNORECASE):
                roadmap_title = non_empty[0]
                start_idx = 1
            
            formatted_lines = []
            for line in non_empty[start_idx:]:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"^(?:Step\s+)?(\d+)[:.]?\s*(.*)$", line, re.IGNORECASE)
                if match:
                    step_num = match.group(1)
                    step_text = match.group(2)
                    parts = re.split(r"([-—:])", step_text, maxsplit=1)
                    if len(parts) == 3:
                        title = parts[0].strip()
                        sep = parts[1]
                        desc = parts[2].strip()
                        formatted_lines.append(f"{step_num}. **{title}** {sep} {desc}")
                    else:
                        formatted_lines.append(f"{step_num}. {step_text}")
                else:
                    formatted_lines.append(line)
            
            roadmap_content = "\n".join(formatted_lines)
            yield {
                "raw": f"\n\n### 🗺️ {roadmap_title}\n{roadmap_content}\n\n",
                "planned": ""
            }
        elif self.show_type == "code":
            yield {
                "raw": f"\n\n```{self.show_lang}\n{cleaned}\n```\n\n",
                "planned": ""
            }
        else:
            yield {
                "raw": f"\n\n### 📋 {self.show_type.capitalize()}\n{cleaned}\n\n",
                "planned": ""
            }
            
        self.show_buffer = ""
        self.state = "OUTSIDE"

    def _handle_char(self, char: str) -> Generator[Dict[str, str], None, None]:
        """
        Process a single character based on the current state.
        """
        if self.state == "SHOW":
            self.show_buffer += char
            yield {"raw": "", "planned": ""}
        elif self.state == "CODE_MD":
            yield {"raw": char, "planned": ""}
        elif self.state == "SPEAK":
            yield {"raw": char, "planned": char}
        elif self.state == "FOLLOWUP":
            # Followup content is hidden from chat and not spoken aloud
            yield {"raw": "", "planned": ""}
        else:
            yield {"raw": char, "planned": char}
