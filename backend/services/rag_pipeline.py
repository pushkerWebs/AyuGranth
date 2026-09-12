"""
AayuGranth RAG Pipeline.
Integrates Intent Routing, MongoDB Atlas vector retrieval, retry-enabled Gemini synthesis,
evidence type isolation (TK vs Prior Art vs Regulatory vs Statutory), and intent-aware fallbacks.
"""

import asyncio
import json
import logging
import re
import time
from typing import TypedDict, List, Dict, Any, Optional, Tuple

from core.database import get_db
from core.config import settings
from services.similarity_engine import search_similar_chunks
from services.citation_verifier import verify_citations
from services.confidence_engine import compute_confidence
from services.llm_router import get_llm
from services.intent_router import classify_intent
from routes.escalation import auto_escalate

logger = logging.getLogger("aayugranth.rag")
logger.setLevel(logging.INFO)


def _extract_text_from_llm_response(response: Any) -> str:
    """Safely extract string text from Gemini / LangChain response (handling lists or parts)."""
    if hasattr(response, "content"):
        c = response.content
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            texts = []
            for part in c:
                if isinstance(part, str):
                    texts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    texts.append(part["text"])
                elif hasattr(part, "text"):
                    texts.append(getattr(part, "text", ""))
                else:
                    texts.append(str(part))
            return "".join(texts)
    return str(response)


def _parse_llm_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from LLM output, stripping markdown code blocks if present."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        # Try finding first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
    return None


def _classify_evidence_type(chunk: Dict[str, Any]) -> str:
    """
    Classify a chunk into distinct evidence categories:
    - 'prior_art' (patent literature, publication numbers)
    - 'traditional_knowledge' (classical treatises, Samhitas, TKDL, pharmacopeias)
    - 'abs' (Biological Diversity Act, NBA, SBB, benefit sharing)
    - 'regulatory' (FSSAI, CDSCO, drug licensing, GMP, heavy metal limits)
    - 'statutory' (general Acts, patent statutes, legal provisions)
    """
    doc = str(chunk.get("source_document", "")).lower()
    law_t = str(chunk.get("law_type", "")).lower()
    src_t = str(chunk.get("source_type", "")).lower()
    pub_no = str(chunk.get("publication_number", "")).strip()

    combined = f"{doc} {law_t} {src_t}"

    if pub_no or "patent" in combined or "prior art" in combined or "ipr" in src_t:
        return "prior_art"

    if any(k in combined for k in [
        "samhita", "charaka", "sushruta", "ashtanga", "tkdl", "traditional knowledge",
        "classical", "ayurveda pharmacopeia", "nighantu", "afi", "api", "formulary"
    ]):
        return "traditional_knowledge"

    if any(k in combined for k in ["abs", "biodiversity", "nagoya", "benefit sharing", "nba", "sbb"]):
        return "abs"

    if any(k in combined for k in ["fssai", "cdsco", "ayush licen", "drug licen", "gmp", "heavy metal", "regulatory", "compliance"]):
        return "regulatory"

    return "statutory"


def _source_categories(chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """Expose retrieved source metadata separated strictly by evidence type."""
    statutory, classical, patents = [], [], []
    for chunk in chunks:
        ev_type = _classify_evidence_type(chunk)
        title = str(chunk.get("source_document", "Retrieved source"))
        item = {
            "title": title,
            "section": str(chunk.get("section") or ""),
            "reference": str(chunk.get("section") or ""),
            "publication_number": str(chunk.get("publication_number") or ""),
            "relevance": "Retrieved as relevant evidence for this question.",
            "evidence_type": ev_type,
            "date": str(chunk.get("date") or chunk.get("filing_date") or chunk.get("publication_date") or ""),
            "jurisdiction": str(chunk.get("jurisdiction") or "India"),
        }
        if ev_type == "prior_art":
            patents.append(item)
        elif ev_type == "traditional_knowledge":
            classical.append(item)
        else:
            statutory.append(item)
    return statutory, classical, patents


def _build_evidence_index(chunks: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Build numbered evidence blocks for the Gemini prompt and a lookup map
    from EVIDENCE_N → actual chunk metadata.
    """
    context_parts = []
    evidence_map: Dict[str, Dict[str, Any]] = {}

    for idx, c in enumerate(chunks, start=1):
        evidence_id = f"EVIDENCE_{idx}"
        ev_type = _classify_evidence_type(c)
        doc = c.get("source_document", "Statutory Source")
        sec = c.get("section", "General")
        law_t = c.get("law_type", "")
        txt = c.get("chunk_text", "").strip()

        context_parts.append(
            f"--- {evidence_id} | Category: {ev_type.upper()} | Source: {doc} | Section: {sec} | Law: {law_t} ---\n{txt}\n"
        )
        evidence_map[evidence_id] = c

    return "\n".join(context_parts), evidence_map


def _get_intent_fallback(intent: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate intent-specific fallback when AI generation times out or fails.
    Never invents conclusions, novelty, patentability, or medical dosages.
    """
    statutory, classical, patents = _source_categories(chunks)

    fallbacks = {
        "PATENTABILITY": {
            "assessment": "Patentability assessment requires further analysis.",
            "why": "Preliminary evidence-based assessment: The AI synthesis could not be completed from the available evidence. Retrieved statutory and technical provisions are retained below for independent review.",
            "key_points": [
                "Preliminary evidence-based assessment — no conclusive patentability or Section 3(p) determination made without synthesis.",
                "Retrieved corpus documents are available below for manual claim mapping.",
                "Consult an IP attorney or registered patent agent for formal patentability opinions."
            ],
            "confidence_label": "preliminary",
        },
        "PRIOR_ART": {
            "assessment": "Prior-art analysis could not be completed.",
            "why": "The AI synthesis could not be completed. Retrieved documents for review are listed below. Retrieved documents are not confirmed prior art until verified against specific claim elements.",
            "key_points": [
                f"Retrieved {len(patents) if patents else len(chunks)} document(s) for review.",
                "Documents require comparative claim matching before determining prior-art relevance.",
                "No novelty destruction or anticipation is confirmed at this stage."
            ],
            "confidence_label": "preliminary",
        },
        "TK_ANALYSIS": {
            "assessment": "Traditional knowledge analysis could not be fully completed.",
            "why": "The AI synthesis could not be completed. Retrieved classical treatise and traditional knowledge evidence are provided below without fabricated interpretation.",
            "key_points": [
                f"Retrieved {len(classical) if classical else len(chunks)} classical and treatise reference(s).",
                "Textual formulations and classical indications are retained as documented in historical references.",
                "Cross-referencing with TKDL guidelines requires complete manual verification."
            ],
            "confidence_label": "preliminary",
        },
        "ABS": {
            "assessment": "ABS consideration may apply based on the submitted facts and retrieved regulatory evidence.",
            "why": "ABS consideration may apply based on the submitted facts and retrieved regulatory evidence. Applicability of specific obligations depends on the applicable legal pathway and the remaining case facts.",
            "key_points": [
                "Biological Diversity Act and regulatory provisions retrieved for review.",
                "Approval, intimation, and benefit-sharing requirements depend on applicant status and intended commercial or research use.",
                "Applicable authority and procedural requirements must be confirmed against verified case facts.",
            ],
            "confidence_label": "preliminary",
        },
        "REGULATORY": {
            "assessment": "Regulatory assessment could not be completed.",
            "why": "The AI synthesis could not be completed. Retrieved regulatory standards, safety limits, and licensing provisions are displayed below.",
            "key_points": [
                "Statutory and regulatory corpus references retrieved for your jurisdiction.",
                "License classification, permissible heavy metal limits, and labeling rules must be verified with licensed authorities.",
                "No regulatory compliance certificate is implied."
            ],
            "confidence_label": "preliminary",
        },
        "FORMULATION": {
            "assessment": "Formulation guidance could not be fully generated.",
            "why": "The AI synthesis could not be completed. Available ingredient references and known classical uses are displayed below. Dosage and exact ratios cannot be safely generated without complete validation.",
            "key_points": [
                "Retrieved known classical ingredient uses and traditional references.",
                "Dosages and therapeutic combinations must be validated through official pharmacopeias (API/AFI).",
                "Do not use preliminary notes as authoritative clinical or medical advice."
            ],
            "confidence_label": "preliminary",
        },
        "PRODUCT_PASSPORT": {
            "assessment": "Product passport generation could not be completed.",
            "why": "The AI synthesis could not be completed. Retrieved botanical provenance, quality standards, and regulatory citations are preserved below.",
            "key_points": [
                "Botanical origin and compliance provisions retained for passport formulation.",
                "Supply chain traceability data requires manual batch verification."
            ],
            "confidence_label": "preliminary",
        },
        "GENERAL_CHAT": {
            "assessment": "Welcome to AayuGranth Research Intelligence.",
            "why": "I am AayuGranth, your specialized legal and AYUSH research intelligence engine. I assist with patentability assessment, prior-art search, traditional knowledge analysis, ABS obligations, and regulatory compliance.",
            "key_points": [
                "Patentability & Section 3(p) analysis",
                "Prior art & patent comparison",
                "Traditional knowledge & classical treatise retrieval",
                "ABS (Biological Diversity Act) compliance screening",
                "Regulatory & FSSAI / AYUSH licensing guidance"
            ],
            "confidence_label": "high",
        },
        "GENERAL_RESEARCH": {
            "assessment": "AI assessment could not be completed from the available evidence.",
            "why": "The AI synthesis could not be completed from the available evidence. The retrieved evidence is still available below for your review.",
            "key_points": [
                f"Retrieved {len(chunks)} relevant evidence item(s) from the legal and classical corpus.",
                "All retrieved source documents and excerpts are accessible below."
            ],
            "confidence_label": "preliminary",
        },
    }

    return fallbacks.get(intent, fallbacks["GENERAL_RESEARCH"])


def _build_intent_prompt_preamble(intent: str) -> str:
    """Return specific analysis instructions tailored to the classified intent."""
    instructions = {
        "PATENTABILITY": (
            "INTENT: PATENTABILITY ANALYSIS\n"
            "Focus on evaluating patent eligibility, novelty, inventive step, and Section 3(p) implications "
            "(traditional knowledge exclusion) based STRICTLY on the retrieved corpus."
        ),
        "PRIOR_ART": (
            "INTENT: PRIOR-ART SEARCH & COMPARISON\n"
            "Focus on identifying potentially relevant patent literature and prior art. "
            "Clearly distinguish retrieved documents for review from confirmed prior art. "
            "Do NOT claim an item is anticipatory prior art unless the evidence explicitly demonstrates identical claims."
        ),
        "TK_ANALYSIS": (
            "INTENT: TRADITIONAL KNOWLEDGE (TK) ANALYSIS\n"
            "Focus on classical treatises (Samhitas, Nighantus, AFI/API) and documented traditional uses. "
            "Keep traditional knowledge findings strictly grounded in historical and classical evidence."
        ),
        "ABS": (
            "INTENT: ACCESS AND BENEFIT SHARING (ABS)\n"
            "Focus on obligations under the Biological Diversity Act, 2002/2023, National Biodiversity Authority (NBA) "
            "approval requirements, State Biodiversity Board (SBB) intimations, and benefit sharing calculations."
        ),
        "REGULATORY": (
            "INTENT: REGULATORY COMPLIANCE\n"
            "Focus on AYUSH / FSSAI / CDSCO regulatory requirements, manufacturing licenses, permissible limits, "
            "and statutory compliance mandates present in the evidence."
        ),
        "FORMULATION": (
            "INTENT: FORMULATION RESEARCH\n"
            "Focus on ingredient purposes, classical Ayurvedic rationale, and formulation compatibility. "
            "Do NOT prescribe medical treatments or invent clinical dosages."
        ),
        "PRODUCT_PASSPORT": (
            "INTENT: DIGITAL PRODUCT PASSPORT (DPP)\n"
            "Focus on botanical identity, geographical origin, batch compliance, and sustainability standards."
        ),
        "GENERAL_CHAT": (
            "INTENT: GENERAL CHAT & ONBOARDING\n"
            "Greet the user professionally and summarize AayuGranth's capabilities across IP, TKDL, and AYUSH law."
        ),
        "GENERAL_RESEARCH": (
            "INTENT: GENERAL AYUSH RESEARCH\n"
            "Synthesize the retrieved botanical and legal corpus into a structured, evidence-grounded research summary."
        ),
    }
    return instructions.get(intent, instructions["GENERAL_RESEARCH"])


async def _invoke_llm_with_retry(
    prompt: str,
    cleaner_prompt: Optional[str] = None,
    max_retries: Optional[int] = None,
    timeout_s: Optional[float] = None
) -> Tuple[Optional[str], bool, str]:
    """
    Invokes Gemini with explicit timeout, controlled exponential backoff, and cleaner context on retry.
    Returns: (raw_text, success_bool, error_classification)
    """
    timeout = timeout_s if timeout_s is not None else getattr(settings, "GEMINI_TIMEOUT_S", 15.0)
    retries = max_retries if max_retries is not None else getattr(settings, "GEMINI_MAX_RETRIES", 1)

    llm = get_llm("gemini")
    total_attempts = 1 + retries

    for attempt in range(1, total_attempts + 1):
        attempt_start = time.time()
        # Use cleaner/shorter prompt on secondary attempts if available
        current_prompt = prompt if attempt == 1 or not cleaner_prompt else cleaner_prompt
        
        logger.info(
            "[GEMINI INVOCATION] Attempt %d/%d (timeout=%.1fs, prompt_len=%d)",
            attempt, total_attempts, timeout, len(current_prompt)
        )

        try:
            response = await asyncio.wait_for(llm.ainvoke(current_prompt), timeout=timeout)
            duration = round(time.time() - attempt_start, 3)
            raw_text = _extract_text_from_llm_response(response)

            if raw_text and raw_text.strip():
                logger.info(
                    "[GEMINI SUCCESS] Attempt %d succeeded in %.2fs (response_len=%d)",
                    attempt, duration, len(raw_text)
                )
                return raw_text, True, "success"
            else:
                logger.warning("[GEMINI EMPTY] Attempt %d returned empty content in %.2fs", attempt, duration)
                error_type = "empty_response"

        except asyncio.TimeoutError:
            duration = round(time.time() - attempt_start, 3)
            error_type = "timeout"
            logger.warning(
                "[GEMINI TIMEOUT] Attempt %d timed out after %.2fs (limit: %.1fs)",
                attempt, duration, timeout
            )
        except Exception as e:
            duration = round(time.time() - attempt_start, 3)
            error_type = type(e).__name__
            logger.warning(
                "[GEMINI ERROR] Attempt %d failed in %.2fs with %s: %s",
                attempt, duration, error_type, e
            )

        # Backoff before retry if more attempts remain
        if attempt < total_attempts:
            backoff = min(3.0, 1.0 * (attempt ** 1.5))
            logger.info("[GEMINI RETRY] Backing off for %.1fs before attempt %d", backoff, attempt + 1)
            await asyncio.sleep(backoff)

    return None, False, error_type


async def run_rag_query(
    query: str,
    jurisdiction: Optional[str] = "India",
    intent_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute the complete end-to-end RAG pipeline:
    USER QUERY → INTENT ROUTING → RETRIEVAL → EVIDENCE NORMALIZATION → AI SYNTHESIS → VALIDATION → FINAL RESPONSE
    """
    total_start = time.time()
    logger.info("[ASK] Incoming Query: '%s' | Jurisdiction: %s | Intent Override: %s", query[:80], jurisdiction, intent_override)

    stage_timings: Dict[str, float] = {}

    # ── STAGE 0: INTENT ROUTING ──────────────────────────────────────────────
    if intent_override:
        intent = intent_override
        intent_data = {"intent": intent_override, "confidence": 1.0, "reason": "Explicit intent override"}
        stage_timings["INTENT_ROUTING"] = 0.0
        logger.info("[INTENT ROUTER] Intent overridden as '%s'", intent)
    else:
        intent_start = time.time()
        intent_data = classify_intent(query)
        intent = intent_data.get("intent", "GENERAL_RESEARCH")
        stage_timings["INTENT_ROUTING"] = round(time.time() - intent_start, 4)
        logger.info(
            "[INTENT ROUTER] Classified query as '%s' (conf=%.2f, reason='%s') in %.3fs",
            intent, intent_data.get("confidence", 0.0), intent_data.get("reason", ""), stage_timings["INTENT_ROUTING"]
        )

    # ── STAGE 1: RETRIEVAL & EMBEDDINGS ──────────────────────────────────────
    retrieval_start = time.time()
    chunks: List[Dict[str, Any]] = []
    scores: List[float] = []

    try:
        # General chat doesn't strictly need deep corpus retrieval, but we pull a few for context
        top_k = 3 if intent == "GENERAL_CHAT" else 6
        chunks = await search_similar_chunks(query, top_k=top_k)
        scores = [float(c.get("semantic_similarity", 0.0)) for c in chunks]
        stage_timings["RETRIEVAL"] = round(time.time() - retrieval_start, 3)

        chunk_logs = [f"[{c.get('source_document', '')[:25]} | Sec: {c.get('section')} | Sim: {c.get('semantic_similarity')}]" for c in chunks[:3]]
        logger.info("[RETRIEVAL] Found %d chunks in %.2fs: %s", len(chunks), stage_timings["RETRIEVAL"], chunk_logs)
    except Exception as e:
        stage_timings["RETRIEVAL"] = round(time.time() - retrieval_start, 3)
        logger.error("[RETRIEVAL FAILED] Stage exception: %s", e)
        chunks = []
        scores = []

    # ── STAGE 1.5: EVIDENCE NORMALIZATION ────────────────────────────────────
    # Categorize and tag all retrieved chunks by exact evidence type
    statutory_sources, classical_sources, patent_evidence = _source_categories(chunks)

    # ── STAGE 2: GENERATION WITH TIMEOUT & RETRY ─────────────────────────────
    gen_start = time.time()
    parsed_output: Optional[Dict[str, Any]] = None
    llm_raw_answer = ""
    llm_why = ""
    llm_key_points: List[str] = []
    llm_evidence_refs: List[Dict[str, Any]] = []
    llm_confidence = "moderate"
    has_sufficient_corpus_evidence = True
    evidence_map: Dict[str, Dict[str, Any]] = {}
    response_status = "success"
    gemini_raw_text = ""

    if not chunks and intent != "GENERAL_CHAT":
        fallback_data = _get_intent_fallback(intent, chunks)
        llm_raw_answer = fallback_data["assessment"]
        llm_why = "No sufficiently relevant retrieved evidence was available in the legal and classical corpus to ground an assessment."
        llm_key_points = ["No direct corpus matches found for this query."]
        llm_confidence = "low"
        has_sufficient_corpus_evidence = False
        response_status = "insufficient_evidence"
        stage_timings["GENERATION"] = round(time.time() - gen_start, 3)
        logger.info("[GENERATION] No chunks retrieved — using intent-aware empty response.")
    else:
        # Build context with stable EVIDENCE_N labels (never raw chunk IDs)
        context_str, evidence_map = _build_evidence_index(chunks)
        evidence_id_list = ", ".join(evidence_map.keys()) if evidence_map else "NONE"
        intent_preamble = _build_intent_prompt_preamble(intent)

        full_prompt = f"""You are AayuGranth's specialized research intelligence engine for Ayurveda intellectual property, traditional knowledge, and regulatory compliance.

{intent_preamble}

USER QUESTION:
"{query}"

RETRIEVED EVIDENCE CORPUS:
{context_str if context_str else "No direct corpus matches retrieved."}

STRICT INSTRUCTIONS:
1. Ground all claims in the provided evidence. Never invent citations, statutes, or classical treatises.
2. Label assessments as preliminary research intelligence, not binding legal or medical advice.
3. Reference evidence ONLY using the provided labels: {evidence_id_list}. Do NOT invent identifiers.
4. For PRIOR_ART queries, refer to matches as 'Retrieved documents for review' rather than confirming invalidity.
5. For FORMULATION queries, explain ingredient rationale without prescribing specific medicinal dosages.
6. Return ONLY valid JSON matching this schema:
{{
  "assessment": "A concise, intent-specific preliminary assessment",
  "why": "A concise evidence-grounded explanation of the assessment",
  "jurisdiction": "{jurisdiction or 'India'}",
  "confidence": "high" or "moderate" or "low",
  "key_findings": [
    "Key finding or legal requirement 1",
    "Key finding or legal requirement 2",
    "Key finding or legal requirement 3"
  ],
  "evidence": [
    {{
      "evidence_id": "EVIDENCE_1",
      "claim": "Specific supported finding from this evidence",
      "relevance": "Why this evidence matters for the user's question"
    }}
  ],
  "has_sufficient_corpus_evidence": true or false
}}

OUTPUT JSON:"""

        # Concise cleaner prompt for retry in case the primary prompt times out
        clean_context_str, _ = _build_evidence_index(chunks[:3])
        cleaner_prompt = f"""You are AayuGranth. Answer concisely in JSON based on the evidence below.
USER QUESTION: "{query}"
EVIDENCE:
{clean_context_str}
SCHEMA:
{{
  "assessment": "Concise preliminary assessment",
  "why": "Brief explanation",
  "confidence": "moderate",
  "key_findings": ["Point 1", "Point 2"],
  "evidence": [{{"evidence_id": "EVIDENCE_1", "claim": "Finding", "relevance": "Reason"}}],
  "has_sufficient_corpus_evidence": true
}}
OUTPUT JSON:"""

        raw_text, success, error_detail = await _invoke_llm_with_retry(
            prompt=full_prompt,
            cleaner_prompt=cleaner_prompt,
            max_retries=settings.GEMINI_MAX_RETRIES,
            timeout_s=settings.GEMINI_TIMEOUT_S,
        )

        if success and raw_text:
            gemini_raw_text = raw_text
            parsed_output = _parse_llm_json(gemini_raw_text)

            if parsed_output and isinstance(parsed_output, dict) and "assessment" in parsed_output:
                llm_raw_answer = str(parsed_output.get("assessment", "")).strip()
                llm_why = str(parsed_output.get("why", "")).strip()
                llm_key_points = parsed_output.get("key_findings", [])
                llm_confidence = parsed_output.get("confidence", "moderate")
                has_sufficient_corpus_evidence = parsed_output.get("has_sufficient_corpus_evidence", True)
                response_status = "success"

                raw_evidence = parsed_output.get("evidence", [])
                if isinstance(raw_evidence, list):
                    llm_evidence_refs = [
                        item for item in raw_evidence
                        if isinstance(item, dict) and item.get("evidence_id")
                    ]

                logger.info(
                    "[GENERATION] Gemini produced structured assessment (confidence=%s, sufficient=%s, refs=%d)",
                    llm_confidence, has_sufficient_corpus_evidence, len(llm_evidence_refs)
                )
            else:
                logger.warning("[GENERATION WARNING] Gemini returned non-JSON text; falling back to intent template.")
                success = False

        if not success:
            stage_timings["GENERATION"] = round(time.time() - gen_start, 3)
            logger.warning("[GENERATION FALLBACK] Using intent-aware fallback for intent '%s' due to: %s", intent, error_detail)
            fallback_data = _get_intent_fallback(intent, chunks)
            llm_raw_answer = fallback_data["assessment"]
            llm_why = fallback_data["why"]
            llm_key_points = fallback_data["key_points"]
            llm_confidence = fallback_data.get("confidence_label", "moderate")
            has_sufficient_corpus_evidence = bool(chunks)
            response_status = "timeout" if error_detail == "timeout" else "fallback"

        stage_timings["GENERATION"] = round(time.time() - gen_start, 3)

    # ── STAGE 3: EVIDENCE-REFERENCE VALIDATION & CLAIM GROUNDING ─────────────
    verif_start = time.time()
    valid_evidence_ids = set(evidence_map.keys())

    gemini_claimed_ids = [str(ref.get("evidence_id", "")) for ref in llm_evidence_refs]
    verified_ref_ids, unverified_ref_ids = verify_citations(gemini_claimed_ids, valid_evidence_ids)

    verified_claims = []
    for ref in llm_evidence_refs:
        eid = str(ref.get("evidence_id", ""))
        is_valid_ref = eid in valid_evidence_ids
        mapped_chunk = evidence_map.get(eid, {})
        real_chunk_id = str(mapped_chunk.get("chunk_id", ""))
        ev_type = _classify_evidence_type(mapped_chunk)

        verified_claims.append({
            "text": ref.get("claim", ""),
            "source_chunk_id": real_chunk_id,
            "law_name": mapped_chunk.get("source_document", "Retrieved evidence"),
            "section": str(mapped_chunk.get("section") or ""),
            "relevance": ref.get("relevance", ""),
            "evidence_type": ev_type,
            "verified": is_valid_ref and bool(real_chunk_id),
        })

    total_claims = len(verified_claims)
    verified_count = sum(1 for c in verified_claims if c["verified"])
    verified_ratio = (verified_count / total_claims) if total_claims > 0 else (0.8 if chunks else 0.0)

    if chunks and total_claims > 0 and verified_count == 0:
        llm_confidence = "low" if llm_confidence == "low" else "moderate"

    stage_timings["VERIFICATION"] = round(time.time() - verif_start, 3)

    # ── STAGE 4: CONFIDENCE & ABSTENTION ─────────────────────────────────────
    conf_start = time.time()
    conf_label, should_abstain, conf_score = compute_confidence(
        retrieval_scores=scores,
        verified_ratio=verified_ratio,
        llm_confidence=llm_confidence,
        supporting_chunk_count=len(chunks),
        has_sufficient_corpus_evidence=has_sufficient_corpus_evidence
    )

    # If response is fallback or general chat, do not force abstention:
    # let the user see the intent fallback and retrieved evidence!
    if response_status in ("fallback", "timeout") and chunks:
        should_abstain = False
        conf_label = "preliminary"
        conf_score = max(0.55, conf_score)
    elif intent == "GENERAL_CHAT":
        should_abstain = False
        conf_label = "high"
        conf_score = 0.95

    final_answer = llm_raw_answer
    if should_abstain:
        response_status = "abstained"
        final_answer = "Insufficient evidence to reach a reliable assessment."
        llm_why = "The available retrieved evidence did not meet the threshold for a reliable preliminary conclusion."
        try:
            db = get_db()
            await auto_escalate(db, query, reason="low_confidence_corpus_abstention")
        except Exception:
            pass

    stage_timings["CONFIDENCE"] = round(time.time() - conf_start, 3)
    total_duration = round(time.time() - total_start, 3)
    stage_timings["TOTAL"] = total_duration

    # ── STAGE 5: FORMAT STRUCTURED SOURCES & EVIDENCE CARDS ──────────────────
    sources_used = []
    for c in chunks:
        cid = str(c.get("chunk_id", ""))
        ev_type = _classify_evidence_type(c)
        sources_used.append({
            "chunk_id": cid,
            "chunk_text": c.get("chunk_text", ""),
            "source_document": c.get("source_document", "Statutory Document"),
            "section": c.get("section", ""),
            "law_type": c.get("law_type", ""),
            "jurisdiction": c.get("jurisdiction", jurisdiction or "India"),
            "source_type": c.get("source_type", "statute"),
            "evidence_type": ev_type,
            "type": ev_type,
            "date": str(c.get("date") or c.get("filing_date") or c.get("publication_date") or ""),
            "publication_number": str(c.get("publication_number") or ""),
            "semantic_similarity": c.get("semantic_similarity", 0.0),
            "verified": cid in {str(evidence_map.get(vid, {}).get("chunk_id", "")) for vid in verified_ref_ids} if cid else True,
        })

    # Build evidence list
    evidence: List[Dict[str, Any]] = []
    if llm_evidence_refs and response_status == "success":
        for ref in llm_evidence_refs:
            eid = str(ref.get("evidence_id", ""))
            mapped_chunk = evidence_map.get(eid, {})
            if not mapped_chunk:
                continue

            real_chunk_id = str(mapped_chunk.get("chunk_id", ""))
            ev_type = _classify_evidence_type(mapped_chunk)
            evidence.append({
                "claim": ref.get("claim", ""),
                "source": mapped_chunk.get("source_document", ""),
                "source_document": mapped_chunk.get("source_document", ""),
                "section": str(mapped_chunk.get("section") or ""),
                "jurisdiction": mapped_chunk.get("jurisdiction", jurisdiction or "India"),
                "excerpt": mapped_chunk.get("chunk_text", ""),
                "relevance": ref.get("relevance", ""),
                "source_chunk_id": real_chunk_id,
                "semantic_similarity": mapped_chunk.get("semantic_similarity", 0.0),
                "evidence_type": ev_type,
                "type": ev_type,
                "date": str(mapped_chunk.get("date") or mapped_chunk.get("filing_date") or mapped_chunk.get("publication_date") or ""),
                "publication_number": str(mapped_chunk.get("publication_number") or ""),
                "verified": eid in valid_evidence_ids and bool(real_chunk_id),
            })

    # If evidence array is empty (due to fallback, timeout, or Gemini not citing indexes),
    # populate directly from normalized retrieved chunks so retrieved evidence is NEVER lost!
    if not evidence and chunks and not should_abstain:
        for idx, c in enumerate(chunks[:5]):
            ev_type = _classify_evidence_type(c)
            # Intent-aware default relevance label
            if ev_type == "prior_art":
                claim_label = f"Patent document retrieved for review: {c.get('source_document', '')}"
                rel_label = "Retrieved document for review against claimed subject matter."
            elif ev_type == "traditional_knowledge":
                claim_label = f"Classical treatise citation: {c.get('source_document', '')}"
                rel_label = "Historical traditional knowledge documentation."
            elif ev_type == "abs":
                claim_label = f"ABS statutory provision: {c.get('source_document', '')}"
                rel_label = "Biological Diversity compliance and benefit sharing provision."
            elif ev_type == "regulatory":
                claim_label = f"Regulatory requirement: {c.get('source_document', '')}"
                rel_label = "Compliance, safety, or licensing requirement."
            else:
                claim_label = f"Retrieved statutory evidence from {c.get('source_document', 'Corpus')}"
                rel_label = "Retrieved as semantically relevant legal evidence."

            evidence.append({
                "claim": claim_label,
                "source": c.get("source_document", ""),
                "source_document": c.get("source_document", ""),
                "section": str(c.get("section") or ""),
                "jurisdiction": c.get("jurisdiction", jurisdiction or "India"),
                "excerpt": c.get("chunk_text", ""),
                "relevance": rel_label,
                "source_chunk_id": str(c.get("chunk_id", "")),
                "semantic_similarity": c.get("semantic_similarity", 0.0),
                "evidence_type": ev_type,
                "type": ev_type,
                "date": str(c.get("date") or c.get("filing_date") or c.get("publication_date") or ""),
                "publication_number": str(c.get("publication_number") or ""),
                "verified": True,
            })

    return {
        "answer": final_answer,
        "assessment": final_answer,
        "why": llm_why,
        "summary": llm_why,
        "key_points": llm_key_points,
        "claims": verified_claims,
        "sources_used": sources_used,
        "evidence": evidence,
        "statutory_sources": statutory_sources,
        "classical_sources": classical_sources,
        "patent_evidence": patent_evidence,
        "confidence": conf_score,
        "confidence_label": conf_label,
        "abstained": should_abstain,
        "jurisdiction": jurisdiction or "India",
        "intent": intent,
        "intent_metadata": intent_data,
        "response_status": response_status,
        "stage_timings": stage_timings,
        "disclaimer": "This is a preliminary assessment for informational purposes only — not legal advice. Consult a qualified IP/regulatory professional."
    }
