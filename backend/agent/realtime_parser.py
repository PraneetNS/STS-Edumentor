import re
from typing import Generator, Dict, Optional


# ── Code reformatter ────────────────────────────────────────────────────────
# When a model collapses all code onto a single line (spaces instead of \n),
# this restores proper multi-line formatting so the frontend renders it correctly.

# Tokens that should be followed by a newline + indent increase
_BLOCK_OPEN = re.compile(
    r'(\{)\s*(?=\S)'          # opening brace with content on same "line"
    r'|(?<=[):\]>])\s*(\{)\s*$',
    re.MULTILINE
)

def _reformat_code(code: str, lang: str) -> str:
    """
    Detect and fix single-line code by restoring newlines at statement boundaries.
    Only runs when the code has no real newlines (i.e. it's one long line).
    Handles Java, C, C++, JavaScript, TypeScript, Python.
    """
    # If the code already has meaningful newlines, leave it alone
    real_lines = [l for l in code.split('\n') if l.strip()]
    if len(real_lines) > 3:
        return code

    lang = (lang or '').lower()

    if lang in ('python', 'py'):
        return _reformat_python(code)
    else:
        # C-family: Java, JS, TS, C, C++, C#, Go, etc.
        return _reformat_c_family(code)


def _reformat_python(code: str) -> str:
    """Reformat collapsed Python code back to multi-line."""
    # Pattern to find statement boundaries:
    # 2 or more spaces followed by a comment, keyword, assignment, or function call
    pattern = r'(?<!\n)(\s{2,})(?=(?:def\b|class\b|return\b|if\b|elif\b|else:|for\b|while\b|try:|except\b|finally:|with\b|import\b|from\b|pass\b|break\b|continue\b|raise\b|yield\b|assert\b|#|[a-zA-Z_][a-zA-Z0-9_]*\s*(?:=|\()))'
    
    # Replace spaces with newline + the same spaces
    result = re.sub(pattern, r'\n\1', code)
    
    # Clean up empty lines and trailing spaces
    lines = result.split('\n')
    cleaned = []
    for line in lines:
        if line.strip():
            cleaned.append(line.rstrip())
    return '\n'.join(cleaned)



def _reformat_c_family(code: str) -> str:
    """Reformat collapsed C/Java/JS code back to multi-line with proper indentation."""
    result = []
    indent = 0
    i = 0
    # Tokenise by { } ; characters which are the statement/block delimiters
    tokens = re.split(r'(\{|\}|;)', code)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token == '{':
            result.append(' {')
            indent += 1
            result.append('\n' + '    ' * indent)
        elif token == '}':
            indent = max(0, indent - 1)
            result.append('\n' + '    ' * indent + '}')
        elif token == ';':
            result.append(';')
            result.append('\n' + '    ' * indent)
        else:
            result.append(token)
    reformed = ''.join(result)
    # Clean up multiple blank lines and trailing spaces
    reformed = re.sub(r'\n\s*\n', '\n', reformed)
    reformed = re.sub(r' +\n', '\n', reformed)
    return reformed.strip()

def looks_like_truncated_code(code_text: str) -> bool:
    """Heuristic check: a code block that ends right after
    a function/class signature with no body is almost
    certainly truncated, not intentional."""
    code = code_text.strip()
    # Strip HTML/markdown code wrapper if present
    code = re.sub(r"^```[\w]*\n", "", code)
    code = re.sub(r"\n```$", "", code)
    code = code.strip()
    
    lines = [l for l in code.split('\n') if l.strip()]
    if len(lines) == 0:
        return False
    last_line = lines[-1].strip()
    # Signature-only patterns across common languages
    signature_only_patterns = [
        r':\s*$',           # Python "def foo():" with nothing after
        r'\{\s*$',          # JS/Java/C "function foo() {" with nothing after
        r'^(def|function|class|public|private|void)\s',
    ]
    if len(lines) == 1 and any(re.search(p, last_line) for p in signature_only_patterns):
        return True
    return False

class RealtimeStreamingParser:
    """
    State-based real-time streaming parser for LLM responses.
    Parses <speak>, <show>, <followup> tags, <code>, </code>, and standard markdown code fences (```)
    character-by-character to allow immediate streaming to the UI and TTS engines.
    Also supports curly-brace formats like {speak}, {show}, and {followup}.
    """
    def __init__(self) -> None:
        self.buffer = ""
        self.state = "OUTSIDE"  # OUTSIDE, SPEAK, SHOW, FOLLOWUP, CODE_MD, JSON
        self.verbalized_show = False
        self.show_buffer = ""
        self.show_type = "code"
        self.show_lang = "python"
        self.spoken_buffer = ""
        self.show_title = ""

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

        # --- JSON format interceptor ---
        # Buffer any `{...}` payload from the first brace until the closing brace.
        stripped = self.buffer.strip()
        if self.state == "JSON" or (self.state == "OUTSIDE" and stripped.startswith("{")):
            if self.state != "JSON":
                self.state = "JSON"
            if not stripped.endswith("}"):
                return
            converted = self._convert_json_payload(stripped)
            if converted is not None:
                self.buffer = converted
            self.state = "OUTSIDE"

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
        if self.state == "JSON" and self.buffer.strip():
            converted = self._convert_json_payload(self.buffer.strip())
            if converted is not None:
                self.buffer = converted
            self.state = "OUTSIDE"

        while self.buffer:
            matched_tag = self._check_complete_tag()
            if matched_tag:
                yield from self._handle_tag(matched_tag)
                continue
            
            # If the remaining buffer is a potential tag start, it means it's an incomplete tag
            # (e.g., "<speak" or "<show type=") at the end of the stream. Discard it to prevent leakage.
            if self._is_potential_tag_start(self.buffer):
                import logging
                logging.getLogger("edumentor.agent.realtime_parser").warning(
                    f"Discarding incomplete tag at end of stream: {self.buffer!r}"
                )
                self.buffer = ""
                break
                
            char = self.buffer[0]
            self.buffer = self.buffer[1:]
            yield from self._handle_char(char)

        # Flush any remaining show buffer if we end in the middle of a show block
        if self.state == "SHOW" and self.show_buffer:
            yield from self._yield_show_content()

    def _is_potential_tag_start(self, text: str) -> bool:
        """
        Determine if the beginning of the text could be the start of a tag.
        Supports case-insensitive prefix checks with optional spaces.
        """
        if text.startswith("<"):
            tag_end = text.find(">")
            if tag_end != -1:
                tag_candidate = text[:tag_end]
            else:
                tag_candidate = text
                
            clean_after = re.sub(r"\s+", "", tag_candidate[1:]).lower()
            has_slash = clean_after.startswith("/")
            clean_name = clean_after[1:] if has_slash else clean_after
            
            # Check if clean_name is a prefix of any valid tag or starts with show
            if clean_name.startswith("show"):
                return True
            for tag_name in ("speak", "show", "followup", "code"):
                if tag_name.startswith(clean_name):
                    return True
            if self.state == "SHOW" and self.show_type == "table" and "table".startswith(clean_name):
                return True
            return False

        if text.startswith("{"):
            tag_end = text.find("}")
            if tag_end != -1:
                tag_candidate = text[:tag_end]
            else:
                tag_candidate = text
                
            clean_after = re.sub(r"\s+", "", tag_candidate[1:]).lower()
            has_slash = clean_after.startswith("/")
            clean_name = clean_after[1:] if has_slash else clean_after
            
            # Check if clean_name is a prefix of any valid tag or starts with show
            if clean_name.startswith("show"):
                return True
            for tag_name in ("speak", "show", "followup", "code"):
                if tag_name.startswith(clean_name):
                    return True
            if self.state == "SHOW" and self.show_type == "table" and "table".startswith(clean_name):
                return True
            return False

        if text.startswith("`"):
            return len(text) < 3

        return False

    def _check_complete_tag(self) -> Optional[str]:
        """
        Check if the buffer starts with a complete known tag or code fence.
        Supports case-insensitivity and spaces inside tags.
        """
        # Angle bracket tags
        # 1. speak
        match = re.match(r"^<\s*speak\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^<\s*/\s*speak\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 2. followup
        match = re.match(r"^<\s*followup\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^<\s*/\s*followup\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 3. code
        match = re.match(r"^<\s*code\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^<\s*/\s*code\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 4. show close
        match = re.match(r"^<\s*/\s*show\s*>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        if self.state == "SHOW" and self.show_type == "table":
            match = re.match(r"^<\s*/\s*table\s*>", self.buffer, re.IGNORECASE)
            if match:
                return match.group(0)
            
        # 5. show open with attributes
        match = re.match(r"^<\s*show(?:\s+[^>]*)?>", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)

        # Curly brace tags
        # 1. speak
        match = re.match(r"^\{\s*speak\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^\{\s*/\s*speak\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 2. followup
        match = re.match(r"^\{\s*followup\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^\{\s*/\s*followup\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 3. code
        match = re.match(r"^\{\s*code\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.match(r"^\{\s*/\s*code\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 4. show close
        match = re.match(r"^\{\s*/\s*show\s*\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)
            
        # 5. show open with attributes
        match = re.match(r"^\{\s*show(?:\s+[^}]*)?\}", self.buffer, re.IGNORECASE)
        if match:
            return match.group(0)

        if self.buffer.startswith("```"):
            return "```"
                
        return None

    def _handle_tag(self, tag: str) -> Generator[Dict[str, str], None, None]:
        """
        Consume the matched tag and transition states accordingly.
        """
        self.buffer = self.buffer[len(tag):]

        # Normalize tag by removing all spaces and converting to lowercase
        tag_clean = re.sub(r"\s+", "", tag).lower()

        if tag_clean in ("<speak>", "{speak}"):
            if self.state == "SHOW":
                yield from self._yield_show_content()
            self.state = "SPEAK"
            yield {"raw": "", "planned": ""}
        elif tag_clean in ("</speak>", "{/speak}"):
            self.state = "OUTSIDE"
            yield {"raw": "", "planned": ""}
        elif tag_clean in ("<followup>", "{followup}"):
            if self.state == "SHOW":
                yield from self._yield_show_content()
            # Transition to FOLLOWUP state — followup text is hidden from chat and TTS
            self.state = "FOLLOWUP"
            yield {"raw": "", "planned": ""}
        elif tag_clean in ("</followup>", "{/followup}"):
            self.state = "OUTSIDE"
            yield {"raw": "", "planned": ""}
        elif tag_clean in ("<code>", "</code>", "{code}", "{/code}"):
            # Ignore and strip code tags entirely
            yield {"raw": "", "planned": ""}
        elif tag_clean in ("</show>", "{/show}", "</table>"):
            if self.state == "SHOW":
                yield from self._yield_show_content()
            else:
                yield {"raw": "", "planned": ""}
        elif tag_clean.startswith("<show") or tag_clean.startswith("{show"):
            if tag_clean in ("<show>", "{show}"):
                if self.state == "SHOW":
                    # Ignore redundant/duplicate show tag inside show state
                    yield {"raw": "", "planned": ""}
                else:
                    self.state = "SHOW"
                    self.show_type = "code"
                    self.show_lang = "python"
                    self.show_buffer = ""
                    self.show_title = ""
                    
                    # Check if we need to inject a spoken introduction
                    spoken_lower = self.spoken_buffer.lower()
                    introduced = False
                    if any(p in spoken_lower for p in ["below is", "here is", "look at", "following"]):
                        introduced = True
                    elif "code" in spoken_lower or any(w in spoken_lower for w in ["implementation", "function", "write", "script"]):
                        introduced = True
                        
                    planned_intro = ""
                    if not introduced:
                        planned_intro = "Below is the code for this. "
                        
                    yield {"raw": "", "planned": planned_intro}
            else:
                self.state = "SHOW"
                type_match = re.search(r'type\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
                self.show_type = type_match.group(1) if type_match else "code"
                
                lang_match = re.search(r'lang\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
                self.show_lang = lang_match.group(1) if lang_match else "python"
                
                # Extract title if present
                title_match = re.search(r'title\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
                self.show_title = title_match.group(1) if title_match else ""
                
                self.show_buffer = ""
                
                # Check if we need to inject a spoken introduction
                spoken_lower = self.spoken_buffer.lower()
                introduced = False
                if any(p in spoken_lower for p in ["below is", "here is", "look at", "following"]):
                    introduced = True
                elif self.show_type in spoken_lower:
                    introduced = True
                elif self.show_type == "code" and any(w in spoken_lower for w in ["code", "implementation", "function", "write", "script"]):
                    introduced = True
                elif self.show_type in ("roadmap", "workflow") and "diagram" in spoken_lower:
                    introduced = True
                
                planned_intro = ""
                if not introduced:
                    if self.show_type == "code":
                        planned_intro = "Below is the code for this. "
                    elif self.show_type == "workflow":
                        planned_intro = "Below is the workflow for this. "
                    elif self.show_type == "checklist":
                        planned_intro = "Here are the key points. "
                    elif self.show_type == "table":
                        planned_intro = "Below is the table for this. "
                    else:
                        planned_intro = "Here is a diagram for this. "
                        
                yield {"raw": "", "planned": planned_intro}
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

        cleaned = re.sub(
            r"</?(?:checklist|item|step|li|ul|ol|entry|pre|code)(?:\s+[^>]*)?>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        
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
            roadmap_title = self.show_title if self.show_title else "Roadmap"
            start_idx = 0
            if not self.show_title and non_empty and not re.match(r"^(?:Step\s+)?\d+", non_empty[0], re.IGNORECASE):
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
            import logging
            _log = logging.getLogger("edumentor.agent.realtime_parser")
            if looks_like_truncated_code(cleaned):
                _log.warning(f"[CODE] Looks truncated: {cleaned[:150]!r}")
            _log.warning(f"[CODE RAW INPUT] lang={self.show_lang!r} newlines_in_input={cleaned.count(chr(10))} len={len(cleaned)} sample={cleaned[:200]!r}")
            # Reformat single-line code into proper multi-line before emitting
            cleaned = _reformat_code(cleaned, self.show_lang)
            _log.warning(f"[CODE AFTER REFORMAT] newlines={cleaned.count(chr(10))} sample={cleaned[:200]!r}")
            final_raw = f"\n\n```{self.show_lang}\n{cleaned}\n```\n\n"
            _log.warning(f"[CODE FINAL RAW TOKEN] {final_raw[:300]!r}")
            yield {
                "raw": final_raw,
                "planned": ""
            }
        else:
            if self.show_type == "table":
                # Fallback heal for LLMs writing HTML tables but omitting wrapping <table>
                if not cleaned.lower().startswith("<table") and any(cleaned.lower().startswith(x) for x in ("<thead", "<tr", "<tbody", "<td", "<th")):
                    cleaned = f"<table>\n{cleaned}\n</table>"
            display_title = self.show_title if self.show_title else self.show_type.capitalize()
            yield {
                "raw": f"\n\n### 📋 {display_title}\n{cleaned}\n\n",
                "planned": ""
            }
            
        self.show_buffer = ""
        self.state = "OUTSIDE"

    def _convert_json_payload(self, text: str) -> Optional[str]:
        """Convert known JSON response shapes into parser XML tags."""
        try:
            import json as _json

            data = _json.loads(text)
        except Exception:
            speech = self._extract_speech_field_regex(text)
            if not speech:
                return None
            follow_up = self._extract_follow_up_field_regex(text)
            rebuilt = f"<speak>{speech.strip()}</speak>"
            if follow_up:
                rebuilt += f"<followup>{follow_up.strip()}</followup>"
            return rebuilt

        speech = data.get("speech") or data.get("speak") or data.get("text") or ""
        follow_up = data.get("follow_up") or data.get("followup") or data.get("question") or ""
        if not speech:
            return None

        rebuilt = f"<speak>{speech.strip()}</speak>"
        if follow_up:
            rebuilt += f"<followup>{follow_up.strip()}</followup>"
        return rebuilt

    def _extract_speech_field_regex(self, text: str) -> str:
        match = re.search(
            r'["\'](?:speech|speak|text)["\']\s*:\s*["\']((?:\\.|[^"\'\\])*)["\']',
            text,
            re.IGNORECASE,
        )
        if not match:
            return ""
        raw = match.group(1)
        return raw.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", '"').replace("\\'", "'")

    def _extract_follow_up_field_regex(self, text: str) -> str:
        match = re.search(
            r'["\'](?:follow_up|followup|question)["\']\s*:\s*["\']((?:\\.|[^"\'\\])*)["\']',
            text,
            re.IGNORECASE,
        )
        if not match:
            return ""
        raw = match.group(1)
        return raw.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", '"').replace("\\'", "'")

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
            self.spoken_buffer += char
            yield {"raw": char, "planned": char}
        elif self.state == "FOLLOWUP":
            # Followup content is hidden from chat and not spoken aloud
            yield {"raw": "", "planned": ""}
        else:
            self.spoken_buffer += char
            yield {"raw": char, "planned": char}
