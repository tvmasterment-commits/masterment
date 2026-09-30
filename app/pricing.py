"""Small, public-only view of the same approved catalog used by the assistant."""
import re
from .sales import offer_data


def pricing_view(knowledge):
    sections = []
    for section in knowledge["public_pricing"]["sections"]:
        offers = []
        for key in section.get("catalog_keys", []):
            for heading in knowledge["catalog"][key]["price_blocks"]:
                offer = offer_data(knowledge, key, heading)
                offer["selection"] = section["title"] + " — " + offer["name"]
                offer["display_price"] = " setup + ".join(offer["prices"])
                offer["brief"] = section.get("briefs", {}).get(heading, "")
                if key == "monthly":
                    reels = re.search(r"\d+", offer["includes"][0]).group()
                    photos = next(re.search(r"\d+", item).group() for item in offer["includes"] if "photos" in item)
                    offer["summary"] = f"{reels} Reels / month · {photos} Edited Photos"
                offers.append(offer)
        sections.append({**section, "offers": offers})
    return sections
