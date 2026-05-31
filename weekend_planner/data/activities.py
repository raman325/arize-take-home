"""DC-area family activity catalog.

Travel times are rough one-way estimates from a generic central-DC rowhouse.
Age ranges reflect what a venue is genuinely good for — not where they'd
turn a child away. The age-edge-case scenario relies on a couple of entries
(Air & Space, Imagination Stage) having min_age_years > 2 so the age filter
has something to drop.
"""

from __future__ import annotations

from ..schemas import Activity

ACTIVITIES: list[Activity] = [
    Activity(
        id="natl-zoo",
        name="Smithsonian National Zoo",
        description=(
            "Free outdoor zoo with pandas, big cats, and a small mammal house. "
            "Stroller-friendly paths. Most engaging on mild days; little shade in summer."
        ),
        indoor=False,
        min_age_years=1,
        max_age_years=99,
        typical_duration_min=180,
        travel_minutes_from_home=20,
        tags=["animals", "outdoor", "free", "stroller"],
    ),
    Activity(
        id="air-space",
        name="National Air and Space Museum",
        description=(
            "Aircraft and spacecraft exhibits. Most engaging for ages 4+ who can read "
            "the panels; younger kids may enjoy a short browse of the big planes."
        ),
        indoor=True,
        min_age_years=4,
        max_age_years=99,
        typical_duration_min=120,
        travel_minutes_from_home=25,
        tags=["museum", "indoor", "free", "educational"],
    ),
    Activity(
        id="nmnh",
        name="National Museum of Natural History",
        description=(
            "Dinosaur hall, ocean hall, and a live butterfly pavilion (small fee). "
            "Indoor, free admission, good for a rainy day."
        ),
        indoor=True,
        min_age_years=2,
        max_age_years=99,
        typical_duration_min=90,
        travel_minutes_from_home=25,
        tags=["museum", "indoor", "free", "dinosaurs", "rainy-day"],
    ),
    Activity(
        id="building-museum",
        name="National Building Museum — Building Zone",
        description=(
            "Indoor great hall with a dedicated toddler play area (Building Zone). "
            "Foam blocks, ramps, low-stakes climbing. Paid admission."
        ),
        indoor=True,
        min_age_years=1,
        max_age_years=6,
        typical_duration_min=90,
        travel_minutes_from_home=15,
        tags=["museum", "indoor", "playspace", "toddler", "rainy-day"],
    ),
    Activity(
        id="childrens-museum",
        name="National Children's Museum",
        description=(
            "Hands-on indoor museum near the Mall. Slide, sensory play, and the "
            "Innovation Hub. Designed for ages 0–11; toddlers do well here."
        ),
        indoor=True,
        min_age_years=1,
        max_age_years=11,
        typical_duration_min=120,
        travel_minutes_from_home=20,
        tags=["museum", "indoor", "playspace", "rainy-day"],
    ),
    Activity(
        id="botanic-garden",
        name="United States Botanic Garden",
        description=(
            "Conservatory of plants with an indoor jungle, a children's garden, "
            "and an outdoor terrace. Free, partly indoor — works in either weather."
        ),
        indoor=True,
        min_age_years=1,
        max_age_years=99,
        typical_duration_min=60,
        travel_minutes_from_home=20,
        tags=["gardens", "indoor", "outdoor", "free", "rainy-day"],
    ),
    Activity(
        id="rock-creek",
        name="Rock Creek Park nature walk",
        description=(
            "Forested walking trails near the city. Quiet, stroller-passable on the "
            "paved sections. Best when dry; muddy after rain."
        ),
        indoor=False,
        min_age_years=1,
        max_age_years=99,
        typical_duration_min=90,
        travel_minutes_from_home=10,
        tags=["outdoor", "nature", "free", "stroller"],
    ),
    Activity(
        id="glen-echo",
        name="Glen Echo Park carousel",
        description=(
            "Historic Dentzel carousel ($1.50 per ride) in a small art-deco park. "
            "Short outdoor visit; toddlers love the ride."
        ),
        indoor=False,
        min_age_years=2,
        max_age_years=10,
        typical_duration_min=45,
        travel_minutes_from_home=25,
        tags=["outdoor", "carousel", "short"],
    ),
    Activity(
        id="hains-point",
        name="Hains Point playground",
        description=(
            "Riverfront playground at East Potomac Park. Big sandbox, climbing "
            "structures sized for toddlers. Open, sunny, little shade."
        ),
        indoor=False,
        min_age_years=1,
        max_age_years=10,
        typical_duration_min=90,
        travel_minutes_from_home=20,
        tags=["outdoor", "playground", "free", "waterfront"],
    ),
    Activity(
        id="yards-park",
        name="Yards Park water feature",
        description=(
            "Seasonal urban water fountain (May–September) along the Anacostia. "
            "Toddlers splash in shallow water. Bring towels."
        ),
        indoor=False,
        min_age_years=1,
        max_age_years=10,
        typical_duration_min=90,
        travel_minutes_from_home=25,
        tags=["outdoor", "water", "summer", "free"],
    ),
    Activity(
        id="eastern-market",
        name="Eastern Market Saturday market",
        description=(
            "Outdoor farmers + artisan market on Capitol Hill, Saturdays only. "
            "Stroll, snacks, and a nearby playground at Hill Center."
        ),
        indoor=False,
        min_age_years=0,
        max_age_years=99,
        typical_duration_min=60,
        travel_minutes_from_home=15,
        tags=["market", "outdoor", "saturday-only", "food"],
    ),
    Activity(
        id="library-storytime",
        name="DC Public Library — toddler story time",
        description=(
            "Free 30-minute story-and-song sessions at branch libraries. "
            "Designed for ages 0–4. Indoor."
        ),
        indoor=True,
        min_age_years=0,
        max_age_years=4,
        typical_duration_min=45,
        travel_minutes_from_home=10,
        tags=["indoor", "free", "toddler", "books", "short"],
    ),
    Activity(
        id="roosevelt-island",
        name="Theodore Roosevelt Island walk",
        description=(
            "Quiet wooded island in the Potomac with a boardwalk loop. "
            "Stroller-passable on the boardwalk; rest of the trail is dirt."
        ),
        indoor=False,
        min_age_years=2,
        max_age_years=99,
        typical_duration_min=60,
        travel_minutes_from_home=15,
        tags=["outdoor", "nature", "free", "walk"],
    ),
    Activity(
        id="crescent-trail",
        name="Capital Crescent Trail stroller walk",
        description=(
            "Flat, paved former-rail trail. Easy stroller-friendly outdoor walk "
            "in any season — sheltered by trees, exposed in spots."
        ),
        indoor=False,
        min_age_years=0,
        max_age_years=99,
        typical_duration_min=60,
        travel_minutes_from_home=15,
        tags=["outdoor", "stroller", "walk", "free"],
    ),
    Activity(
        id="imagination-stage",
        name="Imagination Stage (Bethesda) — children's theater",
        description=(
            "Indoor children's theater. Most productions are aimed at ages 4–10 "
            "and run about an hour. Ticketed."
        ),
        indoor=True,
        min_age_years=4,
        max_age_years=12,
        typical_duration_min=60,
        travel_minutes_from_home=35,
        tags=["indoor", "theater", "performance"],
    ),
]


ACTIVITIES_BY_ID: dict[str, Activity] = {a.id: a for a in ACTIVITIES}
