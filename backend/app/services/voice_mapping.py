import re
from typing import Dict, Any, List, Optional, Tuple
from app.schemas.form import FormSchemaDefinition, is_identifier_field


MONTH_NAMES = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}

WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50",
}

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"
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
    ],
    "cse": [
        "computer science and engineering",
        "computer science & engineering",
        "computer science",
        "cs",
        "comp sci",
    ],
    "ece": [
        "electronics and communication engineering",
        "electronics and communication",
        "electronics & communication engineering",
        "electronics & communication",
    ],
    "eee": [
        "electrical and electronics engineering",
        "electrical & electronics engineering",
        "electrical engineering",
    ],
    "it": [
        "information technology",
    ],
    "mech": [
        "mechanical engineering",
        "mechanical",
    ],
    "mechanical": [
        "mechanical engineering",
        "mech",
    ],
    "civil": [
        "civil engineering",
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
    "male": ["man", "boy", "m"],
    "female": ["woman", "girl", "f"],
}

STOPWORDS = {
    "i", "belong", "to", "my", "department", "dept", "branch", "stream", "is",
    "choose", "select", "please", "for", "the", "a", "an", "entered", "as", "set",
    "should", "be"
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
    """Normalizes text for robust matching."""
    t = text.lower().replace("&", " and ")
    t = re.sub(r"[/\\_-]", " ", t)
    t = re.sub(r"[^a-z0-9\s]", "", t)
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
                    re.escape(canon_key),
                    re.escape(canon_key.replace("&", " and ")),
                ] + [re.escape(clean_for_matching(a)) for a in alias_list]
                for p in patterns:
                    if re.search(rf"\b{p}\b", cleaned_spoken) or re.search(rf"\b{p}\b", spoken.lower()):
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
        if "birth" in fname or "dob" in fname:
            aliases.extend(["date of birth", "dob", "birthday", "birth date"])
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

        # Strip connectors: "is", "are", "as", "to", "set to", ":", "=", "entered as", "and", "my", etc.
        val = raw_val.strip()
        val = re.sub(r"^(is|are|was|to|set to|as|entered as|should be|colon|equals?|:|=)\s*", "", val, flags=re.IGNORECASE)
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

        # Type conversion & normalization
        if is_ident:
            # Preserve letters, digits, leading zeros, meaningful separators as string
            orig_val = normalize_spoken_identifier(orig_val)

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
    # e.g., "I belong to AI and Data Science."
    for fmeta in field_metadata:
        fname = fmeta["name"]
        if fname not in results and fmeta["type"] in ("select", "radio"):
            options = fmeta["options"] or []
            matched_opt, is_ambig = match_dropdown_option(text, options)
            if matched_opt and not is_ambig:
                results[fname] = matched_opt

    return results
