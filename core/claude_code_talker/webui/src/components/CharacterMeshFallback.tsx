// v0.1.0 unification — error boundary + lazy-load wrapper for the 3D
// mesh viewer. Three concerns it solves:
//
//   1. Bundle size — @google/model-viewer + three.js is ~1MB minified.
//      Pulling it into the main bundle delays first paint of the entire
//      Sessions tab. React.lazy + dynamic import splits it into its own
//      chunk that downloads when the CharacterStage actually needs it.
//
//   2. Graceful degradation — if the GLB fails to load, the web
//      component fails to register, or three.js throws on WebGL init,
//      the error boundary swaps in the CharacterAvatar circle so the
//      character stage stays visible.
//
//   3. Suspense fallback — while the 3D chunk is loading, the avatar
//      circle is the "skeleton" so the layout doesn't jump when the
//      heavier viewer comes in.
import React, { Suspense, forwardRef, useEffect, useState } from "react";
import type { ModelViewerProps, ModelViewerElement } from "./ModelViewer";

// Dynamic import — pulls in @google/model-viewer + three.js only when
// the user actually opens a session with a 3D-meshed character.
const ModelViewerLazy = React.lazy(() =>
  import("./ModelViewer").then((m) => ({ default: m.ModelViewer }))
);

type Props = ModelViewerProps & {
  fallback: React.ReactNode;
};

/** Tiny error boundary specific to the mesh viewer. React 19 doesn't
 *  have an `useErrorBoundary` hook so we still use a class component. */
class MeshErrorBoundary extends React.Component<
  { fallback: React.ReactNode; children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(err: Error) {
    // eslint-disable-next-line no-console
    console.warn("[CharacterStage] mesh viewer error, falling back:", err);
  }
  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

export const CharacterMesh = forwardRef<ModelViewerElement, Props>(
  function CharacterMesh({ fallback, ...mvProps }, ref) {
    // Sanity check: bail to fallback if WebGL isn't available at all,
    // before even trying to load three.js. Catches headless / very old
    // browsers without paying the lazy-import cost.
    const [hasWebGL] = useState(() => {
      try {
        const c = document.createElement("canvas");
        return !!(c.getContext("webgl2") || c.getContext("webgl"));
      } catch {
        return false;
      }
    });
    useEffect(() => {
      if (!hasWebGL) {
        // eslint-disable-next-line no-console
        console.info("[CharacterStage] no WebGL — using avatar fallback");
      }
    }, [hasWebGL]);

    if (!hasWebGL) return <>{fallback}</>;

    return (
      <MeshErrorBoundary fallback={fallback}>
        <Suspense fallback={fallback}>
          <ModelViewerLazy ref={ref} {...mvProps} />
        </Suspense>
      </MeshErrorBoundary>
    );
  }
);
