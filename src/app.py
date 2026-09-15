# -*- coding: utf-8 -*-
"""Streamlit UI for the current AIOps pipeline.

The UI is intentionally path-based for large files: Streamlit's file uploader
is not used for 100GB-class logs because that would move the whole upload into
the web server/session layer. The pipeline itself remains streaming/bounded.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict

import streamlit as st
from ai_engine import MODELS_CONFIG, call_ai_agent, load_prompt
from aiops_pipeline import AIOpsPipeline


st.set_page_config(
    page_title="AIOps SRE Otopilot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .hero {
        padding: 1rem 1.2rem;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,.25);
        margin-bottom: 1rem;
    }
    .small-muted { color: #8b8b8b; font-size: .88rem; }
    div.stButton > button { font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _section_map(report: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    matches = list(re.finditer(r"^###\s+\d+\.\s*(.+?)\s*$", report or "", re.MULTILINE))
    if not matches:
        return {"Rapor": report or ""}
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(report)
        sections[title] = report[start:end].strip()
    return sections


def _fmt_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


TEST_STEPS = {
    "01 · Segmentation": ("segmentation", "Log satırlarından mantıksal event oluşturma. İlk örnek event'leri gösterir."),
    "02 · Parser / Canonical Event": ("parser", "Bir ham logical event'in ortak canonical event modeline dönüşmüş halini gösterir."),
    "03 · Context Inference": ("context", "service, component, error_family, exception_type gibi bağlam bilgisini gösterir."),
    "04 · Drain3 Signal": ("drain_signal", "Event'in template/cluster/sinyal bilgisini gösterir."),
    "05 · Smart Filter": ("smart_filter", "Risk skoru ve actionable / noise kararını gösterir."),
    "06 · Bounded Incident State": ("bounded_incident_state", "Streaming sırasında event'lerin nasıl bounded state ve representative event'lere sıkıştırıldığını gösterir."),
    "07 · Incident Aggregation": ("incident_aggregation", "Representative event'lerden incident adaylarının nasıl oluştuğunu gösterir."),
    "08 · Causal Graph": ("causal_graph", "Incident'ler arasındaki causal edge ve root candidate sonucunu gösterir."),
    "09 · Triage Selection": ("triage_selection", "Agent 1'e gönderilmek üzere seçilen incident'ları ve token bütçesini gösterir."),
    "10 · Agent 1 Triage": ("agent1_triage", "Seçilen incident'ların DeepSeek Agent 1 tarafından nasıl önceliklendirildiğini gösterir."),
    "11 · RCA Context": ("rca_context", "Agent 1 sonrası Expert RCA modeline gönderilen final compact context'i gösterir."),
    "12 · Expert RCA / XAI": ("expert_rca", "Qwen'in ürettiği Root Cause, Causal Chain, XAI Reasoning, Evidence ve Action çıktısını gösterir."),
}


def _pretty(value: Any, max_chars: int = 30000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (kısaltıldı)"


def _run_agent1_for_test(pipeline: AIOpsPipeline) -> Dict[str, Any]:
    triage_incidents = AIOpsPipeline._select_triage_incidents(
        pipeline.last_incident_contexts,
        pipeline.triage_top_k,
        pipeline.triage_max_tokens,
    )
    triage_payload = json.dumps(triage_incidents, ensure_ascii=False, indent=2)
    sys_prompt = load_prompt("common_system.md") + "\n\n" + load_prompt("ajan1_triyaj.md")
    raw, duration, usage = call_ai_agent(
        "Ajan_1_Triyaj",
        sys_prompt,
        triage_payload,
        temperature=0.1,
        max_tokens=1600,
        response_format={"type": "json_object"},
        return_usage=True,
    )
    try:
        obj = json.loads(raw) if raw else None
    except (TypeError, json.JSONDecodeError):
        obj = None
    return {
        "raw": raw or "",
        "object": obj,
        "duration": duration,
        "usage": usage or {},
        "input_incidents": triage_incidents,
    }


def _run_rca_for_test(pipeline: AIOpsPipeline, triage_obj: Any, model: str | None) -> Dict[str, Any]:
    context = pipeline.build_rca_context(triage_obj)
    sys_prompt = load_prompt("common_system.md") + "\n\n" + load_prompt("ajan2_rca.md")

    # Streamlit test screen can reach this function before a model is selected
    # (for example after a widget state reset). Always resolve a valid Expert RCA
    # configuration instead of passing None into call_ai_agent().
    selected = model if model in MODELS_CONFIG else None
    if selected is None:
        preferred = [
            "Ajan_2_RCA_Expert",
            "Ajan_2_Causal_Expert",
            "Ajan_2_RCA_AgirTop",
        ]
        selected = next((key for key in preferred if key in MODELS_CONFIG), None)
    if selected is None:
        selected = next(
            (key for key, cfg in MODELS_CONFIG.items() if cfg.get("role") in {"expert_rca", "rca", "qwen_rca"}),
            None,
        )
    if selected is None:
        return {
            "context": context,
            "report": "",
            "duration": 0.0,
            "usage": {},
            "error": "Expert RCA modeli bulunamadı. MODELS_CONFIG kontrol edilmeli.",
            "model": None,
        }

    report, duration, usage = call_ai_agent(
        selected,
        sys_prompt,
        context,
        temperature=0.1,
        max_tokens=int(os.getenv("QWEN_RCA_MAX_TOKENS", "2200")),
        return_usage=True,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "include_reasoning": False,
        },
    )
    return {
        "context": context,
        "report": report or "",
        "duration": duration,
        "usage": usage or {},
        "model": selected,
        "error": None,
    }


def _test_screen() -> None:
    st.title("🧪 Pipeline Test Ekranı")
    st.caption("Her testte yalnızca seçtiğiniz aşamanın çıktısı gösterilir. Önceki aşamalar arka planda çalışır.")

    with st.sidebar:
        st.header("🧪 Adım Adım Test")
        test_path = st.text_input(
            "📁 Test log dosyası",
            value="data/sre_smoke_test.log",
            key="test_input_path",
        )
        step_label = st.selectbox("🔢 İncelenecek aşama", list(TEST_STEPS.keys()))
        if step_label in {"11 · RCA Context", "12 · Expert RCA / XAI"}:
            rca_options = [k for k, cfg in MODELS_CONFIG.items() if cfg.get("role") in {"expert_rca", "rca", "qwen_rca"}]
            if not rca_options:
                rca_options = [k for k in MODELS_CONFIG.keys() if "qwen" in str(k).lower()]
            selected_test_model = st.selectbox("🧠 Ajan 2 RCA modeli", rca_options, index=0, key="test_rca_model")
        else:
            selected_test_model = None
        sample_limit = st.number_input("Örnek / kayıt limiti", min_value=1, max_value=100, value=5, step=1)
        run_test = st.button("▶️ Seçili Aşamayı Test Et", width='stretch', type="primary")

    stage_key, description = TEST_STEPS[step_label]
    st.info(f"**{step_label}** — {description}")

    if not run_test:
        st.warning("Bir log dosyası ve test aşaması seçip **Seçili Aşamayı Test Et** butonuna basın.")
        st.stop()

    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(test_path.strip())))
    if not os.path.isfile(resolved):
        st.error(f"Dosya bulunamadı: `{resolved}`")
        st.stop()

    pipeline = AIOpsPipeline(threshold=50)
    with st.spinner(f"Gerekli önceki aşamalar çalışıyor: {step_label}"):
        pipeline.process_file(resolved, debug_limit=int(sample_limit))

    trace = pipeline.last_debug_trace or {}

    if stage_key in {"agent1_triage", "rca_context", "expert_rca"}:
        agent1_result = _run_agent1_for_test(pipeline)
        if stage_key == "agent1_triage":
            st.success("✅ Agent 1 tamamlandı")
            st.metric("Input tokens", agent1_result["usage"].get("prompt_tokens", 0))
            st.metric("Output tokens", agent1_result["usage"].get("completion_tokens", 0))
            if agent1_result["object"] is not None:
                st.json(agent1_result["object"])
            else:
                st.code(agent1_result["raw"] or "{}", language="json")
            st.caption(f"Süre: {agent1_result['duration']:.2f} sn · Seçilen incident: {len(agent1_result['input_incidents'])}")
            st.stop()

        rca_result = _run_rca_for_test(pipeline, agent1_result["object"], selected_test_model)
        if stage_key == "rca_context":
            st.success("✅ Final RCA context oluşturuldu")
            st.caption("Agent 1 çıktısı dahil edilmiştir. Bu payload raw log değil, bounded/compact RCA context'idir.")
            st.code(rca_result["context"], language="json")
            st.metric("Estimated / actual input tokens", rca_result["usage"].get("prompt_tokens", 0))
            st.stop()

        if rca_result.get("error"):
            st.error(rca_result["error"])
            st.stop()
        if not rca_result["report"]:
            st.error("Expert RCA boş yanıt döndürdü.")
            st.stop()
        st.success("✅ Expert RCA + XAI tamamlandı")
        st.caption(f"Model: {rca_result.get('model', 'bilinmiyor')}")
        st.caption(
            f"Süre: {rca_result['duration']:.2f} sn · "
            f"Input tokens: {rca_result['usage'].get('prompt_tokens', 0):,} · "
            f"Output tokens: {rca_result['usage'].get('completion_tokens', 0):,}"
        )
        sections = _section_map(rca_result["report"])
        for title, content in sections.items():
            with st.expander(title, expanded=True):
                st.markdown(content)
        st.stop()

    data = trace.get(stage_key)
    if data is None:
        st.error(f"`{stage_key}` aşaması için debug çıktısı oluşmadı.")
        st.stop()

    st.success(f"✅ {step_label} tamamlandı")

    if stage_key == "segmentation":
        validation = (pipeline.segmenter.last_result or {}).get("validation", {})
        counts = (validation.get("event_line_counts") or {})
        source_counts = (validation.get("first_line_sources") or {})
        cols = st.columns(5)
        cols[0].metric("Physical lines", validation.get("total_lines", 0))
        cols[1].metric("Logical events", validation.get("event_count", 0))
        cols[2].metric("Detected headers", validation.get("header_matches", 0))
        cols[3].metric("Internal headers", validation.get("internal_header_candidates", 0))
        cols[4].metric("Zero-loss", "PASS" if validation.get("accounting_zero_loss") else "FAIL")
        st.caption(
            f"Coverage: {float(validation.get('coverage_score', 0.0) or 0.0):.2f}% · "
            f"Unmatched strong headers: {validation.get('candidate_unmatched_headers', 0)} · "
            f"Parser success: {float((validation.get('parser_validation') or {}).get('success_ratio', 0.0) or 0.0):.2f}% · "
            f"Regex boundaries: {source_counts.get('regex', 0)} · Orphan boundaries: {source_counts.get('orphan', 0)} · "
            f"Multiline events: {counts.get('multiline_events', 0)}"
        )
        st.subheader("Detected logical events")
        for idx, event in enumerate(data.get("events", []), 1):
            with st.expander(f"Event #{idx}", expanded=(idx == 1)):
                st.code(str(event), language="text")
    elif stage_key == "bounded_incident_state":
        stats = data.get("stats", {})
        cols = st.columns(5)
        cols[0].metric("Active states", stats.get("active_states", 0))
        cols[1].metric("Aggregated events", stats.get("aggregated_event_count", 0))
        cols[2].metric("Represented", stats.get("represented_events", 0))
        cols[3].metric("Coarsened", stats.get("coarsened_events", 0))
        cols[4].metric("State limit", stats.get("max_states", 0))
        st.subheader("Representative events")
        st.json(data.get("representative_events", []))
    elif stage_key in {"causal_graph"}:
        graph = data
        cols = st.columns(4)
        cols[0].metric("Nodes", graph.get("node_count", 0))
        cols[1].metric("Edges", graph.get("edge_count", 0))
        cols[2].metric("Confidence", f"{float(graph.get('graph_confidence', 0.0) or 0.0):.3f}")
        cols[3].metric("Root status", graph.get("root_cause_status", "unconfirmed"))
        st.write("**Root candidates:**", graph.get("root_cause_candidates", []))
        edges = graph.get("edges", []) or []
        if edges:
            st.dataframe([
                {
                    "Source": e.get("source"),
                    "Target": e.get("target"),
                    "Score": e.get("score"),
                    "Validation": e.get("validation_source"),
                    "Evidence": ", ".join(e.get("evidence", []) or []),
                }
                for e in edges
            ], width='stretch', hide_index=True)
        else:
            st.info("Bu çalıştırmada causal edge oluşmadı.")
    elif stage_key == "rca_context":
        st.caption("Bu, Qwen Expert RCA'ya giden compact payload'dır; raw log gönderilmez.")
        st.code(_pretty(data), language="json")
    elif stage_key == "triage_selection":
        st.metric("Estimated input tokens", data.get("estimated_input_tokens", 0))
        st.caption(f"Toplam incident: {data.get('all_incidents', 0)} · seçilen: {len(data.get('selected_incidents', []) or [])}")
        st.json(data.get("selected_incidents", []))
    else:
        events = data.get("events") if isinstance(data, dict) else None
        if events is not None:
            st.caption(f"Gösterilen örnek sayısı: {len(events)}")
            for idx, item in enumerate(events, start=1):
                with st.expander(f"Örnek #{idx}", expanded=(idx == 1)):
                    # Segmentation output is a raw logical-event string, not JSON.
                    # Using st.json(string) makes Streamlit attempt json.loads() and
                    # display a misleading "Json Parse Error" for normal text logs.
                    if isinstance(item, str):
                        st.code(item, language="text")
                    elif isinstance(item, (dict, list)):
                        st.json(item)
                    else:
                        st.code(str(item), language="text")
        else:
            st.code(_pretty(data), language="json")

    st.markdown("---")
    st.caption(f"Test dosyası: {resolved} · Boyut: {_fmt_bytes(os.path.getsize(resolved))}")


def _run_analysis(input_path: str, rca_model: str) -> Dict[str, Any]:
    pipeline = AIOpsPipeline(threshold=50)
    start = time.time()

    with st.status("🚀 AIOps pipeline çalışıyor...", expanded=True) as status:
        st.write("1/4 · Streaming segmentation + parser + smart filter")
        pipeline.process_file(input_path)

        seg = pipeline.last_segmentation_result or {}
        stats = pipeline.last_stats or {}
        graph = pipeline.last_causal_graph or {}

        st.write(
            f"Segmentation: {seg.get('source')} · coverage=%{seg.get('coverage_score', 0)} · "
            f"actionable={stats.get('actionable', 0):,}"
        )
        st.write(
            f"2/4 · Incident aggregation: {len(pipeline.last_incident_contexts):,} incident · "
            f"bounded states max={stats.get('max_active_incident_states', 0):,}"
        )
        st.write(
            f"3/4 · Causal graph: {graph.get('edge_count', 0):,} edge · "
            f"root={graph.get('root_cause_candidates', [])}"
        )

        triage_payload = json.dumps(
            AIOpsPipeline._select_triage_incidents(
                pipeline.last_incident_contexts,
                pipeline.triage_top_k,
                pipeline.triage_max_tokens,
            ),
            ensure_ascii=False,
            indent=2,
        )
        sys_prompt_1 = load_prompt("common_system.md") + "\n\n" + load_prompt("ajan1_triyaj.md")
        st.write("4/4 · Agent 1 triage + Agent 2 expert RCA")
        filtered_logs, duration_1, triage_usage = call_ai_agent(
            "Ajan_1_Triyaj",
            sys_prompt_1,
            triage_payload,
            temperature=0.1,
            max_tokens=1600,
            response_format={"type": "json_object"},
            return_usage=True,
        )

        try:
            triage_obj = json.loads(filtered_logs) if filtered_logs else None
        except (TypeError, json.JSONDecodeError):
            triage_obj = None

        rca_context = pipeline.build_rca_context(triage_obj)
        sys_prompt_2 = load_prompt("common_system.md") + "\n\n" + load_prompt("ajan2_rca.md")
        rca_report, duration_2, rca_usage = call_ai_agent(
            rca_model,
            sys_prompt_2,
            rca_context,
            temperature=0.1,
            max_tokens=int(os.getenv("QWEN_RCA_MAX_TOKENS", "2200")),
            return_usage=True,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
                "include_reasoning": False,
            },
        )
        rca_report = rca_report or ""

        if not rca_report or "API Hatası" in rca_report or "Bağlantı Hatası" in rca_report:
            status.update(label="❌ AI analizi tamamlanamadı", state="error")
        else:
            status.update(label="✅ AIOps analizi tamamlandı", state="complete")

    elapsed = time.time() - start
    return {
        "pipeline": pipeline,
        "segmentation": seg,
        "stats": stats,
        "graph": graph,
        "triage_obj": triage_obj,
        "triage_raw": filtered_logs or "",
        "triage_usage": triage_usage or {},
        "triage_duration": duration_1,
        "rca_context": rca_context,
        "rca_report": rca_report,
        "rca_usage": rca_usage or {},
        "rca_duration": duration_2,
        "total_elapsed": elapsed,
        "input_path": input_path,
        "input_size": os.path.getsize(input_path) if os.path.exists(input_path) else 0,
    }


st.markdown(
    '<div class="hero"><h1>🚀 AIOps SRE Otopilot</h1>'
    '<div class="small-muted">Streaming + bounded incident state · Causal Graph · Agent 1 Triage · Expert RCA · XAI</div></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    mode = st.radio("🧭 Ekran", ["Canlı Analiz", "🧪 Adım Adım Test"], index=0)

if mode == "🧪 Adım Adım Test":
    _test_screen()
    st.stop()

with st.sidebar:
    st.header("⚙️ Analiz Ayarları")

    input_path = st.text_input(
        "📁 Log dosyası yolu",
        value="",
        help="100GB gibi büyük dosyalar için dosya yolu kullanılır; dosya Streamlit upload alanına taşınmaz.",
    )

    rca_options = ["Ajan_2_RCA_Expert", "Ajan_2_RCA_Hizli", "Claude-3", "Ajan_2_RCA_AgirTop"]
    selected_model = st.selectbox("🧠 Ajan 2 RCA modeli", rca_options, index=0)
    st.caption(MODELS_CONFIG[selected_model]["model_id"])

    st.markdown("---")
    run_btn = st.button("🚨 KRİZ ANALİZİNİ BAŞLAT", width='stretch', type="primary")
    clear_btn = st.button("🧹 Sonucu Temizle", width='stretch')

if clear_btn:
    st.session_state.pop("aiops_result", None)
    st.rerun()

if run_btn:
    if not input_path.strip():
        st.error("Log dosyası yolu boş bırakılamaz.")
        st.stop()
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(input_path.strip())))
    if not os.path.isfile(resolved):
        st.error(f"Dosya bulunamadı: `{resolved}`")
        st.stop()
    st.session_state["aiops_result"] = _run_analysis(resolved, selected_model)

result = st.session_state.get("aiops_result")
if not result:
    st.info("Sol panelden bir log dosyası yolu seçip **Kriz Analizini Başlat** butonuna basın.")
    st.markdown(
        "**Büyük log notu:** 100GB sınıfı dosyalar için upload yerine erişilebilir dosya yolu kullanın. "
        "Pipeline dosyayı satır/event bazında işler ve aktif incident state'i bounded tutar."
    )
    st.stop()

stats = result["stats"]
seg = result["segmentation"]
graph = result["graph"]

st.subheader("📊 Pipeline Özeti")
metric_rows = [
    ("Logical Event", f"{stats.get('raw_blocks', 0):,}"),
    ("Actionable Signal", f"{stats.get('actionable', 0):,}"),
    ("Incident", f"{len(result['pipeline'].last_incident_contexts):,}"),
    ("Collapsed", f"{max(0, stats.get('actionable', 0) - len(result['pipeline'].last_incident_contexts)):,}"),
    ("Causal Edge", f"{graph.get('edge_count', 0):,}"),
    ("RCA Context", f"{result['rca_usage'].get('prompt_tokens', 0):,} token"),
]
cols = st.columns(len(metric_rows))
for col, (label, value) in zip(cols, metric_rows):
    col.metric(label, value)

stream = seg.get("llm_context", {}).get("streaming", {}) or {}
bounded = stream.get("bounded_incident_state", {}) or {}

with st.expander("🔎 Teknik Ölçümler", expanded=False):
    left, right = st.columns(2)
    with left:
        st.write({
            "Input": result["input_path"],
            "Input size": _fmt_bytes(result["input_size"]),
            "Segmentation source": seg.get("source"),
            "Coverage": seg.get("coverage_score", 0),
            "Verified": seg.get("verified"),
            "Parsed": stats.get("parsed", 0),
            "Filtered out": stats.get("filtered_out", 0),
        })
    with right:
        st.write({
            "Streaming windows": stats.get("windows_finalized", 0),
            "Max active representatives": stats.get("max_active_window_events", 0),
            "Max active incident states": stats.get("max_active_incident_states", 0),
            "State limit": bounded.get("max_active_states", 0),
            "Aggregated events": bounded.get("aggregated_events", 0),
            "Represented events": bounded.get("represented_events", 0),
            "Coarsened events": bounded.get("coarsened_events", 0),
        })

st.markdown("---")

report = result["rca_report"]
if not report or "API Hatası" in report or "Bağlantı Hatası" in report:
    st.error(report or "Expert RCA boş yanıt döndürdü.")
else:
    st.header("📊 Nihai XAI SRE Raporu")
    st.caption(
        f"Toplam AI süresi: {result['triage_duration'] + result['rca_duration']:.2f} sn · "
        f"Agent 1: {result['triage_usage'].get('total_tokens', 0):,} token · "
        f"RCA: {result['rca_usage'].get('total_tokens', 0):,} token"
    )

    sections = _section_map(report)
    labels = list(sections.keys())
    tab_labels = []
    for title in labels:
        lower = title.lower()
        if "kök" in lower or "root" in lower:
            tab_labels.append("🎯 Kök Neden")
        elif "reasoning" in lower or "gerekçe" in lower:
            tab_labels.append("🧠 XAI Reasoning")
        elif "kanıt" in lower or "evidence" in lower:
            tab_labels.append("🧾 Kanıtlar")
        elif "çözüm" in lower or "action" in lower:
            tab_labels.append("🛠️ Aksiyon")
        else:
            tab_labels.append(title[:24])

    tabs = st.tabs(tab_labels)
    for tab, title in zip(tabs, labels):
        with tab:
            st.markdown(sections[title])

    st.markdown("---")
    st.subheader("🔗 Causal Graph")
    graph_cols = st.columns(4)
    graph_cols[0].metric("Nodes", graph.get("node_count", 0))
    graph_cols[1].metric("Edges", graph.get("edge_count", 0))
    graph_cols[2].metric("Graph Confidence", f"{float(graph.get('graph_confidence', 0.0) or 0.0):.3f}")
    graph_cols[3].metric("Root Status", graph.get("root_cause_status", "unconfirmed"))

    edges = graph.get("edges", []) or []
    if edges:
        edge_rows = [
            {
                "Source": e.get("source"),
                "Target": e.get("target"),
                "Score": e.get("score"),
                "Validation": e.get("validation_source"),
                "Evidence": ", ".join(e.get("evidence", []) or []),
            }
            for e in edges
        ]
        st.dataframe(edge_rows, width='stretch', hide_index=True)
    else:
        st.info("Causal edge oluşmadı; graph root cause'u doğrulamıyor.")

    st.subheader("🧠 Agent 1 Triage")
    st.code(result["triage_raw"] or "{}", language="json")

    with st.expander("🧪 RCA Context (Qwen'e gönderilen compact context)", expanded=False):
        st.code(result["rca_context"], language="json")

    with st.expander("⚙️ Segmentation Detayı", expanded=False):
        st.json(seg)

    st.download_button(
        "⬇️ XAI raporunu indir",
        data=report,
        file_name="aiops_xai_report.md",
        mime="text/markdown",
        width='stretch',
    )

    st.success(
        f"Analiz tamamlandı · Input={_fmt_bytes(result['input_size'])} · "
        f"{stats.get('raw_blocks', 0):,} logical event · "
        f"{len(result['pipeline'].last_incident_contexts):,} incident · "
        f"{graph.get('edge_count', 0):,} causal edge"
    )
