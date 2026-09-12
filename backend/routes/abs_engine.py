"""Evidence-grounded Access and Benefit Sharing screening routes."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.rag_pipeline import run_rag_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/abs", tags=["abs_engine"])

_ABS_TRIGGER_REGIONS = {
    "india", "brazil", "south africa", "kenya", "malaysia", "indonesia",
    "peru", "colombia", "costa rica", "philippines", "thailand", "vietnam",
    "china", "mexico", "ethiopia",
}


class ABSScreenRequest(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
    source_region: str | None = None
    is_biological: bool | None = None
    category: str | None = None
    product_use: str | None = None
    access_use_context: str | None = None
    applicant_entity_status: str | None = None
    research_or_commercial_purpose: str | None = None
    traditional_knowledge_used: bool | None = None
    ip_activity: str | None = None
    access_from_region: bool | None = None
    procurement_details: str | None = None
    existing_permissions: str | None = None


class EvidenceItem(BaseModel):
    source_chunk_id: str
    source: str
    document: str
    section: str = ""
    page: str = ""
    excerpt: str
    relevance: str = ""
    evidence_type: str = ""
    semantic_similarity: float = 0.0
    verified: bool = False


class ObligationItem(BaseModel):
    area: str
    status: str
    color: str
    what_this_means: str
    next_step: str
    why_it_matters: str
    details: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ABSScreenResponse(BaseModel):
    overall_status: str
    applicable: bool
    reasoning: str
    color: str
    region_triggers_abs: bool
    is_biological: bool | None
    input_screening: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    obligations: list[ObligationItem] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: str = "INSUFFICIENT EVIDENCE"
    confidence_score: float | None = None
    sources: list[str] = Field(default_factory=list)
    escalate: bool = False
    response_status: str = "insufficient_evidence"
    disclaimer: str = "Information, not legal advice"


class ABSObligationsRequest(ABSScreenRequest):
    pass


class ABSObligationsResponse(ABSScreenResponse):
    pass


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _region_triggers(region: str | None) -> bool:
    value = _clean(region).lower()
    return bool(value) and any(candidate in value for candidate in _ABS_TRIGGER_REGIONS)


def _display(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip()


def _input_screening(request: ABSScreenRequest) -> dict[str, Any]:
    return {
        "ingredients": list(request.ingredients),
        "source_region": _display(request.source_region),
        "biological_origin": _display(request.is_biological),
        "category": _display(request.category),
        "product_use": _display(request.product_use),
        "access_use_context": _display(request.access_use_context),
        "applicant_entity_status": _display(request.applicant_entity_status),
        "research_or_commercial_purpose": _display(request.research_or_commercial_purpose),
        "traditional_knowledge_used": _display(request.traditional_knowledge_used),
        "ip_activity": _display(request.ip_activity),
        "access_from_region": _display(request.access_from_region),
        "procurement_details": _display(request.procurement_details),
        "existing_permissions": _display(request.existing_permissions),
    }


def _information_gaps(request: ABSScreenRequest) -> list[str]:
    gaps: list[str] = []
    if request.is_biological is None:
        gaps.append("Whether the ingredients are of biological origin")
    if not _clean(request.source_region):
        gaps.append("Source region or country of access")
    if not _clean(request.applicant_entity_status):
        gaps.append("Applicant or entity status")
    if not _clean(request.access_use_context):
        gaps.append("Nature of access or use")
    if not _clean(request.research_or_commercial_purpose):
        gaps.append("Whether the activity is research, commercial utilization, or another purpose")
    if request.traditional_knowledge_used is None:
        gaps.append("Whether associated traditional knowledge was used")
    if not _clean(request.ip_activity):
        gaps.append("Whether an intellectual-property application is planned or already filed")
    if request.access_from_region is None and _clean(request.source_region).lower() == "india":
        gaps.append("Whether the resource was accessed from India")
    if not _clean(request.procurement_details):
        gaps.append("Source or procurement details")
    if not _clean(request.existing_permissions):
        gaps.append("Existing permissions or agreements, if any")
    return gaps


def _evidence_from_rag(rag_result: dict[str, Any]) -> list[EvidenceItem]:
    raw_items = rag_result.get("evidence") or []
    evidence: list[EvidenceItem] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        chunk_id = _clean(item.get("source_chunk_id"))
        excerpt = _clean(item.get("excerpt"))
        source = _clean(item.get("source") or item.get("source_document"))
        if not chunk_id or not excerpt or not source or chunk_id in seen:
            continue
        if item.get("verified") is False and item.get("evidence") is not None:
            continue
        seen.add(chunk_id)
        evidence.append(EvidenceItem(
            source_chunk_id=chunk_id,
            source=source,
            document=source,
            section=_clean(item.get("section")),
            page=_clean(item.get("page")),
            excerpt=excerpt,
            relevance=_clean(item.get("relevance")),
            evidence_type=_clean(item.get("evidence_type") or item.get("type")),
            semantic_similarity=float(item.get("semantic_similarity") or 0.0),
            verified=bool(item.get("verified", True)),
        ))
    return evidence


# ── Area-specific keyword sets for evidence matching ─────────────────────

_AREA_TERMS: dict[str, tuple[str, ...]] = {
    "COMPETENT AUTHORITY": ("authority", "nba", "sbb", "biodiversity board", "jurisdiction", "national biodiversity", "state biodiversity"),
    "APPROVAL / INTIMATION": ("approval", "intimation", "permission", "access", "application", "prior approval", "form i", "section 3", "section 7"),
    "BENEFIT-SHARING": ("benefit", "sharing", "monetary", "non-monetary", "royalty", "fair and equitable"),
    "IPR / DISCLOSURE": ("patent", "intellectual property", "disclosure", "section 6", "ipr", "form iii", "form 3"),
    "REQUIRED DOCUMENTATION": ("document", "form", "record", "procurement", "agreement", "consent", "prior informed"),
}


def _evidence_for_area(evidence: list[EvidenceItem], area: str) -> list[EvidenceItem]:
    terms = _AREA_TERMS[area]
    matched = [item for item in evidence if any(term in f"{item.excerpt} {item.relevance}".lower() for term in terms)]
    return matched[:3] or evidence[:1]


def _status_color(status: str) -> str:
    return {
        "RELEVANT": "green",
        "POTENTIALLY APPLICABLE": "yellow",
        "NOT CLEARLY TRIGGERED": "slate",
        "INFORMATION REQUIRED": "amber",
        "NOT IDENTIFIED": "slate",
    }.get(status, "slate")


# ── AI Failure Message Filter ────────────────────────────────────────────

_AI_FAILURE_TERMS = (
    "could not be completed",
    "could not be fully completed",
    "ai synthesis",
    "synthesis could not",
    "could not be generated",
    "could not be fully generated",
    "stage exception",
    "timeout",
    "timed out",
    "traditional knowledge analysis could not",
    "formulation guidance could not",
    "patentability assessment requires further",
    "prior-art analysis could not",
)


def _is_ai_failure_text(text: str | None) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(term in lower for term in _AI_FAILURE_TERMS)


# ── Parse RAG answer to extract per-area findings ────────────────────────

def _parse_area_findings(rag_result: dict[str, Any]) -> dict[str, str]:
    """Extract area-specific reasoning from the RAG answer and key_points.

    Returns a dict mapping area name → relevant reasoning excerpt.
    """
    answer = _clean(rag_result.get("answer") or rag_result.get("assessment"))
    why = _clean(rag_result.get("why"))
    key_points = rag_result.get("key_points") or []
    
    # Exclude internal AI errors from per-area finding parsing
    text_chunks = [t for t in [answer, why] if t and not _is_ai_failure_text(t)]
    text_chunks.extend(str(p) for p in key_points if p and not _is_ai_failure_text(str(p)))
    combined_text = " ".join(text_chunks)

    area_findings: dict[str, str] = {}
    if not combined_text.strip():
        return area_findings

    for area, terms in _AREA_TERMS.items():
        # Collect sentences that match this area's terms
        sentences = re.split(r'(?<=[.;])\s+', combined_text)
        matched: list[str] = []
        for sentence in sentences:
            s_lower = sentence.lower()
            if any(term in s_lower for term in terms) and not _is_ai_failure_text(sentence):
                cleaned = sentence.strip()
                if cleaned and len(cleaned) > 15:
                    matched.append(cleaned)
        if matched:
            area_findings[area] = " ".join(matched[:3])

    return area_findings


def _detect_authority_from_evidence(evidence: list[EvidenceItem]) -> str | None:
    """Try to determine the competent authority from evidence excerpts.

    Returns 'NBA', 'SBB', or None if indeterminate.
    """
    nba_signals = 0
    sbb_signals = 0
    for item in evidence:
        text = f"{item.excerpt} {item.relevance} {item.section}".lower()
        if any(k in text for k in ("national biodiversity authority", "nba", "section 3", "section 4", "section 6")):
            nba_signals += 1
        if any(k in text for k in ("state biodiversity board", "sbb", "section 7", "intimation")):
            sbb_signals += 1

    if nba_signals > 0 and sbb_signals == 0:
        return "NBA"
    if sbb_signals > 0 and nba_signals == 0:
        return "SBB"
    if nba_signals > 0 and sbb_signals > 0:
        return "NBA/SBB"
    return None


# ── Evidence-grounded obligation builder ─────────────────────────────────

def _build_obligation(
    area: str,
    request: ABSScreenRequest,
    area_evidence: list[EvidenceItem],
    gaps: list[str],
    rag_result: dict[str, Any],
    area_findings: dict[str, str],
) -> ObligationItem:
    has_evidence = bool(area_evidence)
    bio_known = request.is_biological is not None
    region_known = bool(_clean(request.source_region))
    facts_missing = not _clean(request.applicant_entity_status) or not _clean(request.access_use_context)

    # ── Determine status ─────────────────────────────────────────────
    if not bio_known or not region_known:
        status = "INFORMATION REQUIRED"
    elif request.is_biological is False:
        status = "NOT CLEARLY TRIGGERED"
    elif area == "IPR / DISCLOSURE" and not _clean(request.ip_activity):
        status = "INFORMATION REQUIRED"
    elif area in {"APPROVAL / INTIMATION", "COMPETENT AUTHORITY", "BENEFIT-SHARING"}:
        # Keep conditional: exact statutory pathway and exemptions require confirmation
        status = "POTENTIALLY APPLICABLE"
    elif has_evidence and facts_missing:
        status = "POTENTIALLY APPLICABLE"
    elif has_evidence:
        status = "RELEVANT"
    else:
        status = "NOT IDENTIFIED"

    # ── Build area-specific evidence excerpt for grounding ────────────
    evidence_excerpt = ""
    if area_evidence:
        # Use the best-matching evidence excerpt for grounded text
        best = area_evidence[0]
        evidence_excerpt = best.excerpt[:300] if best.excerpt else ""
        evidence_source = f"{best.source}" + (f", {best.section}" if best.section else "")
    else:
        evidence_source = ""

    # ── Retrieve any LLM-parsed finding for this area ────────────────
    llm_finding = area_findings.get(area, "")

    # ── Build what_this_means (evidence-grounded) ────────────────────
    # ── Build next_step (case-specific) ──────────────────────────────
    # ── Build why_it_matters (legally grounded) ──────────────────────

    if status == "NOT CLEARLY TRIGGERED":
        meaning = "The provided screening states that the resource is not biological, so this area is not clearly triggered by the submitted facts."
        next_step = "Re-run the screening if the biological origin or resource facts change."
        why = "The screening cannot apply a biological-resource pathway to a purely non-biological declaration."

    elif status == "INFORMATION REQUIRED":
        # Identify the specific missing facts relevant to THIS area
        area_gaps = _gaps_for_area(area, request)
        missing_str = ", ".join(area_gaps[:3]) if area_gaps else "the missing case facts"
        meaning = f"This area cannot be assessed conclusively because {missing_str} has not been provided."
        if llm_finding:
            meaning += f" The retrieved evidence indicates: {llm_finding[:200]}"
        next_step = f"Provide {missing_str.lower()} before relying on a specific ABS pathway."
        why = "The authority, pathway, and compliance effect depend on case facts that are not present in this screening."

    elif status == "NOT IDENTIFIED":
        meaning = "No reliable evidence for this area was identified in the retrieved corpus."
        next_step = "Confirm the relevant facts and consult the applicable authority or legal professional if the activity proceeds."
        why = "Absence from the retrieved corpus is not proof that no legal requirement exists."

    elif status == "POTENTIALLY APPLICABLE":
        # Evidence exists but some facts are missing — use evidence to ground the explanation
        meaning = _grounded_meaning_for_area(area, request, evidence_excerpt, evidence_source, llm_finding, partial=True)
        next_step = _grounded_next_step_for_area(area, request, area_evidence)
        why = _grounded_why_for_area(area, evidence_source, partial=True)

    else:  # RELEVANT
        meaning = _grounded_meaning_for_area(area, request, evidence_excerpt, evidence_source, llm_finding, partial=False)
        next_step = _grounded_next_step_for_area(area, request, area_evidence)
        why = _grounded_why_for_area(area, evidence_source, partial=False)

    # ── Include RAG answer as supporting details ─────────────────────
    details = ""
    if has_evidence:
        rag_answer = _clean(rag_result.get("answer") or rag_result.get("assessment"))
        if rag_answer and not _is_ai_failure_text(rag_answer):
            details = rag_answer
        elif area_evidence:
            details = f"Retrieved regulatory provisions from {area_evidence[0].document} are available for {area.lower()} review."

    return ObligationItem(
        area=area,
        status=status,
        color=_status_color(status),
        what_this_means=meaning,
        next_step=next_step,
        why_it_matters=why,
        details=details,
        evidence=area_evidence,
    )


def _gaps_for_area(area: str, request: ABSScreenRequest) -> list[str]:
    """Return the specific information gaps relevant to a given obligation area."""
    if area == "COMPETENT AUTHORITY":
        gaps = []
        if not _clean(request.applicant_entity_status):
            gaps.append("applicant or entity status (determines NBA vs SBB jurisdiction)")
        if not _clean(request.access_use_context):
            gaps.append("nature of access or use")
        if not _clean(request.source_region):
            gaps.append("source region")
        return gaps
    elif area == "APPROVAL / INTIMATION":
        gaps = []
        if not _clean(request.applicant_entity_status):
            gaps.append("applicant or entity status")
        if not _clean(request.research_or_commercial_purpose):
            gaps.append("whether the purpose is research or commercial utilization")
        if not _clean(request.access_use_context):
            gaps.append("nature of access or use")
        return gaps
    elif area == "BENEFIT-SHARING":
        gaps = []
        if not _clean(request.research_or_commercial_purpose):
            gaps.append("whether the activity is research or commercial utilization")
        if not _clean(request.applicant_entity_status):
            gaps.append("applicant or entity status")
        return gaps
    elif area == "IPR / DISCLOSURE":
        gaps = []
        if not _clean(request.ip_activity):
            gaps.append("whether an intellectual-property application is planned or already filed")
        if not _clean(request.applicant_entity_status):
            gaps.append("applicant or entity status")
        return gaps
    elif area == "REQUIRED DOCUMENTATION":
        gaps = []
        if not _clean(request.procurement_details):
            gaps.append("source or procurement details")
        if not _clean(request.existing_permissions):
            gaps.append("existing permissions or agreements")
        if request.traditional_knowledge_used is None:
            gaps.append("whether traditional knowledge was used")
        return gaps
    return []


def _grounded_meaning_for_area(
    area: str,
    request: ABSScreenRequest,
    evidence_excerpt: str,
    evidence_source: str,
    llm_finding: str,
    partial: bool,
) -> str:
    """Build a case-specific, evidence-grounded 'what this means' explanation."""
    ingredients_str = ", ".join(request.ingredients) if request.ingredients else "the stated resources"
    region = _display(request.source_region)
    qualifier = "may be applicable" if partial else "is relevant"

    if area == "COMPETENT AUTHORITY":
        detected = _detect_authority_from_evidence([])  # Will use area_evidence in caller context
        base = f"Based on the stated biological origin ({ingredients_str}) and source region ({region}), a competent authority pathway {qualifier}."
        if llm_finding:
            base += f" The retrieved evidence indicates: {llm_finding[:250]}"
        elif evidence_excerpt:
            base += f" Retrieved evidence from {evidence_source} discusses: \"{evidence_excerpt[:200]}...\""
        if partial:
            base += " The specific authority (e.g. NBA, SBB, or another body) cannot be conclusively determined without additional facts."
        return base

    elif area == "APPROVAL / INTIMATION":
        return (
            "The submitted facts indicate that the Section 7 commercial-utilisation pathway may be relevant. "
            "Prior intimation requirements should be confirmed based on the exact biological resource, "
            "source/access circumstances, and any applicable exemption."
        )

    elif area == "BENEFIT-SHARING":
        base = f"Benefit-sharing considerations {qualifier} given the biological origin of {ingredients_str}."
        if llm_finding:
            base += f" {llm_finding[:250]}"
        elif evidence_excerpt:
            base += f" Evidence from {evidence_source}: \"{evidence_excerpt[:200]}...\""
        # Always conditional per requirement 5
        base += " If the applicable ABS framework is triggered for this access/use, benefit-sharing conditions may need to be determined by the competent authority under the applicable framework."
        return base

    elif area == "IPR / DISCLOSURE":
        ip = _display(request.ip_activity)
        if ip != "Not provided":
            base = f"Based on the stated IP activity ({ip}) involving {ingredients_str}, IPR/disclosure requirements {qualifier}."
        else:
            base = f"IPR/disclosure requirements {qualifier} for biological resources ({ingredients_str})."
        if llm_finding:
            base += f" {llm_finding[:250]}"
        elif evidence_excerpt:
            base += f" Evidence from {evidence_source}: \"{evidence_excerpt[:200]}...\""
        if partial and ip == "Not provided":
            base += " Applicant/entity status and the nature of the IP activity are required to determine the applicable IPR/ABS pathway."
        return base

    else:  # REQUIRED DOCUMENTATION
        base = f"Documentation requirements {qualifier} for the use of {ingredients_str} from {region}."
        if llm_finding:
            base += f" {llm_finding[:250]}"
        elif evidence_excerpt:
            base += f" Evidence from {evidence_source}: \"{evidence_excerpt[:200]}...\""
        if partial:
            base += " The specific documentation depends on the applicable pathway and competent authority determination."
        return base


def _grounded_next_step_for_area(
    area: str,
    request: ABSScreenRequest,
    area_evidence: list[EvidenceItem],
) -> str:
    """Build a case-specific next step based on available/missing facts."""
    if area == "COMPETENT AUTHORITY":
        if not _clean(request.applicant_entity_status):
            return "Confirm the applicant/entity status and nature of access to determine whether NBA, SBB, or another authority applies."
        detected = _detect_authority_from_evidence(area_evidence)
        if detected:
            return f"Review the cited evidence regarding {detected} jurisdiction and confirm that its scope matches the planned activity."
        return "Review the cited statutory passage and confirm which authority has jurisdiction for this access/use scenario."

    elif area == "APPROVAL / INTIMATION":
        if not _clean(request.research_or_commercial_purpose):
            return "Clarify whether the intended purpose is research or commercial utilization to determine the approval pathway."
        return "Review the cited approval/intimation requirements against the planned activity and confirm the applicable form/process."

    elif area == "BENEFIT-SHARING":
        if not _clean(request.research_or_commercial_purpose):
            return "Determine the nature of use (research vs. commercial) to assess whether benefit-sharing conditions are triggered."
        return "If the ABS pathway is triggered, consult the competent authority to determine any applicable benefit-sharing terms."

    elif area == "IPR / DISCLOSURE":
        ip = _display(request.ip_activity)
        if ip == "Not provided":
            return "Confirm whether any IP application is planned or filed, and the applicant/entity status, to assess IPR/ABS disclosure requirements."
        return "Review the cited disclosure requirements against the planned IP activity and confirm compliance steps with qualified counsel."

    else:  # REQUIRED DOCUMENTATION
        return "Identify the applicable pathway and authority, then confirm the specific forms and documentation needed for compliance."


def _grounded_why_for_area(area: str, evidence_source: str, partial: bool) -> str:
    """Build a case-specific 'why it matters' explanation."""
    source_note = f" (see {evidence_source})" if evidence_source else ""

    if area == "COMPETENT AUTHORITY":
        base = f"The competent authority determines the legal pathway, forms, and compliance requirements{source_note}."
        if partial:
            base += " An incorrect authority assumption may lead to non-compliance."
        return base

    elif area == "APPROVAL / INTIMATION":
        base = f"Accessing biological resources without required approvals may result in penalties under the applicable framework{source_note}."
        return base

    elif area == "BENEFIT-SHARING":
        base = f"Benefit-sharing is a conditional obligation that is determined only after the applicable ABS pathway is confirmed{source_note}."
        if partial:
            base += " A conditional assessment avoids treating a general statutory provision as an automatic obligation."
        return base

    elif area == "IPR / DISCLOSURE":
        base = f"Non-disclosure of biological resource origin in IP applications may affect the validity of granted rights{source_note}."
        return base

    else:  # REQUIRED DOCUMENTATION
        base = f"Proper documentation demonstrates compliance and supports downstream IP and regulatory activities{source_note}."
        return base


def _build_query(request: ABSScreenRequest) -> str:
    facts = [
        f"Ingredients: {', '.join(request.ingredients) or 'Not provided'}",
        f"Source region: {_display(request.source_region)}",
        f"Biological origin: {_display(request.is_biological)}",
        f"Category: {_display(request.category)}",
        f"Product/use information: {_display(request.product_use)}",
        f"Access/use context: {_display(request.access_use_context)}",
        f"Applicant/entity status: {_display(request.applicant_entity_status)}",
        f"Research or commercial purpose: {_display(request.research_or_commercial_purpose)}",
        f"Traditional knowledge used: {_display(request.traditional_knowledge_used)}",
        f"IP activity: {_display(request.ip_activity)}",
        f"Access from source region: {_display(request.access_from_region)}",
        f"Procurement details: {_display(request.procurement_details)}",
        f"Existing permissions: {_display(request.existing_permissions)}",
    ]
    return (
        "Assess Access and Benefit Sharing considerations using only the supplied facts and retrieved ABS/statutory evidence. "
        "Do not infer applicant status, commercial use, access method, traditional knowledge use, approval, exemption, Form III, authority, or benefit-sharing amount. "
        "Distinguish ABS relevance, possible pathway, missing facts, and obligations actually supported by evidence. "
        "For each of these five areas — (1) competent authority, (2) approval/intimation, (3) benefit-sharing, (4) IPR/disclosure, (5) required documentation — "
        "state what the evidence supports, what remains uncertain, and what facts are needed. "
        "Use conditional language where facts are incomplete and identify evidence IDs for every substantive finding.\n\n" + "\n".join(facts)
    )


def _overall_status(
    request: ABSScreenRequest,
    region_triggers: bool,
    evidence: list[EvidenceItem],
    gaps: list[str],
) -> tuple[str, bool, str]:
    if request.is_biological is False:
        return "NO ABS TRIGGER IDENTIFIED FROM PROVIDED INFORMATION", False, "green"
    if request.is_biological is None or not _clean(request.source_region):
        return "ABS PATHWAY REQUIRES FURTHER FACTS", False, "amber"
    if request.is_biological and region_triggers:
        # Factor in evidence strength: don't fully assert MAY APPLY without evidence
        if evidence:
            return "ABS CONSIDERATION MAY APPLY", True, "yellow"
        else:
            return "ABS PATHWAY REQUIRES FURTHER FACTS", False, "amber"
    return "NO ABS TRIGGER IDENTIFIED FROM PROVIDED INFORMATION", False, "green"


async def _assess(request: ABSScreenRequest) -> dict[str, Any]:
    region_triggers = _region_triggers(request.source_region)
    gaps = _information_gaps(request)
    rag_result: dict[str, Any] = {}

    if request.is_biological is not False and (request.ingredients or _clean(request.source_region) or _clean(request.product_use)):
        try:
            rag_result = await run_rag_query(
                _build_query(request),
                jurisdiction=_clean(request.source_region) or None,
                intent_override="ABS",
            )
        except Exception as exc:
            logger.warning("ABS evidence retrieval failed: %s", exc)
            rag_result = {
                "response_status": "retrieval_error",
                "confidence_label": "low",
                "confidence": 0.0,
                "abstained": True,
                "answer": "Insufficient evidence was retrieved for a reliable ABS assessment.",
                "key_points": [],
                "evidence": [],
            }

    evidence = _evidence_from_rag(rag_result)

    # Compute overall status with evidence factored in
    status, applicable, color = _overall_status(request, region_triggers, evidence, gaps)

    # Qualitative evidence confidence only: HIGH, MODERATE, LOW, INSUFFICIENT EVIDENCE
    # Reflects evidence quality/coverage, not a hardcoded percentage.
    if not evidence:
        confidence_label = "INSUFFICIENT EVIDENCE"
    else:
        verified_count = sum(1 for e in evidence if e.verified)
        has_statutory = any("regulation" in (e.document or "").lower() or "act" in (e.document or "").lower() for e in evidence)
        # For preliminary screening where exact statutory pathways and exemptions
        # still require confirmation, confidence is kept at MODERATE
        facts_provided = all([
            _clean(request.source_region),
            _clean(request.applicant_entity_status),
            _clean(request.research_or_commercial_purpose),
            _clean(request.access_use_context),
            _clean(request.procurement_details),
            _clean(request.existing_permissions),
        ])
        if len(evidence) >= 4 and verified_count >= 3 and facts_provided and has_statutory:
            confidence_label = "HIGH"
        elif len(evidence) >= 1 or verified_count >= 1 or has_statutory:
            confidence_label = "MODERATE"
        else:
            confidence_label = "LOW"
    confidence_score = None

    raw_findings = [str(item).strip() for item in (rag_result.get("key_points") or []) if str(item).strip()]
    clean_findings = [
        item for item in raw_findings
        if not _is_ai_failure_text(item)
        and not any(k in item.lower() for k in ("samhita", "treatise", "tkdl", "classical reference", "classical and treatise"))
    ]
    if not clean_findings and evidence:
        clean_findings = [
            "Biological Diversity Act and regulatory provisions retrieved for review.",
            "Approval, intimation, and benefit-sharing requirements depend on applicant status and intended commercial or research use.",
            "Applicable authority and procedural requirements must be confirmed against verified case facts.",
        ]
    elif not evidence:
        clean_findings = ["No reliable ABS/statutory evidence was retrieved for this screening."]
    key_findings = clean_findings

    # Parse LLM answer to extract per-area findings
    area_findings = _parse_area_findings(rag_result)

    obligations = [
        _build_obligation(area, request, _evidence_for_area(evidence, area), gaps, rag_result, area_findings)
        for area in ["COMPETENT AUTHORITY", "APPROVAL / INTIMATION", "BENEFIT-SHARING", "IPR / DISCLOSURE", "REQUIRED DOCUMENTATION"]
    ]

    reasoning = _clean(rag_result.get("why") or rag_result.get("answer"))
    if _is_ai_failure_text(reasoning) or not reasoning:
        if evidence:
            reasoning = (
                "ABS consideration may apply based on the submitted facts and retrieved regulatory evidence. "
                "Applicability of specific obligations depends on the applicable legal pathway and the remaining case facts."
            )
        else:
            reasoning = "No reliable ABS/statutory evidence was retrieved. The system is abstaining from specific legal conclusions."
    elif not evidence:
        reasoning = "No reliable ABS/statutory evidence was retrieved. The system is abstaining from specific legal conclusions."

    sources = list(dict.fromkeys(item.source_chunk_id for item in evidence))
    return {
        "overall_status": status,
        "applicable": applicable,
        "reasoning": reasoning,
        "color": color,
        "region_triggers_abs": region_triggers,
        "is_biological": request.is_biological,
        "input_screening": _input_screening(request),
        "information_gaps": gaps,
        "key_findings": key_findings,
        "obligations": obligations,
        "evidence": evidence,
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "sources": sources,
        "escalate": bool(rag_result.get("abstained") or not evidence),
        "response_status": _clean(rag_result.get("response_status")) or ("success" if evidence else "insufficient_evidence"),
        "disclaimer": "Information, not legal advice",
    }


@router.post("/screen", response_model=ABSScreenResponse)
async def abs_screen(request: ABSScreenRequest) -> ABSScreenResponse:
    return ABSScreenResponse(**await _assess(request))


@router.post("/obligations", response_model=ABSObligationsResponse)
async def abs_obligations(request: ABSObligationsRequest) -> ABSObligationsResponse:
    return ABSObligationsResponse(**await _assess(request))


__all__ = [
    "ABSScreenRequest", "ABSScreenResponse", "ABSObligationsRequest",
    "ABSObligationsResponse", "ObligationItem", "EvidenceItem", "abs_screen",
    "abs_obligations", "_assess",
]
