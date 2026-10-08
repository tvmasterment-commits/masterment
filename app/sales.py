"""Catalog routing and no-key answers; approved facts live in business.json."""
import re


def match_catalog(text, knowledge):
    from .language import intake_text
    text = intake_text(text)
    catalog = knowledge.get("catalog", {})
    keys = [key for key, entry in catalog.items()
            if any(re.search(pattern, text, re.I) for pattern in entry["patterns"])]
    # Specific requests take precedence over overlapping generic words.
    suppress = set()
    if any(key in keys for key in ("wedding", "sweet16", "real_estate")):
        suppress.update(("photography", "event", "single"))
    if "nightclub" in keys:
        suppress.add("event")
    if "management" in keys:
        suppress.add("website")
    if "bot_maintenance" in keys:
        suppress.add("bot")
    if "monthly" in keys:
        suppress.add("single")
    if "real_estate" in keys:
        suppress.update(("monthly", "drone"))
    if "bot" in keys and re.search(r"\b(already|existing|have a website)\b", text, re.I):
        suppress.add("website")
    return [key for key in keys if key not in suppress]


def conversation_catalog(history, knowledge):
    turns = []
    for turn in history:
        if turn.get("role") != "user":
            continue
        text = turn.get("content", "")
        if re.search(r"\b(correction|instead|no longer|only need)\b", text, re.I):
            turns = []
        turns.append(text)
    return match_catalog("\n".join(turns), knowledge)


def offer_data(knowledge, key, heading):
    """Shared public/chat projection of an approved price block."""
    entry = knowledge["catalog"][key]
    section = knowledge["business_knowledge"][entry["section"]]
    # A heading is a complete line (optionally with the monthly price on it).
    match = re.search(r"(?m)^" + re.escape(heading) + r"(?=\s*(?:—|$))", section)
    if not match:
        raise ValueError(f"Missing approved price block: {heading}")
    rest = section[match.end():]
    other_headings = {block for item in knowledge["catalog"].values()
                      if item["section"] == entry["section"] for block in item["price_blocks"]}
    boundaries = [m.start() for block in other_headings
                  if (m := re.search(r"(?m)^" + re.escape(block) + r"(?=\s*(?:—|$))", rest))]
    if boundaries:
        rest = rest[:min(boundaries)]
    amounts = list(re.finditer(r"(?:Starting at )?\$[\d,]+(?:/month)?", rest, re.I))
    count = 2 if key in ("website", "bot") else 1
    prices = [m.group() for m in amounts[:count]]
    if len(prices) != count:
        raise ValueError(f"Incomplete approved pricing: {heading}")
    includes = []
    if key == "monthly":
        block = rest.split("Includes:\n", 1)[1].split("\n\n", 1)[0]
        includes = [line.removeprefix("- ") for line in block.splitlines()]
    return {"name": heading.title(), "prices": prices, "includes": includes}


def price_block(knowledge, key, heading):
    offer = offer_data(knowledge, key, heading)
    prices = offer["prices"]
    count = len(prices)
    if count == 2:
        result = f"{heading.title()}: {prices[0]} setup + {prices[1]}"
    else:
        result = f"{heading.title()}: {prices[0]}"
    if key == "monthly":
        result += ". Includes " + "; ".join(offer["includes"])
    return result + "."


def selected_blocks(key, text, knowledge):
    blocks = knowledge["catalog"][key]["price_blocks"]
    if key == "monthly":
        for index, pattern in enumerate((r"essential|\b(2|two)\b", r"growth|weekly|\b(4|four)\b", r"signature|\b(6|six)\b")):
            if re.search(pattern, text, re.I):
                return [blocks[index]]
    if key in ("website", "bot", "music_video"):
        tiers = ("starter", "business", "advanced") if key != "music_video" else ("basic", "standard", "premium|cinematic")
        for index, tier in enumerate(tiers):
            if re.search(r"\b(?:" + tier + r")\b", text, re.I):
                return [blocks[index]]
    if key in ("real_estate", "wedding", "sweet16"):
        photo = bool(re.search(r"photo|photos|photography", text, re.I))
        video = bool(re.search(r"video|reel|film", text, re.I))
        if photo and video:
            return [next(b for b in blocks if "PHOTO + VIDEO" in b)]
        if key == "real_estate" and (photo or video):
            return [blocks[0 if photo else 1]]
        if key == "sweet16" and (photo or video):
            return [blocks[1 if photo else 0]]
    return blocks


def sales_answer(history, lead, knowledge):
    """Answer catalog/policy questions without making up prices or scope."""
    last = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    keys = conversation_catalog(history, knowledge)
    current_keys = match_catalog(last, knowledge)
    prior = "\n".join(m["content"] for m in history if m.get("role") == "user")
    if re.search(r"what (?:services|do you (?:do|offer))|who (?:is|are) masterment|about masterment", last, re.I):
        return knowledge["description"] + " Services include " + "; ".join(knowledge["services"]) + "."
    if re.search(r"discount|cheaper|lower (?:the )?price|deal\b", last, re.I):
        return knowledge["responses"]["discount"]
    if re.search(r"guarantee|viral|guaranteed|unlimited", last, re.I):
        return (knowledge["responses"]["results_limits"])
    volume = re.search(r"\b(\d+)\s+(?:reels?|videos?)\b", last, re.I)
    if re.search(r"outside|(?:doesn.t|don.t|does not|do not) fit|custom quote|\b(?:twenty|100)\s+(?:reels|videos|pages)", last, re.I) or (
        "monthly" in keys and volume and int(volume.group(1)) not in (2, 4, 6)
    ):
        return knowledge["responses"]["custom_scope"]
    if not current_keys and not re.search(r"how much|price|pricing|cost|include|package|starter|standard|premium|advanced|essential|growth|signature", last, re.I):
        return ""
    if not keys:
        if re.search(r"how much|price|pricing|cost", last, re.I):
            return knowledge["responses"]["unpriced"]
        return ""
    replies = []
    if "international" in keys:
        replies.append(knowledge["responses"]["international"])
    if "music_network" in keys:
        replies.append(knowledge["responses"]["music_network"])
    if "talent" in keys:
        replies.append(knowledge["responses"]["talent"])
    if "management" in keys:
        replies.append(knowledge["responses"]["management"])
    if "bot_maintenance" in keys or "unpriced" in keys:
        replies.append(knowledge["responses"]["custom_service"])
    for key in keys:
        if key in ("international", "music_network", "talent", "management"):
            continue
        if "international" in keys:
            continue  # Local production starting prices are not international quotes.
        if key == "real_estate" and re.search(r"recurring|monthly|multiple listings|every month", prior, re.I):
            replies.append(knowledge["responses"]["recurring_properties"])
            continue
        replies.extend(price_block(knowledge, key, block) for block in selected_blocks(key, last if current_keys else prior, knowledge))
        if key == "real_estate" and "drone" in last.lower() and "DRONE ADD-ON" not in selected_blocks(key, last, knowledge):
            replies.append(price_block(knowledge, key, "DRONE ADD-ON"))
    if any("starting at" in reply.lower() for reply in replies):
        replies.append(knowledge["responses"]["starting_prices"])
    if "monthly" in keys:
        replies.append(knowledge["responses"]["monthly_exclusions"])
    if "website" in keys:
        replies.append(knowledge["responses"]["website_exclusions"])
    if "bot" in keys:
        replies.append(knowledge["responses"]["existing_site_bot_limits"])
    if "drone" in keys or ("real_estate" in keys and "drone" in last.lower()):
        replies.append(knowledge["responses"]["drone_limits"])
    if len(keys) > 1:
        replies.append(knowledge["responses"]["combinations"])
    return " ".join(replies)


def catalog_question(history, knowledge):
    from .language import localize_question, intake_text
    text = "\n".join(m["content"] for m in history if m.get("role") == "user")
    text = intake_text(text)
    for key in conversation_catalog(history, knowledge):
        for _, pattern, question in knowledge["catalog"][key].get("questions", []):
            answered = any(
                turn.get("role") == "assistant" and (turn.get("content", "").endswith(question)
                                                      or turn.get("content", "").endswith(localize_question(question)))
                and following.get("role") == "user" and following.get("content", "").strip()
                and "?" not in following["content"]
                for turn, following in zip(history, history[1:])
            )
            if answered:
                continue
            from .conversation import repeated_or_known
            if not re.search(pattern, text, re.I) and not repeated_or_known(question, history, {}):
                return question
    return None


def unsupported_sales_claim(reply, history, knowledge):
    """Reject unapproved monetary amounts, discounts, and explicit promises.

    This is a narrow guard, not a substitute for the approved model instructions.
    """
    prices = lambda text: set(re.findall(r"\$\s*[\d,]+(?:\.\d+)?", text))
    approved = sales_answer(history, {}, knowledge)
    normalized = lambda values: {value.replace(",", "").replace(" ", "") for value in values}
    if normalized(prices(reply)) - normalized(prices(approved)):
        return True
    for match in re.finditer(r"\$\s*[\d,]+(?:\.\d+)?", reply):
        amount = match.group().replace(" ", "")
        if re.search(r"Starting at\s+" + re.escape(amount), approved, re.I):
            qualifier = reply[max(0, match.start() - 30):match.start()]
            if not re.search(r"starting at|starts at|from\s*$", qualifier, re.I):
                return True
    for sentence in re.split(r"[.!?\n]", reply):
        if re.search(r"not|never|no |can.t|cannot|don.t|doesn.t|isn.t|aren.t|without|may|depends|subject", sentence, re.I):
            continue
        if re.search(r"\b(guarantee[ds]?|unlimited|\d+\s*%\s*(?:off|discount)|discount of|availability is confirmed)\b", sentence, re.I):
            return True
    return False
