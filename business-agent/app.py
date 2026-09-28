from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Literal

import requests
import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class RequestFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_name: str | None = None
    order_id: str | None = None
    purchase_date: date | None = None
    item_unopened: bool | None = None
    request_summary: str = Field(min_length=1)
    relevant_details: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    action: Literal["Refund Approved", "Human Review Required"]
    reason: str


def call_model(base_url: str, model: str, messages: list[dict[str, str]]) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    response = requests.post(
        url,
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_model_json(content: str) -> dict:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    return json.loads(cleaned)


def extract_request_facts(base_url: str, model: str, email_text: str) -> RequestFacts:
    content = call_model(
        base_url,
        model,
        [
            {
                "role": "system",
                "content": (
                    "Extract facts from the customer message. Do not decide eligibility or infer missing facts. "
                    "Return one JSON object with customer_name (string or null), order_id (string or null), "
                    "purchase_date (YYYY-MM-DD or null), item_unopened (true, false, or null), "
                    "request_summary (string), and relevant_details (array of strings). "
                    "Set item_unopened only when the message clearly says the product is unopened/sealed "
                    "or opened/used; otherwise use null."
                ),
            },
            {"role": "user", "content": email_text},
        ],
    )
    return RequestFacts.model_validate(parse_model_json(content))


def decide_policy(facts: RequestFacts, today: date | None = None) -> PolicyDecision:
    today = today or date.today()
    if facts.purchase_date is None:
        return PolicyDecision(
            action="Human Review Required",
            reason="The purchase date could not be confirmed from the request.",
        )
    if facts.item_unopened is None:
        return PolicyDecision(
            action="Human Review Required",
            reason="The item's opened or unopened condition could not be confirmed.",
        )

    age_in_days = (today - facts.purchase_date).days
    if age_in_days < 0:
        return PolicyDecision(
            action="Human Review Required",
            reason="The purchase date is in the future and needs verification.",
        )
    if age_in_days <= 30 and facts.item_unopened:
        return PolicyDecision(
            action="Refund Approved",
            reason=f"Purchased {age_in_days} days ago and reported unopened; both automatic-refund conditions are met.",
        )

    reasons = []
    if age_in_days > 30:
        reasons.append(f"the purchase was {age_in_days} days ago, over the 30-day window")
    if not facts.item_unopened:
        reasons.append("the item is reported opened")
    return PolicyDecision(
        action="Human Review Required",
        reason=" and ".join(reasons).capitalize() + ".",
    )


def draft_customer_email(
    base_url: str, model: str, facts: RequestFacts, decision: PolicyDecision
) -> str:
    outcome = (
        "The refund is approved under the policy. Confirm approval without promising a processing timeline."
        if decision.action == "Refund Approved"
        else "The case needs human review. Do not promise or deny a refund; politely acknowledge the request and say the team will follow up."
    )
    content = call_model(
        base_url,
        model,
        [
            {
                "role": "system",
                "content": (
                    "Write a concise, polite customer email. Return JSON with one string field named email. "
                    "Do not invent order details or commitments."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Customer name: {facts.customer_name or 'Customer'}\n"
                    f"Order ID: {facts.order_id or 'not provided'}\n"
                    f"Decision: {decision.action}\nReason: {decision.reason}\n"
                    f"Required handling: {outcome}"
                ),
            },
        ],
    )
    email = parse_model_json(content).get("email")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("The model did not return an email draft.")
    return email.strip()


st.set_page_config(page_title="Evolus Business Agent on AMD", page_icon="EA", layout="wide")
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
      :root { --ink: #18302d; --muted: #64716d; --line: #dce5df; --green: #16745b; --mint: #e7f3ed; --amber: #9c6418; }
      html, body, [class*="st-"] { font-family: 'DM Sans', sans-serif; }
      .stApp { background: #f5f7f3; color: var(--ink); }
      .block-container { max-width: 1120px; padding-top: 2.5rem; }
      h1, h2, h3 { font-family: 'Manrope', sans-serif; color: var(--ink); letter-spacing: 0; }
      .eyebrow { color: var(--green); font-size: .76rem; font-weight: 700; text-transform: uppercase; }
      .hero { border-bottom: 1px solid var(--line); padding: .2rem 0 1.35rem; margin-bottom: 1.5rem; }
      .hero p { color: var(--muted); margin: .4rem 0 0; }
      .section-label { color: var(--muted); font-size: .75rem; font-weight: 700; text-transform: uppercase; }
      .step { display:flex; gap:.8rem; align-items:flex-start; padding:.75rem 0; border-bottom:1px solid var(--line); }
      .step-mark { width:1.65rem; height:1.65rem; flex:0 0 1.65rem; border-radius:50%; display:grid; place-items:center; background:var(--mint); color:var(--green); font-weight:700; }
      .step-title { font-weight:700; color:var(--ink); }
      .step-detail { font-size:.9rem; color:var(--muted); margin-top:.12rem; }
      .decision { padding:1rem 1.1rem; border-left:4px solid var(--green); background:#eaf4ee; margin:.8rem 0 1rem; }
      .decision.review { border-color:#c18429; background:#fff4df; }
      div[data-testid="stTextArea"] textarea { background:#fff; }
      div.stButton > button { background:var(--green); color:#fff; border:0; min-height:2.75rem; font-weight:700; }
      div.stButton > button:hover { background:#105b48; color:#fff; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><div class="eyebrow">Evolus Business Agent on AMD</div>'
    '<h1>Customer support triage</h1>'
    '<p>Turn refund requests into a policy-grounded decision and a ready-to-review response.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Model connection")
    base_url = st.text_input(
        "OpenAI-compatible base URL",
        value=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        help="For Ollama, enable its OpenAI-compatible API. The app adds /chat/completions.",
    )
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", "llama3.1"))
    st.caption("The model extracts request facts and drafts the response. Python applies the refund policy.")

left, right = st.columns([1.15, 0.85], gap="large")
with left:
    st.markdown('<div class="section-label">Customer message</div>', unsafe_allow_html=True)
    email_text = st.text_area(
        "Paste a support email or refund request",
        height=300,
        placeholder="Hello, I ordered ... on YYYY-MM-DD. The item is still sealed ...",
        label_visibility="collapsed",
    )
    analyze = st.button("Analyze request", use_container_width=True, type="primary")

with right:
    st.markdown('<div class="section-label">Decision workflow</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="step"><div class="step-mark">1</div><div><div class="step-title">Parse request</div>'
        '<div class="step-detail">Extract date, item condition, and customer context.</div></div></div>'
        '<div class="step"><div class="step-mark">2</div><div><div class="step-title">Check policy</div>'
        '<div class="step-detail">Apply the 30-day and unopened-item rules in code.</div></div></div>'
        '<div class="step"><div class="step-mark">3</div><div><div class="step-title">Prepare response</div>'
        '<div class="step-detail">Draft an approval or a polite review acknowledgment.</div></div></div>',
        unsafe_allow_html=True,
    )

if analyze:
    if not email_text.strip():
        st.warning("Paste a customer message to begin.")
    elif not base_url.strip() or not model.strip():
        st.warning("Enter a model endpoint and model name in the sidebar.")
    else:
        try:
            with st.spinner("Parsing the request with the configured model..."):
                facts = extract_request_facts(base_url, model, email_text.strip())
            decision = decide_policy(facts)
            with st.spinner("Drafting the customer response..."):
                draft = draft_customer_email(base_url, model, facts, decision)

            st.divider()
            st.subheader("Triage result")
            review_class = "review" if decision.action == "Human Review Required" else ""
            st.markdown(
                f'<div class="decision {review_class}"><strong>{decision.action}</strong><br>{decision.reason}</div>',
                unsafe_allow_html=True,
            )
            result_left, result_right = st.columns([0.9, 1.1], gap="large")
            with result_left:
                st.markdown("**Parsed request**")
                st.write(f"**Customer:** {facts.customer_name or 'Not identified'}")
                st.write(f"**Order:** {facts.order_id or 'Not provided'}")
                st.write(f"**Purchase date:** {facts.purchase_date or 'Not confirmed'}")
                condition = {True: "Unopened", False: "Opened", None: "Not confirmed"}[facts.item_unopened]
                st.write(f"**Item condition:** {condition}")
                st.caption(facts.request_summary)
            with result_right:
                st.markdown("**Draft response**")
                st.text_area("Email draft", value=draft, height=220, label_visibility="collapsed")
            with st.expander("Agent workflow details"):
                st.markdown(f"1. **Parsing Request:** {facts.request_summary}")
                st.markdown(f"2. **Checking Policy:** {decision.reason}")
                st.markdown(f"3. **Deciding Action:** **{decision.action}**")
        except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            st.error(f"Could not complete triage: {exc}")
            st.caption("Check that the model server is running, the model is available, and the endpoint supports chat completions.")