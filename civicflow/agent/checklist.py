# Honolulu DPP building-permit submittal requirements

from __future__ import annotations

from typing import Any, Dict, List, Set


# Permit type / category constants

ALL: Set[str] = set()   # Sentinel: applies to every permit

RESIDENTIAL = {"Residential", "R-3 Dwelling", "Single Family Dwelling", "SFD"}
COMMERCIAL = {"Commercial", "Store", "Office", "Hotel", "Multi-Family"}
NEW_BLDG = {"newbuilding"}
ADDITION = {"addition"}
ALTERATION = {"alteration"}
ADDITION_OR_ALTERATION = ADDITION | ALTERATION
SOLAR = {"solar", "solarvpinstallation"}
POOL = {"pool"}
ELECTRICAL = {"electricalwork"}
PLUMBING = {"plumbingwork"}
DEMOLITION = {"demolition"}
FENCE = {"fence"}


# Requirement definitions

REQUIREMENTS: List[Dict[str, Any]] = [
    # Universal / all permit types
    {
        "id": "U-001",
        "section": "Application",
        "description": "Completed building permit application form (BP-1) signed by the owner or authorized agent.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-002",
        "section": "Application",
        "description": "Proof of property ownership or written authorization from the owner.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-003",
        "section": "Plans",
        "description": "Two (2) sets of construction drawings, minimum 1/4\" = 1'-0\" scale for floor plans.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-004",
        "section": "Plans",
        "description": "Site plan showing property boundaries, setbacks, existing and proposed structures, and north arrow.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-005",
        "section": "Plans",
        "description": "Floor plan(s) with dimensions, room labels, door/window locations, and square footage.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-006",
        "section": "Plans",
        "description": "Elevation drawings for all affected exterior walls.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-007",
        "section": "Plans",
        "description": "Title block on each plan sheet: project address, TMK, owner name, designer name & license, date, revision history.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-008",
        "section": "Zoning",
        "description": "Zoning compliance table showing allowable vs. proposed lot coverage, FAR, setbacks, and height.",
        "applies_to": ALL,
        "required": True,
    },
    {
        "id": "U-009",
        "section": "Accessibility",
        "description": "Accessibility compliance notes (ADA/HRS 103) for commercial and multi-family projects.",
        "applies_to": COMMERCIAL,
        "required": True,
    },
    # New Building
    {
        "id": "NB-001",
        "section": "Structural",
        "description": "Structural drawings: foundation plan, framing plans, sections, and connection details.",
        "applies_to": NEW_BLDG,
        "required": True,
    },
    {
        "id": "NB-002",
        "section": "Structural",
        "description": "Soils report or geotechnical investigation report for new foundations.",
        "applies_to": NEW_BLDG,
        "required": True,
    },
    {
        "id": "NB-003",
        "section": "Structural",
        "description": "Structural calculations stamped by a licensed Hawaii PE.",
        "applies_to": NEW_BLDG,
        "required": True,
    },
    {
        "id": "NB-004",
        "section": "Energy",
        "description": "Hawaii Energy Code compliance documentation (IECC / Title 23).",
        "applies_to": NEW_BLDG,
        "required": True,
    },
    {
        "id": "NB-005",
        "section": "Fire",
        "description": "Fire protection plan (sprinkler system layout) if building area or occupancy requires it.",
        "applies_to": NEW_BLDG,
        "required": False,  # Conditional on size / occupancy
    },
    {
        "id": "NB-006",
        "section": "Civil",
        "description": "Grading and drainage plan with erosion/sediment control for lots >= 10,000 sq ft disturbed.",
        "applies_to": NEW_BLDG,
        "required": False,
    },
    # Additions / Alterations
    {
        "id": "AD-001",
        "section": "Plans",
        "description": "Existing conditions plan clearly delineating existing vs. proposed work.",
        "applies_to": ADDITION_OR_ALTERATION,
        "required": True,
    },
    {
        "id": "AD-002",
        "section": "Structural",
        "description": "Structural analysis showing existing structure can support the proposed addition loads.",
        "applies_to": ADDITION_OR_ALTERATION,
        "required": True,
    },
    # Solar PV
    {
        "id": "PV-001",
        "section": "Solar",
        "description": "Roof plan showing module layout, setbacks from ridge/eave/hip, and fire access pathways.",
        "applies_to": SOLAR,
        "required": True,
    },
    {
        "id": "PV-002",
        "section": "Solar",
        "description": "Single-line electrical diagram showing PV array, inverter(s), AC/DC disconnects, and utility interconnection.",
        "applies_to": SOLAR,
        "required": True,
    },
    {
        "id": "PV-003",
        "section": "Solar",
        "description": "Structural attachment details showing rafter/truss size, span, spacing, and module mounting hardware.",
        "applies_to": SOLAR,
        "required": True,
    },
    {
        "id": "PV-004",
        "section": "Solar",
        "description": "HECO/utility interconnection approval or application letter.",
        "applies_to": SOLAR,
        "required": False,
    },
    {
        "id": "PV-005",
        "section": "Solar",
        "description": "Manufacturer spec sheets for PV modules and inverter(s).",
        "applies_to": SOLAR,
        "required": True,
    },
    # Electrical work (non-solar)
    {
        "id": "EL-001",
        "section": "Electrical",
        "description": "Electrical plan showing panel location, load calculations, circuit schedule, and new work.",
        "applies_to": ELECTRICAL,
        "required": True,
    },
    {
        "id": "EL-002",
        "section": "Electrical",
        "description": "Load calculation sheet per NEC Article 220.",
        "applies_to": ELECTRICAL,
        "required": True,
    },
    # Plumbing
    {
        "id": "PL-001",
        "section": "Plumbing",
        "description": "Plumbing isometric or riser diagram showing supply, drainage, vent, and fixture units.",
        "applies_to": PLUMBING,
        "required": True,
    },
    # Pool
    {
        "id": "PO-001",
        "section": "Pool",
        "description": "Pool plan with dimensions, depth profile, equipment pad layout, and barrier/fencing details.",
        "applies_to": POOL,
        "required": True,
    },
    {
        "id": "PO-002",
        "section": "Pool",
        "description": "Barrier/fence plan meeting Hawaii barrier requirements (5-foot minimum height).",
        "applies_to": POOL,
        "required": True,
    },
    # Demolition
    {
        "id": "DM-001",
        "section": "Demolition",
        "description": "Asbestos survey or clearance report from a certified inspector.",
        "applies_to": DEMOLITION,
        "required": True,
    },
    {
        "id": "DM-002",
        "section": "Demolition",
        "description": "Utility disconnection confirmation letters (HECO, BWS, gas).",
        "applies_to": DEMOLITION,
        "required": True,
    },
    # Fence
    {
        "id": "FE-001",
        "section": "Fence",
        "description": "Fence/wall plan showing location, height, materials, and setbacks from all property lines.",
        "applies_to": FENCE,
        "required": True,
    },
]


# Helper: get requirements that apply to a given permit


def get_applicable_requirements(permit: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Build set of active categories for this permit
    active: Set[str] = set()

    # Residential / commercial
    cr = str(permit.get("commercialresidential", "")).strip()
    if cr:
        active.add(cr)
        if cr == "Residential":
            active.update(RESIDENTIAL)
        elif cr == "Commercial":
            active.update(COMMERCIAL)

    # Work type flags
    flag_map = {
        "newbuilding": NEW_BLDG,
        "addition": ADDITION,
        "alteration": ALTERATION,
        "solar": SOLAR,
        "solarvpinstallation": SOLAR,
        "electricalwork": ELECTRICAL,
        "plumbingwork": PLUMBING,
        "demolition": DEMOLITION,
        "pool": POOL,
        "fence": FENCE,
    }
    for flag, cats in flag_map.items():
        val = permit.get(flag)
        if val is True or str(val).upper() in ("Y", "TRUE", "1", "YES"):
            active.update(cats)

    # Infer categories from permit-type text too
    # This only widens the active set
    permit_type_text = str(permit.get("buildingpermittype", "")).lower()
    type_keyword_map = {
        "new building": NEW_BLDG,
        "addition": ADDITION,
        "alteration": ALTERATION,
        "demolition": DEMOLITION,
        "solar": SOLAR,
        "pool": POOL,
        "fence": FENCE,
        "electrical": ELECTRICAL,
        "plumbing": PLUMBING,
    }
    for keyword, cats in type_keyword_map.items():
        if keyword in permit_type_text:
            active.update(cats)

    result = []
    for req in REQUIREMENTS:
        scope: Set[str] = req["applies_to"]
        if not scope or scope & active:   # ALL (empty set) or overlap
            result.append(req)
    return result
