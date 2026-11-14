/**
 * A stand-in for @react-sigma/core (Sigma needs WebGL, which jsdom lacks). It renders its children
 * and the control buttons, and keeps what the view hands to Sigma, so tests can inspect the loaded
 * graph, the settings (reducers, hover drawing) and the registered events. The Sigma instance
 * also answers what the Overlap mode's contour layer reads: display data, viewport and size.
 * Use with `vi.mock("@react-sigma/core", () => import("@/test/reactSigma"))`.
 */
import { type ReactNode, useCallback } from "react";
import type { Settings } from "sigma/settings";
import type { EdgeDisplayData, NodeDisplayData } from "sigma/types";
import { vi } from "vitest";

import type { NetworkEdge, NetworkGraph, NetworkNode } from "@/lib/sigmaNetwork";

type NetworkSettings = Partial<Settings<NetworkNode, NetworkEdge>>;

type NodeEvent = { node: string };

export const sigmaStub: {
  graph: NetworkGraph | null;
  loads: number;
  renders: number;
  handlers: { enterNode?: (event: NodeEvent) => void; leaveNode?: (event: NodeEvent) => void };
  settings: NetworkSettings;
  gotoNode: ReturnType<typeof vi.fn>;
} = { graph: null, loads: 0, renders: 0, handlers: {}, settings: {}, gotoNode: vi.fn() };

export function resetSigmaStub(): void {
  sigmaStub.graph = null;
  sigmaStub.loads = 0;
  sigmaStub.renders = 0;
  sigmaStub.handlers = {};
  sigmaStub.settings = {};
  sigmaStub.gotoNode = vi.fn();
}

export function SigmaContainer({ children, settings }: { children?: ReactNode; settings?: NetworkSettings }) {
  Object.assign(sigmaStub.settings, settings);
  return <div data-testid="sigma">{children}</div>;
}

export function ControlsContainer({ children }: { children?: ReactNode }) {
  return <div data-testid="sigma-controls">{children}</div>;
}

export function ZoomControl({ labels = {} }: { labels?: Record<string, string> }) {
  return (
    <>
      {Object.values(labels).map((label) => (
        <button key={label} type="button" title={label} />
      ))}
    </>
  );
}

export const FullScreenControl = ZoomControl;

export function useLoadGraph() {
  return useCallback((graph: NetworkGraph) => {
    sigmaStub.graph = graph;
    sigmaStub.loads += 1;
  }, []);
}

export function useRegisterEvents() {
  return useCallback((handlers: typeof sigmaStub.handlers) => {
    sigmaStub.handlers = handlers;
  }, []);
}

export function useSetSettings() {
  return useCallback((settings: NetworkSettings) => {
    Object.assign(sigmaStub.settings, settings);
  }, []);
}

/** Pixels per layout unit in the stub: Sigma's `scaleSize` at the default camera. */
export const STUB_PIXELS_PER_UNIT = 10;

function loadedGraph(): NetworkGraph {
  if (!sigmaStub.graph) throw new Error("no graph loaded");
  return sigmaStub.graph;
}

const sigma = {
  getGraph: loadedGraph,
  getNodeDisplayData: (key: string): NetworkNode | undefined =>
    loadedGraph().hasNode(key) ? loadedGraph().getNodeAttributes(key) : undefined,
  framedGraphToViewport: ({ x, y }: { x: number; y: number }) => ({ x, y }),
  scaleSize: (size: number): number => size * STUB_PIXELS_PER_UNIT,
  scheduleRender: () => {
    sigmaStub.renders += 1;
  },
};

export function useSigma() {
  return sigma;
}

export function useCamera() {
  return { gotoNode: sigmaStub.gotoNode };
}

/** Sigma's view of a node after the view's reducer, as the stub was last configured. */
export function drawnNode(key: string): Partial<NodeDisplayData> {
  const reducer = sigmaStub.settings.nodeReducer;
  if (!reducer) throw new Error("no node reducer set");
  return reducer(key, sigma.getGraph().getNodeAttributes(key));
}

export function drawnEdge(key: string): Partial<EdgeDisplayData> {
  const reducer = sigmaStub.settings.edgeReducer;
  if (!reducer) throw new Error("no edge reducer set");
  return reducer(key, sigma.getGraph().getEdgeAttributes(key));
}
