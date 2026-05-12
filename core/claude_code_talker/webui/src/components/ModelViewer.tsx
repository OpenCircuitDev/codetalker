// Thin React wrapper around the <model-viewer> custom element from
// @google/model-viewer. The import has a side effect of registering
// the custom element globally with the browser; this component just
// gives us a typed React surface to use it from JSX.
//
// Why createElement instead of JSX: React 19's react-jsx transform
// looks up custom elements via React.JSX.IntrinsicElements and the
// augmentation paths for that are fragile across TS versions. Using
// createElement bypasses the JSX type lookup entirely while keeping
// the same runtime behavior.
import React, { forwardRef, useEffect, useRef } from "react";
import "@google/model-viewer";

export type ModelViewerProps = {
  src: string;
  alt?: string;
  autoRotate?: boolean;
  /** Auto-rotation delay in milliseconds before the spin starts. */
  autoRotateDelay?: number;
  /** Auto-rotation speed in degrees per second. Default ~30. */
  rotationPerSecond?: string;
  cameraControls?: boolean;
  disableZoom?: boolean;
  shadowIntensity?: string;
  /** HDR or "neutral" / "legacy" environment for image-based lighting. */
  environmentImage?: string;
  /** Camera orbit string: "<theta> <phi> <radius>" e.g. "0deg 75deg 105%". */
  cameraOrbit?: string;
  /** Exposure 0–10, default 1. Higher = brighter scene. */
  exposure?: string;
  /** Show a hint cursor that the model is interactive. */
  interactionPrompt?: "auto" | "none" | "when-focused";
  className?: string;
  style?: React.CSSProperties;
};

/** Imperative handle for the underlying <model-viewer> DOM element so
 *  callers can drive cameraOrbit etc. via direct prop assignment. */
export type ModelViewerElement = HTMLElement & {
  cameraOrbit: string;
  cameraTarget: string;
  fieldOfView: string;
  exposure: number;
};

export const ModelViewer = forwardRef<ModelViewerElement, ModelViewerProps>(
  function ModelViewer(props, externalRef) {
    const internalRef = useRef<ModelViewerElement | null>(null);
    useEffect(() => {
      if (typeof externalRef === "function") externalRef(internalRef.current);
      else if (externalRef) (externalRef as React.MutableRefObject<ModelViewerElement | null>).current = internalRef.current;
    });
    return React.createElement("model-viewer", {
      ref: internalRef,
      src: props.src,
      alt: props.alt,
      "auto-rotate": props.autoRotate ? "" : undefined,
      "auto-rotate-delay": props.autoRotateDelay?.toString(),
      "rotation-per-second": props.rotationPerSecond,
      "camera-controls": props.cameraControls ? "" : undefined,
      "disable-zoom": props.disableZoom ? "" : undefined,
      "shadow-intensity": props.shadowIntensity,
      "environment-image": props.environmentImage,
      "camera-orbit": props.cameraOrbit,
      exposure: props.exposure,
      "interaction-prompt": props.interactionPrompt,
      className: props.className,
      style: props.style,
    });
  }
);
