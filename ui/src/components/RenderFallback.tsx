import { Component, type ReactNode } from "react";

interface RenderFallbackProps {
  fallback: ReactNode;
  children: ReactNode;
}

/**
 * Shows `fallback` when its children fail to render or load, e.g. a WebGL context that cannot be
 * created or a lazy chunk that cannot be fetched. The error is reported to the console, not hidden.
 */
export class RenderFallback extends Component<RenderFallbackProps, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: Error): void {
    console.error("3D view failed; showing the 2D network instead:", error);
  }

  override render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
