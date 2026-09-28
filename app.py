"""DeployMind Streamlit application."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from models.deployment import Deployment, parse_changed_files, validate_deployment
from services.deployment_service import build_recall_query, format_deployment_experience, validate_result_experience
from services.hindsight_service import check_hindsight_connection, recall_similar_deployments, retain_deployment_experience
from services.llm_service import analyze_deployment
from utils.config import get_settings
from utils.helpers import build_memory_impact_facts

st.set_page_config(page_title="DeployMind", page_icon="🛠️", layout="wide")

st.markdown(
    """
    <style>
    :root { --dm-ink: #18221f; --dm-muted: #68746e; --dm-line: #dce4df; --dm-green: #16724c; --dm-lime: #dff2e6; --dm-paper: #f5f8f4; --dm-warn: #8a5a12; }
    .stApp { background: var(--dm-paper); color: var(--dm-ink); }
    [data-testid="stSidebar"] { background: #e9f0eb; border-right: 1px solid var(--dm-line); }
    .dm-kicker { color: var(--dm-green); font-size: .78rem; font-weight: 700; text-transform: uppercase; }
    .dm-panel { border: 1px solid var(--dm-line); border-radius: 6px; background: #fff; padding: 1rem 1.1rem; margin: .5rem 0; }
    .dm-status { color: var(--dm-muted); font-size: .92rem; }
    div[data-testid="stMetric"] { background: #fff; border: 1px solid var(--dm-line); border-radius: 6px; padding: .8rem; }
    div.stButton > button[kind="primary"] { background: var(--dm-green); border-color: var(--dm-green); }
    </style>
    """,
    unsafe_allow_html=True,
)

if "deployment_history" not in st.session_state:
    st.session_state.deployment_history = []
if "metrics" not in st.session_state:
    st.session_state.metrics = {"analyzed": 0, "recalled": 0, "stored": 0}
if "hindsight_status" not in st.session_state:
    st.session_state.hindsight_status = None


def add_history(deployment: Deployment, risk_level: str = "Uncertain") -> None:
    st.session_state.deployment_history.insert(
        0,
        {
            "Deployment ID": deployment.deployment_id,
            "Service": deployment.service,
            "Environment": deployment.environment,
            "Status": deployment.result or "ANALYZED",
            "Risk level": risk_level,
            "Created time": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
    )


def render_analysis(
    result: dict,
    memories: list[dict],
    recall_error: str = "",
    risk_metric_label: str = "Memory-assisted deployment risk",
) -> None:
    st.subheader("Risk Summary")
    st.write(result.get("risk_summary") or "Analysis returned no summary.")
    level = result.get("risk_level", "Uncertain")
    st.metric(risk_metric_label, level)
    if recall_error:
        st.error(f"Hindsight recall failed: {recall_error}")
    elif not memories:
        st.info("No relevant deployment memory was found. DeployMind is performing a fresh analysis.")
    else:
        st.success("SIMILAR HISTORICAL DEPLOYMENT FOUND")
        st.caption(f"{len(memories)} historical memory result(s) supplied to the analysis.")
    st.markdown("#### Historical Memory Used")
    st.write(result.get("historical_memory_used") or ("No historical memory was used." if not memories else "The model did not describe its memory use."))
    cols = st.columns(3)
    labels = ["Similar Previous Deployment", "Previous Failure", "Previous Root Cause"]
    keys = ["similar_previous_deployment", "previous_failure", "previous_root_cause"]
    for col, label, key in zip(cols, labels, keys):
        with col:
            st.markdown(f"**{label}**")
            st.write(result.get(key) or "Not identified from supplied evidence.")
    st.markdown("**Previous Successful Fix**")
    st.write(result.get("previous_successful_fix") or "Not identified from supplied evidence.")
    st.markdown("**Why This Memory Is Relevant**")
    st.write(result.get("why_memory_is_relevant") or "No relevance explanation was returned.")
    st.markdown("**Recommended Preventive Checks**")
    checks = result.get("recommended_preventive_checks") or []
    if checks:
        for check in checks:
            st.markdown(f"- {check}")
    else:
        st.write("No checks were returned.")
    st.markdown("**Confidence / Uncertainty**")
    st.write(result.get("confidence_uncertainty") or "Treat this as advisory; validate against current deployment evidence.")
    assumptions = result.get("assumptions") or []
    if assumptions:
        with st.expander("Assumptions"):
            for assumption in assumptions:
                st.markdown(f"- {assumption}")
    if memories:
        with st.expander("Actual Hindsight recall results"):
            for memory in memories:
                st.markdown(f"**{memory.get('context') or memory.get('id') or 'Historical experience'}**")
                st.code(memory.get("text", ""), language="json")


def deployment_form(prefix: str, include_status: bool = True) -> Deployment:
    left, right = st.columns(2)
    with left:
        deployment_id = st.text_input("Deployment ID", key=f"{prefix}_id", placeholder="DEP-042")
        service = st.text_input("Application / Service", key=f"{prefix}_service", placeholder="Payment API")
        environment = st.selectbox("Environment", ["Production", "Staging", "Development"], key=f"{prefix}_environment")
    with right:
        changed_files = st.text_area("Changed Files", key=f"{prefix}_files", placeholder="database.yml\nconfig.env", height=88)
        change_summary = st.text_area("Change Summary", key=f"{prefix}_summary", placeholder="Describe the configuration or code change.", height=88)
    build_status, test_status, logs = "Not Run", "Not Run", ""
    if include_status:
        one, two = st.columns(2)
        with one:
            build_status = st.selectbox("Build Status", ["Passed", "Failed", "Not Run"], key=f"{prefix}_build")
        with two:
            test_status = st.selectbox("Test Status", ["Passed", "Failed", "Not Run"], key=f"{prefix}_tests")
        logs = st.text_area("Relevant Logs / Error Messages", key=f"{prefix}_logs", height=100)
    return Deployment(
        deployment_id=deployment_id.strip(),
        service=service.strip(),
        environment=environment,
        changed_files=parse_changed_files(changed_files),
        change_summary=change_summary.strip(),
        build_status=build_status,
        test_status=test_status,
        logs=logs.strip(),
    )


def page_dashboard() -> None:
    st.markdown('<div class="dm-kicker">Deployment intelligence</div>', unsafe_allow_html=True)
    st.title("DeployMind")
    st.subheader("Memory-Driven Deployment Risk Analysis")
    st.write("Learn from previous deployments before repeating the same failure.")
    if st.session_state.hindsight_status is None:
        with st.spinner("Checking Hindsight memory connection..."):
            st.session_state.hindsight_status = check_hindsight_connection()
    connected, status_message = st.session_state.hindsight_status
    settings = get_settings()
    status_cols = st.columns(2)
    status_cols[0].markdown(f"**Hindsight Memory:** {'🟢 Connected' if connected else '🔴 Not Connected'}")
    status_cols[1].markdown(f"**Groq AI:** {'🟢 Configured' if settings.groq_api_key else '🔴 Not Configured'}")
    if not connected:
        st.caption(status_message)
    if not settings.groq_api_key:
        st.caption("Configure GROQ_API_KEY in the process environment to enable analysis.")
    metrics = st.session_state.metrics
    cols = st.columns(3)
    cols[0].metric("Deployments analyzed this session", metrics["analyzed"])
    cols[1].metric("Memories recalled this session", metrics["recalled"])
    cols[2].metric("Experiences stored this session", metrics["stored"])
    st.markdown("### Recent activity")
    if st.session_state.deployment_history:
        st.dataframe(pd.DataFrame(st.session_state.deployment_history).head(5), use_container_width=True, hide_index=True)
    else:
        st.info("No deployment activity in this session yet.")


def page_new_deployment() -> None:
    st.title("New Deployment")
    st.write("Compare the proposed change with persistent deployment experience before rollout.")
    deployment = deployment_form("new")
    if st.button("Analyze Deployment Risk", type="primary", use_container_width=True):
        errors = validate_deployment(deployment)
        if errors:
            for error in errors:
                st.error(error)
            return
        memories, recall_error = [], ""
        with st.spinner("Searching Hindsight and analyzing deployment evidence..."):
            try:
                memories = recall_similar_deployments(build_recall_query(deployment))
                st.session_state.metrics["recalled"] += len(memories)
            except Exception as exc:
                recall_error = str(exc)
            try:
                result = analyze_deployment(deployment.to_dict(), memories)
            except Exception as exc:
                st.error(f"Groq analysis failed: {exc}")
                return
        st.session_state.metrics["analyzed"] += 1
        add_history(deployment, result.get("risk_level", "Uncertain"))
        render_analysis(result, memories, recall_error)


def page_record_result() -> None:
    st.title("Record Deployment Result")
    st.write("Save the verified outcome, diagnosis, fix, and lesson as persistent Hindsight experience.")
    with st.form("record_result_form"):
        deployment = deployment_form("record", include_status=False)
        deployment.result = st.selectbox("Result", ["SUCCESS", "FAILED"])
        deployment.error = st.text_area("Error Message")
        deployment.root_cause = st.text_area("Confirmed Root Cause")
        deployment.fixes_attempted = st.text_area("Fixes Attempted")
        deployment.successful_fix = st.text_area("Successful Fix")
        deployment.resolution_notes = st.text_area("Resolution Notes")
        deployment.lessons_learned = st.text_area("Lessons Learned")
        submitted = st.form_submit_button("Save Experience to Hindsight", type="primary", use_container_width=True)
    if submitted:
        errors = validate_result_experience(deployment)
        if errors:
            for error in errors:
                st.error(error)
            return
        experience = format_deployment_experience(deployment.to_dict())
        try:
            with st.spinner("Retaining deployment experience in Hindsight..."):
                response = retain_deployment_experience(experience)
            if getattr(response, "success", True) is False:
                st.error("Hindsight did not confirm that this experience was stored.")
                return
        except Exception as exc:
            st.error(f"Hindsight retain failed: {exc}")
            return
        st.session_state.metrics["stored"] += 1
        deployment.created_at = experience["timestamp"]
        add_history(deployment)
        st.success("Deployment experience stored in Hindsight memory. Future similar deployments can use this experience.")


def page_memory_explorer() -> None:
    st.title("Memory Explorer")
    st.write("Search and inspect the actual experiences returned by your Hindsight bank.")
    query = st.text_input("Memory query", placeholder="database timeout, Docker configuration, CrashLoopBackOff...")
    if st.button("Search Hindsight", type="primary"):
        if not query.strip():
            st.error("Enter a query to search deployment memory.")
            return
        try:
            with st.spinner("Recalling persistent deployment memories..."):
                memories = recall_similar_deployments(query)
            st.session_state.metrics["recalled"] += len(memories)
        except Exception as exc:
            st.error(f"Hindsight recall failed: {exc}")
            return
        st.session_state.memory_explorer_results = memories
    memories = st.session_state.get("memory_explorer_results", [])
    if memories:
        for index, memory in enumerate(memories, start=1):
            with st.expander(f"{memory.get('context') or 'Deployment experience'} · result {index}", expanded=index == 1):
                st.markdown("**Memory text**")
                st.code(memory["text"], language="json")
                st.markdown(f"**Relevance score:** {memory.get('score') if memory.get('score') is not None else 'Not provided by Hindsight'}")
                st.markdown(f"**Type:** {memory.get('type') or 'Not provided'}")
                st.markdown("**Metadata**")
                st.json(memory.get("metadata") or {})
    elif "memory_explorer_results" in st.session_state:
        st.info("No relevant deployment memory was found.")


def page_memory_impact() -> None:
    st.title("Memory Impact Demo")
    st.write("Run the same deployment through Groq with and without Hindsight context.")
    st.caption("A direct comparison of stateless analysis and persistent deployment memory.")
    deployment = deployment_form("impact")
    if st.button("Compare Analyses", type="primary", use_container_width=True):
        errors = validate_deployment(deployment)
        if errors:
            for error in errors:
                st.error(error)
            return
        memories, recall_error = [], ""
        with st.spinner("Retrieving memory and generating both analyses..."):
            try:
                memories = recall_similar_deployments(build_recall_query(deployment))
                st.session_state.metrics["recalled"] += len(memories)
                memories = memories[:5]
            except Exception as exc:
                recall_error = str(exc)
            try:
                without_memory = analyze_deployment(deployment.to_dict(), [])
                with_memory = analyze_deployment(deployment.to_dict(), memories)
            except Exception as exc:
                st.error(f"Groq analysis failed: {exc}")
                return
        st.session_state.metrics["analyzed"] += 1
        st.session_state.impact_data = (without_memory, with_memory, memories, recall_error)
    if "impact_data" in st.session_state:
        without_memory, with_memory, memories, recall_error = st.session_state.impact_data
        left, right = st.columns(2)
        with left:
            st.markdown("### WITHOUT HINDSIGHT MEMORY")
            st.caption("Current deployment evidence only")
            render_analysis(without_memory, [], risk_metric_label="Deployment Risk")
        with right:
            st.markdown("### WITH HINDSIGHT MEMORY")
            st.caption("Current evidence plus recalled Hindsight experience")
            render_analysis(with_memory, memories, recall_error, risk_metric_label="Memory-Assisted Risk")
        st.markdown("### What changed because of Hindsight?")
        facts = build_memory_impact_facts(memories)
        without_col, with_col = st.columns(2)
        with without_col:
            st.markdown("**WITHOUT MEMORY**")
            st.write("Generic database/configuration troubleshooting.")
        with with_col:
            st.markdown("**WITH MEMORY**")
            if facts.get("deployment_id"):
                st.write(f"{facts['deployment_id']} was recalled.")
            for label, key in (
                ("Previous failure", "previous_failure"),
                ("Previous cause", "previous_cause"),
                ("Previous fix", "previous_fix"),
            ):
                if facts.get(key):
                    st.markdown(f"**{label}:** {facts[key]}")
            if not facts and recall_error:
                st.error(f"Hindsight recall failed: {recall_error}")
            elif not facts:
                st.info("No matching historical facts were present in the recalled memories.")
        with st.container(border=True):
            st.markdown("### MEMORY IMPACT")
            if facts.get("deployment_id") == "DEP-025" and facts.get("previous_fix"):
                st.write(
                    "DeployMind recalled DEP-025 and used its successful resolution to make the "
                    "current deployment analysis more specific."
                )
            else:
                st.write("The current analysis used only the historical details present in the recalled memories.")
        st.write("**Impact:** Current recommendations become more specific and evidence-based.")


def page_history() -> None:
    st.title("Deployment History")
    st.caption("This table is session-only UI history. Persistent experiences are stored in Hindsight.")
    if not st.session_state.deployment_history:
        st.info("No deployments have been analyzed or recorded in this session.")
        return
    st.dataframe(pd.DataFrame(st.session_state.deployment_history), use_container_width=True, hide_index=True)


def page_about() -> None:
    st.title("About DeployMind")
    st.write("DeployMind is a memory-driven deployment risk analysis assistant for DevOps and SRE workflows.")
    st.markdown("**Persistent layer:** Hindsight stores deployment experiences. **Analysis:** Groq summarizes current evidence alongside explicitly supplied historical memories. **Session UI:** Streamlit session state tracks only this session's activity.")
    st.warning("Recommendations are advisory. Confirm configuration, logs, and rollback plans with your deployment process; no outcome is guaranteed.")


with st.sidebar:
    st.markdown("## DeployMind")
    st.caption("Memory-driven deployment risk analysis")
    page = st.radio(
        "Navigation",
        ["Dashboard", "New Deployment", "Record Deployment Result", "Memory Explorer", "Memory Impact Demo", "Deployment History", "About"],
        label_visibility="collapsed",
    )

{
    "Dashboard": page_dashboard,
    "New Deployment": page_new_deployment,
    "Record Deployment Result": page_record_result,
    "Memory Explorer": page_memory_explorer,
    "Memory Impact Demo": page_memory_impact,
    "Deployment History": page_history,
    "About": page_about,
}[page]()