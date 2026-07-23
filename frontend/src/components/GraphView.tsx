import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import type { InvestigationGraph } from "../types";
import "./GraphView.css";

const LABEL_COLORS: Record<string, string> = {
  Customer: "#3b82f6",
  Account: "#0ea5e9",
  Transaction: "#a855f7",
  Device: "#f59e0b",
  IPAddress: "#ef4444",
  Merchant: "#14b8a6",
  PhoneNumber: "#84cc16",
  EmailAddress: "#eab308",
  Address: "#94a3b8",
  FraudAlert: "#dc2626",
  FraudCase: "#7c3aed",
};

function labelColor(label: string): string {
  return LABEL_COLORS[label] ?? "#64748b";
}

function nodeCaption(label: string, properties: Record<string, unknown>): string {
  const idField = ["customer_id", "account_id", "transaction_id", "device_id", "ip", "merchant_id", "case_id", "alert_id"].find(
    (f) => f in properties,
  );
  const id = idField ? String(properties[idField]) : "";
  return `${label}\n${id}`;
}

interface Props {
  graph: InvestigationGraph;
  height?: number;
  highlightNodeIds?: string[];
  onNodeClick?: (nodeId: string) => void;
}

export function GraphView({ graph, height = 480, highlightNodeIds = [], onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [hiddenLabels, setHiddenLabels] = useState<Set<string>>(new Set());
  const [riskFilter, setRiskFilter] = useState<string>("ALL");

  const labels = useMemo(() => Array.from(new Set(graph.nodes.map((n) => n.label))).sort(), [graph]);

  const elements = useMemo<ElementDefinition[]>(() => {
    const nodeIds = new Set(graph.nodes.map((n) => n.id));
    const nodeEls: ElementDefinition[] = graph.nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
        caption: nodeCaption(n.label, n.properties),
        risk_level: (n.properties.risk_level as string) ?? "",
        ...n.properties,
      },
    }));
    const edgeEls: ElementDefinition[] = graph.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e, i) => ({
        data: { id: `edge-${i}-${e.source}-${e.target}`, source: e.source, target: e.target, label: e.type },
      }));
    return [...nodeEls, ...edgeEls];
  }, [graph]);

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele) => labelColor(ele.data("label")),
            label: "data(caption)",
            "text-wrap": "wrap",
            "font-size": 8,
            color: "#0b1220",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 26,
            height: 26,
            "border-width": 0,
          },
        },
        {
          selector: "node[risk_level = 'CRITICAL']",
          style: { "border-width": 3, "border-color": "#c92a2a" },
        },
        {
          selector: "node[risk_level = 'HIGH']",
          style: { "border-width": 2, "border-color": "#e8590c" },
        },
        {
          selector: "node.highlighted",
          style: { "border-width": 4, "border-color": "#facc15" },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#cbd5e1",
            "target-arrow-color": "#cbd5e1",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 6,
            color: "#64748b",
          },
        },
      ],
      layout: { name: "cose", animate: false, padding: 30 },
    });

    cy.on("tap", "node", (evt) => {
      setSelected(evt.target.data());
      onNodeClick?.(evt.target.id());
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelected(null);
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      n.removeClass("highlighted");
    });
    highlightNodeIds.forEach((id) => cy.getElementById(id).addClass("highlighted"));
  }, [highlightNodeIds]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      const label = n.data("label");
      const risk = n.data("risk_level");
      const hiddenByLabel = hiddenLabels.has(label);
      const hiddenByRisk = riskFilter !== "ALL" && risk !== riskFilter;
      n.style("display", hiddenByLabel || hiddenByRisk ? "none" : "element");
    });
  }, [hiddenLabels, riskFilter]);

  function toggleLabel(label: string) {
    setHiddenLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  return (
    <div className="graph-view">
      <div className="graph-toolbar">
        <div className="legend">
          {labels.map((label) => (
            <button
              key={label}
              className={`legend-item ${hiddenLabels.has(label) ? "off" : ""}`}
              onClick={() => toggleLabel(label)}
              type="button"
            >
              <span className="dot" style={{ background: labelColor(label) }} />
              {label}
            </button>
          ))}
        </div>
        <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
          <option value="ALL">All risk levels</option>
          <option value="LOW">LOW</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="HIGH">HIGH</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <button type="button" className="btn btn-secondary" onClick={() => cyRef.current?.fit(undefined, 30)}>
          Fit view
        </button>
      </div>
      <div className="graph-body">
        <div ref={containerRef} style={{ height }} className="graph-canvas" />
        {selected && (
          <div className="graph-inspector">
            <h3>{String(selected.label)}</h3>
            <dl>
              {Object.entries(selected)
                .filter(([k]) => !["label", "caption"].includes(k))
                .map(([k, v]) => (
                  <div key={k} className="inspector-row">
                    <dt>{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
