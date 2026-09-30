
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class InterruptionResult:
    interruption_type: str
    interrupted: bool
    changed_slots: dict[str, Any]
    new_goal: str


class InterruptDetector:

    CITIES = {
        "Mumbai",
        "Delhi",
        "Bangalore",
        "Bengaluru",
        "Hyderabad",
        "Chennai",
        "Pune",
        "Kolkata",
        "Jaipur",
        "Ahmedabad",
        "Goa",
        "Kochi",
    }

    CORRECTION_WORDS = {
        "no",
        "actually",
        "instead",
        "change",
        "correction",
        "rather",
    }

    # ---------------------------------------------------------
    # HINDI
    # ---------------------------------------------------------

    DEVANAGARI_MAP = {
        "बुक": "book",
        "मी": "me",
        "फ्लाइट": "flight",
        "लाइट": "flight",

        "फ्रॉम": "from",
        "फ्रम": "from",
        "से": "from",
        "टू": "to",

        "दिल्ली": "Delhi",
        "मुंबई": "Mumbai",
        "बॉम्बे": "Mumbai",

        "बंगलोर": "Bangalore",
        "बैंगलोर": "Bangalore",
        "बेंगलुरु": "Bangalore",

        "हैदराबाद": "Hyderabad",
        "चेन्नई": "Chennai",
        "पुणे": "Pune",
        "कोलकाता": "Kolkata",
        "जयपुर": "Jaipur",

        "यात्री": "passengers",
        "यात्रियों": "passengers",
        "पैसेंजर": "passenger",
        "पैसेंजर्स": "passengers",

        "सुबह": "morning",
        "दोपहर": "afternoon",
        "शाम": "evening",
        "रात": "night",

        "आज": "today",
        "कल": "tomorrow",

        "जनवरी": "January",
        "फरवरी": "February",
        "मार्च": "March",
        "अप्रैल": "April",
        "मई": "May",
        "जून": "June",
        "जुलाई": "July",
        "अगस्त": "August",
        "सितंबर": "September",
        "सितम्बर": "September",
        "अक्टूबर": "October",
        "नवंबर": "November",
        "दिसंबर": "December",
    }

    # ---------------------------------------------------------
    # TELUGU
    # ---------------------------------------------------------

    TELUGU_MAP = {
        "బుక్": "book",
        "మీ": "me",
        "లైట్": "flight",
        "ఫ్లైట్": "flight",

        "ఫ్రమ్": "from",
        "ఫ్రం": "from",
        "నుంచి": "from",

        "టు": "to",

        "ముంబై": "Mumbai",
        "బొంబాయి": "Mumbai",
        "ఢిల్లీ": "Delhi",
        "దిల్లీ": "Delhi",

        "బెంగళూరు": "Bangalore",
        "బెంగుళూరు": "Bangalore",

        "హైదరాబాద్": "Hyderabad",
        "చెన్నై": "Chennai",
        "పూణే": "Pune",
        "కోల్కతా": "Kolkata",

        "ఉదయం": "morning",
        "మధ్యాహ్నం": "afternoon",
        "సాయంత్రం": "evening",
        "రాత్రి": "night",

        "ఈరోజు": "today",
        "రేపు": "tomorrow",
    }

    # ---------------------------------------------------------
    # MALAYALAM
    # ---------------------------------------------------------

    MALAYALAM_MAP = {
        "ബുക്ക്": "book",
        "ഫ്ലൈറ്റ്": "flight",
        "ഫ്ലൈറ്": "flight",

        "ഫ്രം": "from",
        "ഫ്രോമ": "from",
        "നിന്ന്": "from",

        "ടു": "to",

        "മുംബൈ": "Mumbai",
        "ബോംബെ": "Mumbai",

        "ഡൽഹി": "Delhi",
        "ദില്ലി": "Delhi",
        "ഡെൽഹി": "Delhi",

        "ബാംഗ്ലൂർ": "Bangalore",
        "ബെംഗളൂരു": "Bangalore",

        "ഹൈദരാബാദ്": "Hyderabad",
        "ചെന്നൈ": "Chennai",
        "പൂനെ": "Pune",
        "കൊൽക്കത്ത": "Kolkata",

        "രാവിലെ": "morning",
        "ഉച്ചയ്ക്ക്": "afternoon",
        "വൈകുന്നേരം": "evening",
        "രാത്രി": "night",

        "ഇന്ന്": "today",
        "നാളെ": "tomorrow",

        "യാത്രക്കാർ": "passengers",
        "പാസഞ്ചേഴ്സ്": "passengers",
    }

    # ---------------------------------------------------------
    # NORMALIZE
    # ---------------------------------------------------------

    def _normalise_transcript(self, text: str) -> str:
        text = text.strip()

        all_maps = [
            self.DEVANAGARI_MAP,
            self.TELUGU_MAP,
            self.MALAYALAM_MAP,
        ]

        for mapping in all_maps:
            for source, target in sorted(
                mapping.items(),
                key=lambda x: len(x[0]),
                reverse=True,
            ):
                text = text.replace(source, target)

        # Common speech-recognition spellings
        replacements = {
            "फ्रॉम": "from",
            "फ्रम": "from",
            "फ्रॉम": "from",

            "फ्रॉम": "from",

            "फ्रॉम": "from",

            "fromm": "from",
            "frm": "from",

            "tommorow": "tomorrow",
            "tomarrow": "tomorrow",

            "around": "round",
        }

        for source, target in replacements.items():
            text = text.replace(source, target)

        text = re.sub(r"\s+", " ", text)

        return text.strip()

    # ---------------------------------------------------------
    # MAIN CLASSIFIER
    # ---------------------------------------------------------

    def classify_interruption(
        self,
        transcript: str,
        current_slots: dict[str, Any] | None = None,
    ) -> InterruptionResult:

        current_slots = current_slots or {}

        normalized = self._normalise_transcript(transcript)

        changed_slots = self.extract_slots(normalized)

        lower = normalized.lower()

        if any(word in lower for word in self.CORRECTION_WORDS):
            interruption_type = "correction"
            interrupted = True

        elif changed_slots:
            interruption_type = "constraint"
            interrupted = False

        else:
            interruption_type = "none"
            interrupted = False

        return InterruptionResult(
            interruption_type=interruption_type,
            interrupted=interrupted,
            changed_slots=changed_slots,
            new_goal=transcript,
        )

    # ---------------------------------------------------------
    # SLOT EXTRACTION
    # ---------------------------------------------------------

    def extract_slots(self, text: str) -> dict[str, Any]:

        slots = {}

        # ORIGIN
        match = re.search(
            r"\bfrom\s+([A-Za-z]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            slots["origin"] = self._normalise_city(
                match.group(1)
            )

        # DESTINATION
        match = re.search(
            r"\bto\s+([A-Za-z]+)",
            text,
            re.IGNORECASE,
        )

        if match:
            slots["destination"] = self._normalise_city(
                match.group(1)
            )

        # DATE
        date = self._extract_date(text)

        if date:
            slots["date"] = date

        # TIME
        time = self._extract_time(text)

        if time:
            slots["time"] = time

        # PASSENGERS
        passengers = self._extract_passengers(text)

        if passengers is not None:
            slots["passengers"] = passengers

        # TRIP TYPE
        lower = text.lower()

        if (
            "round trip" in lower
            or "roundtrip" in lower
            or "return flight" in lower
        ):
            slots["trip_type"] = "round trip"

        elif (
            "one way" in lower
            or "one-way" in lower
        ):
            slots["trip_type"] = "one way"

        return slots

    # ---------------------------------------------------------
    # CITY
    # ---------------------------------------------------------

    def _normalise_city(self, city: str) -> str:

        cities = {
            "mumbai": "Mumbai",
            "bombay": "Mumbai",

            "delhi": "Delhi",

            "bangalore": "Bangalore",
            "bengaluru": "Bangalore",

            "hyderabad": "Hyderabad",
            "chennai": "Chennai",
            "pune": "Pune",
            "kolkata": "Kolkata",
            "jaipur": "Jaipur",
            "ahmedabad": "Ahmedabad",
            "goa": "Goa",
            "kochi": "Kochi",
        }

        return cities.get(
            city.lower(),
            city.title(),
        )

    # ---------------------------------------------------------
    # DATE
    # ---------------------------------------------------------

    def _extract_date(self, text: str):

        lower = text.lower()

        if "day after tomorrow" in lower:
            return "day after tomorrow"

        if "tomorrow" in lower:
            return "tomorrow"

        if "today" in lower:
            return "today"

        # 29 September 2026
        match = re.search(
            r"\b(\d{1,2})\s+"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"(?:\s+(\d{4}))?\b",
            text,
            re.IGNORECASE,
        )

        if match:
            day = match.group(1)
            month = match.group(2)
            year = match.group(3)

            if year:
                return f"{day} {month} {year}"

            return f"{day} {month}"

        # September 29 2026
        match = re.search(
            r"\b"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+(\d{1,2})"
            r"(?:\s+(\d{4}))?"
            r"\b",
            text,
            re.IGNORECASE,
        )

        if match:
            month = match.group(1)
            day = match.group(2)
            year = match.group(3)

            if year:
                return f"{day} {month} {year}"

            return f"{day} {month}"

        # 29/09/2026 or 29-09-2026
        match = re.search(
            r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
            text,
        )

        if match:
            return (
                f"{match.group(1)}/"
                f"{match.group(2)}/"
                f"{match.group(3)}"
            )

        return None

    # ---------------------------------------------------------
    # TIME
    # ---------------------------------------------------------

    def _extract_time(self, text: str):

        lower = text.lower()

        if "morning" in lower:
            return "morning"

        if "afternoon" in lower:
            return "afternoon"

        if "evening" in lower:
            return "evening"

        if "night" in lower:
            return "night"

        if "flexible" in lower:
            return "flexible"

        if "anytime" in lower:
            return "flexible"

        match = re.search(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            lower,
        )

        if match:
            hour = match.group(1)
            minute = match.group(2)
            ampm = match.group(3)

            if minute:
                return f"{hour}:{minute} {ampm}"

            return f"{hour} {ampm}"

        return None

    # ---------------------------------------------------------
    # PASSENGERS
    # ---------------------------------------------------------

    def _extract_passengers(self, text: str):

        lower = text.lower()

        # 14 passengers
        match = re.search(
            r"\b(\d+)\s*"
            r"(?:passengers?|people|persons?|"
            r"members?|travellers?|travelers?)\b",
            lower,
        )

        if match:
            return int(match.group(1))

        # for 14
        match = re.search(
            r"\bfor\s+(\d+)\b",
            lower,
        )

        if match:
            return int(match.group(1))

        # Just "14"
        if re.fullmatch(
            r"\d+",
            lower.strip(),
        ):
            return int(lower.strip())

        return None

