import re
from typing import Dict, Any, List, Optional, Tuple
from app.schemas.form import FormSchemaDefinition, is_identifier_field, is_name_field, is_valid_name


MONTH_NAMES = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09", "செப்டம்பர்": "09", "septembar": "09",
    "october": "10", "oct": "10", "அக்டோபர்": "10", "akdobar": "10",
    "november": "11", "nov": "11", "நவம்பர்": "11", "navambar": "11",
    "december": "12", "dec": "12", "டிசம்பர்": "12", "disambar": "12",
    "january": "01", "jan": "01", "ஜனவரி": "01", "janavari": "01",
    "february": "02", "feb": "02", "பிப்ரவரி": "02", "pebravari": "02",
    "march": "03", "mar": "03", "மார்ச்": "03", "maarss": "03",
    "april": "04", "apr": "04", "ஏப்ரல்": "04", "epral": "04",
    "may": "05", "மே": "05", "mey": "05",
    "june": "06", "jun": "06", "ஜூன்": "06", "joon": "06",
    "july": "07", "jul": "07", "ஜூலை": "07", "joolai": "07",
    "august": "08", "aug": "08", "ஆகஸ்ட்": "08", "aagast": "08",
}

WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50",
    # Tanglish transliteration numbers
    "poojiyam": "0", "poojyam": "0", "suzhiyam": "0",
    "onnu": "1", "ondru": "1", "oru": "1",
    "rendu": "2", "irandu": "2",
    "moonu": "3", "moondru": "3",
    "naalu": "4", "naangu": "4",
    "anju": "5", "aindhu": "5",
    "aaru": "6",
    "ezhu": "7", "yelu": "7",
    "ettu": "8",
    "ombodhu": "9", "onbadhu": "9", "onbathu": "9",
    "patthu": "10", "pathu": "10",
    # Tamil Unicode digits
    "பூஜ்யம்": "0", "சுழியம்": "0",
    "ஒன்று": "1", "ஒன்னு": "1",
    "இரண்டு": "2", "ரெண்டு": "2",
    "மூன்று": "3", "மூனு": "3",
    "நான்கு": "4", "நாலு": "4",
    "ஐந்து": "5", "அஞ்சு": "5",
    "ஆறு": "6",
    "ஏழு": "7",
    "எட்டு": "8",
    "ஒன்பது": "9", "ஒம்போது": "9",
    "பத்து": "10",
}

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Tanglish digit words
    "poojiyam": "0", "poojyam": "0", "suzhiyam": "0",
    "onnu": "1", "ondru": "1", "oru": "1",
    "rendu": "2", "irandu": "2",
    "moonu": "3", "moondru": "3",
    "naalu": "4", "naangu": "4",
    "anju": "5", "aindhu": "5",
    "aaru": "6",
    "ezhu": "7", "yelu": "7",
    "ettu": "8",
    "ombodhu": "9", "onbadhu": "9", "onbathu": "9",
    # Tamil Unicode digits
    "பூஜ்யம்": "0", "சுழியம்": "0",
    "ஒன்று": "1", "ஒன்னு": "1",
    "இரண்டு": "2", "ரெண்டு": "2",
    "மூன்று": "3", "மூனு": "3",
    "நான்கு": "4", "நாலு": "4",
    "ஐந்து": "5", "அஞ்சு": "5",
    "ஆறு": "6",
    "ஏழு": "7",
    "எட்டு": "8",
    "ஒன்பது": "9", "ஒம்போது": "9",
}

STANDARD_OPTION_ALIASES = {
    # Engineering & Computer Science departments
    "ai&ds": [
        "artificial intelligence and data science",
        "artificial intelligence & data science",
        "ai and data science",
        "ai & data science",
        "ai ds",
        "aids",
        "ai and ds",
        "artificial intelligence",
        "செயற்கை நுண்ணறிவு",
        "செயற்கை நுண்ணறிவு மற்றும் தரவு அறிவியல்",
    ],
    "cse": [
        "computer science and engineering",
        "computer science & engineering",
        "computer science",
        "cs",
        "comp sci",
        "கணினி அறிவியல்",
        "கணினி பொறியியல்",
    ],
    "ece": [
        "electronics and communication engineering",
        "electronics and communication",
        "electronics & communication engineering",
        "electronics & communication",
        "மின்னணு மற்றும் தகவல் தொடர்பு பொறியியல்",
    ],
    "eee": [
        "electrical and electronics engineering",
        "electrical & electronics engineering",
        "electrical engineering",
    ],
    "it": [
        "information technology",
        "தகவல் தொழில்நுட்பம்",
    ],
    "mech": [
        "mechanical engineering",
        "mechanical",
        "இயந்திரவியல்",
    ],
    "mechanical": [
        "mechanical engineering",
        "mech",
        "இயந்திரவியல்",
    ],
    "civil": [
        "civil engineering",
        "கட்டுமான பொறியியல்",
    ],
    # Degrees
    "btech": ["b tech", "bachelor of technology"],
    "be": ["b e", "bachelor of engineering"],
    "mtech": ["m tech", "master of technology"],
    # Roles
    "frontend developer": ["frontend engineer", "front end developer", "front end engineer"],
    "backend developer": ["backend engineer", "back end developer", "back end engineer"],
    "full stack developer": ["full stack engineer", "fullstack developer", "fullstack engineer"],
    "qa": ["quality assurance", "qa engineer", "tester"],
    "hr": ["human resources"],
    # General
    "male": ["man", "boy", "m", "ஆண்", "aan"],
    "female": ["woman", "girl", "f", "பெண்", "pen"],
}

STOPWORDS = {
    "i", "belong", "to", "my", "department", "dept", "branch", "stream", "is",
    "choose", "select", "please", "for", "the", "a", "an", "entered", "as", "set",
    "should", "be",
    # Tamil & Tanglish conversational fillers and particles
    "enoda", "ennoda", "ennudaiya", "en", "peyar", "per", "ooru", "oor",
    "iruken", "irukom", "la", "ku", "kaga", "pannunga", "pannidunga", "podunga",
    "vechuko", "veikavum", "kudukanum", "kudu", "solren", "solran", "sollunga",
    "சொல்லுங்க", "பெயர்", "ஊர்", "பண்ணுங்க", "போடுங்க", "என்", "என்னுடைய"
}


def parse_spoken_date(date_str: str) -> Optional[str]:
    """Attempts to normalize spoken dates to YYYY-MM-DD."""
    cleaned = date_str.lower().strip()

    # 1. Match YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", cleaned)
    if iso_match:
        y, m, d = iso_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # 2. Match DD/MM/YYYY or MM/DD/YYYY
    slash_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", cleaned)
    if slash_match:
        d, m, y = slash_match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"

    # 3. Match e.g. "15th august 2000" or "august 15 2000" or "15 august 2000"
    for month_name, month_num in MONTH_NAMES.items():
        if month_name in cleaned:
            # Check pattern: month day year
            m1 = re.search(rf"\b{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b", cleaned)
            if m1:
                day, year = m1.groups()
                return f"{year}-{month_num}-{int(day):02d}"

            # Check pattern: day month year
            m2 = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{month_name}\s*,?\s*(\d{{4}})\b", cleaned)
            if m2:
                day, year = m2.groups()
                return f"{year}-{month_num}-{int(day):02d}"

    return None


def clean_for_matching(text: str) -> str:
    """Normalizes text for robust matching while preserving Tamil Unicode script."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[/\\_-]", " ", t)
    t = re.sub(r"[^a-z0-9\u0B80-\u0BFF\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_spoken_identifier(val: str) -> str:
    """
    Normalizes spoken alphanumeric identifiers (register numbers, student IDs,
    roll numbers, postal codes, phone numbers).
    - Preserves letters, digits, leading zeros, and meaningful hyphens.
    - Never casts to integers or floats.
    - Converts spoken digit words ('zero', 'one', 'double zero', etc.).
    - Collapses spaces between single letters/digits (e.g. 'A 1 2 3 4 5' -> 'A12345').
    - Converts letters to uppercase by default.
    """
    if not val or not val.strip():
        return ""

    cleaned = val.strip()

    # Convert spoken digit words
    for word, digit in DIGIT_WORDS.items():
        cleaned = re.sub(rf"\bdouble\s+{word}\b", f"{digit}{digit}", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\btriple\s+{word}\b", f"{digit}{digit}{digit}", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\b{word}\b", digit, cleaned, flags=re.IGNORECASE)

    # Convert word numbers 10-50 if any remain
    for word, digit_str in WORD_NUMBERS.items():
        cleaned = re.sub(rf"\b{word}\b", digit_str, cleaned, flags=re.IGNORECASE)

    tokens = [t for t in re.split(r"\s+", cleaned.strip()) if t]

    # Check if all tokens are alphanumeric codes
    is_code_like = all(re.match(r"^[A-Za-z0-9_\-\+]+$", t) for t in tokens)
    if is_code_like and len(tokens) > 1:
        # Check if spaced-out characters/digits
        joined = "".join(tokens)
        return joined.upper()
    elif is_code_like and len(tokens) == 1:
        return tokens[0].upper()

    return cleaned.strip()


def match_dropdown_option(spoken: str, options: List[str]) -> Tuple[Optional[str], bool]:
    """
    Deterministic dropdown and select matching algorithm:
    1. Exact match
    2. Case-insensitive & trimmed match
    3. Normalized whitespace & punctuation match (& vs and, hyphens, slashes)
    4. Conservative matching of unambiguous label variations & canonical aliases
    5. Conservative content-word subset
    Returns (matched_option, is_ambiguous). If no match, returns (None, False).
    Never silently selects the first option as a fallback.
    Never invents new options.
    """
    if not spoken or not options:
        return None, False

    trimmed = spoken.strip()
    cleaned_spoken = clean_for_matching(trimmed)
    if not cleaned_spoken:
        return None, False

    # 1. Exact match
    for opt in options:
        if opt == trimmed:
            return opt, False

    # 2. Case-insensitive & trimmed match
    for opt in options:
        if opt.strip().lower() == trimmed.lower():
            return opt, False

    # 3. Normalized whitespace & punctuation match
    for opt in options:
        if clean_for_matching(opt) == cleaned_spoken:
            return opt, False

    # 4. Check if whole option name is mentioned in spoken text on word boundaries
    direct_phrase_matches = set()
    for opt in options:
        opt_clean = clean_for_matching(opt)
        if opt_clean and re.search(rf"\b{re.escape(opt_clean)}\b", cleaned_spoken):
            direct_phrase_matches.add(opt)
    if len(direct_phrase_matches) == 1:
        return list(direct_phrase_matches)[0], False
    elif len(direct_phrase_matches) > 1:
        return None, True

    # 5. Canonical aliases and standard variations
    matches = set()
    for opt in options:
        opt_clean = clean_for_matching(opt)
        opt_key = re.sub(r"[^a-z0-9&]", "", opt.lower())

        for canon_key, alias_list in STANDARD_OPTION_ALIASES.items():
            is_opt_in_group = (
                opt_key == canon_key
                or opt_clean in [clean_for_matching(a) for a in alias_list]
                or any(clean_for_matching(a) == opt_clean for a in alias_list)
            )
            if is_opt_in_group:
                patterns = [
                    canon_key,
                    canon_key.replace("&", " and "),
                ] + [clean_for_matching(a) for a in alias_list]
                for p in patterns:
                    if not p:
                        continue
                    # Guard short words (e.g. 'it') from matching English pronouns in long sentences
                    if len(p) <= 2:
                        if cleaned_spoken == p or re.search(rf"\b(?:dept|department|branch|stream|course|in)\s+{re.escape(p)}\b|\b{re.escape(p)}\s+(?:dept|department|branch)\b", cleaned_spoken):
                            matches.add(opt)
                            break
                        continue

                    if (
                        p == cleaned_spoken
                        or f" {p} " in f" {cleaned_spoken} "
                        or re.search(rf"(?:\b|^){re.escape(p)}(?:\b|$)", cleaned_spoken)
                        or re.search(rf"(?:\b|^){re.escape(p)}(?:\b|$)", spoken.lower())
                    ):
                        matches.add(opt)
                        break

    if len(matches) == 1:
        return list(matches)[0], False
    elif len(matches) > 1:
        return None, True

    # 6. Conservative content-word subset
    spoken_words = set(cleaned_spoken.split()) - STOPWORDS
    subset_matches = set()
    for opt in options:
        opt_clean = clean_for_matching(opt)
        opt_words = set(opt_clean.split())
        if spoken_words and spoken_words.issubset(opt_words):
            subset_matches.add(opt)
        elif opt_words and opt_words.issubset(spoken_words):
            subset_matches.add(opt)

    if len(subset_matches) == 1 and spoken_words:
        return list(subset_matches)[0], False
    elif len(subset_matches) > 1:
        return None, True

    return None, False


def map_transcript_to_fields(transcript: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based slot filling engine.
    Extracts key-value pairs from speech transcript using the form schema fields.
    Preserves alphanumeric identifiers, leading zeros, and string types.
    Maps dropdown and select fields deterministically without fabricating options.
    """
    if not transcript or not transcript.strip():
        return {}

    fields = schema.get("fields", [])
    if not fields:
        return {}

    text = transcript.strip()
    results = {}

    # Guard: Questions and inquiries must never be extracted as field assignments
    t_clean = text.strip().lower()
    is_inquiry = (
        t_clean.endswith("?")
        or bool(re.search(r"^(does|do|is|are|was|were|can|could|would|should|how|what|why|did|has|have)\b", t_clean))
        or any(p in t_clean for p in ["feel like", "feels like", "look like", "looks like", "sound like", "is valid", "valid or not", "is correct", "like a name"])
    )
    is_explicit_cmd = any(w in t_clean for w in [
        "change my ", "change the ", "change it to", "replace my ", "replace the ", "update my ", "update the ", "set my ", "set the "
    ])
    if is_inquiry and not is_explicit_cmd:
        return {}

    # Guard: Clear/remove/delete/empty field commands must never be extracted as field value assignments
    from app.services.intent_service import is_clear_command, is_command_sentence
    if is_clear_command(t_clean):
        return {}

    # Build field aliases and search tokens
    field_metadata = []
    for f in fields:
        fname = f.get("name")
        flabel = f.get("label", "")
        ftype = f.get("type", "text")
        options = f.get("options") or []
        is_ident = is_identifier_field(f)

        aliases = [
            flabel.lower(),
            fname.lower().replace("_", " "),
        ]

        # Add sensible common colloquial shortcuts
        if "name" in fname:
            aliases.extend(["name", "full name"])
        if "email" in fname:
            aliases.extend(["email", "email address", "mail id"])
        if "phone" in fname or "mobile" in fname:
            aliases.extend(["phone", "phone number", "mobile", "mobile number", "contact number"])
        if "dept" in fname or "department" in fname:
            aliases.extend(["department", "dept", "branch", "stream", "belong to", "major", "specialization", "course"])
        if "reg" in fname:
            aliases.extend(["register number", "registration number", "reg no", "roll number"])
        if "roll" in fname:
            aliases.extend(["roll number", "roll no", "roll"])
        if "student" in fname or "id" in fname:
            aliases.extend(["student id", "id number", "identification", "student identification"])
        if "postal" in fname or "zip" in fname or "pin" in fname:
            aliases.extend(["postal code", "zip code", "pincode", "pin code", "postal"])
        if ftype == "date" or "date" in fname or "birth" in fname or "dob" in fname or "date" in flabel.lower():
            aliases.extend(["date", "date of birth", "dob", "birthday", "birth date"])
        if "gender" in fname:
            aliases.extend(["gender", "sex"])
        if "feedback" in fname or "comment" in fname or "message" in fname:
            aliases.extend(["feedback", "comments", "comment", "message", "notes"])
        if "rating" in fname or "satisfaction" in fname:
            aliases.extend(["rating", "satisfaction", "satisfaction rating"])
        if "exp" in fname:
            aliases.extend(["years of experience", "experience", "years experience"])
        if "position" in fname or "role" in fname:
            aliases.extend(["position", "target position", "role", "job title"])

        # Deduplicate aliases and sort by length descending so longer phrases match first
        unique_aliases = sorted(list(set(aliases)), key=len, reverse=True)
        field_metadata.append({
            "name": fname,
            "label": flabel,
            "type": ftype,
            "options": options,
            "is_identifier": is_ident,
            "aliases": unique_aliases,
        })

    # Strategy: Find position of each field's alias in the transcript
    matches = []
    text_lower = f" {text.lower()} "

    for fmeta in field_metadata:
        for alias in fmeta["aliases"]:
            pattern = rf"\b{re.escape(alias)}\b"
            for m in re.finditer(pattern, text_lower):
                # Guard against question prefixes targeting this field, e.g. "does my name", "is my email"
                prefix_context = text_lower[:m.start()].strip()
                if re.search(r"\b(does|do|is|are|was|were|can|could|would|should|how|what|why|did|has|have|check|verify)\s+(?:my\s+|the\s+|this\s+)?$", prefix_context):
                    continue
                matches.append({
                    "start": m.start(),
                    "end": m.end(),
                    "fmeta": fmeta,
                    "matched_alias": alias,
                })
                break  # Pick first match for this field

    # Sort matches by appearance in transcript
    matches.sort(key=lambda x: x["start"])

    # Discard overlapping matches (keep the earlier/longer match)
    filtered_matches = []
    used_names = set()
    last_end = -1

    for m in matches:
        if m["fmeta"]["name"] in used_names:
            continue
        if m["start"] >= last_end:
            filtered_matches.append(m)
            used_names.add(m["fmeta"]["name"])
            last_end = m["end"]

    # Extract value between matches
    for i, curr in enumerate(filtered_matches):
        start_idx = curr["end"]
        if i + 1 < len(filtered_matches):
            end_idx = filtered_matches[i + 1]["start"]
            raw_val = text_lower[start_idx:end_idx]
        else:
            raw_val = text_lower[start_idx:]

        # Strip correction prefixes: e.g. "is wrong. change it to", "is incorrect. change it to", "replace it with", etc.
        val = raw_val.strip()
        val = re.sub(
            r"^(is|are|was)?\s*(wrong|incorrect|not right|mistake)[\s\.,;\-–]+(change|replace|update|set|switch)\s*(it\s*)?(to|with|as)\s*",
            "",
            val,
            flags=re.IGNORECASE
        )
        val = re.sub(
            r"^(is|are|was|to|set to|as|entered as|should be|colon|equals?|:|=)\s*",
            "",
            val,
            flags=re.IGNORECASE
        )
        val = re.sub(
            r"^(change|replace|update|set|switch)\s*(it\s*)?(to|with|as)\s*",
            "",
            val,
            flags=re.IGNORECASE
        )
        val = re.sub(
            r"^(with|to|as|into|by)\s+",
            "",
            val,
            flags=re.IGNORECASE
        )
        # Strip negative contrast clauses: e.g. ", not Computer Science", " instead of X"
        val = re.sub(
            r"[\s,;\-]+(not|instead of|rather than|and not)\s+.*$",
            "",
            val,
            flags=re.IGNORECASE
        )
        val = re.sub(r"\s*(and\s+my|and\s+the|and|also|then|next)\s*$", "", val, flags=re.IGNORECASE)
        val = val.strip().strip(",.;:")

        # Extract according to original case if string
        orig_val = val
        if val in text.lower():
            idx_in_orig = text.lower().find(val)
            if idx_in_orig != -1:
                orig_val = text[idx_in_orig : idx_in_orig + len(val)].strip().strip(",.;:")

        fmeta = curr["fmeta"]
        ftype = fmeta["type"]
        is_ident = fmeta["is_identifier"]

        # Reject if the extracted value itself is a command sentence or instruction
        if is_command_sentence(str(orig_val)):
            continue

        # Reject if the extracted value itself is a question or conversational inquiry
        if "?" in str(orig_val) or any(phrase in str(orig_val).lower() for phrase in [
            "feel like", "feels like", "look like", "looks like", "sound like", "like a name", "is valid", "valid or not", "is correct"
        ]):
            continue

        if is_name_field(fmeta):
            if not is_valid_name(orig_val):
                continue

        # Type conversion & normalization
        if is_ident:
            # Preserve letters, digits, leading zeros, meaningful separators as string
            norm_id = normalize_spoken_identifier(orig_val)
            # An identifier must be a valid alphanumeric token, NOT an English sentence with spaces/punctuation
            if not re.match(r"^[A-Za-z0-9_\-\+]+$", norm_id):
                continue
            orig_val = norm_id

        elif ftype == "number":
            # True quantitative number field
            num_match = re.search(r"\b\d+(\.\d+)?\b", orig_val)
            if num_match:
                orig_val = num_match.group(0)
            elif orig_val.lower() in WORD_NUMBERS:
                orig_val = WORD_NUMBERS[orig_val.lower()]

        elif ftype == "email":
            clean_email = orig_val.lower()
            clean_email = clean_email.replace(" at the rate ", "@").replace(" at ", "@")
            clean_email = clean_email.replace(" dot ", ".").replace(" dot", ".").replace("dot ", ".")
            clean_email = re.sub(r"\s+", "", clean_email)
            orig_val = clean_email

        elif ftype == "date":
            parsed_date = parse_spoken_date(orig_val)
            if parsed_date:
                orig_val = parsed_date

        elif ftype in ("select", "radio"):
            options = fmeta["options"] or []
            matched_opt, is_ambig = match_dropdown_option(orig_val, options)
            if matched_opt:
                orig_val = matched_opt
            else:
                # Never silently select the first option as a fallback
                # Never store invalid option as a valid selection
                orig_val = None

        elif ftype == "checkbox":
            val_lower = orig_val.lower()
            if any(w in val_lower for w in ["yes", "true", "check", "agree", "confirm", "accepted"]):
                orig_val = True
            elif any(w in val_lower for w in ["no", "false", "uncheck", "disagree"]):
                orig_val = False
            else:
                orig_val = True

        if orig_val is not None and str(orig_val).strip() != "":
            results[fmeta["name"]] = orig_val

    # Check for unmapped select/radio fields that may have been spoken directly without mentioning the field name
    # e.g., "I belong to AI and Data Science." (only if no other field was mapped in this utterance)
    if not results:
        for fmeta in field_metadata:
            fname = fmeta["name"]
            if fmeta["type"] in ("select", "radio"):
                options = fmeta["options"] or []
                matched_opt, is_ambig = match_dropdown_option(text, options)
                if matched_opt and not is_ambig:
                    results[fname] = matched_opt

    return results
