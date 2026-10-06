"""Request building and answer parsing for Jev (TypeSafe), the enrichment classifier.

One request carries one review as `state` and a fixed map of typed questions. Jev returns one typed answer per
question with probabilities; code maps those into the shared label schema.
"""

API_URL = "https://api.typesafe.ai/v1/systemone"
PROVIDER = "typesafe"
REQUIRED = ("topic", "intent", "severity", "sentiment")


class InvalidOutput(ValueError):
    """The model's response does not fit the expected answer shape."""


def build_body(text, prompt, model, quote_parts):
    questions = dict(prompt["questions"])
    if quote_parts:
        questions["quote"] = {**prompt["quote_question"],
                              "criteria": {f"part_{i}": part for i, part in enumerate(quote_parts, 1)}}
    return {"state": text, "model": model, "questions": questions}


def _confidence(answer, name):
    value = answer.get("confidence")
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise InvalidOutput(f"{name}: confidence missing or out of range")
    return float(value)


def _choice(answers, name, allowed):
    answer = answers.get(name)
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise InvalidOutput(f"{name}: missing choice answer")
    if answer.get("choice") not in allowed:
        raise InvalidOutput(f"{name}: choice {answer.get('choice')!r} is not an allowed option")
    return answer["choice"], _confidence(answer, name)


def parse_answers(answers, prompt, quote_parts):
    """Map Jev answers to label values. Raises InvalidOutput on any missing or disallowed answer."""
    if not isinstance(answers, dict):
        raise InvalidOutput("answers is not an object")
    questions = prompt["questions"]
    confidence = {}
    topic, confidence["topic"] = _choice(answers, "topic", questions["topic"]["criteria"])
    intent, confidence["intent"] = _choice(answers, "intent", questions["intent"]["criteria"])
    level, confidence["severity"] = _choice(answers, "severity", prompt["severity_levels"])

    score = answers.get("sentiment")
    levels = prompt["sentiment_levels"]
    if not isinstance(score, dict) or score.get("type") != "score" or not isinstance(score.get("probabilities"), dict):
        raise InvalidOutput("sentiment: missing score answer")
    try:
        probabilities = [float(score["probabilities"][str(i)]) for i in range(len(levels))]
    except (KeyError, TypeError, ValueError):
        raise InvalidOutput("sentiment: probabilities do not cover every level") from None
    # Take the most probable level; Jev's docs advise against interpolating between score levels.
    sentiment = levels[max(range(len(levels)), key=probabilities.__getitem__)]
    confidence["sentiment"] = _confidence(score, "sentiment")

    quote_index = None
    if quote_parts:
        options = {f"part_{i}": i - 1 for i in range(1, len(quote_parts) + 1)}
        choice, confidence["quote"] = _choice(answers, "quote", options)
        quote_index = options[choice]
    return {"topic": topic, "intent": intent, "severity": prompt["severity_levels"][level], "sentiment": sentiment,
            "quote_index": quote_index, "confidence": confidence}
